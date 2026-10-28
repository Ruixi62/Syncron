"""Tests du client contre un vrai serveur Syncron (uvicorn + PostgreSQL) lancé dans un thread.

Le client tourne hors écran (QT_QPA_PLATFORM=offscreen) avec ImmediateRunner :
chaque appel réseau est exécuté tout de suite, ce qui rend les scénarios déterministes.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
import uuid
from pathlib import Path

import asyncpg
import pytest
import uvicorn

from syncron_server.app import create_app
from syncron_server.config import Environment, Settings
from syncron_server.db import Database
from syncron_server.migrate import upgrade

from ..server.conftest import ADMIN_URL, FakeDiscord, _asyncpg_dsn

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class LiveServer:
    def __init__(self, tmp: Path) -> None:
        self.db_name = f"syncron_client_{uuid.uuid4().hex[:8]}"
        self.admin_dsn = _asyncpg_dsn(ADMIN_URL)
        asyncio.run(self._sql(f'create database "{self.db_name}"'))
        self.database_url = ADMIN_URL.rsplit("/", 1)[0] + f"/{self.db_name}"
        upgrade(self.database_url)
        asyncio.run(self._sql("create table research_seed as select * from research_categories", self.db_name))
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.discord = FakeDiscord()
        self.settings = Settings(
            env=Environment.TEST,
            database_url=self.database_url,
            public_url=self.url,
            jwt_secret="y" * 48,
            discord_client_id="client-id",
            discord_client_secret="client-secret",
            admin_discord_ids="100000000000000001",
            media_dir=tmp / "media",
            dev_login=True,
        )
        app = create_app(self.settings, Database(self.database_url), self.discord)
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="on")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 15
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError("Le serveur de test n'a pas démarré.")
            time.sleep(0.05)

    async def _sql(self, statement: str, database: str | None = None) -> None:
        dsn = self.admin_dsn if database is None else self.admin_dsn.rsplit("/", 1)[0] + f"/{database}"
        connection = await asyncpg.connect(dsn)
        try:
            await connection.execute(statement)
        finally:
            await connection.close()

    def reset(self) -> None:
        asyncio.run(
            self._sql(
                "truncate audit_log, recipe_ingredients, item_requirements, items, stations, skills, "
                "login_codes, refresh_tokens, users, message_receipts, messages, calendar_events, "
                "research_lines, research_tiers, research_categories restart identity cascade; "
                "insert into research_categories select * from research_seed; "
                "update catalog_state set revision = 0, updated_at = now();",
                self.db_name,
            )
        )
        self.settings.min_client_version = "4.1.0"
        self.settings.nation_name = ""

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(10)
        asyncio.run(self._sql(f'drop database if exists "{self.db_name}" with (force)'))


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    server = LiveServer(tmp_path_factory.mktemp("server"))
    yield server
    server.stop()


@pytest.fixture
def server(live_server):
    live_server.reset()
    return live_server


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    from syncron_client.shell.application import configure_application

    app = QApplication.instance() or QApplication([])
    configure_application(app)
    return app


@pytest.fixture
def make_launcher(qapp, tmp_path, server, monkeypatch):
    from syncron_client.paths import AppPaths
    from syncron_client.shell.application import Launcher
    from syncron_client.tasks import ImmediateRunner

    created = []

    def factory(server_url: str | None = None, user_dir: Path | None = None, browser=None):
        monkeypatch.setenv("SYNCRON_SERVER_URL", server_url or server.url)
        launcher = Launcher(
            AppPaths(user_dir or tmp_path / "user"),
            runner=ImmediateRunner(),
            open_browser=browser or (lambda _url: None),
            use_keyring=False,
        )
        created.append(launcher)
        return launcher

    yield factory
    for launcher in created:
        if launcher.shell is not None:
            launcher.shell.window.close()
        launcher.login.close()
        launcher.api.close()
