"""Outil Administration : découpé par système.

    GÉNÉRAL      Vue d'ensemble · Comptes (administrateurs) · Journal
    CRAFT        écrans fournis par l'outil Craft
    R&D          écrans fournis par l'outil R&D
    CALENDRIER   …
    MESSAGERIE   …

Chaque outil fournit ses écrans (`Tool.admin_sections()`) ; un éditeur ne voit
que les systèmes qui lui sont confiés, un administrateur les voit tous.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from syncron_client.platform.admin import AdminSection
from syncron_client.platform.tool import Placement, Tool, ToolHost, ToolInfo
from syncron_client.tools.admin.audit import AuditView
from syncron_client.tools.admin.overview import OverviewView
from syncron_client.tools.admin.users import UsersView
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, label

OVERVIEW = "admin.overview"
USERS = "admin.users"
AUDIT = "admin.audit"
KEY_ROLE = Qt.ItemDataRole.UserRole + 1
NAV_WIDTH = 230


@dataclass(frozen=True, slots=True)
class SectionGroup:
    title: str
    system: str | None
    sections: tuple[AdminSection, ...]


class AdminPage(QWidget):
    def __init__(self, host: ToolHost, groups: list[SectionGroup], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._groups = groups
        self._sections: dict[str, AdminSection] = {}
        self._widgets: dict[str, QWidget] = {}
        self._first_of_system: dict[str, str] = {}

        self.nav = QListWidget()
        self.nav.setIconSize(QSize(17, 17))
        self.nav.setStyleSheet("QListWidget::item { padding: 7px 8px; border-radius: 8px; }")
        heading_font = QFont(self.nav.font())
        heading_font.setPixelSize(11)
        heading_font.setWeight(QFont.Weight.DemiBold)
        for index, group in enumerate(groups):
            header = QListWidgetItem(group.title.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setFont(heading_font)
            header.setForeground(QColor(COLORS.text_faint))
            if index:
                header.setSizeHint(QSize(0, 40))
            self.nav.addItem(header)
            for section in group.sections:
                self._sections[section.key] = section
                if group.system and group.system not in self._first_of_system:
                    self._first_of_system[group.system] = section.key
                item = QListWidgetItem(icons.icon(section.icon, COLORS.text_muted, 17, COLORS.accent), section.title)
                item.setData(KEY_ROLE, section.key)
                self.nav.addItem(item)
        self.nav.currentItemChanged.connect(self._on_nav)
        nav_card = Card(padding=10, spacing=0)
        nav_card.setFixedWidth(NAV_WIDTH)
        nav_card.body.addWidget(self.nav)

        self._title = label("", "heading")
        self._stack = QStackedWidget()
        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(self._title)
        right.addWidget(self._stack, 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(16)
        layout.addWidget(nav_card)
        layout.addLayout(right, 1)

    # -- navigation -----------------------------------------------------------------------

    @property
    def section_keys(self) -> list[str]:
        return list(self._sections)

    @property
    def current_key(self) -> str | None:
        item = self.nav.currentItem()
        return item.data(KEY_ROLE) if item else None

    def section(self, key: str) -> QWidget | None:
        """Écran déjà construit (None s'il n'a jamais été affiché)."""
        return self._widgets.get(key)

    def show_section(self, key: str, item_key: str | None = None) -> QWidget | None:
        if key not in self._sections:
            return None
        if self.current_key != key:
            for row in range(self.nav.count()):
                if self.nav.item(row).data(KEY_ROLE) == key:
                    self.nav.blockSignals(True)
                    self.nav.setCurrentRow(row)
                    self.nav.blockSignals(False)
                    break
        widget = self._widget(key)
        self._title.setText(self._sections[key].title)
        self._stack.setCurrentWidget(widget)
        self.refresh_current()
        if item_key and hasattr(widget, "open_key"):
            widget.open_key(item_key)
        return widget

    def show_system(self, system: str) -> None:
        key = self._first_of_system.get(system)
        if key is not None:
            self.show_section(key)

    def refresh_current(self) -> None:
        widget = self._stack.currentWidget()
        if widget is not None and hasattr(widget, "refresh"):
            widget.refresh()

    def _widget(self, key: str) -> QWidget:
        if key not in self._widgets:
            widget = self._sections[key].factory()
            self._widgets[key] = widget
            self._stack.addWidget(widget)
            if isinstance(widget, OverviewView):
                widget.manageRequested.connect(self.show_system)
        return self._widgets[key]

    def _on_nav(self, current: QListWidgetItem | None, _previous) -> None:
        if current is not None and current.data(KEY_ROLE):
            self.show_section(current.data(KEY_ROLE))


class AdminTool(Tool):
    _INFO = ToolInfo(
        id="admin",
        name="Administration",
        description="Gestion de chaque système du pays, des comptes et du journal.",
        icon="shield",
        version="4.1.0",
        min_role="editor",
        placement=Placement.MANAGE,
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
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

    def groups(self) -> list[SectionGroup]:
        session = self._host.session
        managed = {system: name for system, name in session.systems.items() if session.can_manage(system)}
        journal = dict(managed)
        general = [AdminSection(OVERVIEW, "Vue d'ensemble", "grid", lambda: OverviewView(self._host))]
        if session.has_role("admin"):
            general.append(AdminSection(USERS, "Comptes", "users", lambda: UsersView(self._host, session.systems)))
            journal["accounts"] = "Comptes"
        general.append(AdminSection(AUDIT, "Journal", "history", lambda: AuditView(self._host, journal)))
        groups = [SectionGroup("Général", None, tuple(general))]
        tools = sorted(self._host.tools(), key=lambda tool: tool.info.placement is Placement.MAIN)
        for tool in tools:
            system = tool.info.system
            if system and session.can_manage(system):
                sections = tuple(tool.admin_sections())
                if sections:
                    groups.append(SectionGroup(tool.info.name, system, sections))
        return groups

    def create_page(self) -> QWidget:
        self._page = AdminPage(self._host, self.groups())
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Recharger les données du serveur")
        refresh.triggered.connect(self._refresh)
        self._actions = [refresh]
        self._page.show_section(OVERVIEW)
        return self._page

    def activated(self) -> None:
        if self._page is not None:
            self._page.refresh_current()

    def open(self, key: str) -> None:
        """« section » ou « section|élément » (voir platform.admin.admin_link)."""
        if self._page is not None:
            section, _, item = key.partition("|")
            self._page.show_section(section, item or None)

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def _refresh(self) -> None:
        self._host.catalog.sync()
        if self._page is not None:
            self._page.refresh_current()
