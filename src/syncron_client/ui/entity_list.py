"""Liste filtrable d'éléments (clé, titre, sous-titre, icône) : écrans de gestion."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from syncron_client.ui.widgets import Card, SearchField, label
from syncron_core.text import normalize

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
SEARCH_ROLE = Qt.ItemDataRole.UserRole + 2


class EntityList(Card):
    """Liste filtrable : recherche, sélection, conservation de la sélection au rechargement."""

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
            item.setData(SEARCH_ROLE, normalize(f"{title} {key}"))
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
            haystack = item.data(SEARCH_ROLE) or ""
            item.setHidden(not all(token in haystack for token in tokens))

    def _on_current(self, current: QListWidgetItem | None, _previous) -> None:
        if not self._suppress and current is not None:
            self.selected.emit(current.data(KEY_ROLE))
