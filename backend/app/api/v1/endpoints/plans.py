"""Trade plan endpoints - the pre-buy checklist and exit rules.

State changes are modelled as named actions (``/commit``, ``/abandon``,
``/close``, ``/reviews``) rather than as ``PATCH {"status": "..."}``. Each
transition has its own preconditions - committing requires a complete checklist,
closing requires an executed plan - and an explicit endpoint per transition makes
those rules visible in the API surface instead of hidden inside one handler.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, status

from app.api.deps import CurrentUser, Pagination, PlanServiceDep, PlanStatusFilter
from app.schemas.common import Page
from app.schemas.plans import (
    TradePlanCreate,
    TradePlanDetail,
    TradePlanRead,
    TradePlanReviewCreate,
    TradePlanUpdate,
)

router = APIRouter(prefix="/plans", tags=["trade plans"])

PlanIdPath = Annotated[int, Path(ge=1, description="Trade plan id.")]

#: Shared OpenAPI response documentation. Typed to match FastAPI's own signature,
#: which keys responses by ``int | str`` because it also accepts wildcards such as
#: "4XX" - a plain ``dict[int, ...]`` cannot be spread into it.
ResponseDocs = dict[int | str, dict[str, Any]]

_CONFLICT: ResponseDocs = {
    status.HTTP_409_CONFLICT: {"description": "The plan is not in a state that allows this."}
}
_NOT_FOUND: ResponseDocs = {status.HTTP_404_NOT_FOUND: {"description": "Plan not found."}}


@router.get("", response_model=Page[TradePlanRead], summary="List trade plans")
def list_plans(
    service: PlanServiceDep,
    user: CurrentUser,
    pagination: Pagination,
    plan_status: PlanStatusFilter = None,
) -> Page[TradePlanRead]:
    """Plans newest first, optionally filtered by status."""
    return service.list_plans(
        user.id, status=plan_status, limit=pagination.limit, offset=pagination.offset
    )


@router.post(
    "",
    response_model=TradePlanDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Start a trade plan",
    responses={**_CONFLICT, status.HTTP_404_NOT_FOUND: {"description": "Unknown symbol."}},
)
def create_plan(
    payload: TradePlanCreate, service: PlanServiceDep, user: CurrentUser
) -> TradePlanDetail:
    """Open a draft plan for a company.

    Everything except the symbol is optional at this point - the plan is meant to
    be worked through, and the response's ``readiness`` field lists exactly what is
    still missing before it can be committed to.
    """
    return service.create_plan(user.id, payload)


@router.get(
    "/{plan_id}",
    response_model=TradePlanDetail,
    summary="Get a trade plan",
    responses={**_NOT_FOUND},
)
def get_plan(plan_id: PlanIdPath, service: PlanServiceDep, user: CurrentUser) -> TradePlanDetail:
    """One plan with its readiness assessment, position sizing and review journal."""
    return service.get_plan(user.id, plan_id)


@router.patch(
    "/{plan_id}",
    response_model=TradePlanDetail,
    summary="Update a draft plan",
    responses={**_NOT_FOUND, **_CONFLICT},
)
def update_plan(
    plan_id: PlanIdPath,
    payload: TradePlanUpdate,
    service: PlanServiceDep,
    user: CurrentUser,
) -> TradePlanDetail:
    """Answer checklist questions, or set the thesis and exit rules.

    Only draft plans are editable. Once a plan has been committed to it is a record
    of a decision, and editing it would rewrite the history the review journal
    exists to preserve.
    """
    return service.update_plan(user.id, plan_id, payload)


@router.post(
    "/{plan_id}/commit",
    response_model=TradePlanDetail,
    summary="Commit to a plan",
    responses={
        **_NOT_FOUND,
        **_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": (
                "The checklist is incomplete or the exit rules are missing. The response lists "
                "every blocking reason."
            )
        },
    },
)
def commit_plan(plan_id: PlanIdPath, service: PlanServiceDep, user: CurrentUser) -> TradePlanDetail:
    """Move a plan from draft to ready.

    Rejected unless all five pre-buy questions are answered "yes" **and** both a
    profit target and a stop-loss are set. That is the one hard rule in this
    application: the guide's instruction is to decide the exit before buying, not
    while watching the price move.
    """
    return service.commit_plan(user.id, plan_id)


@router.post(
    "/{plan_id}/abandon",
    response_model=TradePlanDetail,
    summary="Abandon a plan",
    responses={**_NOT_FOUND, **_CONFLICT},
)
def abandon_plan(
    plan_id: PlanIdPath,
    service: PlanServiceDep,
    user: CurrentUser,
    reason: Annotated[
        str | None,
        Body(
            embed=True,
            max_length=4000,
            description="Why you decided not to buy. Recorded in the plan's journal.",
        ),
    ] = None,
) -> TradePlanDetail:
    """Record that you decided not to buy after all.

    The plan is kept, not deleted: a decision not to act, and the reason for it, is
    worth re-reading the next time the same idea comes around.
    """
    return service.abandon_plan(user.id, plan_id, reason=reason)


@router.post(
    "/{plan_id}/close",
    response_model=TradePlanDetail,
    summary="Close an executed plan",
    responses={**_NOT_FOUND, **_CONFLICT},
)
def close_plan(plan_id: PlanIdPath, service: PlanServiceDep, user: CurrentUser) -> TradePlanDetail:
    """Mark a plan closed once the position it governed has been exited."""
    return service.close_plan(user.id, plan_id)


@router.post(
    "/{plan_id}/reviews",
    response_model=TradePlanDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Record a thesis check-in",
    responses={**_NOT_FOUND, **_CONFLICT},
)
def record_review(
    plan_id: PlanIdPath,
    payload: TradePlanReviewCreate,
    service: PlanServiceDep,
    user: CurrentUser,
) -> TradePlanDetail:
    """Record that you re-checked why you own this, and what you concluded.

    This is the guide's "thesis check-in": if the reason you bought has changed,
    that is a far stronger signal than a red candle on a chart. Recording a review
    clears the review-due alert, which is why a substantive note is required.
    """
    return service.record_review(user.id, plan_id, payload)
