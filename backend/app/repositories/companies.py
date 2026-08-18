"""Company, financials and price queries."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import selectinload

from app.core.enums import Sector
from app.models.company import Company
from app.models.financials import AnnualFinancials
from app.models.price import PriceBar
from app.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """Reads and writes for company reference data and market history."""

    model = Company

    # -- Companies ---------------------------------------------------------

    def get_by_symbol(self, symbol: str) -> Company | None:
        """Fetch one company by ticker, case-insensitively."""
        statement = select(Company).where(Company.symbol == symbol.strip().upper())
        return self.session.scalars(statement).one_or_none()

    def _search_statement(
        self, *, search: str | None, sector: Sector | None, active_only: bool
    ) -> Select[tuple[Company]]:
        """Build the shared filter used by both the page and count queries.

        Sharing it guarantees the reported total always matches the rows returned;
        two hand-written WHERE clauses drift the first time a filter is added.
        """
        statement = select(Company)
        if active_only:
            statement = statement.where(Company.is_active.is_(True))
        if sector is not None:
            statement = statement.where(Company.sector == sector)
        if search:
            pattern = f"%{search.strip().lower()}%"
            statement = statement.where(
                func.lower(Company.symbol).like(pattern) | func.lower(Company.name).like(pattern)
            )
        return statement

    def search(
        self,
        *,
        search: str | None = None,
        sector: Sector | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Company], int]:
        """Paginated company search.

        :returns: ``(page of companies, total matching rows)``.
        """
        base = self._search_statement(search=search, sector=sector, active_only=active_only)
        total = self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        page = self.session.scalars(base.order_by(Company.symbol).limit(limit).offset(offset)).all()
        return page, total

    def list_by_sector(self, sector: Sector, *, exclude_id: int | None = None) -> Sequence[Company]:
        """Active companies in one sector - the peer group for comparisons."""
        statement = select(Company).where(Company.sector == sector, Company.is_active.is_(True))
        if exclude_id is not None:
            statement = statement.where(Company.id != exclude_id)
        return self.session.scalars(statement.order_by(Company.symbol)).all()

    def list_by_symbols(self, symbols: Sequence[str]) -> dict[str, Company]:
        """Bulk lookup keyed by upper-cased symbol.

        Used wherever a collection is being resolved (portfolio replay, watchlist
        rendering) to avoid a query per row.
        """
        if not symbols:
            return {}
        wanted = [symbol.strip().upper() for symbol in symbols]
        rows = self.session.scalars(select(Company).where(Company.symbol.in_(wanted))).all()
        return {company.symbol: company for company in rows}

    def get_many(self, company_ids: Sequence[int]) -> dict[int, Company]:
        """Bulk lookup keyed by id.

        The portfolio replay needs a company row per position; without this it
        would issue one SELECT per holding.
        """
        if not company_ids:
            return {}
        rows = self.session.scalars(select(Company).where(Company.id.in_(company_ids))).all()
        return {company.id: company for company in rows}

    def get_with_financials(self, symbol: str) -> Company | None:
        """Fetch a company with its financial history eagerly loaded.

        ``selectinload`` rather than a join: the financials are a small collection
        and a join would multiply the company row, which SQLAlchemy then has to
        de-duplicate.
        """
        statement = (
            select(Company)
            .where(Company.symbol == symbol.strip().upper())
            .options(selectinload(Company.financials))
        )
        return self.session.scalars(statement).one_or_none()

    # -- Financials --------------------------------------------------------

    def list_financials(
        self, company_id: int, *, years: int | None = None
    ) -> Sequence[AnnualFinancials]:
        """Annual figures for one company, oldest fiscal year first.

        ``years`` takes the *most recent* N. The query orders descending to use
        the index, then the result is reversed in Python - cheaper than sorting a
        full history twice in SQL.
        """
        statement = (
            select(AnnualFinancials)
            .where(AnnualFinancials.company_id == company_id)
            .order_by(AnnualFinancials.fiscal_year.desc())
        )
        if years is not None:
            statement = statement.limit(years)
        rows = list(self.session.scalars(statement).all())
        rows.reverse()
        return rows

    def latest_financials_by_company(
        self, company_ids: Sequence[int]
    ) -> dict[int, AnnualFinancials]:
        """Most recent fiscal year per company, in one query.

        Uses a correlated max(fiscal_year) subquery rather than N round trips,
        because the peer-median calculation needs this for every company in a
        sector at once.
        """
        if not company_ids:
            return {}
        latest_year = (
            select(
                AnnualFinancials.company_id.label("company_id"),
                func.max(AnnualFinancials.fiscal_year).label("fiscal_year"),
            )
            .where(AnnualFinancials.company_id.in_(company_ids))
            .group_by(AnnualFinancials.company_id)
            .subquery()
        )
        statement = select(AnnualFinancials).join(
            latest_year,
            (AnnualFinancials.company_id == latest_year.c.company_id)
            & (AnnualFinancials.fiscal_year == latest_year.c.fiscal_year),
        )
        return {row.company_id: row for row in self.session.scalars(statement).all()}

    def replace_financials(self, company_id: int, rows: Sequence[AnnualFinancials]) -> None:
        """Delete and re-insert a company's financial history.

        Restatements are common and a partial upsert would leave a mix of old and
        new figures. Wholesale replacement is unambiguous, and the volume (single
        digits of rows) makes it cheap.

        The delete is a single statement rather than a load-then-delete-each-row
        loop: there is nothing to cascade from these rows, so pulling them into
        the session first would be pure overhead.
        """
        self.session.execute(
            delete(AnnualFinancials).where(AnnualFinancials.company_id == company_id)
        )
        for row in rows:
            row.company_id = company_id
        self.session.add_all(rows)
        self.session.flush()

    # -- Prices ------------------------------------------------------------

    def list_price_bars(
        self, company_id: int, *, sessions: int | None = None
    ) -> Sequence[PriceBar]:
        """Daily bars for one company, oldest first, most recent ``sessions``."""
        statement = (
            select(PriceBar)
            .where(PriceBar.company_id == company_id)
            .order_by(PriceBar.trade_date.desc())
        )
        if sessions is not None:
            statement = statement.limit(sessions)
        rows = list(self.session.scalars(statement).all())
        rows.reverse()
        return rows

    def latest_price_bar(self, company_id: int) -> PriceBar | None:
        """Most recent stored session for one company."""
        statement = (
            select(PriceBar)
            .where(PriceBar.company_id == company_id)
            .order_by(PriceBar.trade_date.desc())
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def latest_price_by_company(self, company_ids: Sequence[int]) -> dict[int, PriceBar]:
        """Most recent bar per company, in one query.

        The portfolio view needs a price for every holding; without this it would
        issue one query per position.
        """
        if not company_ids:
            return {}
        latest_date = (
            select(
                PriceBar.company_id.label("company_id"),
                func.max(PriceBar.trade_date).label("trade_date"),
            )
            .where(PriceBar.company_id.in_(company_ids))
            .group_by(PriceBar.company_id)
            .subquery()
        )
        statement = select(PriceBar).join(
            latest_date,
            (PriceBar.company_id == latest_date.c.company_id)
            & (PriceBar.trade_date == latest_date.c.trade_date),
        )
        return {row.company_id: row for row in self.session.scalars(statement).all()}

    def count_price_bars(self, company_id: int) -> int:
        """Stored sessions for one company."""
        return (
            self.session.scalar(
                select(func.count()).select_from(PriceBar).where(PriceBar.company_id == company_id)
            )
            or 0
        )

    def companies_with_data_flags(self) -> dict[int, tuple[bool, bool]]:
        """Whether each company has financials and price history.

        Returned as one map so a list endpoint can annotate every row without a
        per-row existence check. ``{company_id: (has_financials, has_prices)}``.
        """
        # ``.tuples()`` rather than ``.all()``: it yields real ``tuple[int, int]``
        # rows, so ``dict()`` both works and type-checks. Without it the result is a
        # sequence of ``Row`` objects, which are tuple-like at runtime but not to a
        # type checker.
        financial_counts = dict(
            self.session.execute(
                select(AnnualFinancials.company_id, func.count()).group_by(
                    AnnualFinancials.company_id
                )
            )
            .tuples()
            .all()
        )
        price_counts = dict(
            self.session.execute(
                select(PriceBar.company_id, func.count()).group_by(PriceBar.company_id)
            )
            .tuples()
            .all()
        )
        company_ids = self.session.scalars(select(Company.id)).all()
        return {
            company_id: (
                financial_counts.get(company_id, 0) > 0,
                price_counts.get(company_id, 0) > 0,
            )
            for company_id in company_ids
        }

    def replace_price_history(self, company_id: int, rows: Sequence[PriceBar]) -> None:
        """Delete and re-insert a company's price history.

        Same reasoning as :meth:`replace_financials`, and additionally: providers
        adjust historical closes for bonus issues and splits, so yesterday's
        stored series can legitimately differ from today's.

        Volume matters here - a full market refresh replaces hundreds of bars per
        company - so the delete is one statement and the insert goes through
        ``add_all``, which lets SQLAlchemy batch it.
        """
        self.session.execute(delete(PriceBar).where(PriceBar.company_id == company_id))
        for row in rows:
            row.company_id = company_id
        self.session.add_all(rows)
        self.session.flush()
