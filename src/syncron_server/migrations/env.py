"""Environnement Alembic asynchrone. L'URL vient de SYNCRON_DATABASE_URL (ou de la config passée par migrate())."""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from syncron_server import models  # noqa: F401  (enregistre les tables)
from syncron_server.db import Base

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    url = config.attributes.get("database_url") or os.environ.get("SYNCRON_DATABASE_URL")
    if not url:
        raise RuntimeError("SYNCRON_DATABASE_URL n'est pas défini.")
    return url


def run_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
