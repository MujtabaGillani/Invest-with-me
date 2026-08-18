"""Trade plan endpoints - the pre-commitment invariant.

This module carries more weight than any other test file in the suite. The one
hard rule in the product is that a plan cannot be committed to until all five
pre-buy questions are answered "yes" **and** both exit rules are set, because
that rule is the whole reason the guide says to decide the exit before buying
rather than while watching the price move.

Every way of getting around that rule is tested here explicitly:

* leaving a question unanswered
* answering a question "no"
* answering everything but omitting the profit target
* answering everything but omitting the stop-loss
* editing a plan after it has been committed to
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api

#: All five pre-buy answers set to yes.
ALL_YES = {
    "understands_business": True,
    "revenue_and_profit_healthy": True,
    "debt_manageable_vs_peers": True,
    "comfortable_with_drawdown": True,
    "position_size_appropriate": True,
}

#: Both exit rules, as the guide phrases them.
EXIT_RULES = {"profit_target_pct": "25", "stop_loss_pct": "15"}

THESIS = (
    "Market-leading cement producer with sector-best margins and low gearing; "
    "buying for domestic construction exposure over five years."
)


def create_plan(client: TestClient, api: str, symbol: str = "LUCK", **extra: object) -> dict:
    """Open a draft plan and return its representation."""
    response = client.post(f"{api}/plans", json={"symbol": symbol, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def patch_plan(client: TestClient, api: str, plan_id: int, **fields: object) -> dict:
    response = client.patch(f"{api}/plans/{plan_id}", json=fields)
    assert response.status_code == 200, response.text
    return response.json()


def ready_plan(client: TestClient, api: str, symbol: str = "LUCK") -> dict:
    """A plan taken all the way to READY."""
    plan = create_plan(client, api, symbol)
    patch_plan(client, api, plan["id"], **ALL_YES, **EXIT_RULES, thesis=THESIS)
    response = client.post(f"{api}/plans/{plan['id']}/commit")
    assert response.status_code == 200, response.text
    return response.json()


class TestCreatePlan:
    def test_new_plan_starts_as_an_unanswered_draft(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = create_plan(seeded_client, api)

        assert plan["status"] == "draft"
        assert plan["symbol"] == "LUCK"
        assert plan["committed_at"] is None
        assert plan["reviews"] == []

        # All five questions present and unanswered - null, not false.
        assert len(plan["checklist"]) == 5
        assert all(item["answer"] is None for item in plan["checklist"])
        assert all(item["question"] for item in plan["checklist"])

    def test_a_bare_draft_cannot_be_committed_and_says_why(
        self, seeded_client: TestClient, api: str
    ) -> None:
        readiness = create_plan(seeded_client, api)["readiness"]

        assert readiness["can_commit"] is False
        assert readiness["checklist_complete"] is False
        assert readiness["has_exit_rules"] is False
        assert len(readiness["unanswered_items"]) == 5
        # Five unanswered questions plus the two missing exit rules.
        assert len(readiness["blocking_reasons"]) == 7

    def test_symbol_is_matched_case_insensitively(
        self, seeded_client: TestClient, api: str
    ) -> None:
        assert create_plan(seeded_client, api, "luck")["symbol"] == "LUCK"

    def test_unknown_symbol_is_a_404(self, seeded_client: TestClient, api: str) -> None:
        response = seeded_client.post(f"{api}/plans", json={"symbol": "NOSUCH"})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "company_not_found"

    def test_a_second_open_plan_for_the_same_company_is_rejected(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """Two live plans would mean two stop-losses for one position."""
        first = create_plan(seeded_client, api, "LUCK")

        response = seeded_client.post(f"{api}/plans", json={"symbol": "LUCK"})
        assert response.status_code == 409
        body = response.json()["error"]
        assert body["code"] == "conflict"
        assert body["details"]["plan_id"] == first["id"]

    def test_planning_the_same_company_again_after_abandoning_is_allowed(
        self, seeded_client: TestClient, api: str
    ) -> None:
        first = create_plan(seeded_client, api, "LUCK")
        seeded_client.post(
            f"{api}/plans/{first['id']}/abandon", json={"reason": "Valuation ran away."}
        )

        second = seeded_client.post(f"{api}/plans", json={"symbol": "LUCK"})
        assert second.status_code == 201


class TestCommitInvariant:
    """The rule: all five answers yes, and both exit rules set."""

    def test_one_unanswered_question_blocks_the_commit(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = create_plan(seeded_client, api)
        four_of_five = dict(ALL_YES)
        del four_of_five["position_size_appropriate"]
        patch_plan(seeded_client, api, plan["id"], **four_of_five, **EXIT_RULES)

        response = seeded_client.post(f"{api}/plans/{plan['id']}/commit")

        assert response.status_code == 422
        reasons = response.json()["error"]["details"]["blocking_reasons"]
        assert len(reasons) == 1
        assert reasons[0].startswith("Not yet answered:")

    def test_answering_no_blocks_the_commit_and_is_distinguished_from_unanswered(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """A "no" is a finished thought, but it is not a basis for buying."""
        plan = create_plan(seeded_client, api)
        answers = dict(ALL_YES) | {"debt_manageable_vs_peers": False}
        updated = patch_plan(seeded_client, api, plan["id"], **answers, **EXIT_RULES)

        readiness = updated["readiness"]
        assert readiness["can_commit"] is False
        assert readiness["unanswered_items"] == []
        assert readiness["failed_items"] == ["debt_manageable_vs_peers"]
        assert any(reason.startswith("Answered no:") for reason in readiness["blocking_reasons"])

        assert seeded_client.post(f"{api}/plans/{plan['id']}/commit").status_code == 422

    def test_missing_profit_target_blocks_the_commit(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = create_plan(seeded_client, api)
        patch_plan(seeded_client, api, plan["id"], **ALL_YES, stop_loss_pct="15")

        response = seeded_client.post(f"{api}/plans/{plan['id']}/commit")

        assert response.status_code == 422
        reasons = response.json()["error"]["details"]["blocking_reasons"]
        assert len(reasons) == 1
        assert "No profit target set" in reasons[0]

    def test_missing_stop_loss_blocks_the_commit(self, seeded_client: TestClient, api: str) -> None:
        plan = create_plan(seeded_client, api)
        patch_plan(seeded_client, api, plan["id"], **ALL_YES, profit_target_pct="25")

        response = seeded_client.post(f"{api}/plans/{plan['id']}/commit")

        assert response.status_code == 422
        reasons = response.json()["error"]["details"]["blocking_reasons"]
        assert len(reasons) == 1
        assert "No stop-loss set" in reasons[0]

    def test_a_complete_plan_commits(self, seeded_client: TestClient, api: str) -> None:
        plan = ready_plan(seeded_client, api)

        assert plan["status"] == "ready"
        assert plan["committed_at"] is not None
        # Committing counts as the first review, so the plan is not immediately
        # "review overdue".
        assert plan["last_reviewed_at"] is not None
        assert plan["readiness"]["can_commit"] is True
        assert plan["readiness"]["blocking_reasons"] == []

    def test_committing_twice_is_a_conflict(self, seeded_client: TestClient, api: str) -> None:
        plan = ready_plan(seeded_client, api)
        response = seeded_client.post(f"{api}/plans/{plan['id']}/commit")
        assert response.status_code == 409

    def test_missing_plan_is_a_404(self, seeded_client: TestClient, api: str) -> None:
        response = seeded_client.post(f"{api}/plans/9999/commit")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestAdvisoryNotes:
    """Concerns that inform without blocking - the app does not overrule the user."""

    def test_a_thin_thesis_is_advisory_not_blocking(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = create_plan(seeded_client, api)
        updated = patch_plan(
            seeded_client, api, plan["id"], **ALL_YES, **EXIT_RULES, thesis="cheap"
        )

        readiness = updated["readiness"]
        assert readiness["can_commit"] is True
        assert any("thesis is empty or very short" in note for note in readiness["advisory_notes"])
        assert seeded_client.post(f"{api}/plans/{plan['id']}/commit").status_code == 200

    def test_missing_invalidation_note_is_advisory(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = create_plan(seeded_client, api)
        updated = patch_plan(seeded_client, api, plan["id"], **ALL_YES, **EXIT_RULES, thesis=THESIS)
        assert any(
            "prove this thesis wrong" in note for note in updated["readiness"]["advisory_notes"]
        )

    def test_target_smaller_than_stop_is_flagged_but_permitted(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """Risking more than you aim to make can be deliberate - so it informs only."""
        plan = create_plan(seeded_client, api)
        updated = patch_plan(
            seeded_client,
            api,
            plan["id"],
            **ALL_YES,
            profit_target_pct="10",
            stop_loss_pct="20",
            thesis=THESIS,
            invalidation_note="Exit if margins fall below 10% for two years.",
        )

        readiness = updated["readiness"]
        assert readiness["can_commit"] is True
        assert any("risks more than it aims" in note for note in readiness["advisory_notes"])


class TestPositionSizing:
    def test_sizing_reports_the_users_own_limit_when_no_amount_is_entered(
        self, seeded_client: TestClient, api: str
    ) -> None:
        sizing = create_plan(seeded_client, api)["position_sizing"]

        assert sizing["intended_amount"] is None
        assert sizing["exceeds_limit"] is None
        assert Decimal(sizing["max_position_pct"]) == Decimal("15")
        assert "Enter an intended amount" in sizing["commentary"]

    def test_an_oversized_intended_amount_is_flagged_against_the_profile_limit(
        self, seeded_client: TestClient, api: str
    ) -> None:
        seeded_client.put(
            f"{api}/profile",
            json={
                "time_horizon": "long_term",
                "risk_tolerance": "moderate",
                "investable_capital": "1000000",
                "max_position_pct": "10",
                "max_sector_pct": "35",
            },
        )
        plan = create_plan(seeded_client, api, "LUCK", intended_amount="400000")

        sizing = plan["position_sizing"]
        assert sizing["exceeds_limit"] is True
        # 400k of a 1.4m post-purchase portfolio is ~28.6%, well past the 10% cap.
        assert Decimal(sizing["resulting_weight_pct"]) > Decimal("25")
        assert Decimal(sizing["suggested_max_amount"]) == Decimal("100000.00")

    def test_a_position_inside_the_limit_is_not_flagged(
        self, seeded_client: TestClient, api: str
    ) -> None:
        seeded_client.put(
            f"{api}/profile",
            json={
                "time_horizon": "long_term",
                "risk_tolerance": "moderate",
                "investable_capital": "1000000",
                "max_position_pct": "15",
                "max_sector_pct": "35",
            },
        )
        plan = create_plan(seeded_client, api, "LUCK", intended_amount="100000")
        assert plan["position_sizing"]["exceeds_limit"] is False


class TestEditing:
    def test_a_draft_can_be_edited(self, seeded_client: TestClient, api: str) -> None:
        plan = create_plan(seeded_client, api)
        updated = patch_plan(seeded_client, api, plan["id"], thesis=THESIS)
        assert updated["thesis"] == THESIS

    def test_omitted_fields_are_left_alone_rather_than_cleared(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = create_plan(seeded_client, api, "LUCK", thesis=THESIS)
        updated = patch_plan(seeded_client, api, plan["id"], profit_target_pct="25")
        assert updated["thesis"] == THESIS
        assert Decimal(updated["profit_target_pct"]) == Decimal("25")

    def test_a_committed_plan_cannot_be_edited(self, seeded_client: TestClient, api: str) -> None:
        """It records a decision; editing it would rewrite the journal."""
        plan = ready_plan(seeded_client, api)
        response = seeded_client.patch(f"{api}/plans/{plan['id']}", json={"stop_loss_pct": "40"})

        assert response.status_code == 409
        assert "cannot be edited" in response.json()["error"]["message"]

    def test_an_empty_patch_is_rejected(self, seeded_client: TestClient, api: str) -> None:
        plan = create_plan(seeded_client, api)
        response = seeded_client.patch(f"{api}/plans/{plan['id']}", json={})
        assert response.status_code == 422

    def test_an_out_of_range_stop_loss_is_rejected_at_the_boundary(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = create_plan(seeded_client, api)
        response = seeded_client.patch(f"{api}/plans/{plan['id']}", json={"stop_loss_pct": "100"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "request_validation_error"


class TestLifecycle:
    def test_abandoning_a_draft_records_the_reason_in_the_journal(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = create_plan(seeded_client, api)
        response = seeded_client.post(
            f"{api}/plans/{plan['id']}/abandon",
            json={"reason": "Debt profile is worse than I thought."},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "abandoned"
        assert len(body["reviews"]) == 1
        assert "Abandoned:" in body["reviews"][0]["note"]
        assert body["reviews"][0]["thesis_still_valid"] is False

    def test_a_buy_against_a_ready_plan_marks_it_executed(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = ready_plan(seeded_client, api)

        trade = seeded_client.post(
            f"{api}/portfolio/trades",
            json={
                "symbol": "LUCK",
                "side": "buy",
                "quantity": "100",
                "price": "800",
                "fees": "250",
            },
        )
        assert trade.status_code == 201
        # Linked automatically: the user already wrote the commitment down.
        assert trade.json()["plan_id"] == plan["id"]

        assert seeded_client.get(f"{api}/plans/{plan['id']}").json()["status"] == "executed"

    def test_an_executed_plan_can_be_closed_but_not_abandoned(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = ready_plan(seeded_client, api)
        seeded_client.post(
            f"{api}/portfolio/trades",
            json={"symbol": "LUCK", "side": "buy", "quantity": "100", "price": "800"},
        )

        assert seeded_client.post(f"{api}/plans/{plan['id']}/abandon").status_code == 409
        closed = seeded_client.post(f"{api}/plans/{plan['id']}/close")
        assert closed.status_code == 200
        assert closed.json()["status"] == "closed"

    def test_a_ready_plan_cannot_be_closed_before_it_is_executed(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = ready_plan(seeded_client, api)
        assert seeded_client.post(f"{api}/plans/{plan['id']}/close").status_code == 409


class TestReviews:
    def test_a_review_is_recorded_and_updates_the_review_timestamp(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = ready_plan(seeded_client, api)
        before = plan["last_reviewed_at"]

        response = seeded_client.post(
            f"{api}/plans/{plan['id']}/reviews",
            json={
                "note": "Re-read the half-year accounts: margin held at 17%, gearing unchanged.",
                "thesis_still_valid": True,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert len(body["reviews"]) == 1
        assert body["last_reviewed_at"] >= before

    def test_reviews_are_returned_newest_first(self, seeded_client: TestClient, api: str) -> None:
        plan = ready_plan(seeded_client, api)
        for note in (
            "First check-in: nothing has changed since I bought.",
            "Second check-in: margins slipping, watching the next quarter.",
        ):
            seeded_client.post(f"{api}/plans/{plan['id']}/reviews", json={"note": note})

        reviews = seeded_client.get(f"{api}/plans/{plan['id']}").json()["reviews"]
        assert len(reviews) == 2
        assert reviews[0]["note"].startswith("Second")

    def test_a_review_can_record_that_the_thesis_has_broken(
        self, seeded_client: TestClient, api: str
    ) -> None:
        """Recording a broken thesis must not sell anything by itself."""
        plan = ready_plan(seeded_client, api)
        response = seeded_client.post(
            f"{api}/plans/{plan['id']}/reviews",
            json={
                "note": "Debt rose 40% to fund an unrelated acquisition - not why I bought this.",
                "thesis_still_valid": False,
            },
        )

        assert response.status_code == 201
        assert response.json()["reviews"][0]["thesis_still_valid"] is False
        assert response.json()["status"] == "ready"  # unchanged

    def test_an_empty_review_note_is_rejected(self, seeded_client: TestClient, api: str) -> None:
        """A timestamp-only review would silence the alert without any thinking."""
        plan = ready_plan(seeded_client, api)
        response = seeded_client.post(f"{api}/plans/{plan['id']}/reviews", json={"note": "ok"})
        assert response.status_code == 422

    def test_a_draft_has_no_live_thesis_to_review(
        self, seeded_client: TestClient, api: str
    ) -> None:
        plan = create_plan(seeded_client, api)
        response = seeded_client.post(
            f"{api}/plans/{plan['id']}/reviews",
            json={"note": "Trying to review a plan I have not committed to yet."},
        )
        assert response.status_code == 409


class TestListing:
    def test_plans_are_listed_newest_first_with_a_total(
        self, seeded_client: TestClient, api: str
    ) -> None:
        for symbol in ("LUCK", "HBL", "FFC"):
            create_plan(seeded_client, api, symbol)

        body = seeded_client.get(f"{api}/plans").json()
        assert body["total"] == 3
        assert [item["symbol"] for item in body["items"]] == ["FFC", "HBL", "LUCK"]

    def test_listing_can_be_filtered_by_status(self, seeded_client: TestClient, api: str) -> None:
        ready_plan(seeded_client, api, "LUCK")
        create_plan(seeded_client, api, "HBL")

        drafts = seeded_client.get(f"{api}/plans", params={"plan_status": "draft"}).json()
        assert drafts["total"] == 1
        assert drafts["items"][0]["symbol"] == "HBL"

    def test_pagination_reports_the_full_total(self, seeded_client: TestClient, api: str) -> None:
        for symbol in ("LUCK", "HBL", "FFC"):
            create_plan(seeded_client, api, symbol)

        page = seeded_client.get(f"{api}/plans", params={"limit": 2, "offset": 0}).json()
        assert len(page["items"]) == 2
        assert page["total"] == 3
