"""Daily price history (OHLCV bars).

The technical module needs at least 200 sessions to evaluate a 200-day moving
average, so this table is the largest in the schema; the composite index on
``(company_id, trade_date)`` is what keeps "latest N bars for one symbol" a
single index range scan.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Money, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.company import Company


class PriceBar(Base, TimestampMixin):
    """One trading session's open/high/low/close and traded volume."""

    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint("company_id", "trade_date", name="company_trade_date"),
        # Rules out transposed or corrupt rows at the storage layer, where a
        # bad bar would otherwise poison every downstream indicator.
        CheckConstraint("high >= low", name="high_ge_low"),
        CheckConstraint("volume >= 0", name="volume_non_negative"),
        Index("ix_price_bars_company_date", "company_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    trade_date: Mapped[date]

    open: Mapped[Money]
    high: Mapped[Money]
    low: Mapped[Money]
    #: Closing price - the series every indicator is calculated from.
    close: Mapped[Money]
    #: Shares traded. ``BigInteger`` because an active PSX session can exceed the
    #: 2.1bn ceiling of a 32-bit column. Zero is legitimate (a halted session).
    volume: Mapped[int] = mapped_column(BigInteger)

    company: Mapped[Company] = relationship(back_populates="price_bars")
