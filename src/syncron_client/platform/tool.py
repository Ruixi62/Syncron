"""Contrat d'un outil de la plateforme.

Cycle de vie, piloté par le shell :

    setup(host)      au démarrage : chargement des données (rapide, sans UI)
    create_page()    à la première ouverture : construction de l'interface
    activated()      à chaque fois que l'outil devient visible
    deactivated()    quand l'utilisateur change d'outil
    shutdown()       à la fermeture : sauvegarde de l'état

Points d'intégration optionnels (méthodes à redéfinir si utiles) :
    page_actions()   boutons affichés dans la barre du haut quand l'outil est actif
    status()         pastille dans la barre latérale (ex. erreurs de données)
    search()/open()  résultats dans la recherche globale (Ctrl+K)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import QWidget

from syncron_client.paths import AppPaths, ToolPaths

if TYPE_CHECKING:
    from syncron_client.api.client import ApiClient
    from syncron_client.catalog_store import CatalogStore
    from syncron_client.session import Session
    from syncron_client.tasks import TaskRunner


class StatusLevel(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class ToolStage(StrEnum):
    """Maturité d'un outil : AVAILABLE = utilisable ; PLANNED = annoncé, en attente de développement."""

    AVAILABLE = "available"
    PLANNED = "planned"


class NotifyLevel(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ToolInfo:
    id: str
    name: str
    description: str
    icon: str
    version: str = "1.0.0"
    stage: ToolStage = ToolStage.AVAILABLE
    roadmap: tuple[str, ...] = ()
    min_role: str | None = None


@dataclass(frozen=True, slots=True)
class ToolStatus:
    level: StatusLevel = StatusLevel.OK
    message: str = ""
    badge: str = ""


@dataclass(frozen=True, slots=True)
class SearchHit:
    tool_id: str
    key: str
    title: str
    subtitle: str = ""
    pixmap: QPixmap | None = None


class ToolHost(Protocol):
    """Services offerts par la plateforme à chaque outil."""

    @property
    def app_paths(self) -> AppPaths: ...

    @property
    def api(self) -> ApiClient: ...

    @property
    def session(self) -> Session: ...

    @property
    def runner(self) -> TaskRunner: ...

    @property
    def catalog(self) -> CatalogStore: ...

    def handle_error(self, error: Exception, context: str = "") -> None: ...

    def tool_paths(self, tool_id: str) -> ToolPaths: ...

    def notify(self, message: str, level: NotifyLevel = NotifyLevel.INFO) -> None: ...

    def status_changed(self, tool_id: str) -> None: ...

    def open_tool(self, tool_id: str, key: str | None = None) -> None: ...


class Tool(ABC):
    @property
    @abstractmethod
    def info(self) -> ToolInfo:
        """Identité de l'outil (id unique, nom, icône du design system)."""

    @abstractmethod
    def setup(self, host: ToolHost) -> None:
        """Chargement des données. Appelé une fois, avant toute autre méthode."""

    @abstractmethod
    def create_page(self) -> QWidget:
        """Construit la page de l'outil. Appelé une fois, à la première ouverture."""

    def page_actions(self) -> Sequence[QAction]:
        return ()

    def status(self) -> ToolStatus:
        return ToolStatus()

    def search(self, query: str, limit: int) -> Sequence[SearchHit]:
        return ()

    def open(self, key: str) -> None:
        """Affiche l'élément `key` d'un SearchHit. La page existe déjà."""

    def activated(self) -> None:
        """L'outil devient visible."""

    def deactivated(self) -> None:
        """L'outil est masqué."""

    def shutdown(self) -> None:
        """Fermeture de l'application : sauvegarder l'état."""
