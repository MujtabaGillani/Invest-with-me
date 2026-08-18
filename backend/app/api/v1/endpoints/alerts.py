"""Alert endpoints.

Evaluation is an explicit ``POST /alerts/evaluate`` rather than a side effect of
listing alerts. Two reasons: a GET must not write to the database, and the client
gets a meaningful summary ("2 new, 1 resolved") instead of a silently changed
list.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.deps import AlertServiceDep, CurrentUser
from app.schemas.alerts import AlertEvaluationResult, AlertRead
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/alerts", tags=["alerts"])

AlertIdPath = Annotated[int, Path(ge=1, description="Alert id.")]


@router.get("", response_model=list[AlertRead], summary="List alerts")
def list_alerts(
    service: AlertServiceDep,
    user: CurrentUser,
    include_acknowledged: Annotated[
        bool, Query(description="Include alerts you have already dismissed.")
    ] = False,
) -> list[AlertRead]:
    """Stored alerts, newest first.

    Read-only: it reports what the last evaluation found. Call
    ``POST /alerts/evaluate`` to re-check the portfolio against your rules.
    """
    return service.list_alerts(user.id, include_acknowledged=include_acknowledged)


@router.post(
    "/evaluate",
    response_model=AlertEvaluationResult,
    summary="Re-evaluate the portfolio against your rules",
)
def evaluate_alerts(service: AlertServiceDep, user: CurrentUser) -> AlertEvaluationResult:
    """Check every holding against the rules you set for yourself.

    Idempotent: running it repeatedly does not duplicate alerts, and conditions that
    no longer hold are cleared automatically. Every alert it raises corresponds to
    one of your own pre-committed thresholds - a profit target, a stop-loss, a
    concentration limit, a review interval - not to a prediction made by this
    system.
    """
    return service.evaluate(user.id)


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertRead,
    summary="Dismiss one alert",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Alert not found."}},
)
def acknowledge_alert(
    alert_id: AlertIdPath, service: AlertServiceDep, user: CurrentUser
) -> AlertRead:
    """Dismiss an alert. The row is kept as part of your decision journal."""
    return service.acknowledge(user.id, alert_id)


@router.post(
    "/acknowledge-all",
    response_model=MessageResponse,
    summary="Dismiss all open alerts",
)
def acknowledge_all_alerts(service: AlertServiceDep, user: CurrentUser) -> MessageResponse:
    """Dismiss every currently open alert."""
    count = service.acknowledge_all(user.id)
    return MessageResponse(message=f"Dismissed {count} alert(s).")
