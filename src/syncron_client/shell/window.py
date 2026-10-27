"""Fenêtre principale de la plateforme : navigation entre l'accueil, les outils et les paramètres."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QPixmap, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from syncron_client.platform.registry import ToolRegistry
from syncron_client.platform.tool import NotifyLevel, ToolStage
from syncron_client.settings import JsonSettingsStore
from syncron_client.shell.command_palette import CommandPalette
from syncron_client.shell.home_page import HomePage
from syncron_client.shell.host import ShellHost
from syncron_client.shell.settings_page import SettingsPage
from syncron_client.shell.sidebar import HOME_ID, SETTINGS_ID, Sidebar
from syncron_client.shell.toast import Toast
from syncron_client.shell.top_bar import TopBar
from syncron_core import APP_DISPLAY_NAME

MIN_SIZE = (1120, 720)


class ShellWindow(QMainWindow):
    logoutRequested = Signal()

    def __init__(self, registry: ToolRegistry, host: ShellHost, settings: JsonSettingsStore, parent=None):
        super().__init__(parent)
        self._registry = registry
        self._host = host
        self._settings = settings
        self._pages: dict[str, QWidget] = {}
        self._current: str | None = None

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setMinimumSize(*MIN_SIZE)
        self.resize(1380, 860)

        self._sidebar = Sidebar()
        self._top_bar = TopBar()
        self._stack = QStackedWidget()
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._top_bar)
        right_layout.addWidget(self._stack, 1)
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar)
        layout.addWidget(right, 1)
        self.setCentralWidget(central)

        self._home = HomePage(registry)
        self._add_page(HOME_ID, self._home)
        self._settings_page = SettingsPage(host, registry, settings)
        self._add_page(SETTINGS_ID, self._settings_page)
        for tool in registry:
            planned = tool.info.stage is ToolStage.PLANNED
            manage = tool.info.min_role is not None
            self._sidebar.add_tool(tool.info.id, tool.info.name, tool.info.icon, planned, manage)
            self._sidebar.set_status(tool.info.id, tool.status())

        self._toast = Toast(self)
        self._palette = CommandPalette(registry, self)

        self._sidebar.navigate.connect(self.show_page)
        self._home.openRequested.connect(self.show_page)
        self._top_bar.searchRequested.connect(self._palette.open_centered)
        self._palette.hitChosen.connect(self.open_in_tool)
        host.notified.connect(lambda message, level: self._toast.show_message(message, NotifyLevel(level)))
        host.statusChanged.connect(self._refresh_status)
        host.openRequested.connect(lambda tool_id, key: self.open_in_tool(tool_id, key or None))
        self._sidebar.account.logoutRequested.connect(self.logoutRequested)
        self._settings_page.logoutRequested.connect(self.logoutRequested)
        self._top_bar.retryRequested.connect(self.retry_connection)
        host.session.onlineChanged.connect(self._on_online_changed)
        self._install_shortcuts()
        self._refresh_account()
        self._on_online_changed(host.session.online)

        self._restore_state()

    # -- navigation --------------------------------------------------------------

    @property
    def current_page(self) -> str | None:
        return self._current

    def show_page(self, page_id: str) -> None:
        if page_id == self._current:
            return
        if page_id not in self._pages and page_id not in self._registry:
            page_id = HOME_ID
        if self._current in self._registry:
            self._registry.get(self._current).deactivated()
        if page_id in self._registry:
            tool = self._registry.get(page_id)
            if page_id not in self._pages:
                self._add_page(page_id, tool.create_page())
            self._top_bar.set_page(tool.info.name, tool.info.description, tool.page_actions())
            tool.activated()
        elif page_id == HOME_ID:
            self._home.refresh()
            self._top_bar.set_page("Accueil", "Vue d'ensemble de tes outils")
        else:
            self._settings_page.refresh()
            self._top_bar.set_page("Paramètres", "Compte, serveur, stockage local, à propos")
        self._stack.setCurrentWidget(self._pages[page_id])
        self._sidebar.set_current(page_id)
        self._current = page_id

    def open_in_tool(self, tool_id: str, key: str | None = None) -> None:
        if tool_id not in self._registry:
            return
        self.show_page(tool_id)
        if key:
            self._registry.get(tool_id).open(key)

    def open_search(self) -> None:
        self._palette.open_centered()

    def retry_connection(self) -> None:
        """Hors ligne -> nouvelle tentative : si le serveur répond, on repasse en ligne et on synchronise."""
        host = self._host

        def done(_user) -> None:
            host.session.set_user(_user)
            host.session.set_online(True)
            host.catalog.sync()
            host.notify("Connexion rétablie.", NotifyLevel.SUCCESS)

        def failed(error: Exception) -> None:
            host.handle_error(error, "Toujours hors ligne")

        token = host.api.refresh_token
        if token:
            host.runner.run(lambda: host.api.resume(token), done, failed)
        else:
            host.session.expired.emit("Connecte-toi pour retrouver tes données à jour.")

    @property
    def top_bar(self) -> TopBar:
        return self._top_bar

    @property
    def sidebar(self) -> Sidebar:
        return self._sidebar

    @property
    def palette(self) -> CommandPalette:
        return self._palette

    @property
    def toast(self) -> Toast:
        return self._toast

    # -- interne -----------------------------------------------------------------

    def _add_page(self, page_id: str, page: QWidget) -> None:
        self._pages[page_id] = page
        self._stack.addWidget(page)

    def _refresh_account(self) -> None:
        session = self._host.session
        self._sidebar.account.set_account(session.display_name, session.role.label, session.online)
        avatar = (session.user or {}).get("avatar_url")
        if avatar and session.online:

            def show(content: bytes) -> None:
                pixmap = QPixmap()
                if pixmap.loadFromData(content):
                    self._sidebar.account.set_avatar(pixmap)

            self._host.runner.run(lambda: self._host.api.download(avatar), show, lambda _error: None)

    def _on_online_changed(self, online: bool) -> None:
        self._top_bar.set_offline(not online)
        self._refresh_account()

    def _refresh_status(self, tool_id: str) -> None:
        if tool_id in self._registry:
            self._sidebar.set_status(tool_id, self._registry.get(tool_id).status())
            self._home.refresh(tool_id)

    def _install_shortcuts(self) -> None:
        search = QAction(self)
        search.setShortcut(QKeySequence("Ctrl+K"))
        search.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        search.triggered.connect(self.open_search)
        self.addAction(search)
        targets = [HOME_ID, *(tool.info.id for tool in self._registry)]
        for index, page_id in enumerate(targets[:9]):
            jump = QAction(self)
            jump.setShortcut(QKeySequence(f"Ctrl+{index + 1}"))
            jump.triggered.connect(lambda _checked=False, target=page_id: self.show_page(target))
            self.addAction(jump)

    def _restore_state(self) -> None:
        geometry = self._settings.get("window_geometry")
        if isinstance(geometry, str):
            self.restoreGeometry(QByteArray.fromHex(geometry.encode("ascii")))
        last_page = self._settings.get("last_page", HOME_ID)
        self.show_page(last_page if isinstance(last_page, str) else HOME_ID)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._toast.reposition()

    def closeEvent(self, event: QCloseEvent) -> None:
        for tool in self._registry:
            tool.shutdown()
        self._settings.set("window_geometry", bytes(self.saveGeometry().toHex()).decode("ascii"))
        self._settings.set("last_page", self._current or HOME_ID)
        try:
            self._settings.save()
        except OSError:
            self._host.notify("Préférences de la fenêtre non enregistrées.", NotifyLevel.ERROR)
        super().closeEvent(event)
