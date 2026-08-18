"""The investor's own plan - guide section 1, "start with your own goals".

Written down *before* any stock is looked at, and then used as the yardstick
for everything else: position sizing, concentration warnings, and whether a
short-term technical reading is even relevant to this user.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import RiskTolerance, TimeHorizon
from app.db.base import Base, Money, TimestampMixin, enum_column

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User


class InvestorProfile(Base, TimestampMixin):
    """One row per user: horizon, risk limits and capital available."""

    __tablename__ = "investor_profiles"
    __table_args__ = (
        CheckConstraint(
            "max_position_pct > 0 AND max_position_pct <= 100", name="max_position_pct_range"
        ),
        CheckConstraint(
            "max_sector_pct > 0 AND max_sector_pct <= 100", name="max_sector_pct_range"
        ),
        CheckConstraint(
            "drawdown_tolerance_pct >= 0 AND drawdown_tolerance_pct <= 100",
            name="drawdown_tolerance_pct_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    time_horizon: Mapped[TimeHorizon] = mapped_column(enum_column(TimeHorizon))
    risk_tolerance: Mapped[RiskTolerance] = mapped_column(enum_column(RiskTolerance))
    #: "Could you stay calm if this dropped 30%?" captured as a number so the
    #: pre-buy checklist can compare it against a plan instead of asking again.
    drawdown_tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("30"))

    #: Total amount the user is willing to have invested in equities.
    investable_capital: Mapped[Money] = mapped_column(default=Decimal(0))
    #: Ceiling for any single holding, as a percent of portfolio value.
    max_position_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("15"))
    #: Ceiling for any single sector - the guide's diversification rule.
    max_sector_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("35"))

    # -- Money-hygiene declarations (guide section 1, "How much") ----------
    #: False means the user is investing money they may need soon.
    emergency_fund_in_place: Mapped[bool] = mapped_column(default=False)
    #: True is surfaced as a standing warning; the guide is explicit that money
    #: earmarked for rent or debt payments does not belong in equities.
    investing_borrowed_money: Mapped[bool] = mapped_column(default=False)

    #: How often an open position's thesis should be revisited.
    review_interval_days: Mapped[int] = mapped_column(default=90)

    goals_note: Mapped[str | None] = mapped_column(Text())

    user: Mapped[User] = relationship(back_populates="profile")
