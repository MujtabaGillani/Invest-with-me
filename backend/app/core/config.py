"""Application configuration.

All runtime configuration is read from environment variables (prefix ``PSX_``)
or a local ``.env`` file exactly once, at import time, and exposed through the
cached :func:`get_settings` accessor. Nothing else in the codebase should read
``os.environ`` directly - that keeps configuration testable (override the
dependency) and auditable (one place to look).
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment. Drives docs exposure and error verbosity."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


def _split_csv(value: str | list[str]) -> list[str]:
    """Accept either a real list or a comma-separated string for list settings.

    Pydantic-settings parses ``list`` fields as JSON by default, which makes
    ``PSX_CORS_ORIGINS=http://a,http://b`` fail. Docker/CI operators expect CSV,
    so we normalise it here instead of forcing JSON into env files.
    """
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CsvList = Annotated[list[str], BeforeValidator(_split_csv)]


class Settings(BaseSettings):
    """Typed, validated view of the process environment."""

    model_config = SettingsConfigDict(
        env_prefix="PSX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # -- Application ------------------------------------------------------
    app_name: str = "PSX Invest API"
    api_v1_prefix: str = "/api/v1"
    environment: Environment = Environment.LOCAL
    debug: bool = True

    # -- Persistence ------------------------------------------------------
    database_url: str = "sqlite+pysqlite:///./psx_invest.db"
    sql_echo: bool = False
    #: ``create_all`` at startup. Convenient locally, forbidden in production
    #: where Alembic owns the schema.
    auto_migrate: bool = True
    seed_on_startup: bool = True

    # -- HTTP -------------------------------------------------------------
    cors_origins: CsvList = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # -- Market data ------------------------------------------------------
    #: Key resolved through ``app.providers.registry``. Swapping this is the
    #: only change needed to move from seeded data to a live PSX feed.
    market_data_provider: str = "seeded"

    # -- Identity ---------------------------------------------------------
    #: v1 is single-user: every request is attributed to this account.
    default_user_email: str = "investor@example.com"
    default_user_name: str = "Investor"

    # -- Observability ----------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def docs_url(self) -> str | None:
        """Hide interactive docs in production."""
        return None if self.is_production else "/docs"

    @property
    def openapi_url(self) -> str | None:
        return None if self.is_production else "/openapi.json"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that every caller sees the same object. Tests clear the cache
    (``get_settings.cache_clear()``) after patching the environment.
    """
    return Settings()


__all__ = ["CsvList", "Environment", "Settings", "get_settings"]
