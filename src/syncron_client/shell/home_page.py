"""Accueil : présentation et carte de chaque outil (description, état)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from syncron_client.platform.registry import ToolRegistry
from syncron_client.platform.tool import StatusLevel, Tool, ToolStage
from syncron_client.ui import icons
from syncron_client.ui.brand import logo_pixmap
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, Chip, button, label
from syncron_core import APP_DISPLAY_NAME, APP_TAGLINE

TOOL_COLUMNS = 3


class ToolCard(Card):
    openRequested = Signal(str)

    def __init__(self, tool: Tool, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=20, spacing=12)
        self._tool = tool
        planned = tool.info.stage is ToolStage.PLANNED
        badge = QLabel()
        badge.setFixedSize(44, 44)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color, background = (COLORS.violet, COLORS.violet_soft) if planned else (COLORS.accent, COLORS.accent_soft)
        badge.setPixmap(icons.pixmap(tool.info.icon, color, 22))
        badge.setStyleSheet(f"background: {background}; border-radius: 13px;")
        self._status = Chip("", "neutral")
        head = QHBoxLayout()
        head.addWidget(badge)
        head.addStretch(1)
        head.addWidget(self._status, 0, Qt.AlignmentFlag.AlignTop)

        if planned:
            open_button = button("Voir le programme", "arrow-right")
        else:
            open_button = button(f"Ouvrir {tool.info.name}", "arrow-right", "primary")
        open_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        open_button.clicked.connect(lambda: self.openRequested.emit(tool.info.id))

        self.body.addLayout(head)
        self.body.addWidget(label(tool.info.name, "heading"))
        self.body.addWidget(label(tool.info.description, "muted", wrap=True))
        self.body.addStretch(1)
        self.body.addWidget(open_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.refresh()

    def refresh(self) -> None:
        if self._tool.info.stage is ToolStage.PLANNED:
            self._status.set_content("En développement", "violet", "clock")
            return
        status = self._tool.status()
        if status.level is StatusLevel.ERROR:
            self._status.set_content(status.badge + " erreur(s)", "danger", "alert")
        elif status.level is StatusLevel.WARNING:
            self._status.set_content("Avertissements", "warning", "info")
        else:
            self._status.set_content("Prêt", "success", "check")


class HomePage(QScrollArea):
    openRequested = Signal(str)

    def __init__(self, registry: ToolRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._cards: dict[str, ToolCard] = {}

        hero = Card(padding=28, spacing=0)
        hero.setStyleSheet(
            "QFrame[card='true'] { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f" stop:0 #10241f, stop:0.55 {COLORS.surface}, stop:1 #0f1d2a); }}"
        )
        logo = QLabel()
        logo.setFixedSize(76, 76)
        logo.setPixmap(logo_pixmap(76))
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(label("BIENVENUE", "overline"))
        texts.addWidget(label(APP_DISPLAY_NAME, "display"))
        texts.addWidget(label(APP_TAGLINE + ". Tout fonctionne hors ligne, sur ta machine.", "muted", wrap=True))
        hero_row = QHBoxLayout()
        hero_row.setSpacing(22)
        hero_row.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        hero_row.addLayout(texts, 1)
        hero.body.addLayout(hero_row)

        grid = QGridLayout()
        grid.setSpacing(16)
        for index, tool in enumerate(registry):
            card = ToolCard(tool)
            card.openRequested.connect(self.openRequested)
            self._cards[tool.info.id] = card
            grid.addWidget(card, index // TOOL_COLUMNS, index % TOOL_COLUMNS)
        for column in range(TOOL_COLUMNS):
            grid.setColumnStretch(column, 1)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(20)
        layout.addWidget(hero)
        layout.addWidget(label("TES OUTILS", "overline"))
        layout.addLayout(grid)
        layout.addStretch(1)
        self.setWidget(content)

    def refresh(self, tool_id: str | None = None) -> None:
        for card_id, card in self._cards.items():
            if tool_id is None or card_id == tool_id:
                card.refresh()
