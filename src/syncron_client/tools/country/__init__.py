"""Rubrique Pays : la page d'accueil du pays, avec les onglets R&D, Membres et Banque.

L'accueil résume l'essentiel (avancement de la R&D, membres, solde de la banque) ; un clic
sur une carte ouvre l'onglet correspondant.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from syncron_client.platform.hub import HubTool
from syncron_client.platform.tool import ToolInfo
from syncron_client.tools.bank import money
from syncron_client.tools.research.model import parse_domains
from syncron_client.ui import icons
from syncron_client.ui.brand import logo_pixmap
from syncron_client.ui.snow import Snowfall
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, Chip, button, label


class SummaryCard(Card):
    openRequested = Signal(str)

    def __init__(self, tool_id: str, title: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=20, spacing=8)
        badge = QLabel()
        badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icons.pixmap(icon_name, COLORS.accent, 20))
        badge.setStyleSheet(f"background: {COLORS.accent_soft}; border-radius: 12px;")
        open_button = button("Ouvrir", "arrow-right", "ghost")
        open_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        open_button.clicked.connect(lambda: self.openRequested.emit(tool_id))
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(badge)
        head.addWidget(label(title, "heading"), 1)
        head.addWidget(open_button)
        self.value = label("—", "stat")
        self.detail = label(" ", "muted", wrap=True)
        self.chip = Chip("", "neutral")
        self.chip.hide()
        self.body.addLayout(head)
        self.body.addWidget(self.value)
        self.body.addWidget(self.detail)
        self.body.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignLeft)
        self.body.addStretch(1)

    def show_data(self, value: str, detail: str, chip: tuple[str, str] | None = None) -> None:
        self.value.setText(value)
        self.detail.setText(detail)
        self.chip.setVisible(chip is not None)
        if chip is not None:
            self.chip.set_content(chip[0], chip[1], "check" if chip[1] == "success" else "info")


class CountryHome(QScrollArea):
    openRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hero = Card(padding=26, spacing=0)
        hero.setStyleSheet(
            "QFrame[card='true'] { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f" stop:0 {COLORS.hero_start}, stop:0.55 {COLORS.surface}, stop:1 {COLORS.hero_end}); }}"
        )
        logo = QLabel()
        logo.setFixedSize(64, 64)
        logo.setPixmap(logo_pixmap(64))
        self.title = label("", "display")
        self.subtitle = label("", "muted", wrap=True)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(label("NOTRE PAYS", "overline"))
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        row = QHBoxLayout()
        row.setSpacing(20)
        row.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addLayout(texts, 1)
        hero.body.addLayout(row)
        self.snow = Snowfall(hero) if COLORS.festive else None

        self.cards = {
            "research": SummaryCard("research", "R&D", "flask"),
            "members": SummaryCard("members", "Membres", "users"),
            "bank": SummaryCard("bank", "Banque", "database"),
        }
        grid = QGridLayout()
        grid.setSpacing(16)
        for index, card in enumerate(self.cards.values()):
            card.openRequested.connect(self.openRequested)
            grid.addWidget(card, 0, index)
            grid.setColumnStretch(index, 1)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(hero)
        layout.addLayout(grid)
        layout.addStretch(1)
        self.setWidget(content)

    def set_nation(self, name: str, online: bool) -> None:
        self.title.setText(name or "Notre pays")
        self.subtitle.setText(
            "Avancement de la recherche, membres et finances du pays, au même endroit."
            + ("" if online else " Hors ligne : dernières données reçues.")
        )

    def show_summary(self, summary: dict[str, Any]) -> None:
        domains = summary.get("research")
        if domains is not None:
            total = sum(d.tier_count for d in domains)
            done = sum(d.completed for d in domains)
            ready = [d for d in domains if d.ready()]
            names = ", ".join(f"{d.name} {d.next_level}" for d in ready)
            self.cards["research"].show_data(
                f"{done} / {total}",
                f"paliers validés dans {len(domains)} domaines",
                (f"Prêt à valider : {names}", "success") if ready else None,
            )
        members = summary.get("members")
        if members is not None:
            with_profile = sum(1 for m in members if m.get("nickname") or m.get("title") or m.get("bio"))
            self.cards["members"].show_data(str(len(members)), f"membre(s), dont {with_profile} avec un profil rempli")
        bank = summary.get("bank")
        if bank is not None:
            self.cards["bank"].show_data(
                money(int(bank["balance"])),
                f"+{money(int(bank['income_30_days']))} et −{money(int(bank['expenses_30_days']))} sur 30 jours",
            )


class CountryTool(HubTool):
    home_title = "Accueil du pays"
    _INFO = ToolInfo(
        id="country",
        name="Pays",
        description="La page du pays : avancement de la R&D, membres et banque.",
        icon="flag",
        version="5.3.0",
    )

    def __init__(self) -> None:
        super().__init__()
        self._home: CountryHome | None = None
        self.summary: dict[str, Any] = {}

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def home(self) -> CountryHome | None:
        return self._home

    def create_home(self) -> QWidget:
        self._home = CountryHome()
        self._home.openRequested.connect(self.show_child)
        return self._home

    def open(self, key: str) -> None:
        tool_id, _, item = key.partition(":")
        child = self.child(tool_id)
        if child is not None:
            self.show_child(tool_id)
            if item:
                child.open(item)

    def refresh_home(self) -> None:
        session = self._host.session
        if self._home is None:
            return
        self._home.set_nation(session.nation_name, session.online)
        research = self.child("research")
        if research is not None and getattr(research, "domains", None):
            self.summary["research"] = research.domains
            self._home.show_summary(self.summary)
        if not session.online:
            return
        api = self._host.api

        def load() -> dict[str, Any]:
            return {"research": parse_domains(api.research()), "members": api.members(), "bank": api.bank()}

        def done(summary: dict[str, Any]) -> None:
            self.summary = summary
            if self._home is not None:
                self._home.show_summary(summary)

        self._host.runner.run(load, done, lambda error: self._host.handle_error(error, "Pays"))
