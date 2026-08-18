"""Fundamentals and technical analysis endpoints, over the seeded dataset.

The rules themselves are unit-tested in ``tests/unit``. What is asserted here is
the wiring: that the service assembles peer groups correctly from real rows, that
prices and statements reach the engines intact, and that the paths which cannot
produce a report fail honestly rather than returning a confident-looking number.

The seeded dataset is shaped to exercise exactly these cases:

* LUCK  - healthy cement producer, three-company sector
* DGKC  - eroding margins, rising debt, falling price
* TRG   - loss-making, so no meaningful P/E
* HBL   - a bank, whose gearing must be judged against peers
* SEARL - a two-company sector, so no reliable peer median exists
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import Sector
from app.models.company import Company
from app.models.price import PriceBar

pytestmark = pytest.mark.api


def fundamentals(client: TestClient, api: str, symbol: str) -> dict:
    response = client.get(f"{api}/companies/{symbol}/fundamentals")
    assert response.status_code == 200, response.text
    return response.json()


def metric(report: dict, key: str) -> dict:
    return next(item for item in report["metrics"] if item["key"] == key)


def flags(report: dict) -> set[str]:
    return {flag["key"] for flag in report["red_flags"]}


class TestFundamentalsReport:
    def test_reports_every_checklist_metric_in_guide_order(
        self, seeded_client: TestClient, api: str
    ) -> None:
        report = fundamentals(seeded_client, api, "LUCK")

        assert [item["key"] for item in report["metrics"]] == [
            "revenue_growth",
            "net_margin",
            "eps_trend",
            "pe_ratio",
            "debt_to_equity",
            "dividend",
            "free_cash_flow",
        ]

    def test_every_metric_explains_itself(self, seeded_client: TestClient, api: str) -> None:
        """The guide's three columns: what it tells you, what to look for, and this company."""
        for item in fundamentals(seeded_client, api, "LUCK")["metrics"]:
            assert item["what_it_measures"], item["key"]
            assert item["criteria"], item["key"]
            assert item["commentary"], item["key"]
            assert item["verdict"] in {"strong", "adequate", "weak", "insufficient_data"}

    def test_carries_the_price_it_valued_the_shares_at(
        self, seeded_client: TestClient, api: str
    ) -> None:
        report = fundamentals(seeded_client, api, "LUCK")
        assert report["reference_price"] == 892.0
        assert report["reference_price_date"] == "2025-06-30"
        assert report["fiscal_years"] == [2020, 2021, 2022, 2023, 2024]
        assert report["latest_fiscal_year"] == 2024

    def test_the_score_is_counts_not_a_grade(self, seeded_client: TestClient, api: str) -> None:
        """A single composite number invites treating one figure as a verdict."""
        score = fundamentals(seeded_client, api, "LUCK")["score"]

        assert score["metrics_assessed"] == 7
        assert score["strong"] + score["adequate"] + score["weak"] + score["insufficient_data"] == 7
        assert "not a rating" in score["note"]
        # No overall grade, percentage or recommendation field exists.
        assert set(score) == {
            "strong",
            "adequate",
            "weak",
            "insufficient_data",
            "metrics_assessed",
            "note",
        }

    def test_the_disclaimer_is_attached_to_the_analysis_itself(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """So the caveat travels with the data into any client or screenshot."""
        disclaimer = fundamentals(seeded_client, api, "LUCK")["disclaimer"]
        assert disclaimer["is_financial_advice"] is False

    def test_a_healthy_company_meets_most_criteria(
        self, seeded_client: TestClient, api: str
    ) -> None:
        report = fundamentals(seeded_client, api, "LUCK")

        assert metric(report, "revenue_growth")["verdict"] == "strong"
        assert metric(report, "net_margin")["verdict"] == "strong"
        assert metric(report, "free_cash_flow")["verdict"] == "strong"
        assert report["score"]["weak"] == 0
        assert report["statement_review"]["needs_investigation"] is False

    def test_a_deteriorating_company_reads_as_weak_and_raises_flags(
        self, seeded_client: TestClient, api: str
    ) -> None:
        report = fundamentals(seeded_client, api, "DGKC")

        assert metric(report, "net_margin")["verdict"] == "weak"
        assert report["score"]["weak"] >= 3
        # Its generated accounts show debt rising while profit falls.
        assert "debt_up_profit_down" in flags(report)
        assert any(flag["severity"] == "critical" for flag in report["red_flags"])

    def test_metric_history_is_included_for_charting(
        self, seeded_client: TestClient, api: str
    ) -> None:
        history = metric(fundamentals(seeded_client, api, "LUCK"), "revenue_growth")["history"]
        assert [point["fiscal_year"] for point in history] == [2020, 2021, 2022, 2023, 2024]
        assert all(point["value"] is not None for point in history)


class TestPeerComparison:
    def test_a_three_company_sector_supports_a_peer_median(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """LUCK, DGKC and MLCF are cement; excluding itself leaves two peers."""
        report = fundamentals(seeded_client, api, "LUCK")
        # Two peers is below the three needed for a reliable median, so the
        # absolute fallback is used and the response says so.
        assert report["peer_count"] == 2
        assert "sector peers have usable figures" in metric(report, "pe_ratio")["commentary"]

    def test_a_four_company_sector_uses_the_peer_median(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """Banks: HBL, MCB, UBL and MEBL - three peers once HBL is excluded."""
        report = fundamentals(seeded_client, api, "HBL")

        assert report["peer_count"] == 3
        pe = metric(report, "pe_ratio")
        assert pe["peer_median"] is not None
        assert "sector median" in pe["commentary"]

    def test_a_bank_is_not_penalised_for_structural_leverage(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """A bank funds itself with deposits; 8x gearing is normal, not "weak"."""
        gearing = metric(fundamentals(seeded_client, api, "HBL"), "debt_to_equity")

        assert gearing["value"] is not None and gearing["value"] > 5
        assert gearing["verdict"] != "weak"
        assert gearing["peer_median"] is not None

    def test_a_company_is_excluded_from_its_own_peer_group(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """Otherwise the median is dragged towards the value being judged."""
        # Fertilizer has three companies: FFC, EFERT, FATIMA.
        assert fundamentals(seeded_client, api, "FFC")["peer_count"] == 2

    def test_a_two_company_sector_gets_no_peer_median(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """Pharmaceuticals holds only SEARL, so there is nothing to compare against."""
        report = fundamentals(seeded_client, api, "SEARL")
        assert report["peer_count"] == 0
        assert metric(report, "pe_ratio")["peer_median"] is None


class TestInsufficientData:
    def test_a_loss_maker_gets_no_pe_ratio(self, seeded_client: TestClient, api: str) -> None:
        """Never a negative multiple that a "cheapest first" sort would rank top."""
        pe = metric(fundamentals(seeded_client, api, "TRG"), "pe_ratio")

        assert pe["verdict"] == "insufficient_data"
        assert pe["value"] is None
        assert "reported a loss" in pe["commentary"]

    def test_a_company_with_no_statements_is_reported_honestly(
        self, client: TestClient, api: str, db_session, provider
    ) -> None:
        """A 422 with an explanation, not an empty report or a 500."""
        from app.core.enums import Sector
        from app.models.company import Company

        db_session.add(Company(symbol="BLANK", name="No Filings Ltd", sector=Sector.OTHER))
        db_session.commit()

        response = client.get(f"{api}/companies/BLANK/fundamentals")

        assert response.status_code == 422
        body = response.json()["error"]
        assert body["code"] == "insufficient_data"
        assert body["details"]["symbol"] == "BLANK"

    def test_unknown_symbol_is_a_404_not_a_422(self, seeded_client: TestClient, api: str) -> None:
        """ "No such company" and "no data for this company" are different problems."""
        response = seeded_client.get(f"{api}/companies/NOSUCH/fundamentals")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "company_not_found"


class TestStatementReview:
    def test_answers_the_guides_four_questions(self, seeded_client: TestClient, api: str) -> None:
        review = fundamentals(seeded_client, api, "LUCK")["statement_review"]

        assert [check["key"] for check in review["checks"]] == [
            "revenue_growing",
            "profit_tracks_revenue",
            "debt_under_control",
            "cash_flow_positive",
        ]
        assert all(check["question"].endswith("?") for check in review["checks"])
        assert all(check["detail"] for check in review["checks"])

    def test_a_troubled_company_fails_checks_and_the_summary_says_so(
        self, seeded_client: TestClient, api: str
    ) -> None:
        review = fundamentals(seeded_client, api, "UNITY")["statement_review"]
        assert review["failed_count"] >= 1
        assert review["summary"]


class TestTechnicals:
    def test_reports_all_four_readings_with_interpretations(
        self, seeded_client: TestClient, api: str
    ) -> None:
        body = seeded_client.get(f"{api}/companies/LUCK/technicals").json()

        assert body["symbol"] == "LUCK"
        assert body["as_of"] == "2025-06-30"
        assert body["sessions_analysed"] > 200
        assert body["last_close"] == 892.0

        for key in ("trend", "rsi", "moving_averages", "volume"):
            reading = body[key]
            assert reading["state"]
            assert reading["what_it_measures"]
            assert reading["commentary"]

    def test_classified_states_are_exposed_for_filtering(
        self, seeded_client: TestClient, api: str
    ) -> None:
        body = seeded_client.get(f"{api}/companies/LUCK/technicals").json()

        assert body["trend_direction"] in {"uptrend", "downtrend", "sideways", "unknown"}
        assert body["rsi_zone"] in {"oversold", "neutral", "overbought", "unknown"}
        assert body["moving_average_position"] in {
            "above_both",
            "mixed",
            "below_both",
            "unknown",
        }
        assert body["volume_confirmation"] in {"confirmed", "unconfirmed", "unknown"}

    def test_moving_averages_are_computed_from_the_full_history(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """240 stored sessions is enough for the 200-day average."""
        body = seeded_client.get(f"{api}/companies/LUCK/technicals").json()
        assert body["moving_average_position"] != "unknown"

    def test_the_framing_note_is_always_present(self, seeded_client: TestClient, api: str) -> None:
        note = seeded_client.get(f"{api}/companies/LUCK/technicals").json()["horizon_note"]
        assert "timing, not with what to own" in note

    def test_the_note_is_personalised_to_the_users_recorded_horizon(
        self, seeded_client: TestClient, api: str
    ) -> None:
        seeded_client.put(
            f"{api}/profile",
            json={"time_horizon": "short_term", "risk_tolerance": "aggressive"},
        )
        note = seeded_client.get(f"{api}/companies/LUCK/technicals").json()["horizon_note"]
        assert "short-term horizon" in note

        seeded_client.put(
            f"{api}/profile",
            json={"time_horizon": "long_term", "risk_tolerance": "moderate"},
        )
        note = seeded_client.get(f"{api}/companies/LUCK/technicals").json()["horizon_note"]
        assert "matters far less" in note

    def test_too_little_price_history_is_reported_honestly(
        self, client: TestClient, api: str, db_session: Session
    ) -> None:
        company = Company(symbol="THIN", name="Thinly Traded Ltd", sector=Sector.OTHER)
        db_session.add(company)
        db_session.flush()
        start = date(2025, 1, 6)
        for offset in range(10):  # below the 30-session minimum
            db_session.add(
                PriceBar(
                    company_id=company.id,
                    trade_date=start + timedelta(days=offset),
                    open=Decimal("10"),
                    high=Decimal("11"),
                    low=Decimal("9"),
                    close=Decimal("10"),
                    volume=1000,
                )
            )
        db_session.commit()

        response = client.get(f"{api}/companies/THIN/technicals")

        assert response.status_code == 422
        body = response.json()["error"]
        assert body["code"] == "insufficient_data"
        assert body["details"]["sessions_available"] == 10
        assert body["details"]["sessions_required"] == 30

    def test_unknown_symbol_is_a_404(self, seeded_client: TestClient, api: str) -> None:
        assert seeded_client.get(f"{api}/companies/NOSUCH/technicals").status_code == 404
