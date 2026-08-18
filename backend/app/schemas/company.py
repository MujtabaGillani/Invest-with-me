"""Company, financial statement and price history schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.core.enums import Sector
from app.schemas.common import ReadSchema


class PriceBarRead(ReadSchema):
    """One trading session."""

    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class AnnualFinancialsRead(ReadSchema):
    """Reported figures for one fiscal year, exactly as stored.

    Derived measures are deliberately absent - they belong to the fundamentals
    report, which explains and judges them. This endpoint is the raw record, so a
    user can reconcile it against the annual report.
    """

    fiscal_year: int
    revenue: Decimal | None = None
    net_profit: Decimal | None = None
    eps: Decimal | None = None
    total_assets: Decimal | None = None
    total_equity: Decimal | None = None
    total_debt: Decimal | None = None
    operating_cash_flow: Decimal | None = None
    capital_expenditure: Decimal | None = None
    dividend_per_share: Decimal | None = None
    shares_outstanding: Decimal | None = None
    source: str | None = None


class CompanySummary(ReadSchema):
    """List-view representation of a company."""

    id: int
    symbol: str
    name: str
    sector: Sector
    sector_label: str
    is_active: bool

    last_close: Decimal | None = Field(
        default=None, description="Most recent close held locally, if any."
    )
    last_close_date: date | None = None
    #: Whether each kind of analysis can be run, so the UI can disable a tab
    #: instead of offering it and then showing an error.
    has_financials: bool = False
    has_price_history: bool = False


class CompanyDetail(CompanySummary):
    """Single-company view, including the raw statements."""

    business_summary: str | None = None
    website: str | None = None
    fiscal_years: list[int] = Field(default_factory=list)
    financials: list[AnnualFinancialsRead] = Field(default_factory=list)


class PriceHistoryRead(ReadSchema):
    """A company's stored price series."""

    symbol: str
    sessions: int
    bars: list[PriceBarRead]
