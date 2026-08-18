"""Settings parsing.

These exist because of a bug that reached the repository: ``PSX_CORS_ORIGINS`` is
documented in ``.env.example`` as comma-separated, the README tells the reader to
``cp .env.example .env``, and doing exactly that crashed the application at startup.

The cause was that pydantic-settings JSON-decodes complex field types (``list[str]``)
*before* validators run, so the CSV value raised ``SettingsError`` and the parsing
validator was never reached. No test fed that field from a file or an environment
variable - every test used the in-code default, which bypasses the source entirely.

So the tests below deliberately drive settings the way a real deployment does: from
environment variables and from a ``.env`` file on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Environment, Settings, get_settings

pytestmark = pytest.mark.unit


class TestDefaults:
    def test_boots_with_no_configuration_at_all(self, tmp_path: Path) -> None:
        """Every setting has a working default, so an absent .env still runs."""
        settings = Settings(_env_file=None)

        assert settings.environment is Environment.LOCAL
        assert settings.is_sqlite is True
        assert settings.cors_origins == [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]

    def test_docs_are_exposed_outside_production(self) -> None:
        settings = Settings(_env_file=None, environment=Environment.LOCAL)
        assert settings.docs_url == "/docs"
        assert settings.openapi_url == "/openapi.json"
        assert settings.is_production is False

    def test_docs_are_hidden_in_production(self) -> None:
        """An interactive API console on a production host is not wanted."""
        settings = Settings(_env_file=None, environment=Environment.PRODUCTION)
        assert settings.docs_url is None
        assert settings.openapi_url is None
        assert settings.is_production is True


class TestCsvLists:
    """The regression this module exists for."""

    def test_reads_a_comma_separated_list_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PSX_CORS_ORIGINS", "http://a.example,http://b.example")

        settings = Settings(_env_file=None)

        assert settings.cors_origins == ["http://a.example", "http://b.example"]

    def test_reads_a_comma_separated_list_from_a_dotenv_file(self, tmp_path: Path) -> None:
        """The exact scenario that broke: the shipped .env.example, copied verbatim."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "PSX_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173\n",
            encoding="utf-8",
        )

        settings = Settings(_env_file=env_file)

        assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]

    def test_the_shipped_env_example_actually_loads(self) -> None:
        """Guards the documented onboarding path end to end.

        `.env.example` is what a new developer copies. If it cannot be loaded, the
        first thing they do after cloning fails - so the file itself is the fixture.
        """
        example = Path(__file__).resolve().parents[2] / ".env.example"
        assert example.is_file(), "backend/.env.example is missing"

        settings = Settings(_env_file=example)

        assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
        assert settings.environment is Environment.LOCAL
        assert settings.market_data_provider == "seeded"
        assert settings.is_sqlite is True

    def test_a_single_value_is_still_a_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PSX_CORS_ORIGINS", "http://only.example")
        assert Settings(_env_file=None).cors_origins == ["http://only.example"]

    def test_whitespace_around_entries_is_trimmed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # People write "a, b, c" - the space after the comma is natural.
        monkeypatch.setenv("PSX_CORS_ORIGINS", " http://a.example , http://b.example ")
        assert Settings(_env_file=None).cors_origins == [
            "http://a.example",
            "http://b.example",
        ]

    def test_empty_entries_are_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A trailing comma is a typo, not a request for an empty origin.
        monkeypatch.setenv("PSX_CORS_ORIGINS", "http://a.example,,")
        assert Settings(_env_file=None).cors_origins == ["http://a.example"]

    def test_an_empty_value_disables_cors_rather_than_erroring(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An operator setting the variable to nothing means "allow no origins"."""
        monkeypatch.setenv("PSX_CORS_ORIGINS", "")
        assert Settings(_env_file=None).cors_origins == []

    def test_a_real_list_still_works(self) -> None:
        """In-code construction, used by the test fixtures, must keep working."""
        settings = Settings(_env_file=None, cors_origins=["http://x.example"])
        assert settings.cors_origins == ["http://x.example"]


class TestBooleanAndNumericParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("true", True), ("false", False), ("1", True), ("0", False), ("True", True)],
    )
    def test_booleans_accept_the_spellings_env_files_use(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
    ) -> None:
        monkeypatch.setenv("PSX_SEED_ON_STARTUP", raw)
        assert Settings(_env_file=None).seed_on_startup is expected

    def test_an_unknown_environment_name_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Better to fail at startup than to run with production guards half-applied."""
        monkeypatch.setenv("PSX_ENVIRONMENT", "prodction")  # deliberate typo
        with pytest.raises(ValueError, match="environment"):
            Settings(_env_file=None)


class TestDatabaseUrl:
    def test_recognises_sqlite(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PSX_DATABASE_URL", "sqlite+pysqlite:///./local.db")
        assert Settings(_env_file=None).is_sqlite is True

    def test_recognises_postgres(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Drives the connect-args and pragma branches in app/db/session.py.
        monkeypatch.setenv("PSX_DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
        assert Settings(_env_file=None).is_sqlite is False


class TestSettingsCache:
    def test_get_settings_returns_one_shared_instance(self) -> None:
        get_settings.cache_clear()
        try:
            assert get_settings() is get_settings()
        finally:
            get_settings.cache_clear()

    def test_settings_are_immutable(self) -> None:
        """Frozen, so nothing can reconfigure the application mid-request."""
        settings = Settings(_env_file=None)
        with pytest.raises(ValueError, match="frozen"):
            settings.database_url = "sqlite+pysqlite:///:memory:"  # type: ignore[misc]
