"""Outil « rubrique » : regroupe d'autres outils dans des onglets, avec sa propre page d'accueil.

Exemple : Pays = Accueil du pays · R&D · Membres · Banque. Chaque outil regroupé garde tout
ce qui fait un outil (données, liens des messages, recherche, écrans d'administration) ; il
déclare seulement `ToolInfo.parent`. La barre latérale et l'accueil n'affichent que la rubrique.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from syncron_client.platform.tool import StatusLevel, Tool, ToolHost, ToolStatus
from syncron_client.ui.widgets import SegmentedControl

HOME_TAB = ""


class HubPage(QWidget):
    childChanged = Signal(str)  # identifiant de l'outil affiché ("" : accueil de la rubrique)

    def __init__(self, home: QWidget, home_title: str, children: Sequence[Tool], parent: QWidget | None = None):
        super().__init__(parent)
        self._children = {tool.info.id: tool for tool in children}
        self._order = [HOME_TAB, *self._children]
        self._pages: dict[str, QWidget] = {HOME_TAB: home}
        self.tabs = SegmentedControl([(home_title, "home"), *((tool.info.name, tool.info.icon) for tool in children)])
        self.tabs.currentChanged.connect(lambda index: self.show(self._order[index]))
        self.stack = QStackedWidget()
        self.stack.addWidget(home)
        self._current = HOME_TAB
        bar = QHBoxLayout()
        bar.setContentsMargins(24, 14, 24, 0)
        bar.addWidget(self.tabs)
        bar.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(bar)
        layout.addWidget(self.stack, 1)

    @property
    def current(self) -> str:
        return self._current

    def page(self, tool_id: str) -> QWidget | None:
        return self._pages.get(tool_id)

    def show(self, tool_id: str) -> None:
        if tool_id not in self._order:
            return
        previous = self._children.get(self._current)
        if tool_id != self._current and previous is not None:
            previous.deactivated()
        if tool_id not in self._pages:
            page = self._children[tool_id].create_page()
            self._pages[tool_id] = page
            self.stack.addWidget(page)
        index = self._order.index(tool_id)
        if self.tabs.current_index() != index:
            self.tabs.blockSignals(True)
            self.tabs.set_current_index(index)
            self.tabs.blockSignals(False)
        self.stack.setCurrentWidget(self._pages[tool_id])
        self._current = tool_id
        self.childChanged.emit(tool_id)


class HubTool(Tool):
    """À redéfinir : `info`, `create_home()` (page d'accueil de la rubrique), `home_title`."""

    home_title = "Accueil"

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._page: HubPage | None = None

    @property
    def page(self) -> HubPage | None:
        return self._page

    def setup(self, host: ToolHost) -> None:
        self._host = host

    def children(self) -> list[Tool]:
        return [tool for tool in self._host.tools() if tool.info.parent == self.info.id]

    @abstractmethod
    def create_home(self) -> QWidget: ...

    def refresh_home(self) -> None:
        """Rafraîchit l'accueil de la rubrique (appelé à chaque affichage de l'onglet)."""

    def create_page(self) -> QWidget:
        self._page = HubPage(self.create_home(), self.home_title, self.children())
        self._page.childChanged.connect(self._on_child)
        return self._page

    def current_child(self) -> str:
        return self._page.current if self._page is not None else HOME_TAB

    def child(self, tool_id: str) -> Tool | None:
        return next((tool for tool in self.children() if tool.info.id == tool_id), None)

    def show_child(self, tool_id: str) -> None:
        if self._page is not None:
            self._page.show(tool_id)

    def activated(self) -> None:
        self._on_child(self.current_child())

    def deactivated(self) -> None:
        current = self.child(self.current_child())
        if current is not None:
            current.deactivated()

    def page_actions(self) -> Sequence[QAction]:
        current = self.child(self.current_child())
        return current.page_actions() if current is not None else []

    def status(self) -> ToolStatus:
        """Les pastilles des onglets s'additionnent sur la rubrique."""
        statuses = [tool.status() for tool in self.children()]
        badges = [int(status.badge) for status in statuses if status.badge.isdigit()]
        messages = [status.message for status in statuses if status.message]
        if not badges and not messages:
            return ToolStatus()
        return ToolStatus(StatusLevel.INFO, " · ".join(messages), str(sum(badges)) if badges else "")

    def _on_child(self, tool_id: str) -> None:
        current = self.child(tool_id)
        if current is not None:
            current.activated()
        else:
            self.refresh_home()
        self._host.status_changed(self.info.id)
