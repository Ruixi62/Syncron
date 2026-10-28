"""Tests du serveur sur un vrai PostgreSQL.

Base : SYNCRON_TEST_DATABASE_URL (par défaut postgresql+asyncpg://syncron@127.0.0.1:5433/postgres) ;
une base jetable est créée pour la session de tests, migrée avec Alembic, puis supprimée.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field

import asyncpg
import httpx
import pytest
from sqlalchemy import text

from syncron_server.app import create_app
from syncron_server.config import Environment, Settings
from syncron_server.db import Database
from syncron_server.discord import DiscordError, DiscordUser
from syncron_server.migrate import upgrade_async

ADMIN_DISCORD_ID = "100000000000000001"
ADMIN_URL = os.environ.get("SYNCRON_TEST_DATABASE_URL", "postgresql+asyncpg://syncron@127.0.0.1:5433/postgres")


@dataclass
class FakeDiscord:
    """Remplace Discord : un code d'autorisation = un utilisateur connu."""

    users: dict[str, DiscordUser] = field(default_factory=dict)
    guilds: dict[str, set[str]] = field(default_factory=dict)
    fail: bool = False

    def authorize_url(self, state: str, redirect_uri: str, scopes: tuple[str, ...]) -> str:
        return f"https://discord.test/authorize?state={state}&scope={'+'.join(scopes)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> str:
        if self.fail or code not in self.users:
            raise DiscordError("refusé")
        return f"token-{code}"

    async def fetch_user(self, access_token: str) -> DiscordUser:
        return self.users[access_token.removeprefix("token-")]

    async def fetch_guild_ids(self, access_token: str) -> set[str]:
        return self.guilds.get(access_token.removeprefix("token-"), set())


def _asyncpg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session")
async def database_url():
    name = f"syncron_test_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(_asyncpg_dsn(ADMIN_URL))
    await admin.execute(f'create database "{name}"')
    await admin.close()
    url = ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"
    await upgrade_async(url)
    connection = await asyncpg.connect(_asyncpg_dsn(url))
    await connection.execute("create table research_seed as select * from research_categories")
    await connection.close()
    yield url
    admin = await asyncpg.connect(_asyncpg_dsn(ADMIN_URL))
    await admin.execute(f'drop database if exists "{name}" with (force)')
    await admin.close()


@pytest.fixture
def settings(database_url, tmp_path) -> Settings:
    return Settings(
        env=Environment.TEST,
        database_url=database_url,
        public_url="https://api.syncron.test",
        jwt_secret="x" * 48,
        discord_client_id="client-id",
        discord_client_secret="client-secret",
        admin_discord_ids=ADMIN_DISCORD_ID,
        media_dir=tmp_path / "media",
        dev_login=True,
    )


@pytest.fixture
async def database(settings):
    db = Database(settings.database_url)
    async with db.engine.begin() as connection:
        await connection.execute(
            text(
                "truncate audit_log, recipe_ingredients, item_requirements, items, stations, skills, "
                "login_codes, refresh_tokens, users, message_receipts, messages, calendar_events, "
                "research_lines, research_tiers, research_categories restart identity cascade"
            )
        )
        await connection.execute(text("insert into research_categories select * from research_seed"))
        await connection.execute(text("update catalog_state set revision = 0, updated_at = now()"))
    yield db
    await db.dispose()


@pytest.fixture
def discord() -> FakeDiscord:
    return FakeDiscord()


@pytest.fixture
async def client(settings, database, discord):
    app = create_app(settings, database, discord)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.syncron.test") as http:
        yield http


async def login(client: httpx.AsyncClient, username: str, role: str = "player") -> dict[str, str]:
    response = await client.post("/api/v1/auth/dev-login", json={"username": username, "role": role})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def editor(client) -> dict[str, str]:
    return await login(client, "editeur", "editor")


@pytest.fixture
async def admin(client) -> dict[str, str]:
    return await login(client, "patron", "admin")


@pytest.fixture
async def player(client) -> dict[str, str]:
    return await login(client, "joueur", "player")


@pytest.fixture
async def seeded(client, editor):
    from ..sample import sample_document

    response = await client.post("/api/v1/admin/craft/import?dry_run=false", json=sample_document(), headers=editor)
    assert response.status_code == 200, response.text
    return response.json()
