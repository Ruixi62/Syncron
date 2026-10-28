"""Outil Calendrier : les événements du pays (réunions, guerres, événements, économie).

Lecture pour tous ; création et modification dans l'Administration, section
« Calendrier », pour les comptes qui gèrent ce système. Le dernier état reçu
est gardé sur le disque pour la consultation hors ligne.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget

from syncron_client.platform.admin import AdminSection, admin_link, call_api
from syncron_client.platform.tool import Tool, ToolHost, ToolInfo
from syncron_client.tools.calendar.admin import EventsAdmin
from syncron_client.tools.calendar.model import Event, grid_range
from syncron_client.tools.calendar.page import CalendarPage
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS

EVENTS_SECTION = "calendar.events"
UPCOMING_DAYS = 60
UPCOMING_COUNT = 6
CACHE_FILE = "events.json"
MAX_CACHED_MONTHS = 24


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


class CalendarTool(Tool):
    _INFO = ToolInfo(
        id="calendar",
        name="Calendrier",
        description="Réunions, guerres, événements et rendez-vous économiques du pays.",
        icon="calendar",
        version="4.1.0",
        system="calendar",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._page: CalendarPage | None = None
        self._admin: EventsAdmin | None = None
        self._actions: list[QAction] = []
        self._cache: dict[str, Any] = {}

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> CalendarPage | None:
        return self._page

    @property
    def admin(self) -> EventsAdmin | None:
        return self._admin

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._cache_path = host.tool_paths(self.info.id).user_dir / CACHE_FILE
        try:
            loaded = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = {}
        self._cache = loaded if isinstance(loaded, dict) else {}

    def create_page(self) -> QWidget:
        self._page = CalendarPage(self._host.session.can_manage(self.info.system))
        self._page.monthChanged.connect(self.load_month)
        self._page.newRequested.connect(
            lambda day: self._host.open_tool("admin", admin_link(EVENTS_SECTION, f"new:{day.isoformat()}"))
        )
        self._page.editRequested.connect(lambda key: self._host.open_tool("admin", admin_link(EVENTS_SECTION, key)))
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Recharger le calendrier")
        refresh.triggered.connect(self.refresh)
        self._actions = [refresh]
        return self._page

    def activated(self) -> None:
        if self._page is not None:
            self._page.set_editable(self._host.session.can_manage(self.info.system))
        self.refresh()

    def refresh(self) -> None:
        if self._page is None:
            return
        self.load_month(*self._page.month)
        self._load_upcoming()

    def open(self, key: str) -> None:
        """`key` : identifiant d'un événement (lien d'un message)."""

        def show(raw: dict[str, Any]) -> None:
            event = Event.from_api(raw)
            self.load_month(event.first_day.year, event.first_day.month, focus=event)

        call_api(self._host, lambda: self._host.api.event(key), show)

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def admin_sections(self) -> Sequence[AdminSection]:
        return [AdminSection(EVENTS_SECTION, "Événements", "calendar", self._create_admin)]

    # -- données ------------------------------------------------------------------------------

    def load_month(self, year: int, month: int, focus: Event | None = None) -> None:
        key = _month_key(year, month)
        start, end = grid_range(year, month)

        def show(raw_events: list[dict[str, Any]]) -> None:
            if self._page is None:
                return
            events = [Event.from_api(raw) for raw in raw_events]
            self._page.set_month(year, month, events)
            if focus is not None:
                self._page.focus_event(focus)

        def done(raw_events: list[dict[str, Any]]) -> None:
            self._store(key, raw_events)
            show(raw_events)

        def failed(error: Exception) -> None:
            show(self._cache.get(key, []))
            self._host.handle_error(error, "Calendrier")

        if not self._host.session.online:
            show(self._cache.get(key, []))
            return
        self._host.runner.run(lambda: self._host.api.events(start, end), done, failed)

    def _load_upcoming(self) -> None:
        now = datetime.now().astimezone()

        def show(raw_events: list[dict[str, Any]]) -> None:
            if self._page is None:
                return
            events = [e for e in (Event.from_api(raw) for raw in raw_events) if (e.ends_at or e.starts_at) >= now]
            events.sort(key=lambda e: e.starts_at)
            self._page.set_upcoming(events[:UPCOMING_COUNT])

        def done(raw_events: list[dict[str, Any]]) -> None:
            self._store("upcoming", raw_events)
            show(raw_events)

        if not self._host.session.online:
            show(self._cache.get("upcoming", []))
            return
        end = now + timedelta(days=UPCOMING_DAYS)
        self._host.runner.run(
            lambda: self._host.api.events(now, end), done, lambda _error: show(self._cache.get("upcoming", []))
        )

    def _store(self, key: str, raw_events: list[dict[str, Any]]) -> None:
        self._cache[key] = raw_events
        if len(self._cache) > MAX_CACHED_MONTHS:
            current = date.today()
            keep = {_month_key(current.year, current.month), "upcoming", key}
            self._cache = {k: v for k, v in self._cache.items() if k in keep}
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            return

    def _create_admin(self) -> EventsAdmin:
        self._admin = EventsAdmin(self._host)
        self._admin.changed.connect(self.refresh)
        return self._admin
