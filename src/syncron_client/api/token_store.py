"""Conservation du jeton de rafraîchissement entre deux lancements.

Coffre du système (Gestionnaire d'identification Windows, trousseau macOS,
Secret Service Linux) via `keyring` ; à défaut, fichier user/session.json
lisible par le seul utilisateur.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from syncron_core.io import atomic_write_text

SERVICE = "Syncron"


class TokenStore:
    def __init__(self, server_url: str, fallback_file: Path, use_keyring: bool = True) -> None:
        self._account = server_url
        self._fallback = fallback_file
        self._keyring = _load_keyring() if use_keyring else None

    @property
    def secure(self) -> bool:
        return self._keyring is not None

    def load(self) -> str | None:
        if self._keyring is not None:
            try:
                return self._keyring.get_password(SERVICE, self._account)
            except Exception:
                self._keyring = None
        try:
            data = json.loads(self._fallback.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        value = data.get(self._account) if isinstance(data, dict) else None
        return value if isinstance(value, str) else None

    def save(self, refresh_token: str | None) -> None:
        if self._keyring is not None:
            try:
                if refresh_token:
                    self._keyring.set_password(SERVICE, self._account, refresh_token)
                else:
                    self._delete_keyring()
                return
            except Exception:
                self._keyring = None
        self._save_file(refresh_token)

    def _delete_keyring(self) -> None:
        try:
            self._keyring.delete_password(SERVICE, self._account)
        except Exception:
            return

    def _save_file(self, refresh_token: str | None) -> None:
        try:
            data = json.loads(self._fallback.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        if refresh_token:
            data[self._account] = refresh_token
        else:
            data.pop(self._account, None)
        atomic_write_text(self._fallback, json.dumps(data))
        try:
            os.chmod(self._fallback, 0o600)
        except OSError:
            return


def _load_keyring():
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return None
    try:
        backend = keyring.get_keyring()
    except Exception:
        return None
    if isinstance(backend, fail.Keyring) or getattr(backend, "priority", 0) <= 0:
        return None
    return keyring
