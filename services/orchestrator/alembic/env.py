from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sqlalchemy_url() -> str:
    backend = os.getenv("SYNCORE_DB_BACKEND", "sqlite").strip().lower()
    if backend == "postgres":
        return os.getenv(
            "POSTGRES_DSN",
            "postgresql://agentos:agentos@localhost:5432/agentos",
        )
    sqlite_path = os.getenv("SQLITE_DB_PATH", ".syncore/syncore.db")
    if sqlite_path.startswith("sqlite:///"):
        return sqlite_path
    return f"sqlite:///{sqlite_path}"


target_metadata = None


def run_migrations_offline() -> None:
    url = _sqlalchemy_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_sqlalchemy_url(), poolclass=pool.NullPool)

    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
