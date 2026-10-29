"""Intégration de l'outil Craft dans la plateforme.

Le catalogue vient du serveur (CatalogStore) ; le calcul est fait localement
par le moteur de syncron_core : instantané, et disponible hors ligne sur le
dernier catalogue reçu. La gestion du catalogue (objets, ateliers,
compétences, import / export) est fournie à l'Administration par
`admin_sections()`.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QWidget

from syncron_client.platform.admin import AdminSection
from syncron_client.platform.tool import NotifyLevel, SearchHit, Tool, ToolHost, ToolInfo
from syncron_client.settings import JsonSettingsStore
from syncron_client.tools.craft.admin import CraftAdmin
from syncron_client.tools.craft.admin.context import CraftAdminContext
from syncron_client.tools.craft.ui.craft_page import CraftPage
from syncron_client.ui import icons
from syncron_client.ui.item_icons import IconProvider
from syncron_client.ui.theme import COLORS
from syncron_core.calculator import CraftCalculator
from syncron_core.catalog import CraftRepository
from syncron_core.catalog_service import CatalogService
from syncron_core.exporters.registry import default_registry

SEARCH_ICON_SIZE = 28


class CraftTool(Tool):
    _INFO = ToolInfo(
        id="craft",
        name="Craft",
        description="Ressources, étapes, ateliers, prérequis et temps de fabrication.",
        icon="hammer",
        version="4.3.0",
        system="craft",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._repository = CraftRepository()
        self._catalog = CatalogService(self._repository)
        self._calculator = CraftCalculator(self._repository)
        self._exporters = default_registry()
        self._settings: JsonSettingsStore | None = None
        self._icons: IconProvider | None = None
        self._page: CraftPage | None = None
        self._actions: list[QAction] = []
        self._export_actions: list[QAction] = []
        self._admin: CraftAdmin | None = None

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def catalog(self) -> CatalogService:
        return self._catalog

    @property
    def page(self) -> CraftPage | None:
        return self._page

    @property
    def admin(self) -> CraftAdmin | None:
        return self._admin

    # -- cycle de vie ------------------------------------------------------------

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._settings = JsonSettingsStore(host.tool_paths(self.info.id).user_dir / "settings.json")
        self._icons = IconProvider(self._catalog, host.catalog)
        self._repository.replace(host.catalog.data)
        host.catalog.changed.connect(self._on_catalog_changed)
        host.catalog.imagesUpdated.connect(self._on_images_updated)

    def create_page(self) -> QWidget:
        self._page = CraftPage(
            self._catalog, self._calculator, self._exporters, self._settings, self._host, self._icons
        )
        self._page.planChanged.connect(self._on_plan_changed)
        self._actions = self._build_actions(self._page)
        self._on_plan_changed(self._page.detail_panel.plan)
        return self._page

    def activated(self) -> None:
        self.refresh()

    def shutdown(self) -> None:
        self._host.catalog.changed.disconnect(self._on_catalog_changed)
        self._host.catalog.imagesUpdated.disconnect(self._on_images_updated)
        if self._page is not None:
            try:
                self._page.save_state()
            except OSError as exc:
                self._host.notify(f"Préférences Craft non enregistrées : {exc}", NotifyLevel.ERROR)

    # -- intégration plateforme --------------------------------------------------

    def admin_sections(self) -> Sequence[AdminSection]:
        if self._admin is None:
            self._admin = CraftAdmin(CraftAdminContext(self._host))
        return self._admin.sections()

    def page_actions(self) -> Sequence[QAction]:
        return [action for action in self._actions if action.text()]

    def search(self, query: str, limit: int) -> Sequence[SearchHit]:
        hits = []
        for item in self._catalog.search(query)[:limit]:
            subtitle = "Ressource primaire" if item.recipe is None else self._catalog.station_name(item.station_id)
            pixmap = self._icons.item_pixmap(item.id, SEARCH_ICON_SIZE)
            hits.append(SearchHit(self.info.id, item.id, item.name, subtitle, pixmap))
        return hits

    def open(self, key: str) -> None:
        if self._page is not None:
            self._page.open_item(key)

    def refresh(self) -> None:
        def done(changed: bool) -> None:
            if changed:
                self._host.notify(
                    f"Catalogue mis à jour (révision {self._host.catalog.revision}).", NotifyLevel.SUCCESS
                )

        self._host.catalog.sync(done)

    # -- interne -----------------------------------------------------------------

    def _on_catalog_changed(self, _revision: int) -> None:
        self._repository.replace(self._host.catalog.data)
        if self._page is not None:
            self._page.data_changed()
        if self._admin is not None:
            self._admin.data_changed()

    def _on_images_updated(self) -> None:
        if self._page is not None:
            self._page.images_changed()
        else:
            self._icons.clear()
        if self._admin is not None:
            self._admin.data_changed()

    def _build_actions(self, page: CraftPage) -> list[QAction]:
        def action(text: str, icon_name: str, slot, shortcut: str | None = None, tip: str = "") -> QAction:
            created = QAction(icons.icon(icon_name, COLORS.text_muted, 16), text, page)
            created.triggered.connect(slot)
            if shortcut:
                created.setShortcut(QKeySequence(shortcut))
                created.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            created.setToolTip(f"{tip or text}" + (f"  ({shortcut})" if shortcut else ""))
            page.addAction(created)
            return created

        self._export_actions = [
            action("TXT", "download", lambda: page.export_plan("txt"), "Ctrl+E", "Exporter en texte"),
            action("JSON", "download", lambda: page.export_plan("json"), "Ctrl+Shift+E", "Exporter en JSON"),
            action("Copier", "copy", page.copy_raw_materials, "Ctrl+Shift+C", "Copier les ressources"),
        ]
        return [
            *self._export_actions,
            action("Actualiser", "refresh", self.refresh, "F5", "Récupérer la dernière version du catalogue"),
            action("", "search", page.catalog_panel.focus_search, "Ctrl+F", "Rechercher dans le catalogue"),
            action("", "edit", page.detail_panel.focus_quantity, "Ctrl+L", "Modifier la quantité"),
        ]

    def _on_plan_changed(self, plan) -> None:
        for exported in self._export_actions:
            exported.setEnabled(plan is not None)
