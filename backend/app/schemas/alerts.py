"""Alert schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.enums import AlertKind, AlertSeverity
from app.schemas.common import ReadSchema


class AlertRead(ReadSchema):
    """A single alert."""

    id: int
    kind: AlertKind
    severity: AlertSeverity
    message: str
    #: Numbers behind the message so the UI can render the specifics precisely.
    context: dict[str, Any] = Field(default_factory=dict)

    company_id: int | None = None
    symbol: str | None = None
    company_name: str | None = None

    created_at: datetime
    acknowledged_at: datetime | None = None
    is_acknowledged: bool = False


class AlertEvaluationResult(ReadSchema):
    """Outcome of running the portfolio monitor.

    Returned by the explicit evaluate endpoint so the UI can say "3 new, 2 already
    known" instead of silently refreshing a list.
    """

    created: int
    already_open: int
    resolved: int = Field(
        description=(
            "Previously raised alerts whose condition no longer holds; these are "
            "acknowledged automatically."
        )
    )
    alerts: list[AlertRead]
    note: str = Field(
        default=(
            "Every alert here is one of your own pre-committed rules crossing its threshold. "
            "None of them is a recommendation to act."
        )
    )
