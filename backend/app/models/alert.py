"""Alerts raised by the portfolio monitor.

Every alert corresponds to a rule the *user* wrote down (a profit target, a
stop-loss, a concentration limit) crossing its threshold - never to a prediction
made by this system. The wording of :attr:`message` follows that rule: it states
what happened and which of the user's own limits it touched.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AlertKind, AlertSeverity
from app.db.base import Base, TimestampMixin, enum_column

if TYPE_CHECKING:  # pragma: no cover
    from app.models.company import Company
    from app.models.user import User


class Alert(Base, TimestampMixin):
    """A single notification, de-duplicated by :attr:`dedupe_key`."""

    __tablename__ = "alerts"
    __table_args__ = (
        # The monitor is idempotent: re-evaluating the portfolio must not create
        # a second "stop-loss breached on LUCK" row every time the page loads.
        # The key encodes user + kind + subject (see AlertService.build_dedupe_key).
        UniqueConstraint("user_id", "dedupe_key", name="user_dedupe_key"),
        Index("ix_alerts_user_acknowledged", "user_id", "acknowledged_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    #: Null for portfolio-wide alerts such as sector concentration.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[AlertKind] = mapped_column(enum_column(AlertKind), index=True)
    severity: Mapped[AlertSeverity] = mapped_column(enum_column(AlertSeverity))
    message: Mapped[str] = mapped_column(Text())

    #: Numbers behind the message (threshold, observed value, symbol). Stored as
    #: JSON so the UI can render a precise explanation without the backend
    #: pre-formatting prose, and so new alert kinds need no migration.
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    dedupe_key: Mapped[str] = mapped_column(String(200))
    #: Set when the user dismisses the alert. Rows are kept, not deleted, so the
    #: decision journal shows what the user was told and when.
    acknowledged_at: Mapped[datetime | None]

    user: Mapped[User] = relationship(back_populates="alerts")
    company: Mapped[Company | None] = relationship()

    @property
    def is_acknowledged(self) -> bool:
        return self.acknowledged_at is not None
