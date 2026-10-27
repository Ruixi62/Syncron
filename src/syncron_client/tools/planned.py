"""Outil annoncé, en attente de développement.

Il occupe déjà sa place dans la plateforme (barre latérale, accueil,
paramètres) et présente son programme. Quand son développement commence,
on remplace `PlannedTool` par une vraie sous-classe de `Tool` dans le
paquet de l'outil, sans rien changer d'autre.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from syncron_client.platform.tool import Tool, ToolHost, ToolInfo, ToolStage
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, Chip, label


class PlannedTool(Tool):
    def __init__(self, info: ToolInfo) -> None:
        if info.stage is not ToolStage.PLANNED:
            raise ValueError(f"PlannedTool attend un outil au stade PLANNED : {info.id}")
        self._info = info

    @property
    def info(self) -> ToolInfo:
        return self._info

    def setup(self, host: ToolHost) -> None:
        """Aucune donnée à charger tant que l'outil n'est pas développé."""

    def create_page(self) -> QWidget:
        return PlannedPage(self._info)


class PlannedPage(QScrollArea):
    def __init__(self, info: ToolInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)

        badge = QLabel()
        badge.setFixedSize(72, 72)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icons.pixmap(info.icon, COLORS.accent, 34))
        badge.setStyleSheet(f"background: {COLORS.accent_soft}; border-radius: 22px;")

        hero = Card(padding=32, spacing=10)
        hero.body.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)
        hero.body.addSpacing(6)
        title = label(info.name, "display")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.body.addWidget(title)
        chip_row = QHBoxLayout()
        chip_row.addStretch(1)
        chip_row.addWidget(Chip("En attente de développement", "violet", "clock"))
        chip_row.addStretch(1)
        hero.body.addLayout(chip_row)
        description = label(info.description, "muted", wrap=True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.body.addWidget(description)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(hero)

        if info.roadmap:
            roadmap = Card(flat=True, padding=22, spacing=12)
            roadmap.body.addWidget(label("CE QUI EST PRÉVU", "overline"))
            for feature in info.roadmap:
                row = QHBoxLayout()
                row.setSpacing(10)
                tick = QLabel()
                tick.setPixmap(icons.pixmap("chevron-right", COLORS.accent, 16))
                row.addWidget(tick, 0, Qt.AlignmentFlag.AlignTop)
                row.addWidget(label(feature, wrap=True), 1)
                roadmap.body.addLayout(row)
            layout.addWidget(roadmap)
        layout.addStretch(1)

        centered = QWidget()
        outer = QHBoxLayout(centered)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        content.setMaximumWidth(760)
        outer.addWidget(content, 4)
        outer.addStretch(1)
        self.setWidget(centered)
