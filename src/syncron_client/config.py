"""Adresse du serveur.

Ordre de priorité :
    1. variable d'environnement SYNCRON_SERVER_URL
    2. réglage de l'utilisateur (Paramètres → Serveur)
    3. syncron.json livré à côté de l'exécutable (écrit par build.py --server-url)
    4. http://127.0.0.1:8000 (développement)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from syncron_client.paths import install_dir
from syncron_client.settings import JsonSettingsStore

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
BUNDLED_CONFIG = "syncron.json"
SERVER_URL_KEY = "server_url"


def bundled_server_url(directory: Path | None = None) -> str | None:
    path = (directory or install_dir()) / BUNDLED_CONFIG
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get(SERVER_URL_KEY)
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and value.startswith(("http://", "https://")) else None


def resolve_server_url(settings: JsonSettingsStore, directory: Path | None = None) -> str:
    candidates = (os.environ.get("SYNCRON_SERVER_URL"), settings.get(SERVER_URL_KEY), bundled_server_url(directory))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
            return candidate.rstrip("/")
    return DEFAULT_SERVER_URL


def version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for part in version.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)
