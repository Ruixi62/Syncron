"""Préférences en JSON : document unique, lecture tolérante, écriture atomique.

Même mécanique pour la plateforme (user/settings.json) et pour chaque outil
(user/<outil>/settings.json), ainsi que pour les futurs stores (stock, favoris…).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from syncron_core.io import atomic_write_json


class JsonSettingsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = self._load()

    @property
    def path(self) -> Path:
        return self._path

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def save(self) -> None:
        atomic_write_json(self._path, self._data)

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
