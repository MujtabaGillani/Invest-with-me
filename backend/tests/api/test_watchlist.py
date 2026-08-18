"""Watchlist endpoints.

The distinctive rule here is that a research note is *required*, with a real
minimum length. The guide's first listed mistake is chasing hype, and making the
user articulate why they are watching something is the cheapest guard against it -
so the constraint is tested rather than assumed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api

NOTE = "Stable urea margins and a long dividend record; want a better entry price."


def add(client: TestClient, api: str, symbol: str = "FFC", **overrides: object) -> dict:
    response = client.post(
        f"{api}/watchlist", json={"symbol": symbol, "research_note": NOTE} | overrides
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestAdding:
    def test_a_watched_company_carries_a_price_snapshot(
        self, seeded_client: TestClient, api: str
    ) -> None:
        item = add(seeded_client, api, "FFC")

        assert item["symbol"] == "FFC"
        assert item["sector_label"] == "Fertilizer"
        assert item["research_note"] == NOTE
        assert Decimal(item["last_close"]) == Decimal("148.30")
        assert item["last_close_date"] == "2025-06-30"
        assert item["has_trade_plan"] is False

    def test_symbol_is_matched_case_insensitively(
        self, seeded_client: TestClient, api: str
    ) -> None:
        assert add(seeded_client, api, "ffc")["symbol"] == "FFC"

    def test_a_research_note_is_required(self, seeded_client: TestClient, api: str) -> None:
        response = seeded_client.post(f"{api}/watchlist", json={"symbol": "FFC"})
        assert response.status_code == 422

    def test_a_token_research_note_is_rejected(self, seeded_client: TestClient, api: str) -> None:
        """ "cheap" is not a reason - the minimum length is deliberate."""
        response = seeded_client.post(
            f"{api}/watchlist", json={"symbol": "FFC", "research_note": "cheap"}
        )
        assert response.status_code == 422

    def test_unknown_symbol_is_a_404(self, seeded_client: TestClient, api: str) -> None:
        response = seeded_client.post(
            f"{api}/watchlist", json={"symbol": "NOSUCH", "research_note": NOTE}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "company_not_found"

    def test_adding_the_same_company_twice_is_a_conflict(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """A conflict, so the client can point at the existing entry."""
        add(seeded_client, api, "FFC")

        response = seeded_client.post(
            f"{api}/watchlist", json={"symbol": "FFC", "research_note": NOTE}
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"]["symbol"] == "FFC"

    def test_a_negative_target_price_is_rejected(self, seeded_client: TestClient, api: str) -> None:
        response = seeded_client.post(
            f"{api}/watchlist",
            json={"symbol": "FFC", "research_note": NOTE, "target_entry_price": "-10"},
        )
        assert response.status_code == 422


class TestEntryPrice:
    def test_distance_to_a_target_below_the_price_is_negative(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # FFC closes at 148.30; the user would buy at 135, which is 8.97% lower.
        item = add(seeded_client, api, "FFC", target_entry_price="135")

        assert item["entry_price_reached"] is False
        assert Decimal(item["distance_to_target_pct"]) == Decimal("-8.97")

    def test_a_price_at_or_below_the_target_is_reported_as_reached(
        self, seeded_client: TestClient, api: str
    ) -> None:
        # DGKC closes at 86.40, below the 100 the user named.
        item = add(
            seeded_client,
            api,
            "DGKC",
            research_note="Waiting for the cement cycle to turn before buying.",
            target_entry_price="100",
        )

        assert item["entry_price_reached"] is True
        assert Decimal(item["distance_to_target_pct"]) > 0

    def test_an_entry_price_is_optional(self, seeded_client: TestClient, api: str) -> None:
        item = add(seeded_client, api, "FFC")

        assert item["target_entry_price"] is None
        assert item["distance_to_target_pct"] is None
        assert item["entry_price_reached"] is False


class TestListing:
    def test_lists_entries_newest_first(self, seeded_client: TestClient, api: str) -> None:
        add(seeded_client, api, "FFC")
        add(seeded_client, api, "OGDC", research_note="Cheap on earnings but check receivables.")

        rows = seeded_client.get(f"{api}/watchlist").json()
        assert [row["symbol"] for row in rows] == ["OGDC", "FFC"]

    def test_an_empty_watchlist_is_an_empty_list(self, seeded_client: TestClient, api: str) -> None:
        assert seeded_client.get(f"{api}/watchlist").json() == []

    def test_an_existing_plan_is_flagged_so_the_ui_can_link_to_it(
        self, seeded_client: TestClient, api: str
    ) -> None:
        add(seeded_client, api, "FFC")
        assert seeded_client.get(f"{api}/watchlist").json()[0]["has_trade_plan"] is False

        seeded_client.post(f"{api}/plans", json={"symbol": "FFC"})
        assert seeded_client.get(f"{api}/watchlist").json()[0]["has_trade_plan"] is True


class TestUpdating:
    def test_the_note_and_target_can_be_revised(self, seeded_client: TestClient, api: str) -> None:
        item = add(seeded_client, api, "FFC", target_entry_price="135")

        response = seeded_client.patch(
            f"{api}/watchlist/{item['id']}",
            json={
                "research_note": "Revisited after the results: dividend cover looks thinner.",
                "target_entry_price": "125",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "dividend cover" in body["research_note"]
        assert Decimal(body["target_entry_price"]) == Decimal("125.0000")

    def test_omitted_fields_are_left_alone(self, seeded_client: TestClient, api: str) -> None:
        item = add(seeded_client, api, "FFC", target_entry_price="135")

        response = seeded_client.patch(
            f"{api}/watchlist/{item['id']}", json={"target_entry_price": "130"}
        )
        assert response.json()["research_note"] == NOTE

    def test_a_short_replacement_note_is_rejected(
        self, seeded_client: TestClient, api: str
    ) -> None:
        item = add(seeded_client, api, "FFC")
        response = seeded_client.patch(
            f"{api}/watchlist/{item['id']}", json={"research_note": "meh"}
        )
        assert response.status_code == 422

    def test_updating_a_missing_entry_is_a_404(self, seeded_client: TestClient, api: str) -> None:
        response = seeded_client.patch(f"{api}/watchlist/9999", json={"target_entry_price": "1"})
        assert response.status_code == 404


class TestRemoving:
    def test_removing_an_entry_returns_204_and_empties_the_list(
        self, seeded_client: TestClient, api: str
    ) -> None:
        item = add(seeded_client, api, "FFC")

        response = seeded_client.delete(f"{api}/watchlist/{item['id']}")

        assert response.status_code == 204
        assert seeded_client.get(f"{api}/watchlist").json() == []

    def test_removing_a_missing_entry_is_a_404(self, seeded_client: TestClient, api: str) -> None:
        assert seeded_client.delete(f"{api}/watchlist/9999").status_code == 404

    def test_removing_and_re_adding_is_allowed(self, seeded_client: TestClient, api: str) -> None:
        item = add(seeded_client, api, "FFC")
        seeded_client.delete(f"{api}/watchlist/{item['id']}")
        assert add(seeded_client, api, "FFC")["symbol"] == "FFC"
