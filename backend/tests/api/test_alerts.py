"""Alert endpoints and the portfolio monitor.

Three properties matter more than the individual rules, because getting them wrong
makes the whole feature something the user learns to ignore:

1. **Idempotency** - re-evaluating must not duplicate an alert.
2. **Self-resolution** - a condition that stops holding must clear itself.
3. **Reopening** - a dismissed condition that recurs must alert again, reusing its
   row (the unique constraint on ``(user_id, dedupe_key)`` requires it).

Prices are pinned by the seeded provider, so the thresholds crossed here are
exact: LUCK closes at 892.00 and DGKC at 86.40 in every run.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.trade_plan import TradePlan

pytestmark = pytest.mark.api

ALL_YES = {
    "understands_business": True,
    "revenue_and_profit_healthy": True,
    "debt_manageable_vs_peers": True,
    "comfortable_with_drawdown": True,
    "position_size_appropriate": True,
}


def commit_plan(
    client: TestClient,
    api: str,
    symbol: str,
    *,
    profit_target_pct: str = "25",
    stop_loss_pct: str = "15",
) -> dict:
    """Create and commit a plan with both exit rules set."""
    plan = client.post(f"{api}/plans", json={"symbol": symbol}).json()
    client.patch(
        f"{api}/plans/{plan['id']}",
        json={
            **ALL_YES,
            "profit_target_pct": profit_target_pct,
            "stop_loss_pct": stop_loss_pct,
            "thesis": "A thesis long enough to clear the advisory length check.",
        },
    )
    response = client.post(f"{api}/plans/{plan['id']}/commit")
    assert response.status_code == 200, response.text
    return response.json()


def buy(client: TestClient, api: str, symbol: str, *, quantity: str, price: str) -> None:
    response = client.post(
        f"{api}/portfolio/trades",
        json={"symbol": symbol, "side": "buy", "quantity": quantity, "price": price},
    )
    assert response.status_code == 201, response.text


def evaluate(client: TestClient, api: str) -> dict:
    response = client.post(f"{api}/alerts/evaluate")
    assert response.status_code == 200, response.text
    return response.json()


def kinds(body: dict) -> set[str]:
    return {alert["kind"] for alert in body["alerts"]}


def alert_of_kind(body: dict, kind: str) -> dict:
    return next(alert for alert in body["alerts"] if alert["kind"] == kind)


def over_position_limit(body: dict) -> set[str]:
    """Symbols currently reported as breaching the single-position limit."""
    return {
        alert["context"]["subject"]
        for alert in body["alerts"]
        if alert["kind"] == "position_concentration"
    }


class TestEmptyState:
    def test_nothing_to_alert_on(self, seeded_client: TestClient, api: str) -> None:
        result = evaluate(seeded_client, api)
        assert result == {
            "created": 0,
            "already_open": 0,
            "resolved": 0,
            "alerts": [],
            "note": result["note"],
        }

    def test_listing_is_read_only(self, seeded_client: TestClient, api: str) -> None:
        """A GET must not create alerts as a side effect."""
        buy(seeded_client, api, "LUCK", quantity="100", price="700")
        assert seeded_client.get(f"{api}/alerts").json() == []

    def test_the_response_states_what_alerts_are_and_are_not(
        self, seeded_client: TestClient, api: str
    ) -> None:
        note = evaluate(seeded_client, api)["note"]
        assert "your own pre-committed rules" in note
        assert "None of them is a recommendation to act." in note


class TestExitRuleAlerts:
    def test_profit_target_reached(self, seeded_client: TestClient, api: str) -> None:
        # Bought at 700, target +25% = 875. LUCK closes at 892 -> reached.
        commit_plan(seeded_client, api, "LUCK")
        buy(seeded_client, api, "LUCK", quantity="100", price="700")

        result = evaluate(seeded_client, api)
        alert = alert_of_kind(result, "profit_target_reached")

        assert alert["severity"] == "info"
        assert alert["symbol"] == "LUCK"
        assert alert["context"]["target_price"] == "875.00"
        assert "planned to take something off the table" in alert["message"]

    def test_profit_target_not_yet_reached_raises_nothing(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # Bought at 800, target +25% = 1,000, above the 892 close.
        commit_plan(seeded_client, api, "LUCK")
        buy(seeded_client, api, "LUCK", quantity="100", price="800")

        assert "profit_target_reached" not in kinds(evaluate(seeded_client, api))

    def test_stop_loss_breached_is_critical(self, seeded_client: TestClient, api: str) -> None:
        # Bought at 128.50, stop -15% = 109.23. DGKC closes at 86.40 -> breached.
        commit_plan(seeded_client, api, "DGKC")
        buy(seeded_client, api, "DGKC", quantity="500", price="128.50")

        alert = alert_of_kind(evaluate(seeded_client, api), "stop_loss_breached")

        assert alert["severity"] == "critical"
        assert alert["context"]["stop_price"] == "109.23"
        assert "the rule you wrote down" in alert["message"]

    def test_a_holding_with_no_plan_is_told_it_has_no_exit_rules(
        self, seeded_client: TestClient, api: str
    ) -> None:
        buy(seeded_client, api, "LUCK", quantity="100", price="700")

        result = evaluate(seeded_client, api)
        alert = alert_of_kind(result, "thesis_review_due")

        assert alert["severity"] == "warning"
        assert alert["context"]["reason"] == "no_exit_rules"
        assert "no profit target or stop-loss written down" in alert["message"]


class TestIdempotency:
    def test_re_evaluating_does_not_duplicate_alerts(
        self, seeded_client: TestClient, api: str
    ) -> None:
        commit_plan(seeded_client, api, "LUCK")
        buy(seeded_client, api, "LUCK", quantity="100", price="700")

        first = evaluate(seeded_client, api)
        assert first["created"] >= 1

        second = evaluate(seeded_client, api)
        assert second["created"] == 0
        assert second["already_open"] == first["created"]
        assert len(second["alerts"]) == len(first["alerts"])

        third = evaluate(seeded_client, api)
        assert third["created"] == 0
        assert len(third["alerts"]) == len(first["alerts"])

    def test_an_open_alert_is_refreshed_rather_than_re_created(
        self, seeded_client: TestClient, api: str
    ) -> None:
        commit_plan(seeded_client, api, "LUCK")
        buy(seeded_client, api, "LUCK", quantity="100", price="700")

        first_id = alert_of_kind(evaluate(seeded_client, api), "profit_target_reached")["id"]
        second_id = alert_of_kind(evaluate(seeded_client, api), "profit_target_reached")["id"]
        assert first_id == second_id


class TestResolution:
    def test_a_condition_that_stops_holding_clears_itself(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """Alerts that linger after the fact train the user to ignore them."""
        commit_plan(seeded_client, api, "LUCK")
        buy(seeded_client, api, "LUCK", quantity="100", price="700")

        opened = evaluate(seeded_client, api)
        assert "profit_target_reached" in kinds(opened)

        # Exit the position: nothing is held, so no exit-rule alert can apply.
        seeded_client.post(
            f"{api}/portfolio/trades",
            json={"symbol": "LUCK", "side": "sell", "quantity": "100", "price": "892"},
        )

        after = evaluate(seeded_client, api)
        assert after["resolved"] == opened["created"]
        assert after["alerts"] == []

    def test_a_dismissed_condition_that_recurs_alerts_again(
        self, seeded_client: TestClient, api: str
    ) -> None:
        commit_plan(seeded_client, api, "LUCK")
        buy(seeded_client, api, "LUCK", quantity="100", price="700")

        alert_id = alert_of_kind(evaluate(seeded_client, api), "profit_target_reached")["id"]
        assert seeded_client.post(f"{api}/alerts/{alert_id}/acknowledge").status_code == 200
        assert "profit_target_reached" not in kinds(
            {"alerts": seeded_client.get(f"{api}/alerts").json()}
        )

        reopened = evaluate(seeded_client, api)
        alert = alert_of_kind(reopened, "profit_target_reached")

        # Same row reused - the unique (user, dedupe_key) constraint requires it,
        # and reusing it preserves when the condition first fired.
        assert alert["id"] == alert_id
        assert alert["is_acknowledged"] is False
        assert reopened["created"] >= 1


class TestAcknowledgement:
    def test_acknowledging_hides_an_alert_but_keeps_the_row(
        self, seeded_client: TestClient, api: str
    ) -> None:
        buy(seeded_client, api, "LUCK", quantity="100", price="700")
        # An unplanned single holding trips three of the user's own default limits
        # at once: no exit rules recorded, one position at 100% against a 15% cap,
        # and one sector at 100% against a 35% cap.
        result = evaluate(seeded_client, api)
        assert kinds(result) == {
            "thesis_review_due",
            "position_concentration",
            "sector_concentration",
        }
        alert_id = result["alerts"][0]["id"]

        acknowledged = seeded_client.post(f"{api}/alerts/{alert_id}/acknowledge").json()
        assert acknowledged["is_acknowledged"] is True
        assert acknowledged["acknowledged_at"] is not None

        still_open = seeded_client.get(f"{api}/alerts").json()
        assert alert_id not in {row["id"] for row in still_open}

        history = seeded_client.get(f"{api}/alerts", params={"include_acknowledged": True}).json()
        assert alert_id in {row["id"] for row in history}

    def test_acknowledging_twice_is_harmless(self, seeded_client: TestClient, api: str) -> None:
        buy(seeded_client, api, "LUCK", quantity="100", price="700")
        alert_id = evaluate(seeded_client, api)["alerts"][0]["id"]

        first = seeded_client.post(f"{api}/alerts/{alert_id}/acknowledge").json()
        second = seeded_client.post(f"{api}/alerts/{alert_id}/acknowledge").json()
        assert first["acknowledged_at"] == second["acknowledged_at"]

    def test_acknowledge_all_dismisses_everything_open(
        self, seeded_client: TestClient, api: str
    ) -> None:
        commit_plan(seeded_client, api, "DGKC")
        buy(seeded_client, api, "DGKC", quantity="500", price="128.50")
        buy(seeded_client, api, "LUCK", quantity="100", price="700")

        open_count = len(evaluate(seeded_client, api)["alerts"])
        assert open_count >= 2

        response = seeded_client.post(f"{api}/alerts/acknowledge-all")
        assert response.status_code == 200
        assert f"Dismissed {open_count}" in response.json()["message"]
        assert seeded_client.get(f"{api}/alerts").json() == []

    def test_acknowledging_a_missing_alert_is_a_404(
        self, seeded_client: TestClient, api: str
    ) -> None:
        response = seeded_client.post(f"{api}/alerts/9999/acknowledge")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestReviewDueAlert:
    def test_a_freshly_committed_plan_is_not_immediately_overdue(
        self, seeded_client: TestClient, api: str
    ) -> None:
        commit_plan(seeded_client, api, "LUCK")
        buy(seeded_client, api, "LUCK", quantity="100", price="800")

        review_alerts = [
            alert
            for alert in evaluate(seeded_client, api)["alerts"]
            if alert["kind"] == "thesis_review_due"
        ]
        assert review_alerts == []

    def test_a_stale_review_raises_an_alert(
        self, seeded_client: TestClient, api: str, db_session: Session
    ) -> None:
        """Back-dates ``last_reviewed_at`` directly.

        There is no API for "pretend it is 100 days later", and the alternative -
        injecting a clock through five layers purely for this test - would be more
        machinery than the assertion is worth.
        """
        plan = commit_plan(seeded_client, api, "LUCK")
        buy(seeded_client, api, "LUCK", quantity="100", price="800")

        db_session.execute(
            update(TradePlan)
            .where(TradePlan.id == plan["id"])
            .values(last_reviewed_at=utcnow() - timedelta(days=100))
        )
        db_session.commit()

        alert = alert_of_kind(evaluate(seeded_client, api), "thesis_review_due")
        assert alert["context"]["days_since_review"] == 100
        assert alert["context"]["review_interval_days"] == 90
        assert "Does the original thesis still hold?" in alert["message"]

    def test_recording_a_review_clears_the_alert(
        self, seeded_client: TestClient, api: str, db_session: Session
    ) -> None:
        plan = commit_plan(seeded_client, api, "LUCK")
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        db_session.execute(
            update(TradePlan)
            .where(TradePlan.id == plan["id"])
            .values(last_reviewed_at=utcnow() - timedelta(days=100))
        )
        db_session.commit()
        assert "thesis_review_due" in kinds(evaluate(seeded_client, api))

        seeded_client.post(
            f"{api}/plans/{plan['id']}/reviews",
            json={"note": "Re-read the accounts; margin and gearing unchanged, thesis intact."},
        )

        assert "thesis_review_due" not in kinds(evaluate(seeded_client, api))


class TestFundamentalAlerts:
    def test_a_serious_red_flag_on_a_holding_is_surfaced(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """DGKC's generated accounts show debt rising while profit falls."""
        buy(seeded_client, api, "DGKC", quantity="500", price="128.50")

        alert = alert_of_kind(evaluate(seeded_client, api), "fundamental_red_flag")

        assert alert["symbol"] == "DGKC"
        assert alert["context"]["flag"] == "debt_up_profit_down"
        assert "matters more than a price move" in alert["message"]

    def test_a_healthy_holding_raises_no_fundamental_flag(
        self, seeded_client: TestClient, api: str
    ) -> None:
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        assert "fundamental_red_flag" not in kinds(evaluate(seeded_client, api))


