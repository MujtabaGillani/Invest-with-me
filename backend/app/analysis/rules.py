"""Thresholds that turn the guide's qualitative advice into checks.

The source guide says things like "consistent growth over several years" and
"lower is generally safer". Software needs numbers. Every number below is a
**stated, reviewable judgement call**, not a fact about markets - which is
exactly why they live in one annotated module instead of being scattered as
magic numbers through the calculations.

Two rules for anyone changing a value here:

1. Update the rationale comment as well. A threshold with no reasoning is
   indistinguishable from a typo six months later.
2. Check ``tests/unit/test_fundamentals.py`` - several tests pin the boundary
   behaviour deliberately, so a failing test after a tweak may be correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.enums import Sector


@dataclass(frozen=True, slots=True)
class FundamentalRules:
    """Tunable criteria for the fundamentals checklist."""

    # -- History requirements ---------------------------------------------
    #: The guide asks for a trend "over the last 3+ years"; two years is a
    #: single comparison, which is noise rather than a trend.
    min_years_for_trend: int = 3
    #: Years of history considered. Older data describes a different company.
    max_years_considered: int = 5

    # -- Revenue growth (%, compound annual) ------------------------------
    #: Roughly the level at which a business is outgrowing typical Pakistani
    #: nominal GDP growth, i.e. genuinely expanding rather than drifting with
    #: inflation.
    revenue_cagr_strong: float = 12.0
    #: Below this, revenue is flat-to-shrinking in real terms.
    revenue_cagr_adequate: float = 4.0
    #: Share of year-on-year comparisons that must be positive before growth is
    #: called "consistent". 2 of 3, or 3 of 4.
    revenue_consistency_ratio: float = 0.66

    # -- EPS comparability ------------------------------------------------
    #: Change in share count (%) beyond which an EPS series is treated as not
    #: comparable across years.
    #:
    #: PSX publishes EPS **as reported** and does not restate it after a bonus
    #: issue or a split, both of which are common in Pakistan. Lucky Cement's
    #: filings show EPS of 43.06 for FY2023 against 18.91 for FY2024 while net
    #: profit doubled, because the share count went from roughly 319 million to
    #: 1.49 billion. Comparing those two figures answers no useful question.
    #:
    #: 25% is set well above ordinary dilution from an employee scheme or a small
    #: placement - which does not invalidate the comparison - and well below the
    #: step change a bonus issue or split produces. When it trips, the metric
    #: reports insufficient data with the reason, rather than "weak": a business
    #: whose profit tripled must never be scored as deteriorating because of an
    #: accounting convention.
    eps_share_count_change_tolerance_pct: float = 25.0

    # -- Net margin (%) ---------------------------------------------------
    #: A double-digit net margin indicates real pricing power.
    net_margin_strong: float = 10.0
    #: Below this, a modest cost shock wipes out profitability entirely.
    net_margin_adequate: float = 3.0
    #: Margin change (percentage points) within which the margin counts as
    #: "stable" rather than deteriorating - the guide accepts stable *or*
    #: improving.
    net_margin_stability_band: float = 1.5

    # -- Valuation --------------------------------------------------------
    #: P/E is judged against sector peers, per the guide's explicit warning that
    #: a low P/E in one industry is normal in another. Cheap = at or below this
    #: multiple of the peer median.
    pe_discount_to_peers: float = 0.85
    #: Above this multiple of the peer median the stock is expensive *relative to
    #: its own sector*, whatever the absolute number looks like.
    pe_premium_to_peers: float = 1.25
    #: Peers needed before a median is trustworthy enough to judge against.
    #: With fewer, the metric is reported without a verdict rather than compared
    #: to one or two arbitrary companies.
    min_peers_for_median: int = 3
    #: Absolute fallback bands, used only when the sector has too few peers.
    pe_absolute_strong: float = 8.0
    pe_absolute_adequate: float = 18.0

    # -- Debt-to-equity (x) -----------------------------------------------
    #: Absolute bands for a non-financial company: below 0.5x, debt is a
    #: rounding error on the balance sheet.
    debt_to_equity_strong: float = 0.5
    #: Above ~1.5x, a downturn in profits threatens interest cover.
    debt_to_equity_adequate: float = 1.5
    #: Sectors whose business model makes absolute gearing bands meaningless.
    #: Banks fund themselves with deposits, so a 10x "debt"-to-equity ratio is
    #: normal and healthy; power generation carries structural project debt.
    #: For these, only the peer-relative comparison is used - and if there are
    #: too few peers, no verdict is issued at all.
    peer_relative_debt_sectors: frozenset[Sector] = field(
        default_factory=lambda: frozenset({Sector.COMMERCIAL_BANKS, Sector.POWER_GENERATION})
    )
    debt_discount_to_peers: float = 0.85
    debt_premium_to_peers: float = 1.25

    # -- Dividends --------------------------------------------------------
    #: Consecutive paying years that count as a "consistent" record.
    dividend_consistency_years: int = 3

    # -- Free cash flow ---------------------------------------------------
    #: Share of years that must show positive free cash flow to be "stable".
    fcf_positive_ratio_strong: float = 0.99  # effectively "every year"
    fcf_positive_ratio_adequate: float = 0.5

    # -- Red flags --------------------------------------------------------
    #: Price decline (%) over the falling-knife lookback that triggers the
    #: "check why it fell" investigation described in guide section 2.
    falling_knife_price_drop_pct: float = 20.0
    #: Sessions in that lookback - about six months of trading.
    falling_knife_lookback_sessions: int = 125
    #: Debt increase (%) year on year that counts as "rising debt".
    rising_debt_pct: float = 25.0


@dataclass(frozen=True, slots=True)
class TechnicalRules:
    """Tunable criteria for the technical indicators."""

    #: Wilder's default period, and the one the 30/70 bands are calibrated for.
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    #: The two moving averages named in the guide.
    short_ma_period: int = 50
    long_ma_period: int = 200

    #: Lookback for trend classification - "the last few months".
    trend_lookback_sessions: int = 60
    #: Net move (%) over the lookback below which the trend is called sideways
    #: rather than up or down. Without a dead band, every noisy chart reads as
    #: trending in one direction or the other.
    trend_flat_band_pct: float = 3.0

    #: Window for the average volume a session is compared against.
    volume_average_sessions: int = 20
    #: Multiple of that average which makes a move "high volume", and therefore
    #: more meaningful per the guide.
    volume_spike_multiple: float = 1.5
    #: Price move (%) small enough to be noise; volume confirmation of a
    #: non-move is not a useful statement.
    volume_material_move_pct: float = 0.5

    #: Minimum sessions before any indicator is attempted. Below this even an
    #: RSI is unstable, and a 50-day average does not exist.
    min_sessions: int = 30


DEFAULT_FUNDAMENTAL_RULES = FundamentalRules()
DEFAULT_TECHNICAL_RULES = TechnicalRules()
