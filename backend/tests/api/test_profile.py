"""Investor profile endpoints - guide section 1.

The profile is the yardstick everything else is measured against, so two things
are asserted hard: that incoherent limits are rejected at the boundary, and that
the derived warnings state consequences the user may not have connected to the
answers they gave - without telling them their answers are wrong.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api

VALID_PROFILE = {
    "time_horizon": "long_term",
    "risk_tolerance": "moderate",
    "drawdown_tolerance_pct": "30",
    "investable_capital": "1500000",
    "max_position_pct": "15",
    "max_sector_pct": "35",
    "emergency_fund_in_place": True,
    "investing_borrowed_money": False,
    "review_interval_days": 90,
    "goals_note": "Long-term holdings funded from savings I will not need for five years.",
}


def put_profile(client: TestClient, api: str, **overrides: object) -> dict:
    response = client.put(f"{api}/profile", json=VALID_PROFILE | overrides)
    assert response.status_code == 200, response.text
    return response.json()


class TestReadingBeforeWriting:
    def test_an_unwritten_profile_returns_204_not_defaults(
        self, client: TestClient, api: str
    ) -> None:
        """Returning defaults would let the user believe they had already decided."""
        response = client.get(f"{api}/profile")

        assert response.status_code == 204
        assert response.content == b""


class TestUpsert:
    def test_writing_a_profile_returns_it_back(self, client: TestClient, api: str) -> None:
        body = put_profile(client, api)

        assert body["time_horizon"] == "long_term"
        assert body["risk_tolerance"] == "moderate"
        assert Decimal(body["investable_capital"]) == Decimal("1500000.0000")
        assert Decimal(body["max_position_pct"]) == Decimal("15.00")
        assert body["emergency_fund_in_place"] is True

    def test_the_profile_is_then_readable(self, client: TestClient, api: str) -> None:
        put_profile(client, api)
        response = client.get(f"{api}/profile")

        assert response.status_code == 200
        assert response.json()["goals_note"] == VALID_PROFILE["goals_note"]

    def test_writing_again_replaces_rather_than_duplicates(
        self, client: TestClient, api: str
    ) -> None:
        put_profile(client, api)
        put_profile(client, api, max_position_pct="10", risk_tolerance="conservative")

        body = client.get(f"{api}/profile").json()
        assert Decimal(body["max_position_pct"]) == Decimal("10.00")
        assert body["risk_tolerance"] == "conservative"

    def test_a_minimal_payload_uses_documented_defaults(self, client: TestClient, api: str) -> None:
        response = client.put(
            f"{api}/profile", json={"time_horizon": "long_term", "risk_tolerance": "moderate"}
        )

        assert response.status_code == 200
        body = response.json()
        assert Decimal(body["drawdown_tolerance_pct"]) == Decimal("30.00")
        assert Decimal(body["max_position_pct"]) == Decimal("15.00")
        assert Decimal(body["max_sector_pct"]) == Decimal("35.00")
        assert body["review_interval_days"] == 90


class TestValidation:
    def test_a_position_cap_above_the_sector_cap_is_rejected(
        self, client: TestClient, api: str
    ) -> None:
        """Every position belongs to a sector, so this can never be honoured."""
        response = client.put(f"{api}/profile", json=VALID_PROFILE | {"max_position_pct": "40"})

        assert response.status_code == 422
        errors = response.json()["error"]["details"]["errors"]
        assert any("cannot exceed max_sector_pct" in error["message"] for error in errors)

    def test_equal_caps_are_allowed(self, client: TestClient, api: str) -> None:
        body = put_profile(client, api, max_position_pct="35", max_sector_pct="35")
        assert Decimal(body["max_position_pct"]) == Decimal("35.00")

    @pytest.mark.parametrize(
        "overrides",
        [
            {"max_position_pct": "0"},
            {"max_position_pct": "150"},
            {"max_sector_pct": "0"},
            {"drawdown_tolerance_pct": "-5"},
            {"drawdown_tolerance_pct": "150"},
            {"investable_capital": "-1"},
            {"review_interval_days": 1},
            {"review_interval_days": 5000},
            {"time_horizon": "forever"},
            {"risk_tolerance": "reckless"},
        ],
    )
    def test_out_of_range_values_are_rejected(
        self, client: TestClient, api: str, overrides: dict
    ) -> None:
        response = client.put(f"{api}/profile", json=VALID_PROFILE | overrides)
        assert response.status_code == 422

    def test_a_missing_required_field_is_rejected(self, client: TestClient, api: str) -> None:
        response = client.put(f"{api}/profile", json={"time_horizon": "long_term"})
        assert response.status_code == 422


class TestWarnings:
    def test_a_sound_profile_raises_no_warnings(self, client: TestClient, api: str) -> None:
        assert put_profile(client, api)["warnings"] == []

    def test_borrowed_money_is_warned_about_first(self, client: TestClient, api: str) -> None:
        """The guide is explicit that this money does not belong in equities."""
        warnings = put_profile(client, api, investing_borrowed_money=True)["warnings"]

        assert "borrowed" in warnings[0]
        assert "repayment schedule decides when you sell" in warnings[0]

    def test_a_missing_emergency_fund_is_warned_about(self, client: TestClient, api: str) -> None:
        warnings = put_profile(client, api, emergency_fund_in_place=False)["warnings"]
        assert any("emergency fund" in warning for warning in warnings)

    def test_no_investable_capital_is_warned_about(self, client: TestClient, api: str) -> None:
        """Without it, position sizing has nothing to size against."""
        warnings = put_profile(client, api, investable_capital="0")["warnings"]
        assert any("nothing to size against" in warning for warning in warnings)

    def test_a_short_horizon_is_flagged_as_a_different_activity(
        self, client: TestClient, api: str
    ) -> None:
        warnings = put_profile(client, api, time_horizon="short_term")["warnings"]
        assert any("different skills with different risk levels" in warning for warning in warnings)

    def test_contradictory_risk_answers_are_pointed_out(self, client: TestClient, api: str) -> None:
        warnings = put_profile(
            client, api, risk_tolerance="aggressive", drawdown_tolerance_pct="10"
        )["warnings"]
        assert any("opposite directions" in warning for warning in warnings)

    def test_a_generous_position_cap_is_flagged(self, client: TestClient, api: str) -> None:
        warnings = put_profile(client, api, max_position_pct="30", max_sector_pct="60")["warnings"]
        assert any("concentrates a lot of the outcome" in warning for warning in warnings)

    def test_an_infrequent_review_interval_is_flagged(self, client: TestClient, api: str) -> None:
        warnings = put_profile(client, api, review_interval_days=365)["warnings"]
        assert any("A thesis can break well inside that window" in warning for warning in warnings)

    def test_warnings_inform_rather_than_instruct(self, client: TestClient, api: str) -> None:
        """Each states a consequence; none tells the user their answer is wrong."""
        warnings = put_profile(
            client,
            api,
            investing_borrowed_money=True,
            emergency_fund_in_place=False,
            investable_capital="0",
            time_horizon="short_term",
        )["warnings"]

        assert len(warnings) >= 4
        combined = " ".join(warnings).lower()
        for forbidden in ("you must", "you should not", "wrong", "do not invest"):
            assert forbidden not in combined

    def test_warnings_are_recomputed_on_read_not_stored(self, client: TestClient, api: str) -> None:
        put_profile(client, api, investing_borrowed_money=True)
        assert client.get(f"{api}/profile").json()["warnings"]

        put_profile(client, api, investing_borrowed_money=False)
        assert client.get(f"{api}/profile").json()["warnings"] == []


class TestEffectOnOtherEndpoints:
    def test_the_profile_limits_drive_position_sizing(
        self, seeded_client: TestClient, api: str
    ) -> None:
        put_profile(seeded_client, api, investable_capital="1000000", max_position_pct="10")
        plan = seeded_client.post(
            f"{api}/plans", json={"symbol": "LUCK", "intended_amount": "50000"}
        ).json()

        sizing = plan["position_sizing"]
        assert Decimal(sizing["max_position_pct"]) == Decimal("10.00")
        assert Decimal(sizing["suggested_max_amount"]) == Decimal("100000.00")
        assert sizing["exceeds_limit"] is False

    def test_defaults_apply_before_a_profile_is_written(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """Conservative defaults: an undeclared limit is not a generous one."""
        plan = seeded_client.post(f"{api}/plans", json={"symbol": "LUCK"}).json()
        assert Decimal(plan["position_sizing"]["max_position_pct"]) == Decimal("15.00")
