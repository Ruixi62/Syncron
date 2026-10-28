"""Centre de notifications : surveille la messagerie et prévient des nouveaux messages.

Toutes les POLL_INTERVAL_MS, une requête légère (`/inbox/summary`) donne le
nombre de non-lus et le plus récent message. S'il est plus récent que le
dernier vu (mémorisé par compte), les nouveaux messages sont récupérés et
`received` est émis : la plateforme affiche une notification, et une
notification du bureau si la fenêtre n'est pas au premier plan.

Les outils qui publient un message (annonce, événement…) appellent `poll()`
pour que l'auteur voie tout de suite le résultat.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from syncron_client.api.client import ApiClient
from syncron_client.api.errors import NetworkError, SessionExpired
from syncron_client.session import Session
from syncron_client.settings import JsonSettingsStore
from syncron_client.tasks import TaskRunner

POLL_INTERVAL_MS = 60_000
FETCH_LIMIT = 20
SEEN_KEY = "inbox_seen"


class NotificationCenter(QObject):
    unreadChanged = Signal(int)
    received = Signal(list)  # nouveaux messages (dict), du plus récent au plus ancien
    changed = Signal()  # boîte modifiée : nouveaux messages, lus, supprimés

    def __init__(
        self,
        api: ApiClient,
        runner: TaskRunner,
        session: Session,
        settings: JsonSettingsStore,
        interval_ms: int = POLL_INTERVAL_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._runner = runner
        self._session = session
        self._settings = settings
        self._unread = 0
        self._latest: int | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)
        session.onlineChanged.connect(self._on_online_changed)

    @property
    def unread(self) -> int:
        return self._unread

    @property
    def active(self) -> bool:
        return self._session.online and self._session.user is not None

    def start(self) -> None:
        if self.active:
            self.poll()
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        try:
            self._session.onlineChanged.disconnect(self._on_online_changed)
        except (RuntimeError, TypeError):
            return

    def poll(self) -> None:
        if self.active:
            self._runner.run(self._api.inbox_summary, self._on_summary, self._on_error)

    # -- actions sur la boîte ------------------------------------------------------------

    def mark_read(self, ids: list[int] | None, on_done: Callable[[], None] | None = None) -> None:
        """`ids=None` : tout marquer comme lu."""
        self._apply(lambda: self._api.mark_read(ids), on_done)

    def delete(self, message_id: int, on_done: Callable[[], None] | None = None) -> None:
        self._apply(lambda: self._api.delete_message(message_id), on_done)

    def _apply(self, fn: Callable[[], dict[str, Any]], on_done: Callable[[], None] | None) -> None:
        def done(summary: dict[str, Any]) -> None:
            self._set_unread(int(summary["unread"]))
            self.changed.emit()
            if on_done is not None:
                on_done()

        self._runner.run(fn, done, self._on_error)

    # -- interne ----------------------------------------------------------------------------

    def _seen_key(self) -> str:
        return f"{SEEN_KEY}:{self._session.user_id}"

    def _on_summary(self, summary: dict[str, Any]) -> None:
        self._set_unread(int(summary["unread"]))
        latest = int(summary["latest_id"])
        if self._latest is None:
            stored = self._settings.get(self._seen_key(), 0)
            self._latest = stored if isinstance(stored, int) else 0
        if latest > self._latest:
            since = self._latest
            self._latest = latest
            self._remember(latest)
            self._runner.run(
                lambda: self._api.inbox(FETCH_LIMIT, unread_only=True),
                lambda messages: self._on_new(messages, since),
                self._on_error,
            )
        elif latest < self._latest:
            self._latest = latest
            self._remember(latest)

    def _on_new(self, messages: list[dict[str, Any]], since: int) -> None:
        fresh = [message for message in messages if int(message["id"]) > since]
        self.changed.emit()
        if fresh:
            self.received.emit(fresh)

    def _remember(self, latest: int) -> None:
        self._settings.set(self._seen_key(), latest)
        try:
            self._settings.save()
        except OSError:
            return

    def _set_unread(self, unread: int) -> None:
        if unread != self._unread:
            self._unread = unread
            self.unreadChanged.emit(unread)

    def _on_error(self, error: Exception) -> None:
        """En arrière-plan, on reste discret : hors ligne -> pastille, session expirée -> reconnexion."""
        if isinstance(error, SessionExpired):
            self._session.expired.emit(str(error))
        elif isinstance(error, NetworkError):
            self._session.set_online(False)

    def _on_online_changed(self, online: bool) -> None:
        if online and self._session.user is not None:
            self.start()
        else:
            self._timer.stop()
