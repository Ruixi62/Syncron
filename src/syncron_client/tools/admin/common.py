"""Briques communes du mode admin : contexte, appels d'écriture, liste d'entités, mise en forme."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from syncron_client.api.errors import ApiError, NetworkError, SessionExpired
from syncron_client.platform.tool import NotifyLevel, ToolHost
from syncron_client.ui.item_icons import IconProvider
from syncron_client.ui.widgets import Banner, Card, SearchField, label
from syncron_core.catalog import CraftRepository
from syncron_core.catalog_service import CatalogService
from syncron_core.text import normalize

KEY_ROLE = Qt.ItemDataRole.UserRole + 1


class AdminContext:
    """Accès partagé par les vues : hôte, catalogue courant (index local), icônes."""

    def __init__(self, host: ToolHost) -> None:
        self.host = host
        self.repository = CraftRepository(host.catalog.data)
        self.catalog = CatalogService(self.repository)
        self.icons = IconProvider(self.catalog, host.catalog)

    @property
    def api(self):
        return self.host.api

    @property
    def is_admin(self) -> bool:
        return self.host.session.has_role("admin")

    def refresh_data(self) -> None:
        self.repository.replace(self.host.catalog.data)
        self.icons.clear()

    def call(
        self,
        fn: Callable[[], Any],
        on_done: Callable[[Any], None] | None = None,
        banner: Banner | None = None,
        success: str | None = None,
        sync: bool = False,
    ) -> None:
        """Appel API en arrière-plan. Erreur métier -> bannière locale ; réseau/session -> traitement global."""
        if banner is not None:
            banner.hide()

        def done(result: Any) -> None:
            if success:
                self.host.notify(success, NotifyLevel.SUCCESS)
            if sync:
                self.host.catalog.sync()
            if on_done is not None:
                on_done(result)

        def failed(error: Exception) -> None:
            if isinstance(error, (NetworkError, SessionExpired)) or not isinstance(error, ApiError):
                self.host.handle_error(error)
                return
            if banner is not None:
                banner.set_text(str(error))
                banner.show()
            else:
                self.host.notify(error.message, NotifyLevel.ERROR)

        self.host.runner.run(fn, done, failed)


class EntityList(Card):
    """Liste filtrable d'entités (objets, ateliers, compétences)."""

    selected = Signal(str)

    def __init__(self, title: str, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=14, spacing=10)
        self._count = label("", "faint")
        self._search = SearchField(placeholder)
        self._list = QListWidget()
        self._list.setIconSize(QSize(28, 28))
        self._list.setUniformItemSizes(True)
        self._list.setStyleSheet("QListWidget::item { padding: 6px 8px; border-radius: 8px; }")
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(label(title, "overline"))
        header.addWidget(self._count)
        self.body.addLayout(header)
        self.body.addWidget(self._search)
        self.body.addWidget(self._list, 1)
        self._search.textChanged.connect(self._filter)
        self._list.currentItemChanged.connect(self._on_current)
        self._suppress = False

    def set_entries(self, entries: list[tuple[str, str, str, QIcon | None]], keep: str | None = None) -> None:
        """entries : (clé, titre, sous-titre, icône)."""
        self._suppress = True
        self._list.clear()
        for key, title, subtitle, icon in entries:
            item = QListWidgetItem(f"{title}\n{subtitle}" if subtitle else title)
            item.setData(KEY_ROLE, key)
            item.setData(Qt.ItemDataRole.UserRole + 2, normalize(f"{title} {key}"))
            if icon is not None:
                item.setIcon(icon)
            self._list.addItem(item)
        self._count.setText(f"{len(entries)} élément(s)")
        self._filter(self._search.text())
        if keep:
            self.select(keep, emit=False)
        self._suppress = False

    def select(self, key: str, emit: bool = True) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(KEY_ROLE) == key:
                self._suppress = not emit
                self._list.setCurrentItem(item)
                self._suppress = False
                return

    def clear_selection(self) -> None:
        self._suppress = True
        self._list.setCurrentItem(None)
        self._list.clearSelection()
        self._suppress = False

    def current_key(self) -> str | None:
        item = self._list.currentItem()
        return item.data(KEY_ROLE) if item else None

    def count(self) -> int:
        return self._list.count()

    def _filter(self, text: str) -> None:
        tokens = normalize(text).split()
        for row in range(self._list.count()):
            item = self._list.item(row)
            haystack = item.data(Qt.ItemDataRole.UserRole + 2) or ""
            item.setHidden(not all(token in haystack for token in tokens))

    def _on_current(self, current: QListWidgetItem | None, _previous) -> None:
        if not self._suppress and current is not None:
            self.selected.emit(current.data(KEY_ROLE))


def format_datetime(value: str | None) -> str:
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return moment.astimezone().strftime("%d/%m/%Y %H:%M")
