"""Input value objects for the analysis engines.

Plain frozen dataclasses of ``float`` and ``date`` - no ORM rows. The engines
therefore have no idea a database exists, which is what makes their tests read
like arithmetic instead of like integration tests. Translation from ORM rows to
these objects happens once, in :mod:`app.services.analysis_service`.

``Decimal`` is converted to ``float`` at this boundary and nowhere else. That is
safe because everything downstream is a ratio or percentage that gets rounded
for display; money arithmetic (cost basis, realised P/L) stays in ``Decimal``
inside the portfolio service and never passes through here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.enums import Sector


@dataclass(frozen=True, slots=True)
class FinancialYear:
    """One fiscal year of reported figures, in PKR."""

    fiscal_year: int
    revenue: float | None = None
    net_profit: float | None = None
    eps: float | None = None
    total_assets: float | None = None
    total_equity: float | None = None
    total_debt: float | None = None
    operating_cash_flow: float | None = None
    capital_expenditure: float | None = None
    dividend_per_share: float | None = None
    shares_outstanding: float | None = None

    @property
    def free_cash_flow(self) -> float | None:
        """Operating cash flow less capital expenditure.

        Capex is stored as a positive magnitude, so it is subtracted. A missing
        capex figure is treated as zero rather than making free cash flow
        unknown: operating cash flow alone is still the more informative half of
        the calculation, and the guide's test is simply "is it positive".
        """
        if self.operating_cash_flow is None:
            return None
        return self.operating_cash_flow - (self.capital_expenditure or 0.0)

    @property
    def net_margin_pct(self) -> float | None:
        """Net profit as a percentage of revenue."""
        if self.net_profit is None or not self.revenue:
            return None
        return self.net_profit / self.revenue * 100.0

    @property
    def debt_to_equity(self) -> float | None:
        """Interest-bearing debt divided by shareholders' equity.

        Returns ``None`` when equity is zero or negative: the ratio is not
        meaningful there, and negative equity is reported as its own red flag
        rather than as a misleadingly small number.
        """
        if self.total_debt is None or self.total_equity is None or self.total_equity <= 0:
            return None
        return self.total_debt / self.total_equity


@dataclass(frozen=True, slots=True)
class PeerStatistics:
    """Sector aggregates a company is compared against.

    Medians are computed by the caller across *other* companies in the same
    sector, because the guide insists valuation and gearing only mean something
    relative to peers.
    """

    sector: Sector
    peer_count: int = 0
    median_pe: float | None = None
    median_debt_to_equity: float | None = None
    median_net_margin_pct: float | None = None


@dataclass(frozen=True, slots=True)
class FundamentalsInput:
    """Everything the fundamentals checklist needs for one company."""

    symbol: str
    company_name: str
    sector: Sector
    #: Oldest fiscal year first. The engine relies on this ordering.
    years: tuple[FinancialYear, ...]
    peers: PeerStatistics
    #: Latest close, used for P/E and dividend yield.
    reference_price: float | None = None
    reference_price_date: date | None = None
    #: Price change (%) over the falling-knife lookback window, when enough
    #: price history exists. Supplied by the caller so this module stays free of
    #: price-series handling.
    price_change_pct_recent: float | None = None


@dataclass(frozen=True, slots=True)
class PriceBarInput:
    """One trading session, as the technical engine sees it."""

    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True, slots=True)
class TechnicalsInput:
    """A price series for one company.

    :param bars: Oldest session first, gap-free enough to be treated as
        consecutive trading days. Ordering is the caller's responsibility and is
        asserted by the engine before any indicator is computed.
    """

    symbol: str
    bars: tuple[PriceBarInput, ...]

    @property
    def closes(self) -> tuple[float, ...]:
        return tuple(bar.close for bar in self.bars)

    @property
    def volumes(self) -> tuple[int, ...]:
        return tuple(bar.volume for bar in self.bars)
