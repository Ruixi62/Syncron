"""Journal des modifications, filtrable par système."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.tools.admin.overview import SYSTEM_ICONS
from syncron_client.ui import icons
from syncron_client.ui.format import format_datetime
from syncron_client.ui.tables import fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, button, label

PAGE = 50


class AuditView(QWidget):
    def __init__(self, host: ToolHost, systems: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._names = systems
        self._entries: list[dict[str, Any]] = []
        self.system_filter = QComboBox()
        self.system_filter.addItem("Tous les systèmes", None)
        for system, name in systems.items():
            self.system_filter.addItem(
                icons.icon(SYSTEM_ICONS.get(system, "grid"), COLORS.text_muted, 14), name, system
            )
        self.system_filter.currentIndexChanged.connect(lambda _index: self.refresh())
        self.table = make_table(["Quand", "Qui", "Système", "Modification", "Élément"], 3)
        self._more = button("Charger plus", "history")
        self._more.clicked.connect(self._load_more)
        top = QHBoxLayout()
        top.addWidget(label("Afficher", "muted"))
        top.addWidget(self.system_filter)
        top.addStretch(1)
        card = Card(padding=16, spacing=10)
        card.body.addLayout(top)
        card.body.addWidget(self.table, 1)
        card.body.addWidget(self._more, 0, Qt.AlignmentFlag.AlignHCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)

    def entries(self) -> list[dict[str, Any]]:
        return self._entries

    def set_system(self, system: str | None) -> None:
        self.system_filter.setCurrentIndex(max(self.system_filter.findData(system), 0))

    def refresh(self) -> None:
        self._entries = []
        system = self.system_filter.currentData()
        call_api(self._host, lambda: self._host.api.audit(PAGE, system=system), self._append)

    def _load_more(self) -> None:
        before = self._entries[-1]["id"] if self._entries else None
        system = self.system_filter.currentData()
        call_api(self._host, lambda: self._host.api.audit(PAGE, before, system), self._append)

    def _append(self, entries: list[dict[str, Any]]) -> None:
        self._entries += entries
        self._more.setEnabled(len(entries) == PAGE)
        rows = []
        for entry in self._entries:
            what = text_cell(entry["summary"] or entry["action"])
            what.setIcon(icons.icon(SYSTEM_ICONS.get(entry["system"], "edit"), COLORS.text_faint, 16))
            rows.append(
                [
                    muted_cell(format_datetime(entry["created_at"])),
                    text_cell(entry["username"] or "—"),
                    muted_cell(self._names.get(entry["system"], entry["system"])),
                    what,
                    muted_cell(f"{entry['entity_type']} · {entry['entity_id']}"),
                ]
            )
        fill_rows(self.table, rows)
