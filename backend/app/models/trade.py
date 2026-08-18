"""Executed trades - the immutable ledger the portfolio is derived from.

Design note (important for reviewers): there is **no holdings table**. Holdings
are recomputed from this ledger on read by
:mod:`app.services.portfolio_service`.

Why: a stored ``holdings`` row duplicates information that trades already fully
determine, and every duplicate is a chance to disagree with the ledger after a
partially-failed request, a manual correction, or a back-dated trade. Replaying
trades is O(trades per user), which for a retail portfolio is tens of rows -
cheaper than the reconciliation code the alternative would need. If a portfolio
ever grows large enough for this to matter, the fix is a cached projection
rebuilt from this same ledger, not a second source of truth.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import TradeSide
from app.db.base import Base, Money, TimestampMixin, enum_column

if TYPE_CHECKING:  # pragma: no cover
    from app.models.company import Company
    from app.models.trade_plan import TradePlan
    from app.models.user import User


class Trade(Base, TimestampMixin):
    """A single buy or sell that actually happened."""

    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint("fees >= 0", name="fees_non_negative"),
        # The portfolio replay always reads a user's trades in execution order.
        Index("ix_trades_user_company_executed", "user_id", "company_id", "executed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    #: The plan this trade acted on, when there was one. Nullable because trades
    #: can be back-filled from a broker statement for positions bought before
    #: the user started using the tool - and because an unplanned purchase is a
    #: fact worth recording rather than one to reject.
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("trade_plans.id", ondelete="SET NULL"), index=True
    )

    side: Mapped[TradeSide] = mapped_column(enum_column(TradeSide))
    #: Share count. Fractional shares do not exist on PSX, but Numeric keeps the
    #: arithmetic exact and tolerates bonus-share adjustments.
    quantity: Mapped[Money]
    #: Price per share, excluding fees.
    price: Mapped[Money]
    #: Brokerage, CDC and taxes for this trade. Included in cost basis on a buy
    #: and deducted from proceeds on a sell, so reported P/L is what the user
    #: actually keeps rather than a headline gross figure.
    fees: Mapped[Money] = mapped_column(default=Decimal(0))

    executed_at: Mapped[datetime]
    note: Mapped[str | None] = mapped_column(Text())

    user: Mapped[User] = relationship(back_populates="trades")
    company: Mapped[Company] = relationship()
    plan: Mapped[TradePlan | None] = relationship(back_populates="trades")

    @property
    def gross_value(self) -> Decimal:
        """Quantity x price, before fees."""
        return self.quantity * self.price

    @property
    def cash_flow(self) -> Decimal:
        """Signed cash effect: negative for a buy, positive for a sell.

        A buy costs ``gross + fees``; a sell returns ``gross - fees``.
        """
        if self.side is TradeSide.BUY:
            return -(self.gross_value + self.fees)
        return self.gross_value - self.fees
