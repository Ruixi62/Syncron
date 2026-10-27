"""Catalogue : recherche, filtres (type, catégorie, atelier) et liste illustrée."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRect,
    QRectF,
    QSize,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from syncron_client.ui import icons
from syncron_client.ui.item_icons import IconProvider
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, SearchField, SegmentedControl, label
from syncron_core.catalog_service import CatalogService, matches
from syncron_core.duration import format_duration
from syncron_core.models.item import Item, ItemType
from syncron_core.quick_query import parse_quick_query
from syncron_core.text import normalize

ICON_SIZE = 34
ROW_HEIGHT = 54
ID_ROLE = Qt.ItemDataRole.UserRole + 1
SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 2
PIXMAP_ROLE = Qt.ItemDataRole.UserRole + 3
BROKEN_ROLE = Qt.ItemDataRole.UserRole + 4
_TYPE_FILTERS = (None, ItemType.CRAFTED, ItemType.RAW)


class CatalogModel(QAbstractListModel):
    def __init__(self, catalog: CatalogService, icons_provider: IconProvider, parent: QObject | None = None):
        super().__init__(parent)
        self._catalog = catalog
        self._icons = icons_provider
        self._items: list[Item] = []
        self._broken: frozenset[str] = frozenset()

    def set_items(self, items: list[Item], broken: frozenset[str]) -> None:
        self.beginResetModel()
        self._items = items
        self._broken = broken
        self.endResetModel()

    def item_at(self, row: int) -> Item:
        return self._items[row]

    def row_of(self, item_id: str) -> int:
        return next((row for row, item in enumerate(self._items) if item.id == item_id), -1)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        if role == ID_ROLE:
            return item.id
        if role == SUBTITLE_ROLE:
            return self._subtitle(item)
        if role == PIXMAP_ROLE:
            return self._icons.item_pixmap(item.id, ICON_SIZE)
        if role == BROKEN_ROLE:
            return item.id in self._broken
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = f"{item.name}\nid : {item.id}"
            if item.id in self._broken:
                tip += "\n⚠ Erreur dans les données"
            return tip
        return None

    def _subtitle(self, item: Item) -> str:
        if item.recipe is None:
            return "Ressource primaire" + (f" · {item.category}" if item.category else "")
        parts = [self._catalog.station_name(item.recipe.station_id)]
        if item.recipe.time_seconds:
            parts.append(format_duration(item.recipe.time_seconds, compact=True))
        return " · ".join(parts)


class CatalogDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            painter.fillPath(path, QColor(COLORS.surface_hover if selected else COLORS.surface_alt))
            if selected:
                bar = QRectF(rect.left(), rect.top() + 12, 3, rect.height() - 24)
                accent = QPainterPath()
                accent.addRoundedRect(bar, 1.5, 1.5)
                painter.fillPath(accent, QColor(COLORS.accent))

        pixmap = index.data(PIXMAP_ROLE)
        icon_rect = QRect(int(rect.left()) + 12, int(rect.center().y() - ICON_SIZE / 2), ICON_SIZE, ICON_SIZE)
        if pixmap is not None:
            painter.drawPixmap(icon_rect, pixmap)

        text_left = icon_rect.right() + 12
        width = int(rect.right()) - text_left - 10
        broken = bool(index.data(BROKEN_ROLE))
        name_font = QFont(option.font)
        name_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name_font)
        painter.setPen(QColor(COLORS.danger if broken else COLORS.text))
        name = ("⚠ " if broken else "") + index.data(Qt.ItemDataRole.DisplayRole)
        name_rect = QRect(text_left, int(rect.top()) + 9, width, 18)
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(name_font).elidedText(name, Qt.TextElideMode.ElideRight, width),
        )

        sub_font = QFont(option.font)
        sub_font.setPixelSize(12)
        painter.setFont(sub_font)
        painter.setPen(QColor(COLORS.text_faint))
        subtitle = QFontMetrics(sub_font).elidedText(index.data(SUBTITLE_ROLE), Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRect(text_left, int(rect.top()) + 27, width, 16), Qt.AlignmentFlag.AlignVCenter, subtitle)
        painter.restore()


class CatalogFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tokens: list[str] = []
        self._item_type: ItemType | None = None
        self._category: str | None = None
        self._station: str | None = None

    def set_query(self, text: str) -> None:
        self._update(_tokens=normalize(text).split())

    def set_item_type(self, item_type: ItemType | None) -> None:
        self._update(_item_type=item_type)

    def set_category(self, category: str | None) -> None:
        self._update(_category=category)

    def set_station(self, station_id: str | None) -> None:
        self._update(_station=station_id)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, CatalogModel):
            return True
        item = model.item_at(source_row)
        return (
            (self._item_type is None or item.type is self._item_type)
            and (not self._category or item.category == self._category)
            and (not self._station or item.station_id == self._station)
            and matches(item, self._tokens)
        )

    def _update(self, **changes: Any) -> None:
        self.beginFilterChange()
        for name, value in changes.items():
            setattr(self, name, value)
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)


class CatalogPanel(Card):
    """Émet `itemRequested(item_id, quantity)` quand l'utilisateur choisit un objet."""

    itemRequested = Signal(str, int)

    def __init__(self, catalog: CatalogService, icon_provider: IconProvider, parent: QWidget | None = None):
        super().__init__(parent, padding=14, spacing=10)
        self._catalog = catalog
        self._suppress_signal = False

        self._model = CatalogModel(catalog, icon_provider, self)
        self._proxy = CatalogFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._count = label("", "faint")
        header = QHBoxLayout()
        header.addWidget(label("CATALOGUE", "overline"))
        header.addStretch(1)
        header.addWidget(self._count)

        self._search = SearchField("Rechercher, ou « Vis x6 » + Entrée")
        self._search.installEventFilter(self)

        self._type_filter = SegmentedControl([("Tout", None), ("Craftables", None), ("Primaires", None)])
        self._category_filter = QComboBox()
        self._station_filter = QComboBox()
        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(self._category_filter, 1)
        filters.addWidget(self._station_filter, 1)

        self._list = QListView()
        self._list.setModel(self._proxy)
        self._list.setItemDelegate(CatalogDelegate(self._list))
        self._list.setUniformItemSizes(True)
        self._list.setMouseTracking(True)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list.setFrameShape(QListView.Shape.NoFrame)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout: QVBoxLayout = self.body
        layout.addLayout(header)
        layout.addWidget(self._search)
        layout.addWidget(self._type_filter)
        layout.addLayout(filters)
        layout.addWidget(self._list, 1)

        self._search.textChanged.connect(self._on_search_changed)
        self._search.returnPressed.connect(self._on_search_submitted)
        self._type_filter.currentChanged.connect(self._on_type_changed)
        self._category_filter.currentIndexChanged.connect(self._on_category_changed)
        self._station_filter.currentIndexChanged.connect(self._on_station_changed)
        self._list.selectionModel().currentChanged.connect(self._on_current_changed)

    # -- API -------------------------------------------------------------------

    def reload(self, broken: frozenset[str] = frozenset()) -> None:
        current = self.current_item_id()
        self._model.set_items(self._catalog.list_items(), broken)
        self._refill_combo(self._category_filter, "Catégorie", [(c, c) for c in self._catalog.categories()], "layers")
        self._refill_combo(
            self._station_filter,
            "Atelier",
            [(s.name, s.id) for s in self._catalog.stations_in_use()],
            "station",
        )
        self._proxy.set_category(self._category_filter.currentData())
        self._proxy.set_station(self._station_filter.currentData())
        if current:
            self.select_item(current, emit=False)
        self._update_count()

    def current_item_id(self) -> str | None:
        index = self._list.currentIndex()
        return index.data(ID_ROLE) if index.isValid() else None

    def select_item(self, item_id: str, quantity: int = 1, emit: bool = True) -> bool:
        row = self._model.row_of(item_id)
        if row < 0:
            return False
        source_index = self._model.index(row, 0)
        if not self._proxy.mapFromSource(source_index).isValid():
            self._reset_filters()
        proxy_index = self._proxy.mapFromSource(source_index)
        self._suppress_signal = True
        try:
            self._list.selectionModel().setCurrentIndex(proxy_index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            self._list.scrollTo(proxy_index)
        finally:
            self._suppress_signal = False
        if emit:
            self.itemRequested.emit(item_id, quantity)
        return True

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    # -- événements --------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        is_down = (
            watched is self._search
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Down
        )
        if is_down and self._proxy.rowCount() > 0:
            self._list.setFocus()
            if not self._list.currentIndex().isValid():
                self._list.setCurrentIndex(self._proxy.index(0, 0))
            return True
        return super().eventFilter(watched, event)

    def _on_search_changed(self, text: str) -> None:
        self._proxy.set_query(text)
        self._update_count()

    def _on_search_submitted(self) -> None:
        query = parse_quick_query(self._search.text())
        if query.quantity is not None:
            item = self._catalog.resolve(query.text)
            if item is not None:
                self._search.setText(query.text)
                self.select_item(item.id, query.quantity)
                return
        if self._proxy.rowCount() > 0:
            index = self._list.currentIndex()
            if not index.isValid():
                index = self._proxy.index(0, 0)
            self.select_item(index.data(ID_ROLE))

    def _on_type_changed(self, index: int) -> None:
        self._proxy.set_item_type(_TYPE_FILTERS[index])
        self._update_count()

    def _on_category_changed(self) -> None:
        self._proxy.set_category(self._category_filter.currentData())
        self._update_count()

    def _on_station_changed(self) -> None:
        self._proxy.set_station(self._station_filter.currentData())
        self._update_count()

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not self._suppress_signal and current.isValid():
            self.itemRequested.emit(current.data(ID_ROLE), 1)

    # -- interne -------------------------------------------------------------------

    @staticmethod
    def _refill_combo(combo: QComboBox, all_label: str, entries: list[tuple[str, str]], icon_name: str) -> None:
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(icons.icon(icon_name, COLORS.text_faint, 14), all_label, None)
        for text, data in entries:
            combo.addItem(text, data)
        restored = combo.findData(previous) if previous else 0
        combo.setCurrentIndex(max(restored, 0))
        combo.blockSignals(False)

    def _reset_filters(self) -> None:
        self._type_filter.set_current_index(0)
        self._category_filter.setCurrentIndex(0)
        self._station_filter.setCurrentIndex(0)
        self._search.clear()

    def _update_count(self) -> None:
        shown, total = self._proxy.rowCount(), self._model.rowCount()
        self._count.setText(f"{shown}" if shown == total else f"{shown} / {total}")
