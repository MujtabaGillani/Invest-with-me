"""Annual financial statement figures.

One row per company per fiscal year, holding the raw line items the guide's
checklist needs from all three statements:

* income statement - revenue, net profit, EPS
* balance sheet    - total equity, total debt
* cash flow        - operating cash flow, capital expenditure

Only *reported* figures are stored. Everything the checklist actually shows
(net margin, growth rates, free cash flow, P/E, debt-to-equity) is derived in
:mod:`app.analysis.fundamentals`. Keeping raw inputs and derived opinions apart
means a change to a threshold or formula needs no data backfill, and the numbers
in the database always match the company's published accounts.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Money, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.company import Company


class AnnualFinancials(Base, TimestampMixin):
    """Reported full-year figures for one company, in PKR."""

    __tablename__ = "annual_financials"
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_year", name="company_fiscal_year"),
        # A year outside this window is a data-entry error, not a real filing.
        CheckConstraint("fiscal_year BETWEEN 1990 AND 2100", name="fiscal_year_range"),
        Index("ix_annual_financials_company_year", "company_id", "fiscal_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    #: Fiscal year the figures belong to (the year the period *ends*).
    fiscal_year: Mapped[int]

    # -- Income statement -------------------------------------------------
    revenue: Mapped[Money | None]
    net_profit: Mapped[Money | None]
    #: Basic earnings per share as reported. Not recomputed from
    #: ``net_profit / shares_outstanding``: the reported figure is weighted over
    #: the year and accounts for bonus issues, so recomputing it would disagree
    #: with the annual report the user is reading alongside this screen.
    eps: Mapped[Money | None]

    # -- Balance sheet ----------------------------------------------------
    total_assets: Mapped[Money | None]
    total_equity: Mapped[Money | None]
    #: Interest-bearing debt (short + long term), excluding trade payables.
    total_debt: Mapped[Money | None]

    # -- Cash flow --------------------------------------------------------
    #: The guide calls this the most trustworthy number in the accounts.
    operating_cash_flow: Mapped[Money | None]
    #: Stored as a positive magnitude; free cash flow subtracts it.
    capital_expenditure: Mapped[Money | None]

    # -- Shareholder returns ----------------------------------------------
    dividend_per_share: Mapped[Money | None]
    shares_outstanding: Mapped[Money | None]

    #: Provenance, e.g. "Annual Report FY2024" - so a user can verify a figure.
    source: Mapped[str | None] = mapped_column(String(200))

    company: Mapped[Company] = relationship(back_populates="financials")

    @property
    def free_cash_flow(self) -> Decimal | None:
        """Operating cash flow less capital expenditure.

        Convenience for callers holding an ORM row; the reporting path uses
        :func:`app.analysis.fundamentals.assess_free_cash_flow`, which also
        judges stability across years.
        """
        if self.operating_cash_flow is None:
            return None
        capex = self.capital_expenditure or Decimal(0)
        return self.operating_cash_flow - capex
