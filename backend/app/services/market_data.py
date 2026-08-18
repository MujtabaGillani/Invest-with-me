"""Loading market data from a provider into the local database.

This is the only place a provider's output is written to the schema. Everything
else in the application reads from the database, which means the analysis layer
behaves identically whether the data came from the bundled demo set, a live feed
or a CSV import.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.company import Company
from app.models.financials import AnnualFinancials
from app.models.price import PriceBar
from app.providers.base import MarketDataProvider
from app.repositories.companies import CompanyRepository

logger = get_logger(__name__)

#: Sessions requested per company. 320 covers the 200-day moving average with
#: enough margin that a few missing days do not break it.
DEFAULT_SESSIONS = 320


@dataclass(slots=True)
class SyncReport:
    """What a sync actually did - returned to the caller and logged."""

    companies_created: int = 0
    companies_updated: int = 0
    financial_years_written: int = 0
    price_bars_written: int = 0
    symbols_skipped: list[str] = field(default_factory=list)

    @property
    def companies_touched(self) -> int:
        return self.companies_created + self.companies_updated


class MarketDataSyncService:
    """Pull provider data into the database.

    :param session: unit of work. This service **does not commit** - the caller
        (startup routine, admin endpoint or CLI) decides the transaction
        boundary, so a partially completed sync can be rolled back as a whole.
    """

    def __init__(self, session: Session, provider: MarketDataProvider) -> None:
        self.session = session
        self.provider = provider
        self.companies = CompanyRepository(session)

    def sync_all(
        self, *, sessions: int = DEFAULT_SESSIONS, skip_existing: bool = False
    ) -> SyncReport:
        """Load every company the provider knows about.

        :param skip_existing: when true, companies that already have both
            financials and price history are left alone. Used by startup seeding
            so a restart is fast and non-destructive; a deliberate refresh passes
            ``False`` to pick up restatements and adjusted prices.
        """
        report = SyncReport()
        existing_flags = self.companies.companies_with_data_flags() if skip_existing else {}

        for record in self.provider.list_companies():
            company = self.companies.get_by_symbol(record.symbol)
            if company is None:
                company = self.companies.add(
                    Company(
                        symbol=record.symbol.upper(),
                        name=record.name,
                        sector=record.sector,
                        business_summary=record.business_summary,
                        website=record.website,
                    )
                )
                report.companies_created += 1
            else:
                # Reference data can change (a rename, a sector reclassification).
                company.name = record.name
                company.sector = record.sector
                company.business_summary = record.business_summary
                company.website = record.website
                report.companies_updated += 1

            has_financials, has_prices = existing_flags.get(company.id, (False, False))
            if skip_existing and has_financials and has_prices:
                report.symbols_skipped.append(company.symbol)
                continue

            report.financial_years_written += self._sync_financials(company)
            report.price_bars_written += self._sync_prices(company, sessions)

        logger.info(
            "Market data sync complete: %s companies (%s new), %s fiscal years, %s price bars, "
            "%s skipped.",
            report.companies_touched,
            report.companies_created,
            report.financial_years_written,
            report.price_bars_written,
            len(report.symbols_skipped),
        )
        return report

    def sync_symbol(self, symbol: str, *, sessions: int = DEFAULT_SESSIONS) -> SyncReport:
        """Refresh one company. Creates it if the provider knows it and we do not."""
        report = SyncReport()
        symbol = symbol.strip().upper()

        record = next(
            (item for item in self.provider.list_companies() if item.symbol.upper() == symbol),
            None,
        )
        if record is None:
            report.symbols_skipped.append(symbol)
            return report

        company = self.companies.get_by_symbol(symbol)
        if company is None:
            company = self.companies.add(
                Company(
                    symbol=symbol,
                    name=record.name,
                    sector=record.sector,
                    business_summary=record.business_summary,
                    website=record.website,
                )
            )
            report.companies_created += 1
        else:
            report.companies_updated += 1

        report.financial_years_written += self._sync_financials(company)
        report.price_bars_written += self._sync_prices(company, sessions)
        return report

    # -- Internals ---------------------------------------------------------

    def _sync_financials(self, company: Company) -> int:
        """Replace a company's financial history from the provider."""
        records = self.provider.fetch_financials(company.symbol)
        if not records:
            return 0
        rows = [
            AnnualFinancials(
                company_id=company.id,
                fiscal_year=record.fiscal_year,
                revenue=record.revenue,
                net_profit=record.net_profit,
                eps=record.eps,
                total_assets=record.total_assets,
                total_equity=record.total_equity,
                total_debt=record.total_debt,
                operating_cash_flow=record.operating_cash_flow,
                capital_expenditure=record.capital_expenditure,
                dividend_per_share=record.dividend_per_share,
                shares_outstanding=record.shares_outstanding,
                source=record.source,
            )
            for record in records
        ]
        self.companies.replace_financials(company.id, rows)
        return len(rows)

    def _sync_prices(self, company: Company, sessions: int) -> int:
        """Replace a company's price history from the provider."""
        records = self.provider.fetch_price_history(company.symbol, sessions=sessions)
        if not records:
            return 0
        rows = [
            PriceBar(
                company_id=company.id,
                trade_date=record.trade_date,
                open=record.open,
                high=record.high,
                low=record.low,
                close=record.close,
                volume=record.volume,
            )
            for record in records
        ]
        self.companies.replace_price_history(company.id, rows)
        return len(rows)
