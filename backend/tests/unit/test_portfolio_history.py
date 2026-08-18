"""Unit tests for the profit/loss series.

The behaviours worth pinning are the ones a reader of the chart would be misled by
if they broke: that the last point agrees with the portfolio screen, that non-trading
days carry the previous close rather than dropping out or reading as zero, and that
selling reduces invested capital proportionally instead of leaving a phantom cost.

Uses a real SQLite session, because the thing under test is a walk over rows in
execution order and a fake would be reimplementing the query it depends on.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.enums import Sector, TradeSide
from app.models.company import Company
from app.models.price import PriceBar
from app.models.trade import Trade
from app.models.user import User
from app.services.portfolio_history import PortfolioHistoryService

# ``user`` comes from tests/conftest.py - no need for a second one.


@pytest.fixture
def company(db_session: Session) -> Company:
    row = Company(symbol="TEST", name="Test Limited", sector=Sector.CEMENT)
    db_session.add(row)
    db_session.flush()
    return row


def add_bars(db_session: Session, company: Company, start: date, closes: list[str | None]) -> None:
    """One bar per calendar day; ``None`` skips a day, as a holiday would."""
    for offset, close in enumerate(closes):
        if close is None:
            continue
        price = Decimal(close)
        db_session.add(
            PriceBar(
                company_id=company.id,
                trade_date=start + timedelta(days=offset),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1000,
            )
        )
    db_session.flush()


def add_trade(
    db_session: Session,
    user: User,
    company: Company,
    *,
    side: TradeSide,
    quantity: str,
    price: str,
    on: date,
    fees: str = "0",
) -> None:
    db_session.add(
        Trade(
            user_id=user.id,
            company_id=company.id,
            side=side,
            quantity=Decimal(quantity),
            price=Decimal(price),
            fees=Decimal(fees),
            executed_at=datetime.combine(on, datetime.min.time()),
        )
    )
    db_session.flush()


def test_no_trades_yields_an_empty_series(db_session: Session, user: User) -> None:
    """A new account is not an error state, and must not be a divide by zero."""
    result = PortfolioHistoryService(db_session).history(user.id)
    assert result.points == []
    assert result.total_invested == Decimal(0)
    assert result.total_profit == Decimal(0)
    assert result.first_trade_on is None


def test_series_starts_at_the_first_trade(
    db_session: Session, user: User, company: Company
) -> None:
    start = date(2026, 1, 1)
    add_bars(db_session, company, start, ["100", "110", "120"])
    add_trade(db_session, user, company, side=TradeSide.BUY, quantity="10", price="100", on=start)

    result = PortfolioHistoryService(db_session).history(user.id)
    assert result.first_trade_on == start
    assert result.points[0].on_date == start


def test_tracks_invested_and_value_day_by_day(
    db_session: Session, user: User, company: Company
) -> None:
    start = date(2026, 1, 1)
    add_bars(db_session, company, start, ["100", "110", "120"])
    add_trade(db_session, user, company, side=TradeSide.BUY, quantity="10", price="100", on=start)

    points = PortfolioHistoryService(db_session).history(user.id).points
    assert [p.market_value for p in points] == [
        Decimal("1000.00"),
        Decimal("1100.00"),
        Decimal("1200.00"),
    ]
    assert all(p.invested == Decimal("1000.00") for p in points)
    assert [p.profit for p in points] == [
        Decimal("0.00"),
        Decimal("100.00"),
        Decimal("200.00"),
    ]


def test_fees_are_part_of_what_you_invested(
    db_session: Session, user: User, company: Company
) -> None:
    """Cost basis includes the fee, so day one shows a small loss - as it should."""
    start = date(2026, 1, 1)
    add_bars(db_session, company, start, ["100"])
    add_trade(
        db_session,
        user,
        company,
        side=TradeSide.BUY,
        quantity="10",
        price="100",
        on=start,
        fees="50",
    )

    point = PortfolioHistoryService(db_session).history(user.id).points[0]
    assert point.invested == Decimal("1050.00")
    assert point.profit == Decimal("-50.00")


def test_a_non_trading_day_carries_the_previous_close(
    db_session: Session, user: User, company: Company
) -> None:
    """A weekend must not read as the holding becoming worthless."""
    start = date(2026, 1, 1)
    add_bars(db_session, company, start, ["100", None, None, "130"])
    add_trade(db_session, user, company, side=TradeSide.BUY, quantity="10", price="100", on=start)

    values = [p.market_value for p in PortfolioHistoryService(db_session).history(user.id).points]
    assert values == [
        Decimal("1000.00"),
        Decimal("1000.00"),  # held at the last known close
        Decimal("1000.00"),
        Decimal("1300.00"),
    ]


def test_a_holding_with_no_stored_price_falls_back_to_cost(
    db_session: Session, user: User, company: Company
) -> None:
    """Never report a real position as worth nothing because a bar is missing."""
    start = date(2026, 1, 1)
    add_bars(db_session, company, start, [None, "120"])
    add_trade(db_session, user, company, side=TradeSide.BUY, quantity="10", price="100", on=start)

    points = PortfolioHistoryService(db_session).history(user.id).points
    assert points[0].market_value == Decimal("1000.00"), "cost basis, not zero"
    assert points[0].profit == Decimal("0.00")


def test_selling_reduces_invested_proportionally(
    db_session: Session, user: User, company: Company
) -> None:
    start = date(2026, 1, 1)
    add_bars(db_session, company, start, ["100", "150", "150"])
    add_trade(db_session, user, company, side=TradeSide.BUY, quantity="10", price="100", on=start)
    add_trade(
        db_session,
        user,
        company,
        side=TradeSide.SELL,
        quantity="5",
        price="150",
        on=start + timedelta(days=1),
    )

    points = PortfolioHistoryService(db_session).history(user.id).points
    assert points[0].invested == Decimal("1000.00")
    # Half the shares gone, so half the cost basis goes with them.
    assert points[1].invested == Decimal("500.00")
    assert points[1].market_value == Decimal("750.00")


def test_closing_a_position_banks_the_profit_and_clears_the_cost(
    db_session: Session, user: User, company: Company
) -> None:
    start = date(2026, 1, 1)
    add_bars(db_session, company, start, ["100", "150"])
    add_trade(db_session, user, company, side=TradeSide.BUY, quantity="10", price="100", on=start)
    add_trade(
        db_session,
        user,
        company,
        side=TradeSide.SELL,
        quantity="10",
        price="150",
        on=start + timedelta(days=1),
    )

    result = PortfolioHistoryService(db_session).history(user.id)
    assert result.realised_profit == Decimal("500.00")
    final = result.points[-1]
    assert final.invested == Decimal("0.00")
    assert final.market_value == Decimal("0.00")
    assert final.profit_pct is None, "percent of nothing invested is undefined, not 0%"


def test_oversell_is_clamped_rather_than_blanking_the_chart(
    db_session: Session, user: User, company: Company
) -> None:
    """A bad ledger row must not take the whole screen down with it."""
    start = date(2026, 1, 1)
    add_bars(db_session, company, start, ["100", "100"])
    add_trade(db_session, user, company, side=TradeSide.BUY, quantity="10", price="100", on=start)
    add_trade(
        db_session,
        user,
        company,
        side=TradeSide.SELL,
        quantity="999",
        price="100",
        on=start + timedelta(days=1),
    )

    result = PortfolioHistoryService(db_session).history(user.id)
    assert result.points, "still produced a series"
    assert result.points[-1].invested == Decimal("0.00")


def test_final_point_matches_the_portfolio_screen(
    db_session: Session, user: User, company: Company
) -> None:
    """The two screens must not give different answers to "how much have I invested".

    This is the agreement the module docstring promises. If it ever fails, one of
    the two replays has drifted and both screens are suspect.
    """
    from app.services.portfolio import PortfolioService

    start = date(2026, 1, 1)
    add_bars(db_session, company, start, ["100", "110", "125"])
    add_trade(
        db_session,
        user,
        company,
        side=TradeSide.BUY,
        quantity="10",
        price="100",
        on=start,
        fees="25",
    )
    add_trade(
        db_session,
        user,
        company,
        side=TradeSide.BUY,
        quantity="5",
        price="110",
        on=start + timedelta(days=1),
    )

    history_final = PortfolioHistoryService(db_session).history(user.id).points[-1]
    summary = PortfolioService(db_session).get_portfolio(user.id).summary

    assert history_final.invested == summary.total_cost_basis
    assert history_final.market_value == summary.total_market_value
    assert history_final.profit == summary.total_unrealised_pl
