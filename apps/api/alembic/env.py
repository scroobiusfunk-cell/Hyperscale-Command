"""Alembic environment.

The database URL comes from application settings, never from alembic.ini, so
migrations and the app can never disagree about which database they mean.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app import models  # noqa: F401  (import for side effect: populates Base.metadata)
from app.config import load_settings
from app.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# An explicitly configured URL wins, so a caller driving Alembic
# programmatically (the test suite) is not overridden by ambient
# environment. Otherwise the URL comes from application settings, so
# migrations and the app can never disagree about which database they mean.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", load_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        # Alembic run programmatically (the test suite) would otherwise leave
        # this engine to be garbage collected, and psycopg complains about the
        # connection it closes on the way out.
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
