"""Database bootstrap: schema, default user, market data and demo portfolio.

Called from the application lifespan when ``PSX_SEED_ON_STARTUP`` is set, and
usable directly as a script:

.. code-block:: shell

    python -m app.db.seed              # idempotent top-up
    python -m app.db.seed --reset      # drop everything and rebuild

Every step is idempotent. Restarting the server must not duplicate the demo
portfolio or reset a profile the developer edited by hand.
"""

from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import Settings, get_settings
from app.core.enums import RiskTolerance, TimeHorizon, TradePlanStatus, TradeSide
from app.core.logging import configure_logging, get_logger
from app.db.base import Base
from app.db.session import engine, session_scope
from app.models.investor_profile import InvestorProfile
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.providers.registry import build_provider
from app.repositories.companies import CompanyRepository
from app.repositories.users import UserRepository
from app.services.market_data import MarketDataSyncService

logger = get_logger(__name__)


def create_schema() -> None:
    """Create any missing tables.

    Development convenience only. In a deployed environment Alembic owns the
    schema - see ``alembic/`` and the note in ``docs/ARCHITECTURE.md``. Running
    both is safe (``create_all`` skips existing tables) but the migration is the
    authority.
    """
    Base.metadata.create_all(bind=engine)
    logger.info("Schema ensured (%s tables).", len(Base.metadata.tables))


def drop_schema() -> None:
    """Drop every table. Used by ``--reset``; never called at startup."""
    Base.metadata.drop_all(bind=engine)
    logger.warning("All tables dropped.")


def ensure_default_user(session: Session, settings: Settings) -> User:
    """Create the single v1 account if it does not exist."""
    users = UserRepository(session)
    user = users.get_or_create(settings.default_user_email, settings.default_user_name)
    return user


def ensure_market_data(session: Session, *, skip_existing: bool = True) -> None:
    """Load companies, statements and prices from the configured provider."""
    provider = build_provider()
    report = MarketDataSyncService(session, provider).sync_all(skip_existing=skip_existing)
    if provider.metadata.is_synthetic:
        logger.warning(
            "Loaded %s companies of SYNTHETIC market data from provider '%s'. "
            "These figures are generated for demonstration and must not be used for real "
            "investment decisions.",
            report.companies_touched,
            provider.metadata.name,
        )


def ensure_demo_profile(session: Session, user: User) -> None:
    """Give the demo user a plausible starting profile.

    Skipped entirely if a profile already exists, so a developer's own edits
    survive a restart.
    """
    if user.profile is not None:
        return

    session.add(
        InvestorProfile(
            user_id=user.id,
            time_horizon=TimeHorizon.LONG_TERM,
            risk_tolerance=RiskTolerance.MODERATE,
            drawdown_tolerance_pct=Decimal("30"),
            investable_capital=Decimal("1500000"),
            max_position_pct=Decimal("15"),
            max_sector_pct=Decimal("35"),
            emergency_fund_in_place=True,
            investing_borrowed_money=False,
            review_interval_days=90,
            goals_note=(
                "Demonstration profile. Long-term holdings funded from savings I will not need "
                "for at least five years; no borrowed money."
            ),
        )
    )
    session.flush()
    logger.info("Created demo investor profile.")


