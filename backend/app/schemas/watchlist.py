"""Watchlist schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.enums import Sector
from app.schemas.common import ReadSchema, WriteSchema


class WatchlistItemCreate(WriteSchema):
    """Add a company to the watchlist.

    ``research_note`` is required with a real minimum length. The guide's first
    listed mistake is chasing hype, and the cheapest available guard is making
    the user articulate why they are watching something before the app will
    track it.
    """

    symbol: str = Field(min_length=1, max_length=16)
    research_note: str = Field(
        min_length=10,
        max_length=4000,
        description="Why this company is worth watching, in your own words.",
    )
    target_entry_price: Decimal | None = Field(
        default=None, gt=0, description="Price at or below which you would consider buying."
    )


class WatchlistItemUpdate(WriteSchema):
    """Revise a watchlist entry."""

    research_note: str | None = Field(default=None, min_length=10, max_length=4000)
    target_entry_price: Decimal | None = Field(default=None, gt=0)


class WatchlistItemRead(ReadSchema):
    """A watched company with a current price snapshot."""

    id: int
    company_id: int
    symbol: str
    company_name: str
    sector: Sector
    sector_label: str

    research_note: str | None = None
    target_entry_price: Decimal | None = None

    last_close: Decimal | None = None
    last_close_date: date | None = None
    #: How far the price is from the user's own entry level. Negative means the
    #: price is already at or below it.
    distance_to_target_pct: Decimal | None = None
    entry_price_reached: bool = False

    #: True when a plan already exists for this company, so the UI can offer
    #: "open plan" rather than "create plan".
    has_trade_plan: bool = False
    created_at: datetime
