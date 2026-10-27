"""Implémentation de ToolHost : ce que la plateforme offre aux outils.

Découplé de la fenêtre par des signaux : un outil ne touche jamais au shell.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from syncron_client.api.client import ApiClient
from syncron_client.api.errors import ApiError, NetworkError, SessionExpired
from syncron_client.catalog_store import CatalogStore
from syncron_client.paths import AppPaths, ToolPaths
from syncron_client.platform.tool import NotifyLevel
from syncron_client.session import Session
from syncron_client.tasks import TaskRunner


class ShellHost(QObject):
    notified = Signal(str, str)  # message, NotifyLevel
    statusChanged = Signal(str)  # tool_id
    openRequested = Signal(str, str)  # tool_id, key ("" = aucune)

    def __init__(
        self,
        paths: AppPaths,
        api: ApiClient,
        session: Session,
        runner: TaskRunner,
        catalog: CatalogStore,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._paths = paths
        self._api = api
        self._session = session
        self._runner = runner
        self._catalog = catalog

    @property
    def app_paths(self) -> AppPaths:
        return self._paths

    @property
    def api(self) -> ApiClient:
        return self._api

    @property
    def session(self) -> Session:
        return self._session

    @property
    def runner(self) -> TaskRunner:
        return self._runner

    @property
    def catalog(self) -> CatalogStore:
        return self._catalog

    def tool_paths(self, tool_id: str) -> ToolPaths:
        return self._paths.for_tool(tool_id)

    def notify(self, message: str, level: NotifyLevel = NotifyLevel.INFO) -> None:
        self.notified.emit(message, str(level))

    def handle_error(self, error: Exception, context: str = "") -> None:
        """Point unique de traitement des erreurs réseau : session expirée, hors ligne, refus métier."""
        prefix = f"{context} : " if context else ""
        if isinstance(error, SessionExpired):
            self._session.expired.emit(str(error))
        elif isinstance(error, NetworkError):
            self._session.set_online(False)
            self.notify(f"{prefix}{error}", NotifyLevel.WARNING)
        elif isinstance(error, ApiError):
            self.notify(f"{prefix}{error.message}", NotifyLevel.ERROR)
        else:
            self.notify(f"{prefix}{error}", NotifyLevel.ERROR)

    def status_changed(self, tool_id: str) -> None:
        self.statusChanged.emit(tool_id)

    def open_tool(self, tool_id: str, key: str | None = None) -> None:
        self.openRequested.emit(tool_id, key or "")
