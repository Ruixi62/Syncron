"""Emplacements locaux du client.

Le logiciel est téléchargeable et installé n'importe où : les données
personnelles vont dans le dossier applicatif de l'utilisateur
(Windows : %APPDATA%\\Syncron, Linux : ~/.local/share/Syncron), pas à côté de l'exe.

    <user_dir>/
    ├── settings.json       préférences de la plateforme (adresse du serveur, fenêtre…)
    ├── <outil>/settings.json
    └── cache/
        ├── catalog.json    dernier catalogue reçu (+ ETag) : démarrage rapide et mode hors ligne
        └── media/…         images téléchargées
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from syncron_core import APP_NAME


def default_user_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class ToolPaths:
    user_dir: Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    user_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.user_dir / "settings.json"

    @property
    def cache_dir(self) -> Path:
        return self.user_dir / "cache"

    @property
    def catalog_cache(self) -> Path:
        return self.cache_dir / "catalog.json"

    @property
    def media_cache(self) -> Path:
        return self.cache_dir / "media"

    @property
    def session_fallback(self) -> Path:
        return self.user_dir / "session.json"

    def for_tool(self, tool_id: str) -> ToolPaths:
        return ToolPaths(user_dir=self.user_dir / tool_id)

    @classmethod
    def resolve(cls, user_dir: Path | None = None) -> AppPaths:
        return cls(user_dir=(user_dir or default_user_dir()).resolve())
