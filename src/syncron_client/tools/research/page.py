"""Page R&D : les domaines du pays, leur avancement, et le détail de chaque palier.

Les comptes qui gèrent la R&D suivent la progression directement ici :
cocher une condition remplie, saisir la quantité réunie (380 / 1 000),
lancer un palier ou le déclarer terminé.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from syncron_client.tools.research.model import Domain, Line, Tier, TierStatus, unlocked_recipes
from syncron_client.ui import icons
from syncron_client.ui.item_icons import IconProvider
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, Chip, EmptyState, button, icon_button, label
from syncron_core.catalog_service import CatalogService
from syncron_core.converter import STACK, decompose
from syncron_core.text import format_quantity

START, COMPLETE = "start", "complete"


def _bar(maximum: int, value: int, color: str = COLORS.accent) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, max(maximum, 1))
    bar.setValue(min(value, max(maximum, 1)))
    bar.setTextVisible(False)
    bar.setStyleSheet(
        f"QProgressBar {{ background: {COLORS.border}; }}"
        f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
    )
    return bar


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


class DomainCard(QFrame):
    clicked = Signal(str)

    def __init__(self, domain: Domain, selected: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.domain = domain
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        border = COLORS.accent if selected else COLORS.border
        background = COLORS.surface_hover if selected else COLORS.surface
        self.setStyleSheet(
            f"DomainCard {{ background: {background}; border: 1px solid {border}; border-radius: 12px; }}"
        )
        badge = QLabel()
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icons.pixmap(domain.icon, COLORS.accent, 17))
        badge.setStyleSheet(f"background: {COLORS.accent_soft}; border-radius: 10px;")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(domain.name, "heading"))
        state = domain.progress_text
        if domain.active:
            state += " · en cours"
        elif domain.finished:
            state += " · terminé"
        texts.addWidget(label(state, "faint"))
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(badge)
        head.addLayout(texts, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(head)
        layout.addWidget(_bar(domain.tier_count, domain.completed))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.domain.id)
        super().mousePressEvent(event)


class ConditionRow(QWidget):
    """Une condition : état, texte, et pour une condition chiffrée la jauge (et la saisie pour l'équipe)."""

    changed = Signal(int, dict)  # id de la ligne, modification

    def __init__(
        self, line: Line, catalog: CatalogService, provider: IconProvider, editable: bool, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.line = line
        top = QHBoxLayout()
        top.setSpacing(8)
        self.done_box: QCheckBox | None = None
        if editable and line.id is not None:
            self.done_box = QCheckBox()
            self.done_box.setChecked(line.done)
            self.done_box.setToolTip("Condition remplie")
            self.done_box.toggled.connect(lambda checked: self.changed.emit(line.id, {"done": checked}))
            top.addWidget(self.done_box, 0, Qt.AlignmentFlag.AlignTop)
        else:
            glyph = QLabel()
            name, color = ("check-circle", COLORS.success) if line.done else ("circle", COLORS.text_faint)
            glyph.setPixmap(icons.pixmap(name, color, 16))
            top.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        if line.item_id and catalog.get(line.item_id) is not None:
            item_icon = QLabel()
            item_icon.setPixmap(provider.item_pixmap(line.item_id, 18))
            top.addWidget(item_icon, 0, Qt.AlignmentFlag.AlignTop)
        text = label(line.describe(catalog), wrap=True)
        if line.quantity and line.quantity >= STACK.size():
            text.setToolTip(f"{format_quantity(line.quantity)} = {decompose(line.quantity).text()}")
        if line.done:
            text.setStyleSheet(f"color: {COLORS.text_muted};")
        top.addWidget(text, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)
        layout.addLayout(top)
        self.progress_spin: QSpinBox | None = None
        if line.tracked:
            gauge = QHBoxLayout()
            gauge.setContentsMargins(26, 0, 0, 0)
            gauge.setSpacing(8)
            color = COLORS.success if line.done else COLORS.accent
            gauge.addWidget(_bar(line.quantity, line.progress or 0, color), 1)
            if editable and line.id is not None:
                self.progress_spin = QSpinBox()
                self.progress_spin.setRange(0, min(line.quantity * 10, 2_000_000_000))
                self.progress_spin.setGroupSeparatorShown(True)
                self.progress_spin.setKeyboardTracking(False)
                self.progress_spin.setValue(line.progress or 0)
                self.progress_spin.setSuffix(f" / {format_quantity(line.quantity)}")
                self.progress_spin.setToolTip("Quantité déjà réunie (Entrée pour enregistrer)")
                self.progress_spin.setMinimumWidth(130)
                self.progress_spin.editingFinished.connect(self._progress_edited)
                gauge.addWidget(self.progress_spin)
            else:
                percent = round(line.fraction * 100)
                gauge.addWidget(label(f"{line.progress_text()} · {percent} %", "faint"))
            layout.addLayout(gauge)

    def set_progress(self, value: int) -> None:
        """Saisie au clavier puis Entrée (utilisé aussi par les tests)."""
        if self.progress_spin is not None:
            self.progress_spin.setValue(value)
            self._progress_edited()

    def _progress_edited(self) -> None:
        value = self.progress_spin.value()
        if value != (self.line.progress or 0):
            self.changed.emit(self.line.id, {"progress": value})


class TierCard(Card):
    lineChanged = Signal(int, dict)
    actionRequested = Signal(str, int)  # START / COMPLETE, palier
    editRequested = Signal(int)

    def __init__(
        self,
        domain: Domain,
        tier: Tier,
        catalog: CatalogService,
        icon_provider: IconProvider,
        editable: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, flat=True, padding=16, spacing=10)
        self.tier = tier
        status = domain.status(tier.level)
        self.status = status
        self.rows: list[ConditionRow] = []
        if status is TierStatus.ACTIVE:
            self.setStyleSheet(f"QFrame[card='flat'] {{ border: 1px solid {COLORS.accent}; }}")
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(label(tier.title, "heading"), 1)
        if tier.conditions:
            head.addWidget(Chip(f"{tier.done_count} / {len(tier.conditions)} conditions", "neutral"))
        head.addWidget(Chip(status.label, status.tone, status.icon))
        if editable:
            if status is TierStatus.NEXT and not domain.active:
                start = button("Lancer", "play", "ghost")
                start.setToolTip("Déclarer ce palier comme recherche en cours")
                start.clicked.connect(lambda: self.actionRequested.emit(START, tier.level))
                head.addWidget(start)
            if status is TierStatus.ACTIVE:
                complete = button("Valider", "check", "ghost")
                complete.setToolTip("Déclarer ce palier terminé (le pays est prévenu)")
                complete.clicked.connect(lambda: self.actionRequested.emit(COMPLETE, tier.level))
                head.addWidget(complete)
            edit = icon_button("edit", "Modifier ce palier dans l'administration", 15)
            edit.clicked.connect(lambda: self.editRequested.emit(tier.level))
            head.addWidget(edit)
        self.body.addLayout(head)
        if tier.description:
            self.body.addWidget(label(tier.description, "muted", wrap=True))
        if tier.is_empty:
            self.body.addWidget(label("Conditions et récompenses pas encore renseignées.", "faint"))
            return
        columns = QHBoxLayout()
        columns.setSpacing(20)
        conditions = QVBoxLayout()
        conditions.setSpacing(6)
        conditions.addWidget(label("CONDITIONS", "overline"))
        if not tier.conditions:
            conditions.addWidget(label("—", "faint"))
        for line in tier.conditions:
            row = ConditionRow(line, catalog, icon_provider, editable and status is not TierStatus.DONE)
            row.changed.connect(self.lineChanged)
            self.rows.append(row)
            conditions.addWidget(row)
        conditions.addStretch(1)
        rewards = QVBoxLayout()
        rewards.setSpacing(6)
        rewards.addWidget(label("RÉCOMPENSES", "overline"))
        if not tier.rewards:
            rewards.addWidget(label("—", "faint"))
        for line in tier.rewards:
            row = QHBoxLayout()
            row.setSpacing(8)
            glyph = QLabel()
            glyph.setPixmap(icons.pixmap("gift", COLORS.violet, 16))
            row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(label(line.describe(catalog), wrap=True), 1)
            rewards.addLayout(row)
        rewards.addStretch(1)
        columns.addLayout(conditions, 3)
        columns.addLayout(rewards, 2)
        self.body.addLayout(columns)
        recipes = unlocked_recipes(catalog, domain.skill_id, tier.level)
        if recipes:
            self.body.addWidget(label("Débloque dans Craft : " + ", ".join(recipes), "faint", wrap=True))


class ResearchPage(QWidget):
    manageRequested = Signal(str)  # clé « domaine » ou « domaine:palier »
    lineChanged = Signal(int, dict)  # id de la condition, modification
    actionRequested = Signal(str, str, int)  # domaine, START / COMPLETE, palier

    def __init__(self, catalog: CatalogService, icon_provider: IconProvider, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._catalog = catalog
        self._icons = icon_provider
        self._domains: list[Domain] = []
        self._selected: str | None = None
        self._editable = False

        self._domain_list = QVBoxLayout()
        self._domain_list.setSpacing(10)
        self.summary = label("", "faint", wrap=True)
        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(10)
        left_layout.addWidget(label("DOMAINES", "overline"))
        left_layout.addLayout(self._domain_list)
        left_layout.addWidget(self.summary)
        left_layout.addStretch(1)
        left = QScrollArea()
        left.setWidgetResizable(True)
        left.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left.setWidget(left_content)
        left.setMinimumWidth(220)
        left.setMaximumWidth(290)

        self.header_icon = QLabel()
        self.header_icon.setFixedSize(52, 52)
        self.header_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_icon.setStyleSheet(f"background: {COLORS.accent_soft}; border-radius: 15px;")
        self.title = label("", "title")
        self.description = label("", "muted", wrap=True)
        self.progress_label = label("", "heading")
        self.state_chip = Chip("", "neutral")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.manage_button = button("Gérer", "edit")
        self.manage_button.clicked.connect(lambda: self._selected and self.manageRequested.emit(self._selected))
        self.hint = label(
            "Coche les conditions remplies et saisis les quantités réunies : tout le pays voit l'avancement.",
            "faint",
            wrap=True,
        )
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.title)
        titles.addWidget(self.description)
        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(self.header_icon, 0, Qt.AlignmentFlag.AlignTop)
        top.addLayout(titles, 1)
        top.addWidget(self.manage_button, 0, Qt.AlignmentFlag.AlignTop)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_label)
        progress_row.addWidget(self.state_chip)
        progress_row.addStretch(1)
        header = Card(padding=20, spacing=10)
        header.body.addLayout(top)
        header.body.addLayout(progress_row)
        header.body.addWidget(self.progress)
        header.body.addWidget(self.hint)

        self._tiers = QVBoxLayout()
        self._tiers.setSpacing(12)
        self._tier_cards: dict[int, TierCard] = {}
        tiers_content = QWidget()
        tiers_layout = QVBoxLayout(tiers_content)
        tiers_layout.setContentsMargins(0, 0, 6, 0)
        tiers_layout.addLayout(self._tiers)
        tiers_layout.addStretch(1)
        self._tiers_scroll = QScrollArea()
        self._tiers_scroll.setWidgetResizable(True)
        self._tiers_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tiers_scroll.setWidget(tiers_content)

        self._detail = QWidget()
        detail_layout = QVBoxLayout(self._detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(14)
        detail_layout.addWidget(header)
        detail_layout.addWidget(self._tiers_scroll, 1)
        self._empty = EmptyState(
            "flask", "Aucune donnée de R&D", "Les domaines de recherche apparaîtront ici dès la première connexion."
        )
        self._empty.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(16)
        layout.addWidget(left)
        layout.addWidget(self._detail, 1)
        layout.addWidget(self._empty, 1)

    # -- état -------------------------------------------------------------------------------

    @property
    def domains(self) -> list[Domain]:
        return self._domains

    @property
    def selected(self) -> Domain | None:
        return next((d for d in self._domains if d.id == self._selected), None)

    @property
    def tier_cards(self) -> dict[int, TierCard]:
        return self._tier_cards

    @property
    def editable(self) -> bool:
        return self._editable

    def set_editable(self, editable: bool) -> None:
        if editable != self._editable:
            self._editable = editable
            self._render()

    def set_domains(self, domains: list[Domain]) -> None:
        position = self._tiers_scroll.verticalScrollBar().value()
        self._domains = domains
        if self._selected not in {d.id for d in domains}:
            active = next((d for d in domains if d.active), None)
            self._selected = (active or domains[0]).id if domains else None
        self._render()
        QTimer.singleShot(0, lambda: self._tiers_scroll.verticalScrollBar().setValue(position))

    def select(self, domain_id: str, level: int | None = None) -> None:
        if domain_id not in {d.id for d in self._domains}:
            return
        self._selected = domain_id
        self._render()
        self._tiers_scroll.verticalScrollBar().setValue(0)
        if level is not None and level in self._tier_cards:
            card = self._tier_cards[level]
            card.setStyleSheet(f"QFrame[card='flat'] {{ border: 1px solid {COLORS.info}; }}")
            QTimer.singleShot(0, lambda: self._tiers_scroll.ensureWidgetVisible(card, 0, 40))

    def refresh_catalog(self) -> None:
        self._render()

    # -- rendu ------------------------------------------------------------------------------

    def _render(self) -> None:
        _clear(self._domain_list)
        for domain in self._domains:
            card = DomainCard(domain, domain.id == self._selected)
            card.clicked.connect(self.select)
            self._domain_list.addWidget(card)
        total = sum(d.tier_count for d in self._domains)
        done = sum(d.completed for d in self._domains)
        active = next((d for d in self._domains if d.active), None)
        running = f"Recherche en cours : {active.name}, palier {active.completed + 1}." if active else ""
        self.summary.setText(f"{done} palier(s) terminé(s) sur {total}. {running}".strip())
        domain = self.selected
        self._detail.setVisible(domain is not None)
        self._empty.setVisible(domain is None)
        self.manage_button.setVisible(self._editable and domain is not None)
        self.hint.setVisible(self._editable)
        if domain is not None:
            self._render_domain(domain)

    def _render_domain(self, domain: Domain) -> None:
        self.header_icon.setPixmap(icons.pixmap(domain.icon, COLORS.accent, 24))
        self.title.setText(domain.name)
        self.description.setText(domain.description)
        self.description.setVisible(bool(domain.description))
        self.progress_label.setText(domain.progress_text)
        self.progress.setRange(0, max(domain.tier_count, 1))
        self.progress.setValue(domain.completed)
        if domain.active:
            self.state_chip.set_content(f"Palier {domain.completed + 1} en cours", "accent", "play")
        elif domain.finished:
            self.state_chip.set_content("Domaine terminé", "success", "check")
        elif domain.tier_count == 0:
            self.state_chip.set_content("Paliers à définir", "warning", "info")
        else:
            self.state_chip.set_content(f"Prochain : palier {domain.completed + 1}", "info", "flag")
        _clear(self._tiers)
        self._tier_cards = {}
        for tier in domain.tiers:
            card = TierCard(domain, tier, self._catalog, self._icons, self._editable)
            card.lineChanged.connect(self.lineChanged)
            card.actionRequested.connect(
                lambda action, level, key=domain.id: self.actionRequested.emit(key, action, level)
            )
            card.editRequested.connect(lambda level, key=domain.id: self.manageRequested.emit(f"{key}:{level}"))
            self._tier_cards[tier.level] = card
            self._tiers.addWidget(card)
