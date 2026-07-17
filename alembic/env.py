import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config

# Arbitrary but fixed key: every replica must ask for the same lock.
ALEMBIC_LOCK_ID = 727001

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.core.config import get_settings  # noqa: E402

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        # Every api container runs `alembic upgrade head` at startup, and prod
        # scales to several replicas, so without this two of them can both read
        # the old revision and apply the same DDL. The lock is held for the
        # migration transaction and released on commit; late replicas then wake
        # up, re-read the version table, and find themselves already at head.
        connection.exec_driver_sql(
            f"SELECT pg_advisory_xact_lock({ALEMBIC_LOCK_ID})"
        )
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
