"""Session utilisateur : qui est connecté, avec quel rôle et quels systèmes confiés, en ligne ou non."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from PySide6.QtCore import QObject, Signal


class Role(StrEnum):
    PLAYER = "player"
    EDITOR = "editor"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return {"player": 0, "editor": 1, "admin": 2}[self.value]

    @property
    def label(self) -> str:
        return {"player": "Membre", "editor": "Éditeur", "admin": "Administrateur"}[self.value]


class Session(QObject):
    userChanged = Signal(object)
    onlineChanged = Signal(bool)
    expired = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._user: dict[str, Any] | None = None
        self._online = True
        self._meta: dict[str, Any] = {}

    @property
    def user(self) -> dict[str, Any] | None:
        return self._user

    @property
    def online(self) -> bool:
        return self._online

    @property
    def role(self) -> Role:
        try:
            return Role((self._user or {}).get("role", "player"))
        except ValueError:
            return Role.PLAYER

    @property
    def display_name(self) -> str:
        user = self._user or {}
        return user.get("display_name") or user.get("username") or "Hors ligne"

    @property
    def user_id(self) -> str | None:
        return (self._user or {}).get("id")

    @property
    def permissions(self) -> frozenset[str]:
        return frozenset((self._user or {}).get("permissions") or ())

    @property
    def nation_name(self) -> str:
        return str(self._meta.get("nation_name") or "")

    @property
    def systems(self) -> dict[str, str]:
        """Systèmes du serveur : identifiant -> nom (Craft, R&D…)."""
        return dict(self._meta.get("systems") or {})

    def system_name(self, system: str) -> str:
        return str((self._meta.get("systems") or {}).get(system, system))

    def set_meta(self, meta: dict[str, Any]) -> None:
        self._meta = dict(meta)

    def can_manage(self, system: str | None) -> bool:
        """Administrateur : tout. Éditeur : les systèmes que l'administration lui a confiés."""
        if system is None or self._user is None or not self._online:
            return False
        if self.role is Role.ADMIN:
            return True
        return self.role is Role.EDITOR and system in self.permissions

    def has_role(self, minimum: Role | str | None) -> bool:
        if minimum is None:
            return True
        return self._user is not None and self.role.rank >= Role(minimum).rank

    def set_user(self, user: dict[str, Any] | None) -> None:
        self._user = user
        self.userChanged.emit(user)

    def set_online(self, online: bool) -> None:
        if online != self._online:
            self._online = online
            self.onlineChanged.emit(online)
