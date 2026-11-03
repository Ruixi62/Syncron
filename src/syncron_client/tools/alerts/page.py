"""Page Mes alertes : types d'événements suivis, événements en cours et récents."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from syncron_client.tools.intel.model import EVENT_COLORS, EVENT_ICONS, EVENT_NAMES
from syncron_client.ui import icons
from syncron_client.ui.format import format_datetime, relative_time
from syncron_client.ui.tables import fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Banner, Card, Chip, EmptyState, button, label

KINDS = ("meteor", "rift", "volcano", "other")
KIND_HINTS = {
    "meteor": "Chute de météorite : minerais rares à récupérer.",
    "rift": "Faille ouverte sur la carte.",
    "volcano": "Éruption volcanique.",
    "other": "Tout autre événement météo signalé par Iris.",
}


def _badge(kind: str, size: int = 36) -> QLabel:
    badge = QLabel()
    badge.setFixedSize(size, size)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setPixmap(icons.pixmap(EVENT_ICONS[kind], EVENT_COLORS[kind], size // 2))
    badge.setStyleSheet(f"background: {COLORS.surface_alt}; border-radius: {size // 3}px;")
    return badge


class EventCard(Card):
    showRequested = Signal(int, int)

    def __init__(self, event: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=16, spacing=6)
        self.event = event
        kind = event["kind"] if event.get("kind") in EVENT_COLORS else "other"
        self.setStyleSheet(f"QFrame[card='true'] {{ border: 1px solid {EVENT_COLORS[kind]}; }}")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(str(event.get("title") or EVENT_NAMES[kind]), "heading"))
        x, z = event.get("x"), event.get("z")
        where = f"x {x} · z {z}" if x is not None and z is not None else "position inconnue"
        texts.addWidget(label(f"{where} · apparu {relative_time(event.get('first_seen'))}", "muted"))
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(_badge(kind))
        row.addLayout(texts, 1)
        row.addWidget(Chip("En cours", "warning", "alert"), 0, Qt.AlignmentFlag.AlignTop)
        if x is not None and z is not None:
            go = button("Voir sur la carte", "map", "primary")
            go.clicked.connect(lambda: self.showRequested.emit(int(x), int(z)))
            row.addWidget(go, 0, Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(row)


class AlertsPage(QWidget):
    kindToggled = Signal(str, bool)
    showRequested = Signal(int, int)

    def __init__(self, kinds: dict[str, bool], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.boxes: dict[str, QCheckBox] = {}
        self.cards: list[EventCard] = []

        choices = Card(padding=18, spacing=10)
        choices.body.addWidget(label("M'ALERTER POUR", "overline"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        for index, kind in enumerate(KINDS):
            box = QCheckBox(EVENT_NAMES[kind])
            box.setChecked(kinds.get(kind, True))
            box.setToolTip(KIND_HINTS[kind])
            box.toggled.connect(lambda checked, k=kind: self.kindToggled.emit(k, checked))
            self.boxes[kind] = box
            cell = QHBoxLayout()
            cell.setSpacing(8)
            cell.addWidget(_badge(kind, 28))
            cell.addWidget(box, 1)
            grid.addLayout(cell, index // 2, index % 2)
        choices.body.addLayout(grid)
        choices.body.addWidget(
            label(
                "Une notification s'affiche dans le logiciel et sur le bureau (Paramètres › Notifications), "
                "même quand cette page est fermée. Un clic dessus ouvre la carte à l'endroit de l'événement.",
                "faint",
                wrap=True,
            )
        )

        self.disabled = Banner("warning")
        self.disabled.set_text("La surveillance de la carte Iris est désactivée sur le serveur du pays.")
        self.disabled.hide()
        self.checked = label("", "faint")

        self.active_box = QVBoxLayout()
        self.active_box.setSpacing(10)
        self.calm = EmptyState(
            "bell",
            "Rien en cours",
            "Aucun événement météo sur la carte pour l'instant. Tu seras prévenu dès qu'il en apparaît un.",
        )
        self.recent = make_table(["Type", "Événement", "Position", "Début", "Fin"], 1)
        self.recent.setMinimumHeight(220)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(choices)
        layout.addWidget(self.disabled)
        head = QHBoxLayout()
        head.addWidget(label("EN COURS", "overline"), 1)
        head.addWidget(self.checked)
        layout.addLayout(head)
        layout.addLayout(self.active_box)
        layout.addWidget(self.calm)
        layout.addWidget(label("7 DERNIERS JOURS", "overline"))
        layout.addWidget(self.recent, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def set_events(self, events: list[dict[str, Any]], enabled: bool, checked_at: str | None) -> None:
        self.disabled.setVisible(not enabled)
        self.checked.setText(f"Vérifié {relative_time(checked_at)}" if checked_at else "")
        for card in self.cards:
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self.cards = []
        active = [e for e in events if e.get("active")]
        for event in active:
            card = EventCard(event)
            card.showRequested.connect(self.showRequested)
            self.cards.append(card)
            self.active_box.addWidget(card)
        self.calm.setVisible(not active)
        rows = []
        for event in events:
            kind = event["kind"] if event.get("kind") in EVENT_COLORS else "other"
            x, z = event.get("x"), event.get("z")
            rows.append(
                [
                    text_cell(EVENT_NAMES[kind], icon=icons.icon(EVENT_ICONS[kind], EVENT_COLORS[kind], 16)),
                    text_cell(str(event.get("title") or "")),
                    muted_cell(f"{x}, {z}" if x is not None and z is not None else "—"),
                    muted_cell(format_datetime(event.get("first_seen"))),
                    muted_cell("en cours" if event.get("active") else format_datetime(event.get("ended_at"))),
                ]
            )
        fill_rows(self.recent, rows)
