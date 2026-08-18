"""Alembic environment.

Two deliberate departures from the generated template:

1. **The database URL comes from application settings**, not ``alembic.ini``. One
   connection string, one place to change it, and migrations can never run
   against a different database from the application.
2. **``render_as_batch`` is enabled.** SQLite cannot ``ALTER COLUMN``; batch mode
   makes Alembic rebuild the table instead. Without it, any migration that alters
   a column works on Postgres and fails on every developer's local database.
3. **``render_item`` unwraps our custom column types.** Autogenerate would otherwise
   emit ``app.db.base.UtcDateTime()`` into the migration, coupling a historical
   migration to application code - so the migration breaks the day that class is
   renamed or moved. Rendering the underlying ``sa.DateTime(timezone=True)``
   produces identical DDL and keeps migrations self-contained.
"""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import engine_from_config, pool
from sqlalchemy.sql.schema import SchemaItem

from app.core.config import get_settings

# Importing the models package registers every table on Base.metadata, which is
# what autogenerate diffs against. A model missing from app/models/__init__.py
# would silently be absent from generated migrations.
from app.db.base import Base, UtcDateTime
from app.models import *  # noqa: F403 - imported for metadata registration

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def _render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Render custom types as their plain SQLAlchemy equivalents.

    Returning ``False`` falls back to Alembic's default rendering for everything
    else. See point 3 of the module docstring for why this matters.

    The signature mirrors Alembic's own, including the ``Literal[False]`` return -
    a plain ``bool`` would not satisfy it, because ``True`` is not a valid answer.
    """
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _include_object(
    object_: SchemaItem,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    """Filter objects out of autogenerate.

    Currently a pass-through with an explicit hook, so that excluding a
    third-party or externally-managed table later is a one-line change rather
    than a rewrite of this file.
    """
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of applying it.

    Used to hand a reviewable script to a DBA, or to inspect what an upgrade would
    do before running it.
    """
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,
        include_object=_include_object,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Both comparisons are off by default, which means a changed column
            # type or default is silently missed by autogenerate.
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,
            include_object=_include_object,
            render_item=_render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
