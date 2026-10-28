"""Outil R&D : domaines de recherche du pays (global, militaire, ressources, industrie, technologie).

Chaque domaine a ses paliers ; chaque palier, ses conditions et ses
récompenses. Lecture pour tous ; progression et contenu gérés dans
l'Administration, section « R&D ». Dernier état gardé sur le disque pour le
hors-ligne.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget

from syncron_client.platform.admin import AdminSection, admin_link
from syncron_client.platform.tool import StatusLevel, Tool, ToolHost, ToolInfo, ToolStatus
from syncron_client.tools.research.admin import ResearchAdmin
from syncron_client.tools.research.model import Domain, parse_domains
from syncron_client.tools.research.page import ResearchPage
from syncron_client.ui import icons
from syncron_client.ui.item_icons import IconProvider
from syncron_client.ui.theme import COLORS
from syncron_core.catalog import CraftRepository
from syncron_core.catalog_service import CatalogService

DOMAINS_SECTION = "research.domains"
CACHE_FILE = "research.json"


class ResearchTool(Tool):
    _INFO = ToolInfo(
        id="research",
        name="R&D",
        description="Les cinq domaines de recherche du pays : paliers, conditions, récompenses et avancement.",
        icon="flask",
        version="4.1.0",
        system="research",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._page: ResearchPage | None = None
        self._admin: ResearchAdmin | None = None
        self._domains: list[Domain] = []
        self._repository = CraftRepository()
        self._catalog = CatalogService(self._repository)
        self._icons: IconProvider | None = None
        self._actions: list[QAction] = []

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> ResearchPage | None:
        return self._page

    @property
    def admin(self) -> ResearchAdmin | None:
        return self._admin

    @property
    def domains(self) -> list[Domain]:
        return self._domains

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._cache_path = host.tool_paths(self.info.id).user_dir / CACHE_FILE
        self._repository.replace(host.catalog.data)
        self._icons = IconProvider(self._catalog, host.catalog)
        host.catalog.changed.connect(self._on_catalog_changed)
        try:
            self._domains = parse_domains(json.loads(self._cache_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError):
            self._domains = []

    def create_page(self) -> QWidget:
        self._page = ResearchPage(self._catalog, self._icons)
        self._page.manageRequested.connect(lambda key: self._host.open_tool("admin", admin_link(DOMAINS_SECTION, key)))
        self._page.set_editable(self._host.session.can_manage(self.info.system))
        self._page.set_domains(self._domains)
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Recharger la R&D")
        refresh.triggered.connect(self.refresh)
        self._actions = [refresh]
        return self._page

    def activated(self) -> None:
        if self._page is not None:
            self._page.set_editable(self._host.session.can_manage(self.info.system))
        self.refresh()

    def refresh(self) -> None:
        if not self._host.session.online:
            return

        def done(document: dict[str, Any]) -> None:
            self._store(document)
            self._apply(parse_domains(document))

        self._host.catalog.sync()
        self._host.runner.run(self._host.api.research, done, lambda error: self._host.handle_error(error, "R&D"))

    def open(self, key: str) -> None:
        """« militaire » ou « militaire:5 » (lien d'un message)."""
        if self._page is None:
            return
        domain_id, _, level = key.partition(":")
        self._page.select(domain_id, int(level) if level.isdigit() else None)

    def status(self) -> ToolStatus:
        active = next((d for d in self._domains if d.active), None)
        if active is None:
            return ToolStatus()
        return ToolStatus(StatusLevel.INFO, f"{active.name} : palier {active.completed + 1} en cours")

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def admin_sections(self) -> Sequence[AdminSection]:
        return [AdminSection(DOMAINS_SECTION, "Domaines et paliers", "flask", self._create_admin)]

    def shutdown(self) -> None:
        try:
            self._host.catalog.changed.disconnect(self._on_catalog_changed)
        except (RuntimeError, TypeError):
            return

    # -- interne ---------------------------------------------------------------------------

    def _apply(self, domains: list[Domain]) -> None:
        self._domains = domains
        if self._page is not None:
            self._page.set_domains(domains)
        self._host.status_changed(self.info.id)

    def _store(self, document: dict[str, Any]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        except OSError:
            return

    def _create_admin(self) -> ResearchAdmin:
        self._admin = ResearchAdmin(self._host, self._catalog)
        self._admin.changed.connect(self._apply)
        return self._admin

    def _on_catalog_changed(self, _revision: int) -> None:
        self._repository.replace(self._host.catalog.data)
        self._icons.clear()
        if self._page is not None:
            self._page.refresh_catalog()
