"""Outil Recherche : la carte NationsGlory (Iris) et les informations des autres pays.

Le serveur du pays récupère la carte d'iris.nationsglory.fr (territoires, frontières,
régions, atlas, membres, heure et météo du jeu) ; le logiciel la télécharge seulement
quand elle a changé (ETag) et la garde sur le disque pour le hors-ligne. Pendant que la
page est ouverte, l'heure du jeu et les événements météo sont mis à jour chaque minute.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget

from syncron_client.platform.tool import NotifyLevel, SearchHit, Tool, ToolHost, ToolInfo
from syncron_client.tools.intel.model import World, apply_live, apply_members, parse_map
from syncron_client.tools.intel.page import IntelPage
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS

CACHE_FILE = "iris.json"
PARTS = ("map", "live", "members")
LIVE_INTERVAL_MS = 60_000


def build_world(cache: dict[str, Any]) -> World:
    world = parse_map(cache.get("map", {}).get("data"))
    apply_live(world, cache.get("live", {}).get("data"))
    apply_members(world, cache.get("members", {}).get("data"))
    return world


class IntelTool(Tool):
    _INFO = ToolInfo(
        id="intel",
        name="Recherche",
        description="La carte NationsGlory : territoires, frontières, ressources et membres de chaque pays.",
        icon="map",
        version="5.3.0",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._page: IntelPage | None = None
        self._cache: dict[str, Any] = {}
        self._world = World()
        self._loading = False
        self._actions: list[QAction] = []
        self._pending: str | None = None
        self._timer: QTimer | None = None

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> IntelPage | None:
        return self._page

    @property
    def world(self) -> World:
        return self._world

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._cache_path = host.tool_paths(self.info.id).user_dir / CACHE_FILE
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            self._cache = {part: raw[part] for part in PARTS if isinstance(raw.get(part), dict)}
            self._world = build_world(self._cache)
        except (OSError, ValueError, TypeError, AttributeError):
            self._cache = {}

    def create_page(self) -> QWidget:
        self._page = IntelPage()
        self._page.set_world(self._world, offline=not self._host.session.online)
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Recharger la carte")
        refresh.triggered.connect(self.refresh)
        self._actions = [refresh]
        self._timer = QTimer(self._page)
        self._timer.setInterval(LIVE_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh_live)
        return self._page

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def activated(self) -> None:
        self.refresh()
        if self._timer is not None:
            self._timer.start()

    def deactivated(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def search(self, query: str, limit: int) -> Sequence[SearchHit]:
        if len(query.strip()) < 2:
            return ()
        hits = []
        for name in self._world.matches(query)[:limit]:
            chunks = self._world.chunks_of(name)
            detail = f"{chunks} chunks claim" if chunks else "frontière"
            hits.append(SearchHit(self.info.id, name, name, f"Pays · {detail}"))
        return hits

    def open(self, key: str) -> None:
        """`Pays`, `joueur`, ou `at:<x>:<z>` (position en blocs, ex. un événement)."""
        if self._page is None:
            return
        if key.startswith("at:"):
            parts = key.split(":")
            try:
                x, z = int(parts[1]), int(parts[2])
            except (IndexError, ValueError):
                return
            event = next((e for e in self._world.events if e.x == x and e.z == z), None)
            self._page.map.show_block(x, z)
            if event is not None:
                self._page.show_event(event)
            return
        if not self._page.find(key):
            self._pending = key

    # -- données -------------------------------------------------------------------------

    def refresh(self) -> None:
        self._fetch(PARTS)

    def refresh_live(self) -> None:
        self._fetch(("live",))

    def _fetch(self, parts: Sequence[str]) -> None:
        if self._loading or not self._host.session.online:
            return
        self._loading = True
        api = self._host.api
        cache = {part: dict(self._cache.get(part, {})) for part in PARTS}

        def load() -> tuple[dict[str, Any], World | None]:
            changed = False
            for part in parts:
                data, etag = api.iris(part, cache[part].get("etag", "") if cache[part].get("data") else "")
                if data is not None:
                    cache[part] = {"etag": etag, "data": data}
                    changed = True
            if not changed:
                return cache, None
            try:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                self._cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            except OSError:
                cache["_disk_error"] = True
            return cache, build_world(cache) if parts != ("live",) else None

        def done(result: tuple[dict[str, Any], World | None]) -> None:
            self._loading = False
            cache, world = result
            if cache.pop("_disk_error", False):
                self._host.notify("Carte non gardée pour le hors-ligne (disque).", NotifyLevel.WARNING)
            self._cache = cache
            if world is not None:
                self._world = world
                if self._page is not None:
                    self._page.set_world(world)
            elif parts == ("live",) and cache.get("live", {}).get("data") is not None:
                apply_live(self._world, cache["live"]["data"])
                if self._page is not None:
                    self._page.refresh_live()
            if self._pending and self._page is not None and self._page.find(self._pending):
                self._pending = None

        def failed(error: Exception) -> None:
            self._loading = False
            if parts != ("live",):
                self._host.handle_error(error, "Recherche")

        self._host.runner.run(load, done, failed)
