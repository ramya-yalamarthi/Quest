"""Alembic env. Reads DATABASE_URL from the same `app.config` the runtime uses.

Imports `app.db.base.Base` plus every model module so autogenerate sees all
tables (existing ones AND the mitigation_safety ms_* tables).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import DATABASE_URL

# Eager imports so model metadata is registered on Base.
import app.db.models  # noqa: F401
import app.mitigation_safety.db.models  # noqa: F401
from app.db.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
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
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
