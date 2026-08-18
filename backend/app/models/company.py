"""Listed company reference data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Sector
from app.db.base import Base, TickerSymbol, TimestampMixin, enum_column

if TYPE_CHECKING:  # pragma: no cover
    from app.models.financials import AnnualFinancials
    from app.models.price import PriceBar


class Company(Base, TimestampMixin):
    """A company listed on the Pakistan Stock Exchange.

    Reference data only - nothing user-specific and nothing derived. Ratios such
    as P/E are computed on read from :class:`AnnualFinancials` and the latest
    :class:`PriceBar` rather than stored, because a cached ratio silently goes
    stale the moment either input changes and there is no cheap way to tell.
    """

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: PSX ticker, always stored upper-case (normalised in the service layer).
    symbol: Mapped[TickerSymbol] = mapped_column(unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[Sector] = mapped_column(enum_column(Sector), index=True)
    #: One or two sentences on what the business does - directly supports
    #: pre-buy question 1, "do I understand how it makes money?".
    business_summary: Mapped[str | None] = mapped_column(Text())
    website: Mapped[str | None] = mapped_column(String(255))
    #: De-listed or suspended tickers are retained so historic trades still join.
    is_active: Mapped[bool] = mapped_column(default=True)

    financials: Mapped[list[AnnualFinancials]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="AnnualFinancials.fiscal_year",
    )
    price_bars: Mapped[list[PriceBar]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="PriceBar.trade_date",
    )
