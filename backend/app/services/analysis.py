"""Bridge between the database and the pure analysis engines.

This service does three things and nothing else:

1. Load the ORM rows an analysis needs.
2. Translate them into the plain-number value objects in
   :mod:`app.analysis.inputs`.
3. Call the engine and hand back its report.

No thresholds, no verdicts and no wording live here - those belong to
:mod:`app.analysis`. Keeping the translation separate is what lets the entire
rule set be tested without a database.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.orm import Session

from app.analysis.fundamentals import build_fundamentals_report, sector_medians
from app.analysis.indicators import percent_change_over
from app.analysis.inputs import (
    FinancialYear,
    FundamentalsInput,
    PeerStatistics,
    PriceBarInput,
    TechnicalsInput,
)
from app.analysis.rules import (
    DEFAULT_FUNDAMENTAL_RULES,
    DEFAULT_TECHNICAL_RULES,
    FundamentalRules,
    TechnicalRules,
)
from app.analysis.technicals import build_technical_report
from app.core.enums import TimeHorizon
from app.core.errors import InsufficientDataError
from app.core.logging import get_logger
from app.models.company import Company
from app.models.financials import AnnualFinancials
from app.models.price import PriceBar
from app.repositories.companies import CompanyRepository
from app.schemas.analysis import FundamentalsReport, TechnicalReport
from app.services.companies import CompanyService

logger = get_logger(__name__)


def _to_float(value: Decimal | None) -> float | None:
    """Narrow a stored ``Decimal`` to the ``float`` the engines work in."""
    return None if value is None else float(value)


def to_financial_year(row: AnnualFinancials) -> FinancialYear:
    """Translate one ORM financials row into an analysis input."""
    return FinancialYear(
        fiscal_year=row.fiscal_year,
        revenue=_to_float(row.revenue),
        net_profit=_to_float(row.net_profit),
        eps=_to_float(row.eps),
        total_assets=_to_float(row.total_assets),
        total_equity=_to_float(row.total_equity),
        total_debt=_to_float(row.total_debt),
        operating_cash_flow=_to_float(row.operating_cash_flow),
        capital_expenditure=_to_float(row.capital_expenditure),
        dividend_per_share=_to_float(row.dividend_per_share),
        shares_outstanding=_to_float(row.shares_outstanding),
    )


def to_price_bar(row: PriceBar) -> PriceBarInput:
    """Translate one ORM price bar into an analysis input."""
    return PriceBarInput(
        trade_date=row.trade_date,
        open=float(row.open),
        high=float(row.high),
        low=float(row.low),
        close=float(row.close),
        volume=row.volume,
    )


class AnalysisService:
    """Produce fundamentals and technical reports for a company."""

    def __init__(
        self,
        session: Session,
        *,
        fundamental_rules: FundamentalRules = DEFAULT_FUNDAMENTAL_RULES,
        technical_rules: TechnicalRules = DEFAULT_TECHNICAL_RULES,
    ) -> None:
        self.session = session
        self.companies = CompanyRepository(session)
        self.company_service = CompanyService(session)
        self.fundamental_rules = fundamental_rules
        self.technical_rules = technical_rules

    # -- Fundamentals ------------------------------------------------------

    def fundamentals(self, symbol: str) -> FundamentalsReport:
        """Run the fundamentals checklist for one company.

        :raises CompanyNotFoundError: unknown symbol.
        :raises InsufficientDataError: no financial history stored.
        """
        company = self.company_service.require_company(symbol)
        rows = self.companies.list_financials(
            company.id, years=self.fundamental_rules.max_years_considered
        )
        if not rows:
            raise InsufficientDataError(
                f"No financial statements are stored for {company.symbol}, so the fundamentals "
                "checklist cannot be run.",
                details={"symbol": company.symbol},
            )

        latest_bar = self.companies.latest_price_bar(company.id)
        peers = self._peer_statistics(company)

        data = FundamentalsInput(
            symbol=company.symbol,
            company_name=company.name,
            sector=company.sector,
            years=tuple(to_financial_year(row) for row in rows),
            peers=peers,
            reference_price=_to_float(latest_bar.close) if latest_bar else None,
            reference_price_date=latest_bar.trade_date if latest_bar else None,
            price_change_pct_recent=self._recent_price_change(company.id),
        )
        return build_fundamentals_report(data, self.fundamental_rules)

    def _peer_statistics(self, company: Company) -> PeerStatistics:
        """Median P/E, gearing and margin across the company's sector peers.

        The company itself is excluded from its own peer group: including it would
        pull the median towards the value being judged, which is worst exactly
        where it matters most - a small sector with an outlier in it.
        """
        peers = self.companies.list_by_sector(company.sector, exclude_id=company.id)
        if not peers:
            return PeerStatistics(sector=company.sector, peer_count=0)

        peer_ids = [peer.id for peer in peers]
        latest_financials = self.companies.latest_financials_by_company(peer_ids)
        latest_prices = self.companies.latest_price_by_company(peer_ids)

        pairs: list[tuple[FinancialYear, float | None]] = []
        for peer_id in peer_ids:
            row = latest_financials.get(peer_id)
            if row is None:
                continue
            price_bar = latest_prices.get(peer_id)
            pairs.append(
                (to_financial_year(row), _to_float(price_bar.close) if price_bar else None)
            )

        median_pe, median_gearing, median_margin = sector_medians(pairs)
        return PeerStatistics(
            sector=company.sector,
            # Counts peers with usable figures, not peers that merely exist -
            # the "enough peers for a median" rule depends on this being honest.
            peer_count=len(pairs),
            median_pe=median_pe,
            median_debt_to_equity=median_gearing,
            median_net_margin_pct=median_margin,
        )

    def _recent_price_change(self, company_id: int) -> float | None:
        """Percentage price move over the falling-knife lookback window."""
        lookback = self.fundamental_rules.falling_knife_lookback_sessions
        # One extra bar: a change across N sessions needs N+1 observations.
        bars = self.companies.list_price_bars(company_id, sessions=lookback + 1)
        if len(bars) < 2:
            return None
        return percent_change_over([float(bar.close) for bar in bars], lookback)

    # -- Technicals --------------------------------------------------------

    def technicals(self, symbol: str, *, horizon: TimeHorizon | None = None) -> TechnicalReport:
        """Compute technical readings for one company.

        :param horizon: the user's declared time horizon. Only affects the framing
            note in the response.
        :raises InsufficientDataError: fewer than the minimum required sessions.
        """
        company = self.company_service.require_company(symbol)
        # Requesting the long moving-average period plus a margin keeps the query
        # bounded while still supplying everything the indicators need.
        wanted = self.technical_rules.long_ma_period + self.technical_rules.rsi_period + 20
        bars = self.companies.list_price_bars(company.id, sessions=wanted)

        if len(bars) < self.technical_rules.min_sessions:
            raise InsufficientDataError(
                f"{company.symbol} has {len(bars)} stored price sessions; at least "
                f"{self.technical_rules.min_sessions} are needed for a technical reading.",
                details={
                    "symbol": company.symbol,
                    "sessions_available": len(bars),
                    "sessions_required": self.technical_rules.min_sessions,
                },
            )

        data = TechnicalsInput(symbol=company.symbol, bars=tuple(to_price_bar(bar) for bar in bars))
        return build_technical_report(data, horizon=horizon, rules=self.technical_rules)

    # -- Convenience -------------------------------------------------------

    def try_fundamentals(self, symbol: str) -> FundamentalsReport | None:
        """Fundamentals report, or ``None`` when the data will not support one.

        Used by the alert monitor, which sweeps every holding and must not abort
        the whole run because one company has no filings loaded.
        """
        try:
            return self.fundamentals(symbol)
        except InsufficientDataError:
            logger.debug("Skipping fundamentals for %s: insufficient data.", symbol)
            return None

    def bulk_fundamentals(self, symbols: Sequence[str]) -> dict[str, FundamentalsReport]:
        """Fundamentals for several companies, silently skipping unusable ones."""
        reports: dict[str, FundamentalsReport] = {}
        for symbol in symbols:
            report = self.try_fundamentals(symbol)
            if report is not None:
                reports[symbol.upper()] = report
        return reports
