"""User account.

v1 ships single-user: the API resolves one account from configuration rather
than authenticating a request. The table exists anyway so that every
user-owned row (profile, plans, trades, watchlist, alerts) already carries a
``user_id`` foreign key - adding real authentication later becomes a change to
one dependency, not a schema migration across six tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers only
    from app.models.alert import Alert
    from app.models.investor_profile import InvestorProfile
    from app.models.trade import Trade
    from app.models.trade_plan import TradePlan
    from app.models.watchlist import WatchlistItem


class User(Base, TimestampMixin):
    """A person using the tool."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(default=True)

    # ``uselist=False`` - a user has exactly one investment plan (guide section 1).
    profile: Mapped[InvestorProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    watchlist_items: Mapped[list[WatchlistItem]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    trade_plans: Mapped[list[TradePlan]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    trades: Mapped[list[Trade]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alerts: Mapped[list[Alert]] = relationship(back_populates="user", cascade="all, delete-orphan")
