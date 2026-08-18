"""Company browsing, raw statements and price history."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api

#: Companies loaded by the seeded provider.
SEEDED_COMPANY_COUNT = 24


class TestListing:
    def test_lists_every_seeded_company(self, seeded_client: TestClient, api: str) -> None:
        body = seeded_client.get(f"{api}/companies", params={"limit": 200}).json()

        assert body["total"] == SEEDED_COMPANY_COUNT
        assert len(body["items"]) == SEEDED_COMPANY_COUNT

    def test_is_ordered_by_symbol(self, seeded_client: TestClient, api: str) -> None:
        symbols = [
            item["symbol"]
            for item in seeded_client.get(f"{api}/companies", params={"limit": 200}).json()["items"]
        ]
        assert symbols == sorted(symbols)

    def test_each_row_carries_its_latest_close_and_data_availability(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """So the UI can disable an analysis tab instead of offering an error."""
        body = seeded_client.get(f"{api}/companies", params={"search": "LUCK"}).json()
        row = body["items"][0]

        assert row["symbol"] == "LUCK"
        assert row["sector"] == "cement"
        assert row["sector_label"] == "Cement"
        assert Decimal(row["last_close"]) == Decimal("892.00")
        assert row["last_close_date"] == "2025-06-30"
        assert row["has_financials"] is True
        assert row["has_price_history"] is True

    def test_pagination_reports_the_full_total(self, seeded_client: TestClient, api: str) -> None:
        page = seeded_client.get(f"{api}/companies", params={"limit": 5, "offset": 0}).json()

        assert len(page["items"]) == 5
        assert page["total"] == SEEDED_COMPANY_COUNT
        assert page["limit"] == 5
        assert page["offset"] == 0

    def test_paging_through_covers_everything_exactly_once(
        self, seeded_client: TestClient, api: str
    ) -> None:
        collected: list[str] = []
        offset = 0
        while True:
            page = seeded_client.get(
                f"{api}/companies", params={"limit": 10, "offset": offset}
            ).json()
            collected.extend(item["symbol"] for item in page["items"])
            offset += 10
            if offset >= page["total"]:
                break

        assert len(collected) == SEEDED_COMPANY_COUNT
        assert len(set(collected)) == SEEDED_COMPANY_COUNT


class TestFiltering:
    def test_filters_by_sector(self, seeded_client: TestClient, api: str) -> None:
        body = seeded_client.get(f"{api}/companies", params={"sector": "cement"}).json()

        assert body["total"] == 3
        assert {item["symbol"] for item in body["items"]} == {"LUCK", "DGKC", "MLCF"}

    def test_search_matches_a_symbol(self, seeded_client: TestClient, api: str) -> None:
        body = seeded_client.get(f"{api}/companies", params={"search": "ogdc"}).json()
        assert [item["symbol"] for item in body["items"]] == ["OGDC"]

    def test_search_matches_a_company_name(self, seeded_client: TestClient, api: str) -> None:
        body = seeded_client.get(f"{api}/companies", params={"search": "cement"}).json()
        assert {item["symbol"] for item in body["items"]} >= {"LUCK", "DGKC", "MLCF"}

    def test_search_is_case_insensitive(self, seeded_client: TestClient, api: str) -> None:
        lower = seeded_client.get(f"{api}/companies", params={"search": "lucky"}).json()
        upper = seeded_client.get(f"{api}/companies", params={"search": "LUCKY"}).json()
        assert lower["total"] == upper["total"] == 1

    def test_a_search_with_no_matches_returns_an_empty_page_not_an_error(
        self, seeded_client: TestClient, api: str
    ) -> None:
        body = seeded_client.get(f"{api}/companies", params={"search": "zzzz"}).json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_the_reported_total_respects_the_filter(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """The count and the rows must come from the same WHERE clause."""
        body = seeded_client.get(f"{api}/companies", params={"sector": "cement", "limit": 1}).json()
        assert len(body["items"]) == 1
        assert body["total"] == 3


class TestDetail:
    def test_returns_the_business_summary_and_raw_statements(
        self, seeded_client: TestClient, api: str
    ) -> None:
        body = seeded_client.get(f"{api}/companies/LUCK").json()

        assert body["name"] == "Lucky Cement Limited"
        # Directly supports pre-buy question 1, "do I understand how it makes money?".
        assert "cement" in body["business_summary"].lower()
        assert body["website"]
        assert body["fiscal_years"] == [2020, 2021, 2022, 2023, 2024]
        assert len(body["financials"]) == 5

    def test_statements_are_oldest_year_first(self, seeded_client: TestClient, api: str) -> None:
        rows = seeded_client.get(f"{api}/companies/LUCK").json()["financials"]
        years = [row["fiscal_year"] for row in rows]
        assert years == sorted(years)

    def test_statements_carry_provenance(self, seeded_client: TestClient, api: str) -> None:
        """A user must be able to trace a figure back to a filing."""
        rows = seeded_client.get(f"{api}/companies/LUCK").json()["financials"]
        assert all(row["source"] for row in rows)

    def test_no_derived_ratios_are_returned_here(self, seeded_client: TestClient, api: str) -> None:
        """This endpoint is the raw record; judgements live in the analysis report."""
        row = seeded_client.get(f"{api}/companies/LUCK").json()["financials"][0]
        for derived in ("net_margin", "pe_ratio", "debt_to_equity", "free_cash_flow", "verdict"):
            assert derived not in row

    def test_symbol_lookup_is_case_insensitive(self, seeded_client: TestClient, api: str) -> None:
        assert seeded_client.get(f"{api}/companies/luck").json()["symbol"] == "LUCK"

    def test_unknown_symbol_is_a_404(self, seeded_client: TestClient, api: str) -> None:
        response = seeded_client.get(f"{api}/companies/NOSUCH")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "company_not_found"


class TestPriceHistory:
    def test_returns_bars_oldest_first(self, seeded_client: TestClient, api: str) -> None:
        body = seeded_client.get(f"{api}/companies/LUCK/prices", params={"sessions": 30}).json()

        assert body["symbol"] == "LUCK"
        assert body["sessions"] == 30
        dates = [bar["trade_date"] for bar in body["bars"]]
        assert dates == sorted(dates)

    def test_returns_the_most_recent_sessions(self, seeded_client: TestClient, api: str) -> None:
        body = seeded_client.get(f"{api}/companies/LUCK/prices", params={"sessions": 5}).json()

        assert body["bars"][-1]["trade_date"] == "2025-06-30"
        assert Decimal(body["bars"][-1]["close"]) == Decimal("892.00")

    def test_every_bar_is_internally_consistent(self, seeded_client: TestClient, api: str) -> None:
        """high >= low, and both bracket the close - enforced in the schema too."""
        bars = seeded_client.get(f"{api}/companies/LUCK/prices", params={"sessions": 60}).json()[
            "bars"
        ]

        for bar in bars:
            high, low, close = Decimal(bar["high"]), Decimal(bar["low"]), Decimal(bar["close"])
            assert high >= low
            assert low <= close <= high
            assert bar["volume"] >= 0

    def test_requesting_more_sessions_than_exist_returns_what_there_is(
        self, seeded_client: TestClient, api: str
    ) -> None:
        body = seeded_client.get(f"{api}/companies/LUCK/prices", params={"sessions": 1000}).json()
        assert body["sessions"] == 240  # what the test fixture loaded

    def test_unknown_symbol_is_a_404(self, seeded_client: TestClient, api: str) -> None:
        assert seeded_client.get(f"{api}/companies/NOSUCH/prices").status_code == 404


class TestWithoutMarketData:
    def test_an_empty_database_lists_nothing_rather_than_failing(
        self, client: TestClient, api: str
    ) -> None:
        body = client.get(f"{api}/companies").json()
        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}
