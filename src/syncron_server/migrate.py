"""Migrations de schéma : `python -m syncron_server.migrate` (exécuté aussi au démarrage du conteneur)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parent / "alembic.ini"


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    if database_url:
        config.attributes["database_url"] = database_url
    return config


def upgrade(database_url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)


async def upgrade_async(database_url: str, revision: str = "head") -> None:
    """Depuis du code déjà asynchrone (tests) : Alembic lance sa propre boucle dans un thread."""
    await asyncio.to_thread(upgrade, database_url, revision)


def main() -> int:
    from syncron_server.config import Settings

    upgrade(Settings().database_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
