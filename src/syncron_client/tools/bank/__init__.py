"""Outil Banque (dans la rubrique Pays) : solde du pays, entrées et sorties, contributeurs.

Tout membre consulte. Les comptes qui gèrent la Banque saisissent les opérations
directement ici (montant, motif, catégorie, membre, date), les corrigent ou les suppriment.
Dernier état gardé sur le disque pour le hors-ligne.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from PySide6.QtCore import QDate, QRegularExpression, Qt, Signal
from PySide6.QtGui import QAction, QColor, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDateEdit,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import NotifyLevel, Tool, ToolHost, ToolInfo
from syncron_client.ui import icons
from syncron_client.ui.tables import KEY_ROLE, fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import (
    Banner,
    Card,
    SearchField,
    SegmentedControl,
    StatTile,
    ask,
    button,
    compact_combo,
    label,
    plain_tooltip,
)
from syncron_core.text import format_quantity

CACHE_FILE = "bank.json"
MIN_SERVER = "5.2.0"
CATEGORIES = {
    "contribution": "Cotisation",
    "sale": "Vente",
    "purchase": "Achat",
    "tax": "Impôt, taxe",
    "war": "Guerre",
    "salary": "Salaire",
    "other": "Autre",
}


def short_date(value: str) -> str:
    """« 02/11 » cette année, « 02/11/2025 » sinon."""
    moment = datetime.fromisoformat(value).astimezone()
    return moment.strftime("%d/%m" if moment.year == datetime.now().year else "%d/%m/%Y")


def money(amount: int, signed: bool = False) -> str:
    sign = ("+" if amount > 0 else "−") if signed else ("−" if amount < 0 else "")
    return f"{sign}{format_quantity(abs(amount))} $"


@dataclass(frozen=True, slots=True)
class Operation:
    id: int
    amount: int
    label: str
    category: str
    member_id: str | None
    member: str
    occurred_at: str
    author: str | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Operation:
        return cls(
            id=int(raw["id"]),
            amount=int(raw["amount"]),
            label=raw.get("label") or "",
            category=raw.get("category") or "other",
            member_id=str(raw["member_id"]) if raw.get("member_id") else None,
            member=raw.get("member") or "",
            occurred_at=raw["occurred_at"],
            author=raw.get("author"),
        )

    def matches(self, query: str) -> bool:
        haystack = f"{self.label} {self.member} {CATEGORIES.get(self.category, '')} {self.author or ''}".casefold()
        return all(word in haystack for word in query.casefold().split())


class OperationForm(Card):
    """Saisie d'une opération (équipe) : entrée ou sortie, montant, motif, catégorie, membre, date."""

    saveRequested = Signal(object, dict)  # id (None : nouvelle), données
    deleteRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=18, spacing=10)
        self._editing: int | None = None
        self.title = label("Nouvelle opération", "heading")
        self.banner = Banner("danger")
        self.banner.hide()
        self.direction = SegmentedControl([("Entrée", "plus"), ("Sortie", "minus")])
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("Montant en $")
        self.amount.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9  ]{1,17}$"), self))
        self.label_field = QLineEdit()
        self.label_field.setMaxLength(160)
        self.label_field.setPlaceholderText("Motif : cotisation, achat de TNT…")
        self.category = compact_combo(min_chars=12)
        for key, title in CATEGORIES.items():
            self.category.addItem(title, key)
        self.member = compact_combo(editable=True, min_chars=12)
        self.member.lineEdit().setPlaceholderText("Membre (facultatif)")
        self.member.lineEdit().setMaxLength(64)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.save_button = button("Enregistrer", "save", "primary")
        self.save_button.clicked.connect(self._save)
        self.cancel_button = button("Annuler", None, "ghost")
        self.cancel_button.clicked.connect(self.reset)
        self.delete_button = button("Supprimer", "trash", "ghost")
        self.delete_button.setStyleSheet(f"QPushButton {{ color: {COLORS.danger}; }}")
        self.delete_button.clicked.connect(lambda: self._editing and self.deleteRequested.emit(self._editing))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(self.direction, 0, 0, 1, 2)
        grid.addWidget(self.amount, 1, 0)
        grid.addWidget(self.date, 1, 1)
        grid.addWidget(self.label_field, 2, 0, 1, 2)
        grid.addWidget(self.category, 3, 0)
        grid.addWidget(self.member, 3, 1)
        actions = QHBoxLayout()
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        self.body.addWidget(self.title)
        self.body.addWidget(self.banner)
        self.body.addLayout(grid)
        self.body.addLayout(actions)
        self.reset()

    @property
    def editing(self) -> int | None:
        return self._editing

    def set_members(self, members: list[tuple[str, str]]) -> None:
        current = self.member.currentText()
        self.member.clear()
        self.member.addItem("", None)
        for member_id, name in members:
            self.member.addItem(name, member_id)
        self.member.setEditText(current)

    def reset(self) -> None:
        self._editing = None
        self.title.setText("Nouvelle opération")
        self.direction.set_current_index(0)
        self.amount.clear()
        self.label_field.clear()
        self.category.setCurrentIndex(self.category.findData("contribution"))
        self.member.setCurrentIndex(0)
        self.member.setEditText("")
        self.date.setDate(QDate.currentDate())
        self.banner.hide()
        self.delete_button.hide()
        self.cancel_button.hide()

    def load(self, operation: Operation) -> None:
        self._editing = operation.id
        self.title.setText("Modifier l'opération")
        self.direction.set_current_index(0 if operation.amount > 0 else 1)
        self.amount.setText(format_quantity(abs(operation.amount)))
        self.label_field.setText(operation.label)
        self.category.setCurrentIndex(max(self.category.findData(operation.category), 0))
        index = self.member.findData(operation.member_id) if operation.member_id else -1
        if index >= 0:
            self.member.setCurrentIndex(index)
        else:
            self.member.setEditText(operation.member)
        moment = datetime.fromisoformat(operation.occurred_at).astimezone()
        self.date.setDate(QDate(moment.year, moment.month, moment.day))
        self.banner.hide()
        self.delete_button.show()
        self.cancel_button.show()

    def payload(self) -> dict[str, Any] | None:
        digits = "".join(ch for ch in self.amount.text() if ch.isdigit())
        if not digits or int(digits) == 0:
            self._refuse("Indique un montant.")
            return None
        text = self.label_field.text().strip()
        if not text:
            self._refuse("Indique le motif de l'opération.")
            return None
        amount = int(digits) * (1 if self.direction.current_index() == 0 else -1)
        name = self.member.currentText().strip()
        index = self.member.findText(name, Qt.MatchFlag.MatchFixedString) if name else -1
        member_id = self.member.itemData(index) if index > 0 else None
        day = self.date.date()
        moment = datetime(day.year(), day.month(), day.day(), 12, tzinfo=UTC)
        return {
            "amount": amount,
            "label": text,
            "category": self.category.currentData(),
            "member_id": member_id,
            "member_name": "" if member_id else name,
            "occurred_at": moment.isoformat(),
        }

    def _save(self) -> None:
        payload = self.payload()
        if payload is not None:
            self.saveRequested.emit(self._editing, payload)

    def _refuse(self, text: str) -> None:
        self.banner.set_text(text)
        self.banner.show()


class BankPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._operations: list[Operation] = []
        self.balance = StatTile("database", "Solde du pays", "accent")
        self.income = StatTile("plus", "Entrées sur 30 jours", "success")
        self.expenses = StatTile("minus", "Sorties sur 30 jours", "danger")
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        for tile in (self.balance, self.income, self.expenses):
            tiles.addWidget(tile, 1)

        self.search = SearchField("Rechercher : motif, membre, catégorie…")
        self.search.textChanged.connect(self._render)
        self.category_filter = compact_combo(min_chars=12)
        self.category_filter.addItem("Toutes les catégories", None)
        for key, title in CATEGORIES.items():
            self.category_filter.addItem(title, key)
        self.category_filter.currentIndexChanged.connect(lambda _i: self._render())
        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.category_filter)
        self.table = make_table(["Date", "Motif", "Catégorie", "Membre", "Montant"], 1)
        self.empty = label("Aucune opération pour l'instant.", "faint")
        operations = Card(padding=16, spacing=10)
        operations.body.addWidget(label("OPÉRATIONS", "overline"))
        operations.body.addLayout(filters)
        operations.body.addWidget(self.table, 1)
        operations.body.addWidget(self.empty)

        self.form = OperationForm()
        self.form.hide()
        self.contributors = Card(padding=18, spacing=8)
        self.contributors.body.addWidget(label("CONTRIBUTEURS", "overline"))
        self._contributor_rows = QVBoxLayout()
        self._contributor_rows.setSpacing(6)
        self.contributors.body.addLayout(self._contributor_rows)
        side = QWidget()
        side.setFixedWidth(300)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(14)
        side_layout.addWidget(self.form)
        side_layout.addWidget(self.contributors)
        side_layout.addStretch(1)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll.setWidget(side)
        side_scroll.setFixedWidth(312)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(operations, 1)
        body.addWidget(side_scroll)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(tiles)
        layout.addLayout(body, 1)
        self.table.itemSelectionChanged.connect(self._selected)

    @property
    def operations(self) -> list[Operation]:
        return self._operations

    def set_editable(self, editable: bool) -> None:
        self.form.setVisible(editable)

    def set_state(self, state: dict[str, Any]) -> None:
        self._operations = [Operation.from_api(raw) for raw in state.get("transactions", [])]
        self.balance.set_value(money(int(state.get("balance", 0))), f"{state.get('count', 0)} opération(s)")
        self.income.set_value(money(int(state.get("income_30_days", 0))))
        self.expenses.set_value(money(int(state.get("expenses_30_days", 0))))
        _clear(self._contributor_rows)
        contributors = state.get("contributors", [])
        if not contributors:
            self._contributor_rows.addWidget(label("Les cotisations des membres apparaîtront ici.", "faint", True))
        for rank, entry in enumerate(contributors, start=1):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(label(f"{rank}.", "faint"))
            row.addWidget(label(entry["member"]), 1)
            amount = label(money(int(entry["total"])))
            amount.setStyleSheet(f"color: {COLORS.success}; font-weight: 600;")
            row.addWidget(amount)
            self._contributor_rows.addLayout(row)
        self._render()

    def selected_operation(self) -> Operation | None:
        rows = {item.row() for item in self.table.selectedItems()}
        if len(rows) != 1:
            return None
        key = self.table.item(rows.pop(), 1).data(KEY_ROLE)
        return next((op for op in self._operations if str(op.id) == key), None)

    def _render(self) -> None:
        query = self.search.text().strip()
        category = self.category_filter.currentData()
        shown = [
            op
            for op in self._operations
            if (not query or op.matches(query)) and (category is None or op.category == category)
        ]
        rows = []
        for op in shown:
            amount = text_cell(money(op.amount, signed=True), sort_key=op.amount)
            amount.setForeground(QColor(COLORS.success if op.amount > 0 else COLORS.danger))
            amount.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            motif = text_cell(op.label, key=str(op.id))
            motif.setToolTip(plain_tooltip(op.label))
            rows.append(
                [
                    muted_cell(short_date(op.occurred_at), sort_key=op.occurred_at),
                    motif,
                    muted_cell(CATEGORIES.get(op.category, op.category)),
                    muted_cell(op.member or "—"),
                    amount,
                ]
            )
        fill_rows(self.table, rows)
        self.empty.setVisible(not self._operations)

    def _selected(self) -> None:
        operation = self.selected_operation()
        if operation is not None and not self.form.isHidden():
            self.form.load(operation)


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class BankTool(Tool):
    _INFO = ToolInfo(
        id="bank",
        name="Banque",
        description="Le solde du pays, ses entrées et ses sorties, et les plus généreux contributeurs.",
        icon="database",
        version="5.2.0",
        system="bank",
        parent="country",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._page: BankPage | None = None
        self._state: dict[str, Any] = {}
        self._actions: list[QAction] = []

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> BankPage | None:
        return self._page

    @property
    def state(self) -> dict[str, Any]:
        return self._state

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._cache_path = host.tool_paths(self.info.id).user_dir / CACHE_FILE
        try:
            self._state = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._state = {}

    def create_page(self) -> QWidget:
        self._page = BankPage()
        self._page.form.saveRequested.connect(self.save)
        self._page.form.deleteRequested.connect(self._confirm_delete)
        if self._state:
            self._page.set_state(self._state)
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Recharger la banque")
        refresh.triggered.connect(self.refresh)
        self._actions = [refresh]
        return self._page

    def activated(self) -> None:
        self.refresh()

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def refresh(self) -> None:
        session = self._host.session
        if self._page is not None:
            self._page.set_editable(session.can_manage(self.info.system))
        if not session.online or not session.server_at_least(MIN_SERVER):
            return

        def done(state: dict[str, Any]) -> None:
            self._state = state
            try:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                self._cache_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            except OSError:
                self._host.notify("Banque non gardée pour le hors-ligne (disque).", NotifyLevel.WARNING)
            if self._page is not None:
                self._page.set_state(state)
            self._load_members()

        self._host.runner.run(self._host.api.bank, done, lambda error: self._host.handle_error(error, "Banque"))

    def save(self, operation_id: int | None, payload: dict[str, Any]) -> None:
        api = self._host.api

        def call() -> dict[str, Any]:
            if operation_id is None:
                return api.add_bank_transaction(payload)
            return api.edit_bank_transaction(operation_id, payload)

        def done(_raw: dict[str, Any]) -> None:
            if self._page is not None:
                self._page.form.reset()
            self.refresh()

        banner = self._page.form.banner if self._page is not None else None
        call_api(self._host, call, done, banner=banner, success="Opération enregistrée.")

    def delete(self, operation_id: int) -> None:
        def done(_result: Any) -> None:
            if self._page is not None:
                self._page.form.reset()
            self.refresh()

        call_api(
            self._host,
            lambda: self._host.api.delete_bank_transaction(operation_id),
            done,
            success="Opération supprimée.",
        )

    def _confirm_delete(self, operation_id: int) -> None:
        if ask(self._page, "Banque", "Supprimer cette opération ? Le solde sera recalculé."):
            self.delete(operation_id)

    def _load_members(self) -> None:
        if self._page is None or self._page.form.isHidden():
            return

        def done(members: list[dict[str, Any]]) -> None:
            if self._page is not None:
                self._page.form.set_members([(str(m["id"]), m["name"]) for m in members])

        self._host.runner.run(self._host.api.members, done, lambda _error: None)
