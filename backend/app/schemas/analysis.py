"""Result types for the fundamentals and technicals engines.

These double as the HTTP response contract and as the analysis functions' return
types. That is a deliberate decision, recorded in ``docs/ARCHITECTURE.md``: the
analysis layer is pure computation over plain numbers, so a second set of
hand-written DTOs would only add a translation step (and a place for the two
copies to drift) without buying any isolation. SQLAlchemy is what the analysis
layer is kept away from - not Pydantic.

Every assessment carries three pieces of prose alongside its number:

``what_it_measures``  what the metric tells you (the guide's middle column)
``criteria``          what a good reading looks like (the guide's right column)
``commentary``        what *this* company's number means against that criteria

The prose is generated server-side so the explanation always matches the
thresholds that were actually applied, instead of being duplicated in the UI and
going stale the first time a threshold is tuned.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.core.enums import (
    MetricVerdict,
    MovingAveragePosition,
    RsiZone,
    Sector,
    TrendDirection,
    VolumeConfirmation,
)
from app.schemas.common import STANDARD_DISCLAIMER, Disclaimer, ReadSchema

# ===========================================================================
# Fundamentals
# ===========================================================================


class MetricAssessment(ReadSchema):
    """One row of the fundamentals checklist."""

    key: str = Field(description="Stable machine name, e.g. 'net_margin'.")
    label: str = Field(description="Display name, e.g. 'Net profit margin'.")
    verdict: MetricVerdict
    value: float | None = Field(
        default=None, description="Headline number for the metric; null when not computable."
    )
    unit: str | None = Field(
        default=None, description="Unit of `value`: '%', 'x', 'PKR' or null for a count."
    )
    peer_median: float | None = Field(
        default=None,
        description="Median of the same metric across sector peers, when a comparison was used.",
    )
    what_it_measures: str
    criteria: str
    commentary: str = Field(description="How this company reads against the criteria.")
    #: Supporting series (e.g. per-year revenue) so the UI can draw a sparkline
    #: without a second request.
    history: list[YearValue] = Field(default_factory=list)


class YearValue(ReadSchema):
    """A single fiscal-year observation used to build a metric's history."""

    fiscal_year: int
    value: float | None = None


class StatementCheck(ReadSchema):
    """One of the four plain-language questions from guide section 3."""

    key: str
    question: str
    passed: bool | None = Field(
        default=None, description="Null when the underlying figures are unavailable."
    )
    detail: str


class StatementReview(ReadSchema):
    """The four-question sanity check over the three financial statements.

    The guide's rule is quoted directly: if two or more answers are "no", that is
    worth investigating before buying. This object reports that condition; it
    does not turn it into a recommendation.
    """

    checks: list[StatementCheck]
    failed_count: int
    unknown_count: int
    needs_investigation: bool = Field(
        description="True when two or more of the four checks answered 'no'."
    )
    summary: str


class RedFlag(ReadSchema):
    """A specific, evidenced concern - not a generic warning."""

    key: str
    title: str
    detail: str
    severity: str = Field(description="'info', 'warning' or 'critical'.")


class FundamentalsScore(ReadSchema):
    """Aggregate view of the checklist.

    Exposed as counts rather than a single 0-100 grade on purpose. A composite
    score invites exactly the behaviour the guide warns against - treating one
    number as a verdict - and hides which criteria failed.
    """

    strong: int
    adequate: int
    weak: int
    insufficient_data: int
    metrics_assessed: int
    note: str = Field(
        default=(
            "Counts of how many checklist criteria this company currently meets. "
            "This is not a rating, a price target, or a buy/sell signal."
        )
    )


class FundamentalsReport(ReadSchema):
    """Full output of the fundamentals checklist for one company."""

    symbol: str
    company_name: str
    sector: Sector
    sector_label: str
    #: Fiscal years the assessment drew on, oldest first.
    fiscal_years: list[int]
    latest_fiscal_year: int
    #: Price used for the valuation metrics, and the session it came from.
    reference_price: float | None = None
    reference_price_date: date | None = None
    peer_count: int = Field(
        default=0, description="Sector peers with usable data, used for median comparisons."
    )

    metrics: list[MetricAssessment]
    statement_review: StatementReview
    red_flags: list[RedFlag]
    score: FundamentalsScore
    disclaimer: Disclaimer = STANDARD_DISCLAIMER


# ===========================================================================
# Technicals
# ===========================================================================


class IndicatorReading(ReadSchema):
    """A single technical indicator with its interpretation."""

    key: str
    label: str
    value: float | None = None
    unit: str | None = None
    state: str = Field(description="Descriptive state, e.g. 'uptrend', 'overbought'.")
    what_it_measures: str
    commentary: str


class TechnicalReport(ReadSchema):
    """Timing context for a company - explicitly not a reason to buy or sell.

    The guide is unambiguous that indicators are inputs, not verdicts, and that a
    bearish reading on a fundamentally strong stock held for years matters far
    less than the same reading on a short-term trade. :attr:`horizon_note`
    carries that framing into the payload, personalised to the user's declared
    time horizon when one is available.
    """

    symbol: str
    as_of: date
    #: Sessions of history the indicators were computed from.
    sessions_analysed: int
    last_close: float

    trend: IndicatorReading
    rsi: IndicatorReading
    moving_averages: IndicatorReading
    volume: IndicatorReading

    #: Convenience copies of the classified states for filtering and badges.
    trend_direction: TrendDirection
    rsi_zone: RsiZone
    moving_average_position: MovingAveragePosition
    volume_confirmation: VolumeConfirmation

    horizon_note: str = Field(
        default=(
            "Technical readings help with timing, not with what to own. Treat them "
            "as context alongside the fundamentals, never as a signal on their own."
        )
    )
    disclaimer: Disclaimer = STANDARD_DISCLAIMER


# Resolve the forward reference used by MetricAssessment.history.
MetricAssessment.model_rebuild()