def ensure_demo_portfolio(session: Session, user: User) -> None:
    """Create a small demo portfolio, watchlist and plans.

    Deliberately shaped to exercise the interesting paths rather than to look
    tidy:

    * **LUCK** - a healthy holding with a complete, executed plan.
    * **DGKC** - a holding whose plan exists but whose fundamentals now trigger
      the falling-knife red flag, so the alert monitor has something real to find.
    * **HBL** - a holding with **no** plan at all, which raises the
      "no exit rules recorded" alert.
    * **MEBL** - a committed plan that has not been acted on yet.
    * **SYS** - a draft plan with an incomplete checklist, so the readiness
      blocking reasons are visible in the UI immediately.
    """
    if user.trades:
        return  # already seeded

    companies = CompanyRepository(session)
    now = utcnow()

    def company_id(symbol: str) -> int | None:
        company = companies.get_by_symbol(symbol)
        return company.id if company else None

    # -- Executed plan + holding: the happy path ---------------------------
    luck_id = company_id("LUCK")
    if luck_id is not None:
        luck_plan = TradePlan(
            user_id=user.id,
            company_id=luck_id,
            status=TradePlanStatus.EXECUTED,
            understands_business=True,
            revenue_and_profit_healthy=True,
            debt_manageable_vs_peers=True,
            comfortable_with_drawdown=True,
            position_size_appropriate=True,
            thesis=(
                "Market-leading cement producer with the strongest margins in the sector and low "
                "gearing. Buying for exposure to domestic construction over five years."
            ),
            invalidation_note=(
                "Sell if net margin falls below 10% for two consecutive years, or if gearing "
                "rises above 0.6x to fund an acquisition outside cement."
            ),
            intended_amount=Decimal("180000"),
            profit_target_pct=Decimal("25"),
            stop_loss_pct=Decimal("15"),
            committed_at=now - timedelta(days=140),
            # Deliberately older than the 90-day review interval so the
            # THESIS_REVIEW_DUE alert has something to fire on.
            last_reviewed_at=now - timedelta(days=120),
        )
        session.add(luck_plan)
        session.flush()
        session.add(
            Trade(
                user_id=user.id,
                company_id=luck_id,
                plan_id=luck_plan.id,
                side=TradeSide.BUY,
                quantity=Decimal("250"),
                price=Decimal("690.00"),
                fees=Decimal("450.00"),
                executed_at=now - timedelta(days=138),
                note="Initial position, sized inside the 15% single-holding limit.",
            )
        )

    # -- Holding whose fundamentals have deteriorated ----------------------
    dgkc_id = company_id("DGKC")
    if dgkc_id is not None:
        dgkc_plan = TradePlan(
            user_id=user.id,
            company_id=dgkc_id,
            status=TradePlanStatus.EXECUTED,
            understands_business=True,
            revenue_and_profit_healthy=True,
            debt_manageable_vs_peers=True,
            comfortable_with_drawdown=True,
            position_size_appropriate=True,
            thesis=(
                "Bought expecting a cement demand recovery to lift utilisation and repair "
                "margins after the expansion."
            ),
            invalidation_note="Exit if borrowings keep rising while profit falls.",
            intended_amount=Decimal("120000"),
            profit_target_pct=Decimal("30"),
            stop_loss_pct=Decimal("15"),
            committed_at=now - timedelta(days=200),
            last_reviewed_at=now - timedelta(days=30),
        )
        session.add(dgkc_plan)
        session.flush()
        session.add(
            Trade(
                user_id=user.id,
                company_id=dgkc_id,
                plan_id=dgkc_plan.id,
                side=TradeSide.BUY,
                quantity=Decimal("900"),
                price=Decimal("128.50"),
                fees=Decimal("320.00"),
                executed_at=now - timedelta(days=198),
                note="Recovery play - thesis now under pressure.",
            )
        )

    # -- Holding with no plan at all ---------------------------------------
    hbl_id = company_id("HBL")
    if hbl_id is not None:
        session.add(
            Trade(
                user_id=user.id,
                company_id=hbl_id,
                side=TradeSide.BUY,
                quantity=Decimal("700"),
                price=Decimal("98.20"),
                fees=Decimal("280.00"),
                executed_at=now - timedelta(days=260),
                note="Back-filled from an old broker statement - bought before using this tool.",
            )
        )

    # -- Committed but not yet acted on ------------------------------------
    mebl_id = company_id("MEBL")
    if mebl_id is not None:
        session.add(
            TradePlan(
                user_id=user.id,
                company_id=mebl_id,
                status=TradePlanStatus.READY,
                understands_business=True,
                revenue_and_profit_healthy=True,
                debt_manageable_vs_peers=True,
                comfortable_with_drawdown=True,
                position_size_appropriate=True,
                thesis=(
                    "Largest Islamic bank with the fastest deposit growth in the sector and a "
                    "low-cost funding base. Waiting for a pullback before buying."
                ),
                invalidation_note=(
                    "Abandon if deposit growth stalls below 15% a year or if the cost-to-income "
                    "ratio deteriorates two years running."
                ),
                intended_amount=Decimal("150000"),
                profit_target_pct=Decimal("25"),
                stop_loss_pct=Decimal("15"),
                committed_at=now - timedelta(days=6),
                last_reviewed_at=now - timedelta(days=6),
            )
        )

    # -- Incomplete draft --------------------------------------------------
    sys_id = company_id("SYS")
    if sys_id is not None:
        session.add(
            TradePlan(
                user_id=user.id,
                company_id=sys_id,
                status=TradePlanStatus.DRAFT,
                understands_business=True,
                revenue_and_profit_healthy=True,
                # Left unanswered on purpose: the readiness panel should show
                # exactly what is still missing.
                debt_manageable_vs_peers=None,
                comfortable_with_drawdown=None,
                position_size_appropriate=None,
                thesis="Export-billing IT services company - still working through the numbers.",
                intended_amount=Decimal("100000"),
            )
        )

    # -- Watchlist ---------------------------------------------------------
    for symbol, note, target in (
        (
            "FFC",
            "Stable urea margins and a long dividend record. Want a better entry price before "
            "buying for income.",
            Decimal("135.00"),
        ),
        (
            "OGDC",
            "Cheap on earnings but exposed to circular debt and receivables. Need to understand "
            "the cash conversion before committing.",
            Decimal("200.00"),
        ),
        (
            "INDU",
            "Strong balance sheet, but volumes swing with import policy. Watching how the next "
            "two quarters land.",
            None,
        ),
    ):
        watch_id = company_id(symbol)
        if watch_id is None:
            continue
        session.add(
            WatchlistItem(
                user_id=user.id,
                company_id=watch_id,
                research_note=note,
                target_entry_price=target,
            )
        )

    session.flush()
    logger.info("Created demo portfolio, plans and watchlist.")


def seed(*, reset: bool = False, include_demo_data: bool = True) -> None:
    """Run the full bootstrap.

    :param reset: drop every table first. Destructive; never used at startup.
    :param include_demo_data: also create the demo profile, portfolio and
        watchlist. Turned off by tests, which build their own fixtures.
    """
    if reset:
        drop_schema()
    create_schema()

    settings = get_settings()
    with session_scope() as session:
        user = ensure_default_user(session, settings)
        ensure_market_data(session, skip_existing=not reset)
        if include_demo_data:
            ensure_demo_profile(session, user)
            ensure_demo_portfolio(session, user)


def main() -> None:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description="Bootstrap the PSX Invest database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all tables before seeding. Destructive - development only.",
    )
    parser.add_argument(
        "--no-demo-data",
        action="store_true",
        help="Load market data only; skip the demo profile, portfolio and watchlist.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    seed(reset=args.reset, include_demo_data=not args.no_demo_data)
    logger.info("Seeding complete.")


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
