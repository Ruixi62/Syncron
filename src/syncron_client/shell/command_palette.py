"""Recherche globale (Ctrl+K) : interroge tous les outils et ouvre le résultat choisi."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from syncron_client.platform.registry import ToolRegistry
from syncron_client.platform.tool import SearchHit
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import SearchField, label

RESULTS_PER_TOOL = 8
HIT_ROLE = Qt.ItemDataRole.UserRole + 10


class CommandPalette(QDialog):
    hitChosen = Signal(str, str)  # tool_id, key

    def __init__(self, registry: ToolRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self._registry = registry
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(640)

        panel = QWidget()
        panel.setObjectName("Palette")
        panel.setStyleSheet(
            f"#Palette {{ background: {COLORS.surface}; border: 1px solid {COLORS.border_strong};"
            " border-radius: 16px; }"
        )
        self._field = SearchField("Rechercher un objet, une recette…", large=True)
        self._field.installEventFilter(self)
        self._results = QListWidget()
        self._results.setIconSize(QSize(28, 28))
        self._results.setMinimumHeight(340)
        self._results.setStyleSheet(
            f"QListWidget::item {{ padding: 8px 10px; border-radius: 9px; }}"
            f"QListWidget::item:selected {{ background: {COLORS.surface_hover}; }}"
        )
        self._hint = label(
            "Tape au moins un caractère · ↑↓ pour naviguer · Entrée pour ouvrir · Échap pour fermer", "faint"
        )

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(14, 14, 14, 12)
        inner.setSpacing(10)
        inner.addWidget(self._field)
        inner.addWidget(self._results, 1)
        inner.addWidget(self._hint)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        self._field.textChanged.connect(self._search)
        self._field.returnPressed.connect(self._choose_current)
        self._results.itemActivated.connect(self._choose)

    def open_centered(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            top_left = parent.mapToGlobal(parent.rect().topLeft())
            self.move(top_left.x() + (parent.width() - self.width()) // 2, top_left.y() + 90)
        self._field.clear()
        self._search("")
        self.show()
        self._field.setFocus()

    def search_text(self, text: str) -> None:
        self._field.setText(text)

    def result_count(self) -> int:
        return self._results.count()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        is_arrow = (
            watched is self._field
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up)
        )
        if is_arrow:
            step = 1 if event.key() == Qt.Key.Key_Down else -1
            row = max(0, min(self._results.count() - 1, self._results.currentRow() + step))
            self._results.setCurrentRow(row)
            return True
        return super().eventFilter(watched, event)

    def _search(self, text: str) -> None:
        self._results.clear()
        query = text.strip()
        if not query:
            return
        for tool in self._registry:
            for hit in tool.search(query, RESULTS_PER_TOOL):
                self._results.addItem(self._make_item(hit, tool.info.name, tool.info.icon))
        if self._results.count():
            self._results.setCurrentRow(0)

    @staticmethod
    def _make_item(hit: SearchHit, tool_name: str, tool_icon: str) -> QListWidgetItem:
        item = QListWidgetItem(f"{hit.title}\n{tool_name} · {hit.subtitle}" if hit.subtitle else hit.title)
        item.setIcon(QIcon(hit.pixmap) if hit.pixmap is not None else icons.icon(tool_icon, COLORS.accent, 24))
        item.setData(HIT_ROLE, (hit.tool_id, hit.key))
        return item

    def _choose_current(self) -> None:
        item = self._results.currentItem()
        if item is not None:
            self._choose(item)

    def _choose(self, item: QListWidgetItem) -> None:
        tool_id, key = item.data(HIT_ROLE)
        self.accept()
        self.hitChosen.emit(tool_id, key)
