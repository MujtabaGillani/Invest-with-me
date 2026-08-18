"""Portfolio, holding and trade schemas.

All money is ``Decimal``. Percentages are ``Decimal`` too here (rather than the
``float`` used in the analysis package) because they are computed directly from
money values and are shown next to them - a weight that does not tie back to the
values above it looks like a bug to the user, whatever the rounding rules say.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.enums import Sector, TradeSide
from app.schemas.common import ReadSchema, WriteSchema


class TradeCreate(WriteSchema):
    """Record an executed trade."""

    symbol: str = Field(min_length=1, max_length=16)
    side: TradeSide
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0, description="Price per share, excluding fees.")
    fees: Decimal = Field(default=Decimal("0"), ge=0, description="Brokerage, CDC and taxes.")
    executed_at: datetime | None = Field(
        default=None, description="Defaults to now. Accepts a past date for back-filled trades."
    )
    plan_id: int | None = Field(
        default=None, description="The plan this trade acts on, if there is one."
    )
    note: str | None = Field(default=None, max_length=2000)


class TradeRead(ReadSchema):
    """A recorded trade."""

    id: int
    symbol: str
    company_name: str
    side: TradeSide
    quantity: Decimal
    price: Decimal
    fees: Decimal
    gross_value: Decimal
    net_cash_flow: Decimal = Field(
        description="Signed cash effect: negative for a buy, positive for a sell."
    )
    executed_at: datetime
    plan_id: int | None = None
    note: str | None = None


class HoldingRead(ReadSchema):
    """An open position, valued at the latest stored close.

    Derived from the trade ledger on every read - there is no holdings table. See
    the module docstring of :mod:`app.models.trade` for why.
    """

    company_id: int
    symbol: str
    company_name: str
    sector: Sector
    sector_label: str

    quantity: Decimal
    average_cost: Decimal = Field(description="Cost basis per share, including buy-side fees.")
    cost_basis: Decimal = Field(description="Total invested in the shares still held.")

    last_price: Decimal | None = None
    last_price_date: date | None = None
    market_value: Decimal | None = None
    unrealised_pl: Decimal | None = None
    unrealised_pl_pct: Decimal | None = None
    realised_pl: Decimal = Field(
        default=Decimal("0"),
        description="Profit already banked on shares sold from this position, net of fees.",
    )
    weight_pct: Decimal | None = Field(
        default=None, description="Share of total portfolio market value."
    )

    # -- The user's own pre-committed exit rules, resolved to prices --------
    plan_id: int | None = None
    profit_target_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    distance_to_target_pct: Decimal | None = Field(
        default=None, description="How far the price must rise to reach the profit target."
    )
    distance_to_stop_pct: Decimal | None = Field(
        default=None, description="How far the price would have to fall to breach the stop."
    )
    #: True when this holding has no plan at all - i.e. no exit rules were ever
    #: written down. Surfaced prominently rather than silently.
    missing_exit_rules: bool = True
    last_reviewed_at: datetime | None = None


class SectorAllocation(ReadSchema):
    """Portfolio weight in one sector, against the user's own limit."""

    sector: Sector
    sector_label: str
    market_value: Decimal
    weight_pct: Decimal
    holdings_count: int
    exceeds_limit: bool = False


class ConcentrationWarning(ReadSchema):
    """A breach of one of the user's declared diversification limits."""

    kind: str = Field(description="'position' or 'sector'.")
    subject: str = Field(description="Symbol or sector label the warning is about.")
    weight_pct: Decimal
    limit_pct: Decimal
    message: str


class PortfolioSummary(ReadSchema):
    """Aggregate portfolio position."""

    holdings_count: int
    sectors_held: int
    total_cost_basis: Decimal
    total_market_value: Decimal
    total_unrealised_pl: Decimal
    total_unrealised_pl_pct: Decimal | None = None
    total_realised_pl: Decimal = Field(
        description="Banked profit or loss across all closed and partially closed positions."
    )
    total_fees_paid: Decimal
    #: Counts, not a grade - the same reasoning as the fundamentals score.
    holdings_without_exit_rules: int = 0
    diversification_note: str


class PortfolioRead(ReadSchema):
    """Everything the portfolio screen needs in one response."""

    summary: PortfolioSummary
    holdings: list[HoldingRead]
    sector_allocations: list[SectorAllocation]
    concentration_warnings: list[ConcentrationWarning]
    #: Priced from stored closes; the API never claims to be a live quote feed.
    valued_at: datetime | None = None
    market_data_is_synthetic: bool = Field(
        description="True when prices come from the generated demo dataset."
    )
