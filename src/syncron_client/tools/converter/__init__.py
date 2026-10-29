"""Outil Convertisseur : quantités en stacks, lignes, coffres et doubles coffres. Entièrement local."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QWidget

from syncron_client.platform.tool import NotifyLevel, Tool, ToolHost, ToolInfo
from syncron_client.settings import JsonSettingsStore
from syncron_client.tools.converter.page import ConverterPage
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS

PREFERENCES_KEY = "preferences"


class ConverterTool(Tool):
    _INFO = ToolInfo(
        id="converter",
        name="Convertisseur",
        description="Stacks (64), lignes (576), coffres (1 728), doubles coffres (3 456) : division ou unité unique.",
        icon="convert",
        version="4.3.0",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._settings: JsonSettingsStore | None = None
        self._page: ConverterPage | None = None
        self._actions: list[QAction] = []

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> ConverterPage | None:
        return self._page

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._settings = JsonSettingsStore(host.tool_paths(self.info.id).user_dir / "settings.json")

    def create_page(self) -> QWidget:
        stored = self._settings.get(PREFERENCES_KEY, {})
        self._page = ConverterPage(stored if isinstance(stored, dict) else {})
        self._page.settingsChanged.connect(lambda preferences: self._settings.set(PREFERENCES_KEY, preferences))
        copy = QAction(icons.icon("copy", COLORS.text_muted, 16), "Copier", self._page)
        copy.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        copy.setToolTip("Copier le résultat  (Ctrl+Shift+C)")
        copy.triggered.connect(self._copy)
        self._page.addAction(copy)
        self._actions = [copy]
        return self._page

    def activated(self) -> None:
        if self._page is not None:
            self._page.focus_input()

    def open(self, key: str) -> None:
        """`key` : une quantité à convertir (« 2000 », « 3 coffres »…)."""
        if self._page is not None:
            self._page.set_quantity(key)

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def shutdown(self) -> None:
        try:
            self._settings.save()
        except OSError as exc:
            self._host.notify(f"Préférences du convertisseur non enregistrées : {exc}", NotifyLevel.ERROR)

    def _copy(self) -> None:
        if self._page is not None and self._page.copy():
            self._host.notify("Résultat copié.", NotifyLevel.SUCCESS)
