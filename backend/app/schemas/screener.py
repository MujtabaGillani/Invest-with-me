"""Response contracts for the simplified buy/sell screen.

These exist to answer two questions directly, for a user who does not want to read
a seven-metric checklist: *which companies currently pass the checks*, and *which
of the things I own have crossed a rule I set*.

**What these schemas deliberately do not contain.** No predicted price, no
expected return, no probability of profit, no composite 0-100 grade, and no field
named anything like ``recommendation``. Every number here is either an observed
figure, a count of criteria met, or a level derived from the user's own risk
limits. The ranking answers "passes the most checks", which is a statement about
published accounts - not a forecast, and not a claim that buying will be
profitable. See ``docs/ARCHITECTURE.md`` §18.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.enums import Sector
from app.schemas.common import ReadSchema


class SuggestedEntry(ReadSchema):
    """Position size and exit levels proposed for a candidate.

    Derived entirely from the user's own declared limits and the suggestion rules
    in ``app/analysis/rules.py`` - never from a price forecast. The target and stop
    are *policy* ("at what gain would I take money off the table, at what loss
    would I accept I was wrong"), which is why they can be suggested honestly when
    a price target could not.
    """

    suggested_amount: Decimal | None = Field(
        default=None,
        description=(
            "Largest purchase that stays within the user's single-position limit. "
            "Null when no investable capital has been declared yet."
        ),
    )
    suggested_shares: int | None = Field(
        default=None, description="Whole shares that amount buys at the latest price."
    )
    profit_target_pct: Decimal
    profit_target_price: Decimal | None = None
    stop_loss_pct: Decimal
    stop_loss_price: Decimal | None = None
    basis: str = Field(
        description=(
            "Plain-language statement of where these numbers came from, so they are "
            "never mistaken for a prediction."
        )
    )


class BuyCandidate(ReadSchema):
    """One company that currently passes enough of the checklist to look at."""

    symbol: str
    company_name: str
    sector: Sector
    sector_label: str

    checks_passed: int = Field(description="Metrics with a 'strong' verdict.")
    checks_adequate: int
    checks_weak: int
    checks_unknown: int = Field(
        description="Metrics that could not be judged because the data is not published."
    )
    checks_total: int

    last_price: Decimal | None = None
    last_price_date: date | None = None

    why: list[str] = Field(
        default_factory=list,
        description="One plain sentence per passing check - the reason it ranks here.",
    )
    watch_out_for: list[str] = Field(
        default_factory=list,
        description="Weak checks and unavailable data, stated rather than buried.",
    )
    timing_note: str | None = Field(
        default=None,
        description=(
            "Where the price sits relative to its own recent history. Context on "
            "whether now is a calm moment to buy - not a signal that it is."
        ),
    )
    suggested: SuggestedEntry | None = None
    already_owned: bool = False


class BuyCandidatesRead(ReadSchema):
    """The ranked shortlist, plus what the user needs to read it honestly."""

    candidates: list[BuyCandidate]
    companies_scanned: int
    companies_skipped: int = Field(
        description="Companies with too little stored data to assess at all."
    )
    as_of: datetime
    price_delay_minutes: int | None = None
    data_is_synthetic: bool
    unavailable_checks: list[str] = Field(
        default_factory=list,
        description=(
            "Checks that could not be run for any company, because the active data "
            "source does not publish the figures they need."
        ),
    )
    disclaimer: str = Field(
        default=(
            "Ranked by how many of the checklist criteria each company currently meets, "
            "based on published accounts. This is not a prediction, a price target, or "
            "advice to buy. No tool can tell you which shares will be profitable."
        )
    )


class SellReviewItem(ReadSchema):
    """A holding with something about it that needs a decision."""

    symbol: str
    company_name: str
    sector_label: str

    quantity: Decimal
    average_cost: Decimal
    last_price: Decimal | None = None
    unrealised_pl: Decimal | None = None
    unrealised_pl_pct: Decimal | None = None

    #: ``profit_target_reached``, ``stop_loss_breached``, ``review_due``,
    #: ``no_exit_rules`` or ``position_too_large`` - the user's own rule that fired.
    reason: str
    #: Ordering hint: ``act_now`` for a crossed exit rule, ``decide_soon``
    #: otherwise. Not a severity score.
    urgency: str
    headline: str = Field(description="One sentence naming the rule and the number that met it.")
    what_you_said: str | None = Field(
        default=None,
        description="The rule as the user wrote it, quoted back to them.",
    )
    profit_target_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    last_reviewed_at: datetime | None = None


class SellReviewRead(ReadSchema):
    """Everything needing a sell-side decision, most urgent first."""

    items: list[SellReviewItem]
    holdings_count: int
    as_of: datetime
    price_delay_minutes: int | None = None
    data_is_synthetic: bool
    disclaimer: str = Field(
        default=(
            "These are the exit rules you set for yourself, checked against the latest "
            "stored price. The app does not decide whether to sell - it tells you when a "
            "line you drew has been crossed."
        )
    )


class PortfolioValuePoint(ReadSchema):
    """Portfolio cost and market value on one date."""

    on_date: date
    invested: Decimal = Field(description="Cost basis of shares held on this date.")
    market_value: Decimal
    profit: Decimal = Field(description="``market_value - invested`` on this date.")
    profit_pct: Decimal | None = None


class PortfolioHistoryRead(ReadSchema):
    """Invested-versus-value over time, for the profit/loss chart.

    Replayed from the trade ledger against stored closes, so it is a
    reconstruction rather than a stored series - consistent with the rule that
    nothing derived is persisted (ARCHITECTURE §5).
    """

    points: list[PortfolioValuePoint]
    total_invested: Decimal
    total_market_value: Decimal
    total_profit: Decimal
    total_profit_pct: Decimal | None = None
    realised_profit: Decimal = Field(description="Profit already banked on shares sold.")
    first_trade_on: date | None = None
    as_of: datetime
    note: str = Field(
        default=(
            "Reconstructed from your trade ledger and stored closing prices. Days with no "
            "stored close carry the previous close forward."
        )
    )
