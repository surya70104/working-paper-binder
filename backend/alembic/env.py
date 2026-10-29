"""Alembic environment.

The migration URL comes from settings (OAK_MIGRATION_DATABASE_URL), or from
``config.attributes["migration_url"]`` when a test drives Alembic programmatically. Either
way it passes the Binder-only guard: any database other than oak_binder or oak_binder_test is
refused before a connection is attempted (architecture D5). Offline mode
(``alembic upgrade head --sql``) prints SQL and opens no connection.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import oak_binder.models  # noqa: F401  # registers every table on Base.metadata
from oak_binder.config import APP_DATABASE, TEST_DATABASE, Settings, check_binder_url
from oak_binder.db import Base

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migration_url() -> str:
    url = config.attributes.get("migration_url")
    source = "migration_url attribute"
    if not url:
        url = Settings().migration_database_url
        source = "OAK_MIGRATION_DATABASE_URL"
    if not url:
        raise SystemExit(
            "OAK_MIGRATION_DATABASE_URL is not set. Copy backend\\.env.example to backend\\.env "
            "and fill it in. Nothing was changed."
        )
    return check_binder_url(url, allowed=frozenset({APP_DATABASE, TEST_DATABASE}), name=source)


def run_migrations_offline() -> None:
    """Emit SQL to the output buffer. No connection is opened."""
    context.configure(
        url=_migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect as oak_binder_owner and run the migrations in one transaction."""
    engine = create_engine(_migration_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transaction_per_migration=False,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
