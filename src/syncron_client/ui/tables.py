"""Tableaux en lecture seule, stylés par le design system, triables numériquement."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from syncron_client.ui.theme import COLORS
from syncron_core.converter import STACK, decompose
from syncron_core.text import format_quantity

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
SORT_ROLE = Qt.ItemDataRole.UserRole + 2
ROW_HEIGHT = 42


class SortableItem(QTableWidgetItem):
    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine, theirs = self.data(SORT_ROLE), other.data(SORT_ROLE)
        if mine is not None and theirs is not None and type(mine) is type(theirs):
            return mine < theirs
        return super().__lt__(other)


def make_table(headers: Sequence[str], stretch_column: int = 0, sortable: bool = False) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels([header.upper() for header in headers])
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setIconSize(QSize(24, 24))
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for column in range(len(headers)):
        mode = QHeaderView.ResizeMode.Stretch if column == stretch_column else QHeaderView.ResizeMode.ResizeToContents
        header.setSectionResizeMode(column, mode)
    table.setSortingEnabled(sortable)
    return table


def text_cell(
    text: str, sort_key: str | None = None, icon: QIcon | None = None, key: str | None = None
) -> SortableItem:
    cell = SortableItem(text)
    if sort_key is not None:
        cell.setData(SORT_ROLE, sort_key)
    if icon is not None:
        cell.setIcon(icon)
    if key is not None:
        cell.setData(KEY_ROLE, key)
    return cell


def muted_cell(text: str, sort_key: str | int | None = None) -> SortableItem:
    cell = SortableItem(text)
    cell.setForeground(QColor(COLORS.text_muted))
    if sort_key is not None:
        cell.setData(SORT_ROLE, sort_key)
    return cell


def quantity_cell(value: int, *, strong: bool = False, tone: str | None = None) -> SortableItem:
    cell = SortableItem(format_quantity(value))
    cell.setData(SORT_ROLE, value)
    if value >= STACK.size():
        cell.setToolTip(f"{format_quantity(value)} = {decompose(value).text()}")
    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if strong:
        font = QFont(cell.font())
        font.setWeight(QFont.Weight.DemiBold)
        cell.setFont(font)
    if tone:
        cell.setForeground(QColor(tone))
    return cell


def fill_rows(table: QTableWidget, rows: Sequence[Sequence[QTableWidgetItem]]) -> None:
    sorting = table.isSortingEnabled()
    table.setSortingEnabled(False)
    table.clearContents()
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column_index, cell in enumerate(row):
            table.setItem(row_index, column_index, cell)
    table.setSortingEnabled(sorting)
