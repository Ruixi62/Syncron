"""Vue d'ensemble de l'administration : une carte par système géré, les comptes, l'activité récente."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.ui import icons
from syncron_client.ui.format import format_datetime, relative_time
from syncron_client.ui.tables import fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, Chip, button, label

SYSTEM_ICONS = {
    "craft": "hammer",
    "research": "flask",
    "calendar": "calendar",
    "messages": "megaphone",
    "accounts": "users",
}
SYSTEM_COLUMNS = 2


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


class SystemCard(Card):
    manageRequested = Signal(str)

    def __init__(self, system: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=18, spacing=10)
        self.system_id = system["id"]
        self.todo = {todo["label"]: todo["count"] for todo in system.get("todo", [])}
        badge = QLabel()
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icons.pixmap(SYSTEM_ICONS.get(system["id"], "grid"), COLORS.accent, 17))
        badge.setStyleSheet(f"background: {COLORS.accent_soft}; border-radius: 10px;")
        manage = button("Gérer", "arrow-right", "ghost")
        manage.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        manage.clicked.connect(lambda: self.manageRequested.emit(self.system_id))
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(badge)
        head.addWidget(label(system["name"], "heading"), 1)
        head.addWidget(manage)
        self.body.addLayout(head)
        stats = QGridLayout()
        stats.setHorizontalSpacing(18)
        stats.setVerticalSpacing(8)
        for index, stat in enumerate(system["stats"]):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(label(stat["label"], "faint"))
            value = label(stat["value"], "stat")
            value.setWordWrap(True)
            cell.addWidget(value)
            if stat.get("detail"):
                cell.addWidget(label(stat["detail"], "faint", wrap=True))
            stats.addLayout(cell, index // 2, index % 2)
        stats.setColumnStretch(0, 1)
        stats.setColumnStretch(1, 1)
        self.body.addLayout(stats)
        if system.get("todo"):
            self.body.addWidget(label("À COMPLÉTER", "overline"))
            for todo in system["todo"]:
                row = QHBoxLayout()
                row.addWidget(label(todo["label"], "muted"), 1)
                row.addWidget(Chip(str(todo["count"]), "warning" if todo["count"] else "success"))
                self.body.addLayout(row)
        self.body.addStretch(1)
        updated = system.get("updated_at")
        self.body.addWidget(label(f"Dernière modification : {relative_time(updated)}" if updated else " ", "faint"))


class OverviewView(QWidget):
    manageRequested = Signal(str)  # identifiant du système

    def __init__(self, host: ToolHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._data: dict[str, Any] | None = None
        self.cards: dict[str, SystemCard] = {}
        self._systems = QGridLayout()
        self._systems.setSpacing(16)
        self.accounts = Card(padding=18, spacing=8)
        self.accounts_text = label("", "muted", wrap=True)
        self.accounts.body.addWidget(label("COMPTES", "overline"))
        self.accounts.body.addWidget(self.accounts_text)
        self.accounts.hide()
        activity = Card(padding=18, spacing=10)
        activity.body.addWidget(label("ACTIVITÉ RÉCENTE", "overline"))
        self.activity = make_table(["Quand", "Qui", "Système", "Modification"], 3)
        self.activity.setMinimumHeight(260)
        activity.body.addWidget(self.activity, 1)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(16)
        layout.addLayout(self._systems)
        layout.addWidget(self.accounts)
        layout.addWidget(activity, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    @property
    def data(self) -> dict[str, Any] | None:
        return self._data

    def refresh(self) -> None:
        call_api(self._host, self._host.api.overview, self._show)

    def _show(self, data: dict[str, Any]) -> None:
        self._data = data
        _clear(self._systems)
        self.cards = {}
        for index, system in enumerate(data["systems"]):
            card = SystemCard(system)
            card.manageRequested.connect(self.manageRequested)
            self.cards[system["id"]] = card
            self._systems.addWidget(card, index // SYSTEM_COLUMNS, index % SYSTEM_COLUMNS)
        for column in range(SYSTEM_COLUMNS):
            self._systems.setColumnStretch(column, 1)
        accounts = data.get("accounts")
        self.accounts.setVisible(accounts is not None)
        if accounts:
            roles = accounts["by_role"]
            self.accounts_text.setText(
                f"{accounts['total']} compte(s) : {roles.get('player', 0)} membre(s), {roles.get('editor', 0)} "
                f"éditeur(s), {roles.get('admin', 0)} administrateur(s) · {accounts['banned']} suspendu(s)."
            )
        session = self._host.session
        rows = []
        for entry in data["recent"]:
            what = text_cell(entry["summary"] or entry["action"])
            what.setIcon(icons.icon(SYSTEM_ICONS.get(entry["system"], "edit"), COLORS.text_faint, 16))
            system = "Comptes" if entry["system"] == "accounts" else session.system_name(entry["system"])
            rows.append(
                [
                    muted_cell(format_datetime(entry["created_at"])),
                    text_cell(entry["username"] or "—"),
                    muted_cell(system),
                    what,
                ]
            )
        fill_rows(self.activity, rows)
