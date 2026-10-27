"""Registre des outils disponibles, dans l'ordre d'affichage."""

from __future__ import annotations

from collections.abc import Iterator

from syncron_client.platform.tool import Tool

RESERVED_IDS = frozenset({"home", "settings"})


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        tool_id = tool.info.id
        if tool_id in RESERVED_IDS:
            raise ValueError(f"Identifiant d'outil réservé : {tool_id}")
        if not tool_id.isidentifier():
            raise ValueError(f"Identifiant d'outil invalide (lettres, chiffres, _) : {tool_id!r}")
        if tool_id in self._tools:
            raise ValueError(f"Outil déjà enregistré : {tool_id}")
        self._tools[tool_id] = tool

    def get(self, tool_id: str) -> Tool:
        try:
            return self._tools[tool_id]
        except KeyError:
            raise KeyError(f"Outil inconnu : {tool_id}") from None

    def all(self) -> tuple[Tool, ...]:
        return tuple(self._tools.values())

    def __contains__(self, tool_id: object) -> bool:
        return tool_id in self._tools

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)
