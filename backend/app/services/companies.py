"""Company browsing and raw market data reads."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.enums import SECTOR_LABELS, Sector
from app.core.errors import CompanyNotFoundError
from app.models.company import Company
from app.repositories.companies import CompanyRepository
from app.schemas.common import Page
from app.schemas.company import (
    AnnualFinancialsRead,
    CompanyDetail,
    CompanySummary,
    PriceBarRead,
    PriceHistoryRead,
)


class CompanyService:
    """Read-side operations over company reference and market data."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.companies = CompanyRepository(session)

    # -- Lookup ------------------------------------------------------------

    def require_company(self, symbol: str) -> Company:
        """Fetch a company or raise the API-mapped not-found error.

        Every service that starts from a symbol goes through here, so the error
        message and status code are identical across the whole API.
        """
        company = self.companies.get_by_symbol(symbol)
        if company is None:
            raise CompanyNotFoundError(symbol.strip().upper())
        return company

    # -- Listing -----------------------------------------------------------

    def list_companies(
        self,
        *,
        search: str | None = None,
        sector: Sector | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[CompanySummary]:
        """Paginated, searchable company list annotated with data availability."""
        rows, total = self.companies.search(
            search=search, sector=sector, limit=limit, offset=offset
        )
        flags = self.companies.companies_with_data_flags()
        latest_prices = self.companies.latest_price_by_company([row.id for row in rows])

        items: list[CompanySummary] = []
        for company in rows:
            has_financials, has_prices = flags.get(company.id, (False, False))
            price_bar = latest_prices.get(company.id)
            items.append(
                CompanySummary(
                    id=company.id,
                    symbol=company.symbol,
                    name=company.name,
                    sector=company.sector,
                    sector_label=SECTOR_LABELS[company.sector],
                    is_active=company.is_active,
                    last_close=price_bar.close if price_bar else None,
                    last_close_date=price_bar.trade_date if price_bar else None,
                    has_financials=has_financials,
                    has_price_history=has_prices,
                )
            )
        return Page[CompanySummary](items=items, total=total, limit=limit, offset=offset)

    def get_company_detail(self, symbol: str) -> CompanyDetail:
        """One company with its stored financial statements."""
        company = self.require_company(symbol)
        financials = self.companies.list_financials(company.id)
        price_bar = self.companies.latest_price_bar(company.id)
        has_prices = self.companies.count_price_bars(company.id) > 0

        return CompanyDetail(
            id=company.id,
            symbol=company.symbol,
            name=company.name,
            sector=company.sector,
            sector_label=SECTOR_LABELS[company.sector],
            is_active=company.is_active,
            business_summary=company.business_summary,
            website=company.website,
            last_close=price_bar.close if price_bar else None,
            last_close_date=price_bar.trade_date if price_bar else None,
            has_financials=bool(financials),
            has_price_history=has_prices,
            fiscal_years=[row.fiscal_year for row in financials],
            financials=[AnnualFinancialsRead.model_validate(row) for row in financials],
        )

    def get_price_history(self, symbol: str, *, sessions: int = 260) -> PriceHistoryRead:
        """A company's stored daily bars, oldest first."""
        company = self.require_company(symbol)
        bars = self.companies.list_price_bars(company.id, sessions=sessions)
        return PriceHistoryRead(
            symbol=company.symbol,
            sessions=len(bars),
            bars=[PriceBarRead.model_validate(bar) for bar in bars],
        )
