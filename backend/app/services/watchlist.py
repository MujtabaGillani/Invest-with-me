"""Watchlist service."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.enums import SECTOR_LABELS
from app.core.errors import ConflictError, NotFoundError
from app.models.watchlist import WatchlistItem
from app.repositories.companies import CompanyRepository
from app.repositories.plans import TradePlanRepository
from app.repositories.watchlist import WatchlistRepository
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemRead, WatchlistItemUpdate
from app.services.companies import CompanyService

_PERCENT = Decimal("0.01")


class WatchlistService:
    """Manage the companies a user is researching."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.items = WatchlistRepository(session)
        self.companies = CompanyRepository(session)
        self.company_service = CompanyService(session)
        self.plans = TradePlanRepository(session)

    def list_items(self, user_id: int) -> list[WatchlistItemRead]:
        """The user's watchlist with a current price snapshot on each row."""
        rows = self.items.list_for_user(user_id)
        if not rows:
            return []

        prices = self.companies.latest_price_by_company([row.company_id for row in rows])
        planned_company_ids = set(self.plans.active_plans_by_company(user_id))
        return [
            self._to_read_model(
                item,
                last_close=prices[item.company_id].close if item.company_id in prices else None,
                last_close_date=(
                    prices[item.company_id].trade_date if item.company_id in prices else None
                ),
                has_plan=item.company_id in planned_company_ids,
            )
            for item in rows
        ]

    def add_item(self, user_id: int, payload: WatchlistItemCreate) -> WatchlistItemRead:
        """Add a company to the watchlist.

        Duplicates are a conflict rather than a silent no-op, so the client can
        point the user at the entry they already have instead of appearing to have
        done nothing.
        """
        company = self.company_service.require_company(payload.symbol)
        if self.items.get_for_company(user_id, company.id) is not None:
            raise ConflictError(
                f"{company.symbol} is already on your watchlist.",
                details={"symbol": company.symbol},
            )

        item = WatchlistItem(
            user_id=user_id,
            company_id=company.id,
            research_note=payload.research_note,
            target_entry_price=payload.target_entry_price,
        )
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return self._single(user_id, item.id)

    def update_item(
        self, user_id: int, item_id: int, payload: WatchlistItemUpdate
    ) -> WatchlistItemRead:
        """Revise a watchlist entry's note or entry price."""
        item = self.items.get_for_user(user_id, item_id)
        if item is None:
            raise NotFoundError("Watchlist entry not found.", details={"item_id": item_id})

        for field_name in payload.model_fields_set:
            setattr(item, field_name, getattr(payload, field_name))

        self.session.commit()
        return self._single(user_id, item_id)

    def remove_item(self, user_id: int, item_id: int) -> None:
        """Remove a watchlist entry."""
        item = self.items.get_for_user(user_id, item_id)
        if item is None:
            raise NotFoundError("Watchlist entry not found.", details={"item_id": item_id})
        self.session.delete(item)
        self.session.commit()

    # -- Internals ---------------------------------------------------------

    def _single(self, user_id: int, item_id: int) -> WatchlistItemRead:
        """Re-read one entry through the list path.

        Reusing the list builder keeps the price snapshot and plan flag identical
        between a create/update response and a subsequent list refresh.
        """
        for item in self.list_items(user_id):
            if item.id == item_id:
                return item
        raise NotFoundError("Watchlist entry not found.", details={"item_id": item_id})

    @staticmethod
    def _to_read_model(
        item: WatchlistItem,
        *,
        last_close: Decimal | None,
        last_close_date: date | None,
        has_plan: bool,
    ) -> WatchlistItemRead:
        distance: Decimal | None = None
        reached = False
        if item.target_entry_price is not None and last_close is not None and last_close > 0:
            # Negative means the price has already fallen to or below the level the
            # user said they would buy at.
            distance = (
                (item.target_entry_price - last_close) / last_close * Decimal(100)
            ).quantize(_PERCENT, rounding=ROUND_HALF_UP)
            reached = last_close <= item.target_entry_price

        return WatchlistItemRead(
            id=item.id,
            company_id=item.company_id,
            symbol=item.company.symbol,
            company_name=item.company.name,
            sector=item.company.sector,
            sector_label=SECTOR_LABELS[item.company.sector],
            research_note=item.research_note,
            target_entry_price=item.target_entry_price,
            last_close=last_close,
            last_close_date=last_close_date,
            distance_to_target_pct=distance,
            entry_price_reached=reached,
            has_trade_plan=has_plan,
            created_at=item.created_at,
        )
