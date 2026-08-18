"""Trade ledger queries."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models.trade import Trade
from app.repositories.base import BaseRepository


class TradeRepository(BaseRepository[Trade]):
    """Per-user trade ledger.

    Reads are ordered by ``executed_at`` then ``id`` throughout. The tie-break on
    ``id`` matters: two trades recorded with the same timestamp (a bulk import, or
    a same-day buy and sell) must replay in a stable order, or a user's average
    cost would change between two identical requests.
    """

    model = Trade

    def list_for_user(
        self,
        user_id: int,
        *,
        company_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> Sequence[Trade]:
        """Trades in execution order, oldest first."""
        statement = (
            select(Trade)
            .where(Trade.user_id == user_id)
            .options(joinedload(Trade.company))
            .order_by(Trade.executed_at, Trade.id)
        )
        if company_id is not None:
            statement = statement.where(Trade.company_id == company_id)
        if limit is not None:
            statement = statement.limit(limit).offset(offset)
        return self.session.scalars(statement).unique().all()

    def list_recent_for_user(self, user_id: int, *, limit: int = 20) -> Sequence[Trade]:
        """Most recent trades first - for the activity feed, not for replay."""
        statement = (
            select(Trade)
            .where(Trade.user_id == user_id)
            .options(joinedload(Trade.company))
            .order_by(Trade.executed_at.desc(), Trade.id.desc())
            .limit(limit)
        )
        return self.session.scalars(statement).unique().all()

    def get_for_user(self, user_id: int, trade_id: int) -> Trade | None:
        """Fetch one trade, scoped to its owner."""
        statement = (
            select(Trade)
            .where(Trade.user_id == user_id, Trade.id == trade_id)
            .options(joinedload(Trade.company))
        )
        return self.session.scalars(statement).one_or_none()

    def count_for_user(self, user_id: int, *, company_id: int | None = None) -> int:
        """Number of recorded trades."""
        statement = select(func.count()).select_from(Trade).where(Trade.user_id == user_id)
        if company_id is not None:
            statement = statement.where(Trade.company_id == company_id)
        return self.session.scalar(statement) or 0

    def company_ids_traded(self, user_id: int) -> Sequence[int]:
        """Distinct companies the user has ever traded.

        Includes fully closed positions, because realised profit and loss still
        has to be reported for them.
        """
        statement = select(Trade.company_id).where(Trade.user_id == user_id).distinct()
        return self.session.scalars(statement).all()