class TestWatchlistAlerts:
    def test_reaching_a_noted_entry_price_raises_an_alert(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # DGKC closes at 86.40, below the 100 the user said they would buy at.
        seeded_client.post(
            f"{api}/watchlist",
            json={
                "symbol": "DGKC",
                "research_note": "Waiting for the cement cycle to turn before buying.",
                "target_entry_price": "100",
            },
        )

        alert = alert_of_kind(evaluate(seeded_client, api), "watchlist_entry_price_reached")

        assert alert["symbol"] == "DGKC"
        # Crucially, it does not say "buy now".
        assert "Work through the pre-buy checklist before acting" in alert["message"]
        assert "a price level on its own is not a reason to buy" in alert["message"]

    def test_a_price_above_the_target_raises_nothing(
        self, seeded_client: TestClient, api: str
    ) -> None:
        seeded_client.post(
            f"{api}/watchlist",
            json={
                "symbol": "LUCK",
                "research_note": "Good business, want a materially better entry price.",
                "target_entry_price": "600",
            },
        )
        assert "watchlist_entry_price_reached" not in kinds(evaluate(seeded_client, api))


class TestConcentrationAlerts:
    def test_breaching_the_position_limit_raises_an_alert(
        self, seeded_client: TestClient, api: str
    ) -> None:
        seeded_client.put(
            f"{api}/profile",
            json={
                "time_horizon": "long_term",
                "risk_tolerance": "moderate",
                "investable_capital": "1000000",
                "max_position_pct": "15",
                "max_sector_pct": "90",
            },
        )
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        buy(seeded_client, api, "FFC", quantity="100", price="140")

        alert = alert_of_kind(evaluate(seeded_client, api), "position_concentration")
        assert alert["context"]["subject"] == "LUCK"
        assert alert["context"]["limit_pct"] == "15.00"

    def test_trimming_back_under_the_limit_resolves_the_alert(
        self, seeded_client: TestClient, api: str
    ) -> None:
        seeded_client.put(
            f"{api}/profile",
            json={
                "time_horizon": "long_term",
                "risk_tolerance": "moderate",
                "investable_capital": "1000000",
                "max_position_pct": "60",
                "max_sector_pct": "90",
            },
        )
        buy(seeded_client, api, "LUCK", quantity="100", price="800")
        buy(seeded_client, api, "FFC", quantity="100", price="140")
        assert "LUCK" in over_position_limit(evaluate(seeded_client, api))

        # Sell most of LUCK so it falls under 60% of the portfolio. FFC then
        # dominates instead, so the assertion is per-subject rather than per-kind.
        seeded_client.post(
            f"{api}/portfolio/trades",
            json={"symbol": "LUCK", "side": "sell", "quantity": "98", "price": "892"},
        )

        assert "LUCK" not in over_position_limit(evaluate(seeded_client, api))
