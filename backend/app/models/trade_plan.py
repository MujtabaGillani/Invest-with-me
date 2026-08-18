"""Trade plans - the pre-commitment record (guide sections 5 and 6).

This is the heart of the product. The guide's instruction is to decide the exit
*before* buying, "not while emotionally watching the price move". A plan is
therefore a first-class, timestamped row: the five pre-buy checks, the reason
for buying, and the profit target / stop-loss, all captured while the user is
calm and all preserved afterwards so the decision can be reviewed honestly.

A plan cannot leave :attr:`~app.core.enums.TradePlanStatus.DRAFT` until every
checklist item is answered and both exit rules are set - enforced in
:mod:`app.services.trade_plan_service`, which owns that invariant.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import TradePlanStatus
from app.db.base import Base, Money, TimestampMixin, enum_column

if TYPE_CHECKING:  # pragma: no cover
    from app.models.company import Company
    from app.models.plan_review import PlanReview
    from app.models.trade import Trade
    from app.models.user import User


class TradePlan(Base, TimestampMixin):
    """A written intention to buy, including the rules for getting out."""

    __tablename__ = "trade_plans"
    __table_args__ = (
        CheckConstraint(
            "profit_target_pct IS NULL OR profit_target_pct > 0",
            name="profit_target_pct_positive",
        ),
        CheckConstraint(
            "stop_loss_pct IS NULL OR (stop_loss_pct > 0 AND stop_loss_pct < 100)",
            name="stop_loss_pct_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[TradePlanStatus] = mapped_column(
        enum_column(TradePlanStatus), default=TradePlanStatus.DRAFT, index=True
    )

    # -- Guide section 5: the five pre-buy questions -----------------------
    # Nullable on purpose: NULL means "not yet answered", which is different
    # from False ("answered honestly, and the answer is no"). Collapsing the two
    # would let an unfinished checklist look like a failed one.
    understands_business: Mapped[bool | None]
    revenue_and_profit_healthy: Mapped[bool | None]
    debt_manageable_vs_peers: Mapped[bool | None]
    comfortable_with_drawdown: Mapped[bool | None]
    position_size_appropriate: Mapped[bool | None]

    #: Why this stock, in the user's own words. Compared against reality at each
    #: review - the guide's "thesis check-in".
    thesis: Mapped[str | None] = mapped_column(Text())
    #: What would prove the thesis wrong. Written up front, when it is still an
    #: intellectual exercise rather than a loss.
    invalidation_note: Mapped[str | None] = mapped_column(Text())

    # -- Sizing and exit rules (guide section 6) ---------------------------
    intended_amount: Mapped[Money | None]
    #: e.g. 25 -> "sell some or all once up 25%".
    profit_target_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    #: e.g. 15 -> "exit if it falls 15% below what I paid".
    stop_loss_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    #: When the plan was marked READY - the moment of commitment.
    committed_at: Mapped[datetime | None]
    #: Last time the user re-checked the thesis; drives THESIS_REVIEW_DUE.
    last_reviewed_at: Mapped[datetime | None]

    user: Mapped[User] = relationship(back_populates="trade_plans")
    company: Mapped[Company] = relationship()
    trades: Mapped[list[Trade]] = relationship(back_populates="plan")
    reviews: Mapped[list[PlanReview]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        # Newest first. The id tie-break matters because created_at is
        # database-generated with one-second resolution on SQLite, so two reviews
        # recorded in the same second would otherwise order arbitrarily.
        order_by="(PlanReview.created_at.desc(), PlanReview.id.desc())",
    )

    # -- Derived, read-only helpers ---------------------------------------

    @property
    def checklist_answers(self) -> dict[str, bool | None]:
        """The five pre-buy answers keyed by field name, in guide order."""
        return {
            "understands_business": self.understands_business,
            "revenue_and_profit_healthy": self.revenue_and_profit_healthy,
            "debt_manageable_vs_peers": self.debt_manageable_vs_peers,
            "comfortable_with_drawdown": self.comfortable_with_drawdown,
            "position_size_appropriate": self.position_size_appropriate,
        }

    @property
    def checklist_complete(self) -> bool:
        """True when all five questions are answered ``True``.

        "Complete" deliberately means *all yes*: the guide's wording is "if you
        can answer all five confidently". A ``False`` answer is a finished
        thought, but it is not a basis for buying.
        """
        return all(answer is True for answer in self.checklist_answers.values())

    @property
    def unanswered_checklist_items(self) -> list[str]:
        """Field names still awaiting an answer (``None``)."""
        return [key for key, answer in self.checklist_answers.items() if answer is None]

    @property
    def failed_checklist_items(self) -> list[str]:
        """Field names the user answered ``False``."""
        return [key for key, answer in self.checklist_answers.items() if answer is False]

    @property
    def has_exit_rules(self) -> bool:
        """Both a profit target and a stop-loss have been set."""
        return self.profit_target_pct is not None and self.stop_loss_pct is not None
