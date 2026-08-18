"""The market data provider seam.

Everything the application knows about the outside world arrives through
:class:`MarketDataProvider`. Services depend on this protocol, never on a
concrete implementation, so replacing the bundled illustrative dataset with a
live PSX feed, a broker API or a CSV importer is a new class plus one entry in
:mod:`app.providers.registry` - no change to any service, endpoint or test.

The record types below are plain dataclasses rather than ORM models on purpose: a
provider should not be able to touch the database, and a provider author should
not need to know the schema.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.core.enums import Sector


@dataclass(frozen=True, slots=True)
class CompanyRecord:
    """Reference data for one listed company."""

    symbol: str
    name: str
    sector: Sector
    business_summary: str | None = None
    website: str | None = None


@dataclass(frozen=True, slots=True)
class FinancialsRecord:
    """One fiscal year of reported figures, in PKR.

    ``Decimal`` throughout: these values are persisted verbatim, and a float
    round-trip through JSON would introduce differences from the published
    accounts that a user comparing the two would notice.
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


@dataclass(frozen=True, slots=True)
class PriceBarRecord:
    """One trading session."""

    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """Self-description a provider must supply.

    :param is_synthetic: ``True`` when the figures are generated rather than
        sourced from filings. This travels all the way to the UI, which refuses
        to present generated numbers as real market data. A provider that lies
        here is the single worst bug this codebase could ship.
    """

    name: str
    description: str
    is_synthetic: bool
    #: Where a user should go to verify a figure themselves - the guide's
    #: section 8 advice, made actionable.
    verification_sources: list[str] = field(default_factory=list)


@runtime_checkable
class MarketDataProvider(Protocol):
    """Read-only source of companies, financials and prices.

    Implementations must be safe to call repeatedly and must raise
    :class:`~app.core.errors.ProviderError` (not a transport-specific exception)
    for upstream failures, so callers can handle one error type.
    """

    @property
    def metadata(self) -> ProviderMetadata:
        """Describe this provider, including whether its data is synthetic."""
        ...

    def list_companies(self) -> Sequence[CompanyRecord]:
        """Every company this provider can supply data for."""
        ...

    def fetch_financials(self, symbol: str) -> Sequence[FinancialsRecord]:
        """Annual figures for ``symbol``, oldest fiscal year first.

        Returns an empty sequence for an unknown symbol rather than raising -
        "no filings available" is a normal outcome the analysis layer already
        reports honestly.
        """
        ...

    def fetch_price_history(self, symbol: str, sessions: int = 400) -> Sequence[PriceBarRecord]:
        """Up to ``sessions`` daily bars for ``symbol``, oldest first."""
        ...
