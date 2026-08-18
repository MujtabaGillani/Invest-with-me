"""Technical readings and their interpretation (guide section 4).

The guide's framing is carried through this module deliberately: these readings
help with *timing*, not with *what to own*, and a bearish reading on a
fundamentally sound company held for years matters far less than the same reading
on a short-term trade.

So nothing here returns an action. Every reading is a descriptive state plus a
sentence explaining what that state does and does not tell you, and
:func:`build_technical_report` attaches a horizon note tailored to the user's own
declared time horizon when one is known.
"""

from __future__ import annotations

from itertools import pairwise

from app.analysis.indicators import (
    percent_change_over,
    relative_strength_index,
    simple_moving_average,
)
from app.analysis.inputs import TechnicalsInput
from app.analysis.rules import DEFAULT_TECHNICAL_RULES, TechnicalRules
from app.core.enums import (
    MovingAveragePosition,
    RsiZone,
    TimeHorizon,
    TrendDirection,
    VolumeConfirmation,
)
from app.core.numeric import mean, round_or_none
from app.schemas.analysis import IndicatorReading, TechnicalReport


def classify_trend(
    closes: tuple[float, ...], rules: TechnicalRules = DEFAULT_TECHNICAL_RULES
) -> tuple[TrendDirection, float | None]:
    """Classify the trend over the lookback window.

    Uses the net percentage move across the window with a flat dead band: without
    one, a chart that wandered 0.4% higher over three months would be reported as
    an "uptrend", which is noise dressed up as a finding.

    :returns: ``(direction, net change in percent)``.
    """
    change = percent_change_over(closes, rules.trend_lookback_sessions)
    if change is None:
        return TrendDirection.UNKNOWN, None
    if change > rules.trend_flat_band_pct:
        return TrendDirection.UPTREND, change
    if change < -rules.trend_flat_band_pct:
        return TrendDirection.DOWNTREND, change
    return TrendDirection.SIDEWAYS, change


def classify_rsi(rsi: float | None, rules: TechnicalRules = DEFAULT_TECHNICAL_RULES) -> RsiZone:
    """Map an RSI value onto the guide's oversold / neutral / overbought bands."""
    if rsi is None:
        return RsiZone.UNKNOWN
    if rsi < rules.rsi_oversold:
        return RsiZone.OVERSOLD
    if rsi > rules.rsi_overbought:
        return RsiZone.OVERBOUGHT
    return RsiZone.NEUTRAL


def classify_moving_averages(
    last_close: float, short_ma: float | None, long_ma: float | None
) -> MovingAveragePosition:
    """Where price sits relative to the 50-day and 200-day averages.

    ``UNKNOWN`` when either average is unavailable, rather than judging on the
    one that exists: "above both" and "above the only one we could calculate"
    are different statements, and only the first is what the guide describes.
    """
    if short_ma is None or long_ma is None:
        return MovingAveragePosition.UNKNOWN
    if last_close > short_ma and last_close > long_ma:
        return MovingAveragePosition.ABOVE_BOTH
    if last_close < short_ma and last_close < long_ma:
        return MovingAveragePosition.BELOW_BOTH
    return MovingAveragePosition.MIXED


def classify_volume(
    latest_volume: int,
    average_volume: float | None,
    latest_move_pct: float | None,
    rules: TechnicalRules = DEFAULT_TECHNICAL_RULES,
) -> VolumeConfirmation:
    """Decide whether the latest price move was backed by volume.

    ``UNKNOWN`` is returned when the latest session barely moved: confirming a
    0.1% drift tells the user nothing, and labelling it "unconfirmed" would imply
    a judgement that was never made.
    """
    if average_volume is None or average_volume <= 0 or latest_move_pct is None:
        return VolumeConfirmation.UNKNOWN
    if abs(latest_move_pct) < rules.volume_material_move_pct:
        return VolumeConfirmation.UNKNOWN
    if latest_volume >= average_volume * rules.volume_spike_multiple:
        return VolumeConfirmation.CONFIRMED
    return VolumeConfirmation.UNCONFIRMED


def _horizon_note(horizon: TimeHorizon | None) -> str:
    """Frame the readings against the user's own declared holding period.

    This is the guide's most practically useful point about technicals, and it is
    personalised rather than generic: the same RSI reading genuinely warrants a
    different amount of attention from a five-year holder than from a trader.
    """
    base = (
        "Technical readings help with timing, not with what to own. Treat them as context "
        "alongside the fundamentals, never as a signal on their own."
    )
    if horizon is TimeHorizon.LONG_TERM:
        return (
            base + " You have recorded a long-term (3-5+ year) horizon, so a bearish reading "
            "here matters far less than a change in the company's fundamentals."
        )
    if horizon is TimeHorizon.SHORT_TERM:
        return (
            base + " You have recorded a short-term horizon, where timing carries more weight - "
            "but short-term trading is a different skill from investing, with different risks."
        )
    if horizon is TimeHorizon.MEDIUM_TERM:
        return (
            base + " With your recorded 1-3 year horizon, use these to choose when to act on a "
            "decision the fundamentals have already justified."
        )
    return base


