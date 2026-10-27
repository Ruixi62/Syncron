from __future__ import annotations

import json
import threading
import time

import pytest

from syncron_client.api.discord_login import pkce_pair
from syncron_client.api.token_store import TokenStore
from syncron_client.config import resolve_server_url, version_tuple
from syncron_client.settings import JsonSettingsStore
from syncron_client.tasks import TaskRunner


def test_task_runner_calls_back_on_ui_thread(qapp):
    from PySide6.QtCore import QCoreApplication

    main = threading.get_ident()
    seen: dict[str, object] = {}
    runner = TaskRunner()
    runner.run(lambda: threading.get_ident(), lambda worker: seen.update(worker=worker, cb=threading.get_ident()))
    runner.run(lambda: 1 / 0, None, lambda error: seen.update(error=error))
    deadline = time.time() + 5
    while len(seen) < 3 and time.time() < deadline:
        runner.wait(100)
        QCoreApplication.processEvents()
    assert seen["worker"] != main and seen["cb"] == main
    assert isinstance(seen["error"], ZeroDivisionError)


def test_token_store_file_fallback(tmp_path):
    store = TokenStore("https://api.test", tmp_path / "session.json", use_keyring=False)
    assert store.load() is None and not store.secure
    store.save("secret-token")
    assert TokenStore("https://api.test", tmp_path / "session.json", use_keyring=False).load() == "secret-token"
    assert TokenStore("https://autre.test", tmp_path / "session.json", use_keyring=False).load() is None
    store.save(None)
    assert store.load() is None


def test_server_url_priority(tmp_path, monkeypatch):
    settings = JsonSettingsStore(tmp_path / "settings.json")
    monkeypatch.delenv("SYNCRON_SERVER_URL", raising=False)
    assert resolve_server_url(settings, tmp_path) == "http://127.0.0.1:8000"
    (tmp_path / "syncron.json").write_text(json.dumps({"server_url": "https://api.livre.fr/"}))
    assert resolve_server_url(settings, tmp_path) == "https://api.livre.fr"
    settings.set("server_url", "https://perso.fr")
    assert resolve_server_url(settings, tmp_path) == "https://perso.fr"
    monkeypatch.setenv("SYNCRON_SERVER_URL", "https://env.fr")
    assert resolve_server_url(settings, tmp_path) == "https://env.fr"


@pytest.mark.parametrize(("older", "newer"), [("4.0.0", "4.0.1"), ("4.9", "4.10"), ("3.9.9", "4"), ("4.0.0b1", "4.1")])
def test_version_comparison(older, newer):
    assert version_tuple(older) < version_tuple(newer)


def test_pkce_pair_matches_server_check():
    from syncron_server.security import verify_pkce

    verifier, challenge = pkce_pair()
    assert verify_pkce(verifier, challenge)
