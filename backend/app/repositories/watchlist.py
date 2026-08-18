"""Watchlist queries."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.watchlist import WatchlistItem
from app.repositories.base import BaseRepository


class WatchlistRepository(BaseRepository[WatchlistItem]):
    """Per-user watchlist entries."""

    model = WatchlistItem

    def list_for_user(self, user_id: int) -> Sequence[WatchlistItem]:
        """A user's watchlist with companies loaded, newest entry first.

        ``joinedload`` here (rather than ``selectinload``) because it is a
        many-to-one: one extra column set on the same row, no row multiplication.
        """
        statement = (
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .options(joinedload(WatchlistItem.company))
            .order_by(WatchlistItem.created_at.desc(), WatchlistItem.id.desc())
        )
        return self.session.scalars(statement).unique().all()

    def get_for_user(self, user_id: int, item_id: int) -> WatchlistItem | None:
        """Fetch one entry, scoped to its owner.

        Every per-user read is scoped by ``user_id`` in the query itself rather
        than fetched by id and checked afterwards. The scoped query cannot leak
        another user's row through a forgotten check.
        """
        statement = (
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id, WatchlistItem.id == item_id)
            .options(joinedload(WatchlistItem.company))
        )
        return self.session.scalars(statement).one_or_none()

    def get_for_company(self, user_id: int, company_id: int) -> WatchlistItem | None:
        """Find a user's entry for one company, if it exists."""
        statement = select(WatchlistItem).where(
            WatchlistItem.user_id == user_id, WatchlistItem.company_id == company_id
        )
        return self.session.scalars(statement).one_or_none()
