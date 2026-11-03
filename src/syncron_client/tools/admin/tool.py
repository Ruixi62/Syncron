"""Outil Administration : rubriques en haut, onglets de la rubrique dessous, écran en pleine largeur.

    [Vue d'ensemble] [Comptes] [Craft] [R&D] [Calendrier] [Messagerie] [NationsGlory] [Journal]
    Craft :  Objets · Ateliers · Compétences · Import / export
    ┌──────────────────────────────── écran ────────────────────────────────┐

Chaque outil fournit ses écrans (`Tool.admin_sections()`) ; un éditeur ne voit que les
rubriques des systèmes qui lui sont confiés, un administrateur les voit toutes, plus les comptes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from syncron_client.platform.admin import AdminSection
from syncron_client.platform.tool import Placement, Tool, ToolHost, ToolInfo
from syncron_client.tools.admin.audit import AuditView
from syncron_client.tools.admin.iris import IrisView
from syncron_client.tools.admin.nationsglory import NationsGloryView
from syncron_client.tools.admin.overview import SYSTEM_ICONS, OverviewView
from syncron_client.tools.admin.users import UsersView
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import FlowWidget, SegmentedControl, label

OVERVIEW = "admin.overview"
USERS = "admin.users"
AUDIT = "admin.audit"
NATIONSGLORY = "admin.nationsglory"
IRIS = "admin.iris"


@dataclass(frozen=True, slots=True)
class SectionGroup:
    key: str
    title: str
    icon: str
    system: str | None
    sections: tuple[AdminSection, ...]


class GroupTab(QPushButton):
    def __init__(self, group: SectionGroup, parent: QWidget | None = None) -> None:
        super().__init__(group.title.replace("&", "&&"), parent)
        self.group = group
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(icons.icon(group.icon, COLORS.text_muted, 16, COLORS.accent))
        self.setIconSize(QSize(16, 16))
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 10px; padding: 7px 10px;"
            f" color: {COLORS.text_muted}; font-weight: 500; }}"
            f"QPushButton:hover {{ background: {COLORS.surface_alt}; color: {COLORS.text}; }}"
            f"QPushButton:checked {{ background: {COLORS.accent_soft}; color: {COLORS.accent}; font-weight: 600; }}"
        )


class AdminPage(QWidget):
    def __init__(self, host: ToolHost, groups: list[SectionGroup], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._groups = {group.key: group for group in groups}
        self._sections: dict[str, AdminSection] = {}
        self._section_group: dict[str, str] = {}
        self._widgets: dict[str, QWidget] = {}
        self._current_key: str | None = None
        self._current_group: str | None = None

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self.tabs: dict[str, GroupTab] = {}
        tabs = FlowWidget(spacing=2)
        for group in groups:
            tab = GroupTab(group)
            tab.clicked.connect(lambda _checked=False, key=group.key: self.show_group(key))
            self._tab_group.addButton(tab)
            self.tabs[group.key] = tab
            tabs.add(tab)
            for section in group.sections:
                self._sections[section.key] = section
                self._section_group[section.key] = group.key

        self.subtitle = label("", "heading")
        self.subtabs = SegmentedControl()
        self.subtabs.currentChanged.connect(self._on_subtab)
        self._subtab_keys: list[str] = []
        sub_row = QHBoxLayout()
        sub_row.setSpacing(12)
        sub_row.addWidget(self.subtitle)
        sub_row.addWidget(self.subtabs)
        sub_row.addStretch(1)
        self._sub_row = QWidget()
        self._sub_row.setLayout(sub_row)
        sub_row.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(tabs)
        layout.addWidget(self._sub_row)
        layout.addWidget(self._stack, 1)

    # -- navigation -----------------------------------------------------------------------

    @property
    def section_keys(self) -> list[str]:
        return list(self._sections)

    @property
    def group_keys(self) -> list[str]:
        return list(self._groups)

    @property
    def current_key(self) -> str | None:
        return self._current_key

    @property
    def current_group(self) -> str | None:
        return self._current_group

    def section(self, key: str) -> QWidget | None:
        """Écran déjà construit (None s'il n'a jamais été affiché)."""
        return self._widgets.get(key)

    def show_group(self, group_key: str) -> QWidget | None:
        group = self._groups.get(group_key)
        if group is None or not group.sections:
            return None
        current_in_group = self._current_key if self._section_group.get(self._current_key or "") == group_key else None
        return self.show_section(current_in_group or group.sections[0].key)

    def show_section(self, key: str, item_key: str | None = None) -> QWidget | None:
        if key not in self._sections:
            return None
        group_key = self._section_group[key]
        if group_key != self._current_group:
            self._current_group = group_key
            self.tabs[group_key].setChecked(True)
            self._fill_subtabs(self._groups[group_key])
        if key in self._subtab_keys:
            index = self._subtab_keys.index(key)
            if self.subtabs.current_index() != index:
                self.subtabs.blockSignals(True)
                self.subtabs.set_current_index(index)
                self.subtabs.blockSignals(False)
        self._current_key = key
        widget = self._widget(key)
        self._stack.setCurrentWidget(widget)
        self.refresh_current()
        if item_key and hasattr(widget, "open_key"):
            widget.open_key(item_key)
        return widget

    def show_system(self, system: str) -> None:
        group = next((g for g in self._groups.values() if g.system == system), None)
        if group is not None:
            self.show_group(group.key)

    def refresh_current(self) -> None:
        widget = self._stack.currentWidget()
        if widget is not None and hasattr(widget, "refresh"):
            widget.refresh()

    def _fill_subtabs(self, group: SectionGroup) -> None:
        old = self.subtabs
        self.subtabs = SegmentedControl([(section.title, section.icon) for section in group.sections])
        self.subtabs.currentChanged.connect(self._on_subtab)
        self._sub_row.layout().replaceWidget(old, self.subtabs)
        old.hide()
        old.deleteLater()
        self._subtab_keys = [section.key for section in group.sections]
        multiple = len(group.sections) > 1
        self.subtabs.setVisible(multiple)
        self.subtitle.setText(group.title if multiple else group.sections[0].title)
        self.subtitle.setVisible(multiple or group.sections[0].title != group.title)
        self._sub_row.setVisible(multiple or self.subtitle.isVisible())

    def _on_subtab(self, index: int) -> None:
        if 0 <= index < len(self._subtab_keys):
            self.show_section(self._subtab_keys[index])

    def _widget(self, key: str) -> QWidget:
        if key not in self._widgets:
            widget = self._sections[key].factory()
            self._widgets[key] = widget
            self._stack.addWidget(widget)
            if isinstance(widget, OverviewView):
                widget.manageRequested.connect(self.show_system)
        return self._widgets[key]


class AdminTool(Tool):
    _INFO = ToolInfo(
        id="admin",
        name="Administration",
        description="Gestion de chaque système du pays, des comptes et du journal.",
        icon="shield",
        version="5.3.0",
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
        host = self._host
        managed = {system: name for system, name in session.systems.items() if session.can_manage(system)}
        journal = dict(managed)
        groups = [
            SectionGroup(
                "overview",
                "Vue d'ensemble",
                "grid",
                None,
                (AdminSection(OVERVIEW, "Vue d'ensemble", "grid", lambda: OverviewView(host)),),
            )
        ]
        if session.has_role("admin"):
            journal["accounts"] = "Comptes"
            groups.append(
                SectionGroup(
                    "accounts",
                    "Comptes",
                    "users",
                    "accounts",
                    (AdminSection(USERS, "Comptes", "users", lambda: UsersView(host, session.systems)),),
                )
            )
        tools = sorted(host.tools(), key=lambda tool: tool.info.placement is Placement.MAIN)
        for tool in tools:
            system = tool.info.system
            if system and session.can_manage(system):
                sections = tuple(tool.admin_sections())
                if sections:
                    groups.append(SectionGroup(system, tool.info.name, tool.info.icon, system, sections))
        if "nationsglory" in managed:
            groups.append(
                SectionGroup(
                    "nationsglory",
                    "NationsGlory",
                    SYSTEM_ICONS["nationsglory"],
                    "nationsglory",
                    (
                        AdminSection(IRIS, "Carte Iris", "map", lambda: IrisView(host)),
                        AdminSection(NATIONSGLORY, "API NationsGlory", "globe", lambda: NationsGloryView(host)),
                    ),
                )
            )
        groups.append(
            SectionGroup(
                "audit",
                "Journal",
                "history",
                None,
                (AdminSection(AUDIT, "Journal", "history", lambda: AuditView(host, journal)),),
            )
        )
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
