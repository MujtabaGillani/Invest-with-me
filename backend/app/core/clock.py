"""Time helpers.

Every timestamp the application creates goes through :func:`utcnow`. Two reasons:

* **Correctness.** Timezone-aware UTC everywhere means no naive/aware comparison
  errors and no ambiguity when a user in PKT reads a row written by a job in UTC.
* **Testability.** One function to patch when a test needs to control "now",
  instead of hunting for ``datetime.now()`` calls across the service layer.
"""

from __future__ import annotations

from datetime import UTC, date, datetime


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def today() -> date:
    """Current UTC date.

    UTC rather than local: PSX trades in PKT, but every stored ``trade_date``
    comes from the market data provider, so anchoring "today" to the server's
    local timezone would make behaviour depend on where the process runs.
    """
    return utcnow().date()


def as_utc(value: datetime) -> datetime:
    """Coerce a datetime to timezone-aware UTC.

    A naive value is *assumed* to be UTC rather than rejected. Client payloads
    routinely omit the offset, and refusing them would turn a harmless omission
    into a 422 the user cannot act on.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def days_between(earlier: datetime, later: datetime) -> int:
    """Whole days from ``earlier`` to ``later``, tolerating naive inputs."""
    return (as_utc(later) - as_utc(earlier)).days
