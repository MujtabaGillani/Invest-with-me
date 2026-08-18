"""Thesis check-in journal (guide section 6).

Each row is one occasion the user re-examined why they own something. Kept as an
append-only journal rather than a ``last_reviewed_note`` column on the plan,
because the value is in the sequence: reading three consecutive reviews that each
say "margins still slipping" is how a user notices they have been rationalising a
position rather than reassessing it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.trade_plan import TradePlan


class PlanReview(Base, TimestampMixin):
    """One recorded thesis check-in against a plan."""

    __tablename__ = "plan_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("trade_plans.id", ondelete="CASCADE"), index=True
    )

    #: What the user checked and concluded. Required by the API schema with a
    #: minimum length - a review with no content would silence the review-due
    #: alert without any thinking having happened.
    note: Mapped[str] = mapped_column(Text())
    #: False records that the reason for owning the position no longer holds.
    #: This does not sell anything; it captures the conclusion and raises an
    #: alert, leaving the decision with the user.
    thesis_still_valid: Mapped[bool] = mapped_column(default=True)

    plan: Mapped[TradePlan] = relationship(back_populates="reviews")
