"""Watchlist - companies being researched but not yet owned."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Money, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.company import Company
    from app.models.user import User


class WatchlistItem(Base, TimestampMixin):
    """A company the user is tracking, with the reason recorded.

    ``research_note`` is required by the service layer rather than the column:
    the guide's first mistake to avoid is chasing hype, and forcing the user to
    articulate *why* they are watching something is the cheapest guard against
    it. Keeping the constraint in the service (not as ``nullable=False``) lets
    seeded and imported rows exist without a note while still holding
    user-created rows to the rule.
    """

    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="user_company"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    #: Price at or below which the user considers the stock worth buying.
    #: Drives the WATCHLIST_ENTRY_PRICE_REACHED alert.
    target_entry_price: Mapped[Money | None]
    research_note: Mapped[str | None] = mapped_column(Text())

    user: Mapped[User] = relationship(back_populates="watchlist_items")
    company: Mapped[Company] = relationship()