def build_technical_report(
    data: TechnicalsInput,
    *,
    horizon: TimeHorizon | None = None,
    rules: TechnicalRules = DEFAULT_TECHNICAL_RULES,
) -> TechnicalReport:
    """Compute every indicator for one company and interpret each in plain terms.

    :param horizon: the user's declared time horizon, used only to frame the
        result. Analysis is identical regardless of its value.
    :raises ValueError: if there are fewer than
        :attr:`~app.analysis.rules.TechnicalRules.min_sessions` sessions, or if
        the bars are not in ascending date order. Callers translate these into an
        ``InsufficientDataError`` and a 500 respectively - a mis-ordered series is
        a bug in the data layer, not a user-facing condition.
    """
    bars = data.bars
    if len(bars) < rules.min_sessions:
        raise ValueError(
            f"{data.symbol} has {len(bars)} price sessions; at least {rules.min_sessions} "
            "are needed for a technical reading."
        )

    dates = [bar.trade_date for bar in bars]
    if any(earlier >= later for earlier, later in pairwise(dates)):
        raise ValueError(
            f"Price bars for {data.symbol} must be in ascending date order with no duplicates."
        )

    closes = data.closes
    volumes = data.volumes
    last_close = closes[-1]

    # -- Trend -------------------------------------------------------------
    direction, net_change = classify_trend(closes, rules)
    sessions_in_lookback = min(rules.trend_lookback_sessions, len(closes) - 1)
    trend_reading = IndicatorReading(
        key="trend",
        label=f"Trend ({sessions_in_lookback} sessions)",
        value=round_or_none(net_change),
        unit="%",
        state=direction.value,
        what_it_measures="Whether the stock is in a clear uptrend, downtrend or sideways range.",
        commentary=_trend_commentary(direction, net_change, sessions_in_lookback, rules),
    )

    # -- RSI ---------------------------------------------------------------
    rsi_value = relative_strength_index(closes, rules.rsi_period)
    rsi_zone = classify_rsi(rsi_value, rules)
    rsi_reading = IndicatorReading(
        key="rsi",
        label=f"RSI ({rules.rsi_period})",
        value=round_or_none(rsi_value, 1),
        unit=None,
        state=rsi_zone.value,
        what_it_measures=(
            f"Momentum on a 0-100 scale. Below {rules.rsi_oversold:.0f} is often called "
            f"oversold, above {rules.rsi_overbought:.0f} overbought."
        ),
        commentary=_rsi_commentary(rsi_zone, rsi_value, rules),
    )

    # -- Moving averages ---------------------------------------------------
    short_ma = simple_moving_average(closes, rules.short_ma_period)
    long_ma = simple_moving_average(closes, rules.long_ma_period)
    ma_position = classify_moving_averages(last_close, short_ma, long_ma)
    ma_reading = IndicatorReading(
        key="moving_averages",
        label=f"{rules.short_ma_period}-day / {rules.long_ma_period}-day moving averages",
        # The headline number is the gap to the longer average, which is the more
        # meaningful of the two for judging overall trend health.
        value=round_or_none((last_close - long_ma) / long_ma * 100.0) if long_ma else None,
        unit="%" if long_ma else None,
        state=ma_position.value,
        what_it_measures=(
            "Whether price is holding above its medium and long-term averages. Above both "
            "indicates a healthier trend; below both, a weaker one."
        ),
        commentary=_moving_average_commentary(
            ma_position, last_close, short_ma, long_ma, len(closes), rules
        ),
    )

    # -- Volume ------------------------------------------------------------
    average_volume = mean([float(volume) for volume in volumes[-rules.volume_average_sessions :]])
    latest_move_pct = percent_change_over(closes, 1)
    volume_state = classify_volume(volumes[-1], average_volume, latest_move_pct, rules)
    volume_reading = IndicatorReading(
        key="volume",
        label=f"Volume vs {rules.volume_average_sessions}-session average",
        value=(
            round_or_none(volumes[-1] / average_volume)
            if average_volume and average_volume > 0
            else None
        ),
        unit="x",
        state=volume_state.value,
        what_it_measures=(
            "Whether the latest move carried conviction. A price move on high volume is more "
            "meaningful than the same move on low volume."
        ),
        commentary=_volume_commentary(
            volume_state, volumes[-1], average_volume, latest_move_pct, rules
        ),
    )

    return TechnicalReport(
        symbol=data.symbol,
        as_of=bars[-1].trade_date,
        sessions_analysed=len(bars),
        last_close=round(last_close, 2),
        trend=trend_reading,
        rsi=rsi_reading,
        moving_averages=ma_reading,
        volume=volume_reading,
        trend_direction=direction,
        rsi_zone=rsi_zone,
        moving_average_position=ma_position,
        volume_confirmation=volume_state,
        horizon_note=_horizon_note(horizon),
    )


