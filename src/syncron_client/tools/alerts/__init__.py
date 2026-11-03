"""Outil Mes alertes : prévient dès qu'un événement météo apparaît sur la carte Iris.

Le serveur du pays surveille la météo d'iris.nationsglory.fr chaque minute et garde la liste
des événements (météorite, faille, volcan…). Le logiciel la consulte toutes les 30 secondes,
même page fermée, et alerte pour chaque nouvel événement des types choisis : notification
dans le logiciel, notification du bureau (un clic ouvre la carte à l'endroit de l'événement),
pastille de la barre des tâches. Les alertes sont personnelles : chacun choisit les siennes.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget

from syncron_client.platform.tool import StatusLevel, Tool, ToolHost, ToolInfo, ToolStatus
from syncron_client.tools.alerts.page import KINDS, AlertsPage
from syncron_client.tools.intel.model import EVENT_NAMES
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS

PREFS_FILE = "alerts.json"
POLL_INTERVAL_MS = 30_000
SEEN_LIMIT = 500


class AlertsTool(Tool):
    _INFO = ToolInfo(
        id="alerts",
        name="Mes alertes",
        description="Alertes en direct quand une météorite, une faille ou un volcan apparaît sur la carte.",
        icon="bell",
        version="5.3.0",
    )

    def __init__(self, interval_ms: int = POLL_INTERVAL_MS) -> None:
        self._host: ToolHost | None = None
        self._page: AlertsPage | None = None
        self._events: list[dict[str, Any]] = []
        self._enabled_on_server = True
        self._checked_at: str | None = None
        self._kinds = {kind: True for kind in KINDS}
        self._seen: set[int] = set()
        self._polling = False
        self._stopped = False
        self._actions: list[QAction] = []
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> AlertsPage | None:
        return self._page

    @property
    def kinds(self) -> dict[str, bool]:
        return dict(self._kinds)

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._prefs_path = host.tool_paths(self.info.id).user_dir / PREFS_FILE
        try:
            raw = json.loads(self._prefs_path.read_text(encoding="utf-8"))
            for kind, value in (raw.get("kinds") or {}).items():
                if kind in self._kinds:
                    self._kinds[kind] = bool(value)
            self._seen = {int(i) for i in raw.get("seen", []) if isinstance(i, int)}
        except (OSError, ValueError, TypeError, AttributeError):
            self._seen = set()
        host.session.onlineChanged.connect(self._online_changed)
        self._online_changed(host.session.online)

    def create_page(self) -> QWidget:
        self._page = AlertsPage(self._kinds)
        self._page.kindToggled.connect(self.set_kind)
        self._page.showRequested.connect(self._show_on_map)
        self._page.set_events(self._events, self._enabled_on_server, self._checked_at)
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Vérifier maintenant")
        refresh.triggered.connect(self.poll)
        self._actions = [refresh]
        return self._page

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def activated(self) -> None:
        self.poll()

    def status(self) -> ToolStatus:
        active = [e for e in self._events if e.get("active") and self._kinds.get(e.get("kind"), True)]
        if not active:
            return ToolStatus()
        names = ", ".join(sorted({EVENT_NAMES.get(e.get("kind"), "Événement") for e in active}))
        return ToolStatus(StatusLevel.WARNING, f"En cours : {names}", str(len(active)))

    def shutdown(self) -> None:
        self._stopped = True
        self._timer.stop()
        with contextlib.suppress(RuntimeError, TypeError):
            self._host.session.onlineChanged.disconnect(self._online_changed)

    def set_kind(self, kind: str, enabled: bool) -> None:
        self._kinds[kind] = enabled
        self._save()
        self._host.status_changed(self.info.id)

    # -- surveillance --------------------------------------------------------------------

    def _online_changed(self, online: bool) -> None:
        """Première vérification juste après l'ouverture de la fenêtre (pour qu'elle affiche l'alerte)."""
        if online:
            self._timer.start()
            QTimer.singleShot(0, self.poll)
        else:
            self._timer.stop()

    def poll(self) -> None:
        if self._polling or self._stopped or self._host is None or not self._host.session.online:
            return
        self._polling = True
        self._host.runner.run(self._host.api.iris_events, self._received, self._failed)

    def _failed(self, _error: Exception) -> None:
        """Pas de message : la vérification recommence toute seule 30 secondes plus tard."""
        self._polling = False

    def _received(self, data: dict[str, Any]) -> None:
        self._polling = False
        self._enabled_on_server = bool(data.get("enabled", True))
        self._checked_at = data.get("checked_at")
        self._events = [e for e in data.get("events", []) if isinstance(e, dict) and isinstance(e.get("id"), int)]
        fresh = [
            e
            for e in self._events
            if e.get("active") and e["id"] not in self._seen and self._kinds.get(e.get("kind"), True)
        ]
        for event in fresh:
            self._alert(event)
        if fresh or any(e["id"] not in self._seen for e in self._events):
            self._seen.update(e["id"] for e in self._events)
            self._save()
        if self._page is not None:
            self._page.set_events(self._events, self._enabled_on_server, self._checked_at)
        self._host.status_changed(self.info.id)

    def _alert(self, event: dict[str, Any]) -> None:
        x, z = event.get("x"), event.get("z")
        where = f"Position : x {x} · z {z}" if x is not None and z is not None else "Position inconnue"
        key = f"at:{x}:{z}" if x is not None and z is not None else ""
        self._host.notifications.alert(str(event.get("title") or "Événement"), where, "intel" if key else "alerts", key)

    def _show_on_map(self, x: int, z: int) -> None:
        self._host.open_tool("intel", f"at:{x}:{z}")

    def _save(self) -> None:
        seen = sorted(self._seen)[-SEEN_LIMIT:]
        self._seen = set(seen)
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            self._prefs_path.write_text(json.dumps({"kinds": self._kinds, "seen": seen}), encoding="utf-8")
        except OSError:
            return
