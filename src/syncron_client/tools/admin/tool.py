"""Outil « Administration » : visible seulement pour les éditeurs et administrateurs."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from syncron_client.platform.tool import Tool, ToolHost, ToolInfo
from syncron_client.tools.admin.common import AdminContext
from syncron_client.tools.admin.editors import ItemEditor, SkillEditor, StationEditor
from syncron_client.tools.admin.views import AuditView, DashboardView, ImportExportView, UsersView
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import SegmentedControl


class AdminPage(QWidget):
    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.dashboard = DashboardView(context)
        self.items = ItemEditor(context, "OBJETS")
        self.stations = StationEditor(context, "ATELIERS")
        self.skills = SkillEditor(context, "COMPÉTENCES")
        self.audit = AuditView(context)
        self.transfer = ImportExportView(context)
        self.users = UsersView(context) if context.is_admin else None

        sections = [
            ("Tableau de bord", "grid", self.dashboard),
            ("Objets", "box", self.items),
            ("Ateliers", "station", self.stations),
            ("Compétences", "award", self.skills),
        ]
        if self.users is not None:
            sections.append(("Comptes", "users", self.users))
        sections += [("Journal", "history", self.audit), ("Import / export", "database", self.transfer)]
        self._views = [view for _text, _icon, view in sections]
        self.segments = SegmentedControl([(text, icon_name) for text, icon_name, _view in sections])
        self._stack = QStackedWidget()
        for view in self._views:
            self._stack.addWidget(view)
        self.segments.currentChanged.connect(self.show_section)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(self.segments)
        layout.addWidget(self._stack, 1)

    def show_section(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self.refresh_current()

    def refresh_current(self) -> None:
        view = self._views[self._stack.currentIndex()]
        if hasattr(view, "refresh"):
            view.refresh()
        elif hasattr(view, "reload"):
            view.reload()

    def data_changed(self) -> None:
        self.ctx.refresh_data()
        for editor in (self.items, self.stations, self.skills):
            editor.reload()
        if self._stack.currentWidget() in (self.dashboard, self.audit):
            self.refresh_current()


class AdminTool(Tool):
    _INFO = ToolInfo(
        id="admin",
        name="Administration",
        description="Catalogue, images, comptes, import / export et journal des modifications.",
        icon="shield",
        version="4.0.0",
        min_role="editor",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._context: AdminContext | None = None
        self._page: AdminPage | None = None
        self._actions: list[QAction] = []

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> AdminPage | None:
        return self._page

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._context = AdminContext(host)
        host.catalog.changed.connect(self._on_catalog_changed)
        host.catalog.imagesUpdated.connect(self._on_catalog_changed)

    def create_page(self) -> QWidget:
        self._page = AdminPage(self._context)
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Recharger les données du serveur")
        refresh.triggered.connect(self._refresh)
        self._actions = [refresh]
        self._page.data_changed()
        return self._page

    def activated(self) -> None:
        self._refresh()

    def shutdown(self) -> None:
        self._host.catalog.changed.disconnect(self._on_catalog_changed)
        self._host.catalog.imagesUpdated.disconnect(self._on_catalog_changed)
        self._page = None

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def _refresh(self) -> None:
        self._host.catalog.sync()
        if self._page is not None:
            self._page.refresh_current()

    def _on_catalog_changed(self, *_args) -> None:
        if self._page is not None:
            self._page.data_changed()
        elif self._context is not None:
            self._context.refresh_data()