# ---------------------------------------------------------------------------
# Commentary builders
#
# Kept as separate functions so the wording is reviewable in isolation and the
# classification logic above stays readable.
# ---------------------------------------------------------------------------


def _trend_commentary(
    direction: TrendDirection,
    net_change: float | None,
    sessions: int,
    rules: TechnicalRules,
) -> str:
    if direction is TrendDirection.UNKNOWN or net_change is None:
        return "Not enough price history to establish a trend."
    move = f"{net_change:+,.1f}% over the last {sessions} sessions"
    if direction is TrendDirection.UPTREND:
        return f"Price is {move}, a clear uptrend. Trends persist until they do not."
    if direction is TrendDirection.DOWNTREND:
        return (
            f"Price is {move}, a clear downtrend. Check the fundamentals for why before "
            "treating the lower price as a discount."
        )
    return (
        f"Price is {move}, inside the +/-{rules.trend_flat_band_pct:.0f}% band that counts as "
        "sideways - no directional trend to read."
    )


def _rsi_commentary(zone: RsiZone, value: float | None, rules: TechnicalRules) -> str:
    if zone is RsiZone.UNKNOWN or value is None:
        return f"Needs at least {rules.rsi_period + 1} sessions to calculate."
    if zone is RsiZone.OVERSOLD:
        return (
            f"RSI is {value:,.1f}, below {rules.rsi_oversold:.0f}. Often described as oversold "
            "and due for a bounce, but a stock in genuine decline can stay oversold for months."
        )
    if zone is RsiZone.OVERBOUGHT:
        return (
            f"RSI is {value:,.1f}, above {rules.rsi_overbought:.0f}. Often described as "
            "overbought and due for a pullback - which is not a guarantee either way."
        )
    return f"RSI is {value:,.1f}, in the neutral band. No momentum extreme to note."


def _moving_average_commentary(
    position: MovingAveragePosition,
    last_close: float,
    short_ma: float | None,
    long_ma: float | None,
    sessions: int,
    rules: TechnicalRules,
) -> str:
    if position is MovingAveragePosition.UNKNOWN:
        missing = rules.long_ma_period if long_ma is None else rules.short_ma_period
        return (
            f"Only {sessions} sessions of history are available, so the {missing}-day average "
            "cannot be calculated yet."
        )
    detail = (
        f"Price {last_close:,.2f} against a {rules.short_ma_period}-day average of "
        f"{short_ma:,.2f} and a {rules.long_ma_period}-day average of {long_ma:,.2f}."
        if short_ma is not None and long_ma is not None
        else ""
    )
    if position is MovingAveragePosition.ABOVE_BOTH:
        return f"{detail} Holding above both averages - the healthier configuration."
    if position is MovingAveragePosition.BELOW_BOTH:
        return f"{detail} Trading below both averages - the weaker configuration."
    return f"{detail} Above one average and below the other, so the trend is unresolved."


def _volume_commentary(
    state: VolumeConfirmation,
    latest_volume: int,
    average_volume: float | None,
    latest_move_pct: float | None,
    rules: TechnicalRules,
) -> str:
    if average_volume is None or average_volume <= 0:
        return "No usable volume history for comparison."
    ratio = latest_volume / average_volume
    context = (
        f"The latest session traded {latest_volume:,} shares, {ratio:,.2f}x the "
        f"{rules.volume_average_sessions}-session average"
    )
    if state is VolumeConfirmation.UNKNOWN:
        return (
            f"{context}, but price barely moved, so there is no move for volume to confirm "
            "either way."
        )
    move = f"{latest_move_pct:+,.2f}%" if latest_move_pct is not None else "the latest move"
    if state is VolumeConfirmation.CONFIRMED:
        return f"{context}. The {move} move came on heavy volume, which makes it more meaningful."
    return (
        f"{context}. The {move} move came on ordinary volume, so read less into it than the "
        "price change alone suggests."
    )
