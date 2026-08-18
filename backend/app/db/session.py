"""Engine and session lifecycle.

One :class:`~sqlalchemy.engine.Engine` per process (it owns the connection
pool); one :class:`~sqlalchemy.orm.Session` per request, opened and closed by
the :func:`get_session` FastAPI dependency.

Transaction policy: the dependency does **not** commit. Services commit
explicitly at the end of a unit of work, which keeps multi-step operations
(record a trade, recompute the holding, raise an alert) atomic and makes the
commit boundary visible in the code that owns the invariant.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _sqlite_connect_args(settings: Settings) -> dict[str, Any]:
    """SQLite needs two adjustments to behave in a threaded web server."""
    if not settings.is_sqlite:
        return {}
    return {
        # Uvicorn runs sync endpoints in a threadpool, so a connection created
        # on one thread may be used on another.
        "check_same_thread": False,
        # Fail fast instead of hanging when another writer holds the lock.
        "timeout": 15,
    }


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Build the engine for the given settings.

    ``pool_pre_ping`` costs one cheap round-trip per checkout and removes the
    entire class of "server closed the connection unexpectedly" errors after an
    idle period - a worthwhile trade for a low-QPS API.
    """
    settings = settings or get_settings()
    engine = create_engine(
        settings.database_url,
        echo=settings.sql_echo,
        future=True,
        pool_pre_ping=True,
        connect_args=_sqlite_connect_args(settings),
    )

    if settings.is_sqlite:
        _enable_sqlite_pragmas(engine)
    return engine


def _enable_sqlite_pragmas(engine: Engine) -> None:
    """Turn on foreign keys and WAL for SQLite.

    SQLite ignores ``FOREIGN KEY`` clauses unless the pragma is set per
    connection - without this, cascade deletes silently do nothing locally while
    working correctly on Postgres, which is exactly the kind of drift that hides
    bugs until staging.
    """

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


# Module-level singletons. Imported lazily by the app factory and tests so that
# patched settings are picked up before the engine is built.
engine: Engine = create_db_engine()

SessionFactory: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,  # keeps ORM objects usable after commit for serialisation
    future=True,
)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session.

    Rolls back on any unhandled exception so a failed request can never leave a
    partially applied transaction behind for the next one to inherit.
    """
    session = SessionFactory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session for scripts, seeding and background jobs.

    Commits on success, rolls back on failure. Not used by the HTTP layer, which
    relies on :func:`get_session` plus explicit service-level commits.
    """
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
