"""Technical indicator maths.

Separated from :mod:`app.analysis.technicals` so the formulas can be tested
against known values without any of the interpretation or wording around them.
Each function takes a plain sequence of closes or volumes, oldest first, and
returns ``None`` when the series is too short - never a partially-warmed value,
which would be indistinguishable from a real reading.
"""

from __future__ import annotations

from collections.abc import Sequence


def simple_moving_average(values: Sequence[float], period: int) -> float | None:
    """Mean of the most recent ``period`` observations.

    Returns ``None`` when fewer than ``period`` observations exist. A 200-day
    average computed from 150 days is not a 200-day average, and reporting one
    would quietly mislabel a young listing as being "below its 200-day".
    """
    if period <= 0 or len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def relative_strength_index(closes: Sequence[float], period: int = 14) -> float | None:
    """Wilder's RSI over ``period`` sessions.

    Implemented with Wilder's smoothing (the original, and what charting
    platforms show by default) rather than a plain rolling mean of gains and
    losses: a simple mean produces visibly different numbers, so the 30/70 bands
    the guide quotes would not line up with what the user sees on their broker's
    chart.

    Needs ``period + 1`` closes to produce the first value. Returns ``None``
    below that, and ``100.0`` in the degenerate case of no down sessions at all.
    """
    if period <= 0 or len(closes) < period + 1:
        return None

    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]

    # Seed with the simple average of the first `period` changes, as Wilder did.
    gains = [max(change, 0.0) for change in changes[:period]]
    losses = [abs(min(change, 0.0)) for change in changes[:period]]
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    # Then smooth across every remaining change.
    for change in changes[period:]:
        gain = max(change, 0.0)
        loss = abs(min(change, 0.0))
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period

    if average_loss == 0:
        # No downside at all over the smoothed window - RSI is defined as 100.
        return 100.0

    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def percent_change_over(values: Sequence[float], sessions: int) -> float | None:
    """Percentage change across the last ``sessions`` observations.

    ``sessions`` is a *span*, so ``sessions=60`` compares the latest value with
    the one 60 observations earlier and needs 61 observations. When the series is
    shorter, the full available span is used instead of returning ``None`` - a
    company with 40 sessions of history still has a measurable recent move, and
    the caller reports how many sessions were actually used.
    """
    if len(values) < 2:
        return None
    span = min(sessions, len(values) - 1)
    start = values[-(span + 1)]
    if start <= 0:
        return None
    return (values[-1] - start) / start * 100.0
