"""The fundamentals checklist (guide sections 2 and 3).

Each metric is assessed by its own small function so that a reviewer can read
one rule at a time, and so that a change to one criterion cannot alter another.
Every function follows the same contract:

* it takes plain numbers plus a :class:`~app.analysis.rules.FundamentalRules`
* it never raises for missing or nonsensical inputs
* it returns a :class:`~app.schemas.analysis.MetricAssessment` whose verdict is
  ``INSUFFICIENT_DATA`` when the figures cannot support a judgement

That last point is the important one. Silently scoring a company on two years of
data, or computing a P/E on a loss, produces a confident-looking number that is
worse than no number at all.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.analysis.inputs import FinancialYear, FundamentalsInput
from app.analysis.rules import DEFAULT_FUNDAMENTAL_RULES, FundamentalRules
from app.core.enums import SECTOR_LABELS, MetricVerdict
from app.core.numeric import cagr, count_positive, median, pct_change, round_or_none, safe_div
from app.schemas.analysis import (
    FundamentalsReport,
    FundamentalsScore,
    MetricAssessment,
    RedFlag,
    StatementCheck,
    StatementReview,
    YearValue,
)

# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

#: Standard "not enough history" wording, so the reason reads identically
#: wherever a metric bails out.
_NO_DATA = "Not enough reported history to judge this metric."


def _fmt(value: float | None, unit: str | None = None, digits: int = 2) -> str:
    """Format a number for inline commentary, tolerating ``None``."""
    if value is None:
        return "n/a"
    if unit == "%":
        return f"{value:,.{digits}f}%"
    if unit == "x":
        return f"{value:,.{digits}f}x"
    if unit == "PKR":
        return f"PKR {value:,.{digits}f}"
    return f"{value:,.{digits}f}"


def _history(years: Sequence[FinancialYear], attribute: str) -> list[YearValue]:
    """Build a per-year series for one attribute, for sparklines in the UI."""
    return [
        YearValue(fiscal_year=year.fiscal_year, value=round_or_none(getattr(year, attribute), 4))
        for year in years
    ]


def _insufficient(
    key: str,
    label: str,
    what_it_measures: str,
    criteria: str,
    *,
    reason: str = _NO_DATA,
    history: list[YearValue] | None = None,
) -> MetricAssessment:
    """Assemble the standard "cannot judge" assessment."""
    return MetricAssessment(
        key=key,
        label=label,
        verdict=MetricVerdict.INSUFFICIENT_DATA,
        what_it_measures=what_it_measures,
        criteria=criteria,
        commentary=reason,
        history=history or [],
    )


def _share_count_change_pct(years: Sequence[FinancialYear]) -> float | None:
    """Percentage change in share count across the reported years, if known.

    Compares the earliest and latest years that report a positive share count.
    Returns ``None`` when fewer than two do, which is the common case - most
    sources do not publish it, and the caller then falls back to judging the EPS
    series at face value.

    Uses the extremes rather than the largest single step deliberately: a split
    followed by years of stability shows up in the endpoints, and the question
    being asked is whether the *first* and *last* EPS figures are comparable.
    """
    counts = [
        year.shares_outstanding
        for year in years
        if year.shares_outstanding is not None and year.shares_outstanding > 0
    ]
    if len(counts) < 2:
        return None
    # ``pct_change(current, previous)`` - latest first, so the sign reads as
    # growth in the share count rather than a shrinkage back to the old base.
    return pct_change(counts[-1], counts[0])


# ---------------------------------------------------------------------------
# Individual metrics
# ---------------------------------------------------------------------------


def assess_revenue_growth(
    years: Sequence[FinancialYear], rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES
) -> MetricAssessment:
    """Is the business actually growing - consistently, not in one good year?

    Two things are measured, because the guide asks for both: the compound growth
    rate between the first and last year, and how many of the year-on-year steps
    were positive. A company that doubled once and shrank twice has a flattering
    CAGR and an unreliable business, so ``STRONG`` requires both a healthy rate
    and consistency.
    """
    key, label = "revenue_growth", "Revenue growth"
    what = "Whether the business is actually growing."
    criteria = (
        f"Compound growth above {rules.revenue_cagr_strong:.0f}% a year, achieved consistently "
        "across several years rather than in one good year."
    )
    history = _history(years, "revenue")

    revenues = [year.revenue for year in years if year.revenue is not None]
    if len(revenues) < rules.min_years_for_trend:
        return _insufficient(key, label, what, criteria, history=history)

    growth_rate = cagr(revenues[0], revenues[-1], len(revenues) - 1)
    yearly_changes = [
        pct_change(revenues[index], revenues[index - 1]) for index in range(1, len(revenues))
    ]
    positive_years = count_positive(yearly_changes)
    comparisons = len(yearly_changes)
    consistency = positive_years / comparisons if comparisons else 0.0

    if growth_rate is None:
        # Endpoints were zero or negative, so a compound rate is undefined even
        # though there are enough rows to work with.
        return _insufficient(
            key,
            label,
            what,
            criteria,
            reason=(
                "Reported revenue includes a zero or negative figure, so a growth rate "
                "cannot be calculated meaningfully."
            ),
            history=history,
        )

    is_consistent = consistency >= rules.revenue_consistency_ratio
    if growth_rate >= rules.revenue_cagr_strong and is_consistent:
        verdict = MetricVerdict.STRONG
    elif growth_rate >= rules.revenue_cagr_adequate and is_consistent:
        verdict = MetricVerdict.ADEQUATE
    elif growth_rate >= rules.revenue_cagr_strong:
        # Fast on average but erratic - deliberately not "strong".
        verdict = MetricVerdict.ADEQUATE
    else:
        verdict = MetricVerdict.WEAK

    return MetricAssessment(
        key=key,
        label=label,
        verdict=verdict,
        value=round_or_none(growth_rate),
        unit="%",
        what_it_measures=what,
        criteria=criteria,
        commentary=(
            f"Revenue compounded at {_fmt(growth_rate, '%')} a year across "
            f"{len(revenues)} reported years, growing in {positive_years} of {comparisons} "
            "year-on-year comparisons."
        ),
        history=history,
    )


def assess_net_margin(
    years: Sequence[FinancialYear], rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES
) -> MetricAssessment:
    """Is the company profitable, not merely growing revenue?

    The guide asks for a margin that is "positive and stable or improving", so a
    deteriorating margin is downgraded even when its absolute level still looks
    healthy - that erosion is the early signal, and it is invisible if only the
    latest number is checked.
    """
    key, label = "net_margin", "Net profit margin"
    what = "Whether the company is actually profitable, not just growing revenue."
    criteria = (
        f"Positive, at least {rules.net_margin_adequate:.0f}%, and stable or improving "
        "rather than eroding."
    )
    history = [
        YearValue(fiscal_year=year.fiscal_year, value=round_or_none(year.net_margin_pct))
        for year in years
    ]

    margins = [year.net_margin_pct for year in years if year.net_margin_pct is not None]
    if not margins:
        return _insufficient(key, label, what, criteria, history=history)

    latest = margins[-1]
    change = latest - margins[0] if len(margins) > 1 else None
    is_eroding = change is not None and change < -rules.net_margin_stability_band

    if latest <= 0:
        verdict = MetricVerdict.WEAK
    elif latest >= rules.net_margin_strong and not is_eroding:
        verdict = MetricVerdict.STRONG
    elif latest >= rules.net_margin_adequate:
        verdict = MetricVerdict.ADEQUATE
    else:
        verdict = MetricVerdict.WEAK

    if latest <= 0:
        trend_note = "The company is currently loss-making."
    elif change is None:
        trend_note = "Only one year of margin data is available, so no trend is visible yet."
    elif is_eroding:
        trend_note = f"The margin has narrowed by {abs(change):,.1f} percentage points."
    elif change > rules.net_margin_stability_band:
        trend_note = f"The margin has widened by {change:,.1f} percentage points."
    else:
        trend_note = "The margin has held broadly steady."

    return MetricAssessment(
        key=key,
        label=label,
        verdict=verdict,
        value=round_or_none(latest),
        unit="%",
        what_it_measures=what,
        criteria=criteria,
        commentary=f"Latest net margin is {_fmt(latest, '%')}. {trend_note}",
        history=history,
    )


def assess_eps_trend(
    years: Sequence[FinancialYear], rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES
) -> MetricAssessment:
    """Is profit per share growing over time?

    EPS is checked separately from net profit because a company can grow total
    profit while issuing so many new shares that each existing share earns less -
    the shareholder goes backwards while the headline improves.
    """
    key, label = "eps_trend", "Earnings per share (EPS)"
    what = "Profit attributable to each share - the basis for judging whether a price is expensive."
    criteria = "Growing over time, not just in the most recent year."
    history = _history(years, "eps")

    eps_values = [year.eps for year in years if year.eps is not None]
    if len(eps_values) < 2:
        return _insufficient(key, label, what, criteria, history=history)

    # A bonus issue or a split changes the denominator, and exchanges publish EPS
    # without restating the earlier years. Comparing across that break would call
    # a company whose profit tripled "weak", so refuse the comparison instead.
    share_change_pct = _share_count_change_pct(years)
    if (
        share_change_pct is not None
        and abs(share_change_pct) > rules.eps_share_count_change_tolerance_pct
    ):
        return _insufficient(
            key,
            label,
            what,
            criteria,
            reason=(
                f"The share count changed by about {_fmt(abs(share_change_pct), '%')} "
                f"over these years, which points to a bonus issue or a split. "
                f"Reported EPS is not restated for that, so the earlier and later "
                f"figures are calculated on different share bases and cannot be "
                f"compared. Judge profit growth from the revenue and margin checks, "
                f"and read the EPS figures below one year at a time."
            ),
            history=history,
        )

    first, latest = eps_values[0], eps_values[-1]
    steps = [eps_values[i] - eps_values[i - 1] for i in range(1, len(eps_values))]
    rising_steps = count_positive(steps)
    growth_rate = cagr(first, latest, len(eps_values) - 1)

    if latest <= 0:
        verdict = MetricVerdict.WEAK
    elif latest > first and rising_steps / len(steps) >= rules.revenue_consistency_ratio:
        verdict = MetricVerdict.STRONG
    elif latest > first:
        verdict = MetricVerdict.ADEQUATE
    else:
        verdict = MetricVerdict.WEAK

    rate_note = f" That is roughly {_fmt(growth_rate, '%')} a year." if growth_rate else ""

    return MetricAssessment(
        key=key,
        label=label,
        verdict=verdict,
        value=round_or_none(latest, 4),
        unit="PKR",
        what_it_measures=what,
        criteria=criteria,
        commentary=(
            f"EPS moved from {_fmt(first, 'PKR')} to {_fmt(latest, 'PKR')} over "
            f"{len(eps_values)} years, rising in {rising_steps} of {len(steps)} "
            f"year-on-year steps.{rate_note}"
        ),
        history=history,
    )


def assess_pe_ratio(
    latest_eps: float | None,
    reference_price: float | None,
    peer_median_pe: float | None,
    peer_count: int,
    *,
    rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES,
) -> MetricAssessment:
    """How expensive the price is relative to earnings - judged against peers.

    The guide's warning is explicit: "a low P/E in one industry can be normal in
    another". So the peer median is the primary yardstick, and the absolute bands
    are a fallback used only when the sector has too few companies with usable
    data to trust a median.

    A loss-making company has no meaningful P/E. That is reported as
    ``INSUFFICIENT_DATA`` with an explanation, never as a huge or negative
    multiple that a "cheapest first" sort would then rank at the top.
    """
    key, label = "pe_ratio", "P/E ratio (price / earnings)"
    what = "How expensive the stock is relative to the profit it earns."
    criteria = (
        "Compared against other companies in the same sector - a low P/E in one "
        "industry can be perfectly normal in another."
    )

    if reference_price is None:
        return _insufficient(
            key, label, what, criteria, reason="No recent price is available to value the shares."
        )
    if latest_eps is None:
        return _insufficient(key, label, what, criteria)
    if latest_eps <= 0:
        return _insufficient(
            key,
            label,
            what,
            criteria,
            reason=(
                "The company reported a loss in its latest year, so a P/E ratio cannot be "
                "calculated. Judge it on revenue, cash flow and debt instead."
            ),
        )

    pe = safe_div(reference_price, latest_eps)
    if pe is None:  # pragma: no cover - unreachable given the guards above
        return _insufficient(key, label, what, criteria)

    use_peers = peer_median_pe is not None and peer_count >= rules.min_peers_for_median
    if use_peers and peer_median_pe:
        if pe <= peer_median_pe * rules.pe_discount_to_peers:
            verdict = MetricVerdict.STRONG
        elif pe <= peer_median_pe * rules.pe_premium_to_peers:
            verdict = MetricVerdict.ADEQUATE
        else:
            verdict = MetricVerdict.WEAK
        relative = pe / peer_median_pe
        commentary = (
            f"Trading at {_fmt(pe, 'x')} earnings against a sector median of "
            f"{_fmt(peer_median_pe, 'x')} across {peer_count} peers - "
            f"{_fmt(relative, 'x')} the peer median. A higher multiple is not automatically "
            "bad; it means more of the company's expected growth is already in the price."
        )
        peer_value: float | None = peer_median_pe
    else:
        if pe <= rules.pe_absolute_strong:
            verdict = MetricVerdict.STRONG
        elif pe <= rules.pe_absolute_adequate:
            verdict = MetricVerdict.ADEQUATE
        else:
            verdict = MetricVerdict.WEAK
        commentary = (
            f"Trading at {_fmt(pe, 'x')} earnings. Only {peer_count} sector peers have usable "
            f"figures ({rules.min_peers_for_median} are needed for a reliable median), so this "
            "is judged against general bands - compare it against peers yourself before "
            "drawing a conclusion."
        )
        peer_value = None

    return MetricAssessment(
        key=key,
        label=label,
        verdict=verdict,
        value=round_or_none(pe),
        unit="x",
        peer_median=round_or_none(peer_value),
        what_it_measures=what,
        criteria=criteria,
        commentary=commentary,
    )


def assess_debt_to_equity(
    years: Sequence[FinancialYear],
    sector_uses_peer_comparison: bool,
    peer_median_debt_to_equity: float | None,
    peer_count: int,
    *,
    rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES,
) -> MetricAssessment:
    """How much the company relies on borrowed money.

    Absolute bands are used for ordinary companies. For banks and power producers
    - whose business models are built on leverage - only a peer comparison is
    meaningful, and if there are too few peers no verdict is issued at all. A
    bank flagged "weak" for a 9x ratio would be a bug, not a warning.
    """
    key, label = "debt_to_equity", "Debt-to-equity ratio"
    what = "How much the company relies on borrowed money rather than shareholders' funds."
    criteria = (
        "Lower is generally safer, judged against peers in the same sector; high debt means "
        "more risk if profits dip."
    )
    history = [
        YearValue(fiscal_year=year.fiscal_year, value=round_or_none(year.debt_to_equity, 3))
        for year in years
    ]

    ratios = [year.debt_to_equity for year in years if year.debt_to_equity is not None]
    if not ratios:
        negative_equity = any(
            year.total_equity is not None and year.total_equity <= 0 for year in years
        )
        reason = (
            "Shareholders' equity is zero or negative, so this ratio is not meaningful - "
            "see the red flags below."
            if negative_equity
            else _NO_DATA
        )
        return _insufficient(key, label, what, criteria, reason=reason, history=history)

    latest = ratios[-1]
    has_usable_median = (
        peer_median_debt_to_equity is not None and peer_count >= rules.min_peers_for_median
    )

    if sector_uses_peer_comparison and not has_usable_median:
        return _insufficient(
            key,
            label,
            what,
            criteria,
            reason=(
                f"Gearing is {_fmt(latest, 'x')}. This sector is structurally leveraged, so "
                "absolute thresholds do not apply, and there are too few peers with usable "
                "figures to compare against. Review this one manually."
            ),
            history=history,
        )

    # Peer comparison is preferred whenever it is available, except for a company
    # already comfortably inside the absolute "safe" band - there, being below
    # 0.5x is a stronger statement than being below a leveraged peer group.
    compare_to_peers = has_usable_median and peer_median_debt_to_equity is not None
    if compare_to_peers and peer_median_debt_to_equity is not None:
        if sector_uses_peer_comparison or latest > rules.debt_to_equity_strong:
            if latest <= peer_median_debt_to_equity * rules.debt_discount_to_peers:
                verdict = MetricVerdict.STRONG
            elif latest <= peer_median_debt_to_equity * rules.debt_premium_to_peers:
                verdict = MetricVerdict.ADEQUATE
            else:
                verdict = MetricVerdict.WEAK
            commentary = (
                f"Gearing is {_fmt(latest, 'x')} against a sector median of "
                f"{_fmt(peer_median_debt_to_equity, 'x')} across {peer_count} peers."
            )
            peer_value: float | None = peer_median_debt_to_equity
        else:
            verdict = MetricVerdict.STRONG
            commentary = (
                f"Gearing is {_fmt(latest, 'x')}, comfortably below the "
                f"{rules.debt_to_equity_strong:.1f}x level at which borrowing starts to matter."
            )
            peer_value = peer_median_debt_to_equity
    else:
        if latest <= rules.debt_to_equity_strong:
            verdict = MetricVerdict.STRONG
        elif latest <= rules.debt_to_equity_adequate:
            verdict = MetricVerdict.ADEQUATE
        else:
            verdict = MetricVerdict.WEAK
        commentary = (
            f"Gearing is {_fmt(latest, 'x')}, i.e. PKR {latest:,.2f} of borrowing for every "
            "PKR 1 of shareholders' funds."
        )
        peer_value = None

    if len(ratios) > 1 and latest != ratios[0]:
        direction = "risen" if latest > ratios[0] else "fallen"
        commentary += f" It has {direction} from {_fmt(ratios[0], 'x')} over the period shown."
    elif len(ratios) > 1:
        commentary += " It is unchanged over the period shown."

    return MetricAssessment(
        key=key,
        label=label,
        verdict=verdict,
        value=round_or_none(latest, 3),
        unit="x",
        peer_median=round_or_none(peer_value, 3),
        what_it_measures=what,
        criteria=criteria,
        commentary=commentary,
        history=history,
    )


def assess_dividends(
    years: Sequence[FinancialYear],
    reference_price: float | None,
    *,
    rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES,
) -> MetricAssessment:
    """Does the company share profit with shareholders, and reliably?

    Paying no dividend is **not** scored as weak. A company reinvesting every
    rupee into growth is following a legitimate strategy, and marking it down
    would tilt the whole checklist towards mature payers for no defensible
    reason. Such a company is reported as ``INSUFFICIENT_DATA`` with that
    explanation attached.
    """
    key, label = "dividend", "Dividend yield & history"
    what = "Whether the company shares profit with shareholders, and does so consistently."
    criteria = (
        f"A consistent or growing dividend across at least "
        f"{rules.dividend_consistency_years} years."
    )
    history = _history(years, "dividend_per_share")

    dividends = [year.dividend_per_share for year in years if year.dividend_per_share is not None]
    if not dividends:
        return _insufficient(key, label, what, criteria, history=history)

    paying_years = count_positive(dividends)
    latest = dividends[-1]

    if paying_years == 0:
        return _insufficient(
            key,
            label,
            what,
            criteria,
            reason=(
                "No dividend has been paid in the years reported. That is not a negative on "
                "its own - a company reinvesting profit into growth may be the better "
                "long-term holding - but it does mean no income while you hold it."
            ),
            history=history,
        )

    yield_pct: float | None = None
    if reference_price:
        raw_yield = safe_div(latest, reference_price)
        yield_pct = raw_yield * 100.0 if raw_yield is not None else None

    is_consistent = paying_years >= min(rules.dividend_consistency_years, len(dividends))
    is_growing = len(dividends) > 1 and latest > dividends[0]

    if latest <= 0:
        # Paid historically but nothing in the latest year - a cut is a signal.
        verdict = MetricVerdict.WEAK
    elif is_consistent and is_growing:
        verdict = MetricVerdict.STRONG
    else:
        verdict = MetricVerdict.ADEQUATE

    if latest <= 0:
        trend_note = (
            "No dividend was declared in the latest year despite payments earlier in the "
            "period - worth checking why."
        )
    elif is_growing:
        trend_note = f"It has grown from {_fmt(dividends[0], 'PKR')} per share."
    else:
        trend_note = "It has not grown over the period shown."

    yield_note = (
        f" That is a {_fmt(yield_pct, '%')} yield at the reference price." if yield_pct else ""
    )

    return MetricAssessment(
        key=key,
        label=label,
        verdict=verdict,
        value=round_or_none(yield_pct) if yield_pct is not None else round_or_none(latest, 4),
        unit="%" if yield_pct is not None else "PKR",
        what_it_measures=what,
        criteria=criteria,
        commentary=(
            f"Paid a dividend in {paying_years} of {len(dividends)} reported years; the latest "
            f"was {_fmt(latest, 'PKR')} per share.{yield_note} {trend_note}"
        ),
        history=history,
    )


def assess_free_cash_flow(
    years: Sequence[FinancialYear], rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES
) -> MetricAssessment:
    """Does the company generate real cash, not just paper profit?"""
    key, label = "free_cash_flow", "Free cash flow"
    what = "Whether the company generates real cash after funding its own capital spending."
    criteria = "Positive and stable across the years reported."
    history = [
        YearValue(fiscal_year=year.fiscal_year, value=round_or_none(year.free_cash_flow, 2))
        for year in years
    ]

    flows = [year.free_cash_flow for year in years if year.free_cash_flow is not None]
    if not flows:
        return _insufficient(key, label, what, criteria, history=history)

    positive_years = count_positive(flows)
    ratio = positive_years / len(flows)
    latest = flows[-1]

    if latest <= 0:
        verdict = MetricVerdict.WEAK
    elif ratio >= rules.fcf_positive_ratio_strong:
        verdict = MetricVerdict.STRONG
    elif ratio >= rules.fcf_positive_ratio_adequate:
        verdict = MetricVerdict.ADEQUATE
    else:
        verdict = MetricVerdict.WEAK

    if latest <= 0:
        note = (
            "The latest year consumed more cash than it generated. That can be a heavy "
            "investment year rather than a problem - check what the capital spending bought."
        )
    else:
        note = "Cash generation covered capital spending in the latest year."

    return MetricAssessment(
        key=key,
        label=label,
        verdict=verdict,
        value=round_or_none(latest, 2),
        unit="PKR",
        what_it_measures=what,
        criteria=criteria,
        commentary=(
            f"Free cash flow was positive in {positive_years} of {len(flows)} reported years. "
            f"{note}"
        ),
        history=history,
    )


# ---------------------------------------------------------------------------
# Section 3: the four-question statement review
# ---------------------------------------------------------------------------


def review_statements(years: Sequence[FinancialYear]) -> StatementReview:
    """Answer the guide's four plain-language questions.

    "Is revenue growing, is profit growing roughly in line with it, is debt under
    control, and is cash flow positive? If two or more of these are 'no', that is
    worth investigating before buying."

    Unknowns are counted separately from failures. Two missing figures are a data
    gap to fill, not two reasons for concern, and conflating them would raise a
    false alarm on every thinly-reported company.
    """
    checks: list[StatementCheck] = []

    revenues = [year.revenue for year in years if year.revenue is not None]
    profits = [year.net_profit for year in years if year.net_profit is not None]
    gearings = [year.debt_to_equity for year in years if year.debt_to_equity is not None]
    cash_flows = [
        year.operating_cash_flow for year in years if year.operating_cash_flow is not None
    ]

    # 1. Income statement - is revenue growing?
    if len(revenues) < 2:
        checks.append(
            StatementCheck(
                key="revenue_growing",
                question="Is revenue growing?",
                passed=None,
                detail="Fewer than two years of revenue are available.",
            )
        )
    else:
        revenue_change = pct_change(revenues[-1], revenues[0])
        checks.append(
            StatementCheck(
                key="revenue_growing",
                question="Is revenue growing?",
                passed=revenue_change is not None and revenue_change > 0,
                detail=(
                    f"Revenue moved from {_fmt(revenues[0])} to {_fmt(revenues[-1])}"
                    + (
                        f" ({_fmt(revenue_change, '%')} over the period)."
                        if revenue_change is not None
                        else "."
                    )
                ),
            )
        )

    # 2. Income statement - is profit keeping pace with revenue?
    if len(revenues) < 2 or len(profits) < 2:
        checks.append(
            StatementCheck(
                key="profit_tracks_revenue",
                question="Is profit growing roughly in line with revenue?",
                passed=None,
                detail="Not enough paired revenue and profit history to compare.",
            )
        )
    else:
        revenue_change = pct_change(revenues[-1], revenues[0])
        profit_change = pct_change(profits[-1], profits[0])
        if revenue_change is None or profit_change is None:
            passed: bool | None = None
            detail = "A zero or negative base figure makes the comparison meaningless."
        else:
            # "Roughly in line" is read generously: profit must simply not be
            # falling while revenue rises, and must not lag revenue growth by
            # more than half. Demanding a tighter match would flag every company
            # having one heavy-investment year.
            passed = profit_change > 0 and profit_change >= revenue_change * 0.5
            detail = (
                f"Revenue changed {_fmt(revenue_change, '%')} while net profit changed "
                f"{_fmt(profit_change, '%')} over the same period."
            )
        checks.append(
            StatementCheck(
                key="profit_tracks_revenue",
                question="Is profit growing roughly in line with revenue?",
                passed=passed,
                detail=detail,
            )
        )

    # 3. Balance sheet - is debt under control?
    if not gearings:
        negative_equity = any(
            year.total_equity is not None and year.total_equity <= 0 for year in years
        )
        checks.append(
            StatementCheck(
                key="debt_under_control",
                question="Is debt under control?",
                passed=False if negative_equity else None,
                detail=(
                    "Shareholders' equity is zero or negative."
                    if negative_equity
                    else "No usable debt or equity figures are available."
                ),
            )
        )
    else:
        latest_gearing = gearings[-1]
        rising = len(gearings) > 1 and latest_gearing > gearings[0]
        checks.append(
            StatementCheck(
                key="debt_under_control",
                question="Is debt under control?",
                # Uses the general "adequate" band rather than a sector
                # comparison: this is the coarse sanity check, and the
                # sector-aware judgement is the debt-to-equity metric above.
                passed=latest_gearing <= DEFAULT_FUNDAMENTAL_RULES.debt_to_equity_adequate,
                detail=(
                    f"Debt-to-equity is {_fmt(latest_gearing, 'x')}"
                    + (" and has risen over the period." if rising else " and has not risen.")
                ),
            )
        )

    # 4. Cash flow - is operating cash flow positive?
    if not cash_flows:
        checks.append(
            StatementCheck(
                key="cash_flow_positive",
                question="Is cash flow positive?",
                passed=None,
                detail="No operating cash flow figures are available.",
            )
        )
    else:
        positive = count_positive(cash_flows)
        checks.append(
            StatementCheck(
                key="cash_flow_positive",
                question="Is cash flow positive?",
                passed=cash_flows[-1] > 0,
                detail=(
                    f"Operating cash flow was positive in {positive} of {len(cash_flows)} "
                    f"reported years; the latest was {_fmt(cash_flows[-1])}."
                ),
            )
        )

    failed = sum(1 for check in checks if check.passed is False)
    unknown = sum(1 for check in checks if check.passed is None)
    needs_investigation = failed >= 2

    if needs_investigation:
        summary = (
            f"{failed} of the four checks answered no. The guide's rule of thumb is that two "
            "or more is worth investigating before buying."
        )
    elif failed == 1:
        summary = "One of the four checks answered no - worth understanding why before buying."
    elif unknown == len(checks):
        summary = "None of the four checks could be answered from the available data."
    else:
        summary = "All answerable checks came back positive."

    if unknown:
        summary += f" {unknown} could not be answered from the available data."

    return StatementReview(
        checks=checks,
        failed_count=failed,
        unknown_count=unknown,
        needs_investigation=needs_investigation,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Red flags
# ---------------------------------------------------------------------------


def detect_red_flags(
    data: FundamentalsInput, rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES
) -> list[RedFlag]:
    """Surface specific, evidenced concerns from the reported figures.

    Each flag names the observation that triggered it, so the user can go and
    check the filing rather than trusting a label. The headline one is the
    guide's "falling knife": a price that has dropped hard is only a bargain if
    the business behind it has not dropped with it.
    """
    flags: list[RedFlag] = []
    years = data.years
    if not years:
        return flags

    latest = years[-1]
    previous = years[-2] if len(years) > 1 else None

    # -- The falling knife -------------------------------------------------
    price_drop = data.price_change_pct_recent
    if price_drop is not None and price_drop <= -rules.falling_knife_price_drop_pct:
        deteriorating: list[str] = []
        if previous is not None:
            profit_change = pct_change(latest.net_profit, previous.net_profit)
            if profit_change is not None and profit_change < 0:
                deteriorating.append(f"net profit fell {abs(profit_change):,.1f}%")
            elif latest.net_profit is not None and latest.net_profit < 0:
                deteriorating.append("the company is loss-making")

            debt_change = pct_change(latest.total_debt, previous.total_debt)
            if debt_change is not None and debt_change >= rules.rising_debt_pct:
                deteriorating.append(f"borrowings rose {debt_change:,.1f}%")

            if (
                latest.net_margin_pct is not None
                and previous.net_margin_pct is not None
                and latest.net_margin_pct
                < previous.net_margin_pct - rules.net_margin_stability_band
            ):
                deteriorating.append("the net margin narrowed")

        if deteriorating:
            flags.append(
                RedFlag(
                    key="falling_knife",
                    title="Falling price with deteriorating fundamentals",
                    detail=(
                        f"The price is down {abs(price_drop):,.1f}% over roughly the last six "
                        f"months and, in the latest reported year, {' and '.join(deteriorating)}. "
                        "A falling price is only a discount if the business behind it is intact."
                    ),
                    severity="critical",
                )
            )
        else:
            flags.append(
                RedFlag(
                    key="price_decline_unexplained",
                    title="Price down sharply without an obvious cause in the accounts",
                    detail=(
                        f"The price is down {abs(price_drop):,.1f}% over roughly the last six "
                        "months, but the latest reported figures do not show deteriorating "
                        "profit, margin or debt. Find out what the market is pricing in - "
                        "recent announcements, sector news or a change in management - before "
                        "treating this as a discount."
                    ),
                    severity="warning",
                )
            )

    # -- Negative equity ---------------------------------------------------
    if latest.total_equity is not None and latest.total_equity <= 0:
        flags.append(
            RedFlag(
                key="negative_equity",
                title="Negative or zero shareholders' equity",
                detail=(
                    "Liabilities equal or exceed assets in the latest balance sheet. Ratios "
                    "based on equity are meaningless here, and the company depends on "
                    "continued lender support."
                ),
                severity="critical",
            )
        )

    # -- Profit without cash ----------------------------------------------
    if (
        latest.net_profit is not None
        and latest.net_profit > 0
        and latest.operating_cash_flow is not None
        and latest.operating_cash_flow < 0
    ):
        flags.append(
            RedFlag(
                key="profit_without_cash",
                title="Reported profit but negative operating cash flow",
                detail=(
                    "The latest year shows an accounting profit while the business consumed "
                    "cash from operations. The guide calls operating cash flow the most "
                    "trustworthy number in the accounts - check receivables and inventory."
                ),
                severity="warning",
            )
        )

    # -- Dividends funded from borrowing ----------------------------------
    if (
        latest.dividend_per_share is not None
        and latest.dividend_per_share > 0
        and latest.free_cash_flow is not None
        and latest.free_cash_flow < 0
    ):
        flags.append(
            RedFlag(
                key="dividend_exceeds_cash_generation",
                title="Dividend paid in a year of negative free cash flow",
                detail=(
                    "The dividend was not covered by cash the business generated after capital "
                    "spending, so it was funded from reserves or borrowing. Sustainable for a "
                    "year; not indefinitely."
                ),
                severity="warning",
            )
        )

    # -- Rising debt against falling profit -------------------------------
    if previous is not None:
        debt_change = pct_change(latest.total_debt, previous.total_debt)
        profit_change = pct_change(latest.net_profit, previous.net_profit)
        if (
            debt_change is not None
            and debt_change >= rules.rising_debt_pct
            and profit_change is not None
            and profit_change < 0
        ):
            flags.append(
                RedFlag(
                    key="debt_up_profit_down",
                    title="Borrowings rising while profit falls",
                    detail=(
                        f"Debt rose {debt_change:,.1f}% while net profit fell "
                        f"{abs(profit_change):,.1f}% in the latest year. Interest cover is "
                        "moving the wrong way on both sides."
                    ),
                    severity="critical",
                )
            )

    return flags


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _score(metrics: Sequence[MetricAssessment]) -> FundamentalsScore:
    """Count verdicts. Deliberately not a weighted composite - see the schema."""
    counts = dict.fromkeys(MetricVerdict, 0)
    for metric in metrics:
        counts[metric.verdict] += 1
    return FundamentalsScore(
        strong=counts[MetricVerdict.STRONG],
        adequate=counts[MetricVerdict.ADEQUATE],
        weak=counts[MetricVerdict.WEAK],
        insufficient_data=counts[MetricVerdict.INSUFFICIENT_DATA],
        metrics_assessed=len(metrics),
    )


def build_fundamentals_report(
    data: FundamentalsInput, rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES
) -> FundamentalsReport:
    """Run the whole checklist for one company.

    The metric order matches the table in guide section 2, so the API response
    can be rendered top-to-bottom without the frontend needing to know the
    intended sequence.

    :raises ValueError: if ``data.years`` is empty - the caller is expected to
        translate that into an ``InsufficientDataError`` for the HTTP layer,
        since "this company has no filings loaded" is a data problem, not an
        analysis outcome.
    """
    if not data.years:
        raise ValueError(f"No financial history available for {data.symbol}.")

    # Trim to the most recent window; older years describe a different company.
    years = tuple(data.years[-rules.max_years_considered :])
    latest = years[-1]

    metrics = [
        assess_revenue_growth(years, rules),
        assess_net_margin(years, rules),
        assess_eps_trend(years, rules),
        assess_pe_ratio(
            latest.eps,
            data.reference_price,
            data.peers.median_pe,
            data.peers.peer_count,
            rules=rules,
        ),
        assess_debt_to_equity(
            years,
            data.sector in rules.peer_relative_debt_sectors,
            data.peers.median_debt_to_equity,
            data.peers.peer_count,
            rules=rules,
        ),
        assess_dividends(years, data.reference_price, rules=rules),
        assess_free_cash_flow(years, rules),
    ]

    return FundamentalsReport(
        symbol=data.symbol,
        company_name=data.company_name,
        sector=data.sector,
        sector_label=SECTOR_LABELS[data.sector],
        fiscal_years=[year.fiscal_year for year in years],
        latest_fiscal_year=latest.fiscal_year,
        reference_price=round_or_none(data.reference_price),
        reference_price_date=data.reference_price_date,
        peer_count=data.peers.peer_count,
        metrics=metrics,
        statement_review=review_statements(years),
        red_flags=detect_red_flags(
            FundamentalsInput(
                symbol=data.symbol,
                company_name=data.company_name,
                sector=data.sector,
                years=years,
                peers=data.peers,
                reference_price=data.reference_price,
                reference_price_date=data.reference_price_date,
                price_change_pct_recent=data.price_change_pct_recent,
            ),
            rules,
        ),
        score=_score(metrics),
    )


def sector_medians(
    company_years: Sequence[tuple[FinancialYear, float | None]],
) -> tuple[float | None, float | None, float | None]:
    """Compute peer medians for P/E, debt-to-equity and net margin.

    :param company_years: one ``(latest financial year, latest price)`` pair per
        peer company. Companies whose figures cannot produce a given metric are
        skipped for that metric only - so a sector where two of six companies are
        loss-making still yields a usable P/E median from the other four.
    :returns: ``(median_pe, median_debt_to_equity, median_net_margin_pct)``.
    """
    pe_values: list[float] = []
    gearing_values: list[float] = []
    margin_values: list[float] = []

    for year, price in company_years:
        if price is not None and year.eps is not None and year.eps > 0:
            pe = safe_div(price, year.eps)
            if pe is not None:
                pe_values.append(pe)
        if year.debt_to_equity is not None:
            gearing_values.append(year.debt_to_equity)
        if year.net_margin_pct is not None:
            margin_values.append(year.net_margin_pct)

    return median(pe_values), median(gearing_values), median(margin_values)
