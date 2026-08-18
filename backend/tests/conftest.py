"""Shared test fixtures.

Isolation strategy: one in-memory SQLite database per test, created and dropped
around each test function. That is not the fastest possible approach - a nested
transaction rolled back per test would avoid the DDL - but the services under test
commit deliberately, and a savepoint-based scheme would quietly swallow those
commits and stop the tests from exercising the real transaction boundaries.

Determinism: the market data provider is pinned to a fixed ``as_of`` date, so
prices, indicator values and therefore assertions are stable regardless of when
the suite runs.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_market_data_provider
from app.core.config import Environment, Settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.user import User
from app.providers.seeded import SeededMarketDataProvider
from app.repositories.users import UserRepository
from app.services.market_data import MarketDataSyncService

#: Pinned so generated prices - and every assertion about them - are reproducible.
FIXED_AS_OF = date(2025, 6, 30)
FIXED_LATEST_FISCAL_YEAR = 2024

#: Price sessions loaded per company. Enough for the 200-day moving average plus
#: the margin the analysis service requests, and no more - every extra session is
#: an insert repeated 24 times in every test that touches market data.
MARKET_DATA_SESSIONS = 240

TEST_USER_EMAIL = "test-investor@example.com"


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Test settings: in-memory database, no startup seeding."""
    return Settings(
        environment=Environment.LOCAL,
        debug=True,
        database_url="sqlite+pysqlite:///:memory:",
        auto_migrate=False,
        seed_on_startup=False,
        default_user_email=TEST_USER_EMAIL,
        default_user_name="Test Investor",
        log_level="WARNING",
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A fresh in-memory database for one test.

    ``StaticPool`` plus ``check_same_thread=False`` is required: an in-memory
    SQLite database lives inside a single connection, so without a pool that hands
    out the same connection every time, the request thread would open an empty
    second database and every test would fail on a missing table.
    """
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    # Same pragma the application sets - without it SQLite ignores foreign keys,
    # and cascade behaviour would differ between tests and production.
    @event.listens_for(test_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Session factory bound to the test engine."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session for tests that exercise services directly, without HTTP."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def provider() -> SeededMarketDataProvider:
    """Deterministic market data provider."""
    return SeededMarketDataProvider(as_of=FIXED_AS_OF, latest_fiscal_year=FIXED_LATEST_FISCAL_YEAR)


@pytest.fixture
def market_data(
    db_session: Session, provider: SeededMarketDataProvider
) -> SeededMarketDataProvider:
    """Load the full demo market dataset into the test database.

    Requested explicitly by tests that need companies, prices or financials, so
    that tests which do not (most unit-adjacent service tests) stay fast.
    """
    MarketDataSyncService(db_session, provider).sync_all(sessions=MARKET_DATA_SESSIONS)
    db_session.commit()
    return provider


@pytest.fixture
def user(db_session: Session) -> User:
    """The test account."""
    account = UserRepository(db_session).get_or_create(TEST_USER_EMAIL, "Test Investor")
    db_session.commit()
    return account


@pytest.fixture
def app(
    settings: Settings,
    session_factory: sessionmaker[Session],
    provider: SeededMarketDataProvider,
) -> FastAPI:
    """Application wired to the test database and the pinned provider."""
    application = create_app(settings)

    def override_get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_session] = override_get_session
    application.dependency_overrides[get_market_data_provider] = lambda: provider
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """HTTP client.

    Deliberately **not** entered as a context manager: doing so would run the
    application lifespan, which builds its own provider and (in another
    configuration) seeds the real database. Tests set up exactly what they need.

    ``raise_server_exceptions=False`` lets the application's own 500 handler run,
    so the error-envelope contract can be asserted instead of the exception being
    re-raised into the test.
    """
    test_client = TestClient(app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        test_client.close()


@pytest.fixture
def seeded_client(client: TestClient, market_data: SeededMarketDataProvider) -> TestClient:
    """HTTP client with market data already loaded."""
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def api() -> str:
    """The versioned API prefix, so tests do not hard-code it repeatedly."""
    return "/api/v1"


def money(value: str) -> Decimal:
    """Build a ``Decimal`` from a string literal.

    Always from a string, never a float: ``Decimal(0.1)`` is not 0.1, and a test
    that asserts on money must not carry binary rounding error into the fixture.
    """
    return Decimal(value)
