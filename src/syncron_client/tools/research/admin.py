"""Gestion de la R&D.

    ┌ Domaines ┐ ┌ Domaine : nom, icône, paliers, paliers validés, compétence Craft              ┐
    │ Global   │ └──────────────────────────────────────────────────────────────────────────────┘
    │ Militaire│ ┌ Paliers : [1] [2] [3] … (couleur = état, liseré = renseigné)                  ┐
    │ …        │ │ Palier 3 · nom · description                                                  │
    └──────────┘ │ Conditions : texte, objet, quantité, réunis, remplie   (+ Ajouter)            │
                 │ Récompenses : texte                                     (+ Ajouter)            │
                 │ [Reprendre le palier précédent]                 [Enregistrer le palier]        │
                 └──────────────────────────────────────────────────────────────────────────────┘
Une condition tient sur trois rangées, une récompense sur une : rien ne déborde, quelle que
soit la largeur. « Remplie » ne se coche qu'une fois la quantité réunie atteinte.
"""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.tools.research.model import Domain, Line, Tier, parse_domains
from syncron_client.ui import icons
from syncron_client.ui.entity_list import EntityList
from syncron_client.ui.theme import COLORS, TONES
from syncron_client.ui.widgets import (
    Banner,
    Card,
    Chip,
    FlowWidget,
    ask,
    button,
    compact_combo,
    icon_button,
    label,
)
from syncron_core.catalog_service import CatalogService
from syncron_core.models.reference import SkillKind
from syncron_core.text import format_quantity, normalize

DOMAIN_ICONS = (
    ("globe", "Globe"),
    ("sword", "Épée"),
    ("pickaxe", "Pioche"),
    ("station", "Usine"),
    ("cpu", "Technologie"),
    ("flask", "Fiole"),
    ("shield", "Bouclier"),
    ("gem", "Gemme"),
)
DOMAIN_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,31}$")
MAX_SPIN = 2_000_000_000


def _spin(prefix: str) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(0, MAX_SPIN)
    spin.setGroupSeparatorShown(True)
    spin.setSpecialValueText(f"{prefix} —")
    spin.setPrefix(f"{prefix} ")
    spin.setMinimumWidth(130)
    return spin


class LineRow(QFrame):
    """Une condition (texte, objet, quantité, réunis, remplie) ou une récompense (texte seul)."""

    changed = Signal()
    removeRequested = Signal(object)
    moveRequested = Signal(object, int)

    def __init__(self, line: Line, items: list[tuple[str, str]], condition: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.line_id = line.id
        self.condition = condition
        self.setStyleSheet(
            f"LineRow {{ background: {COLORS.surface}; border: 1px solid {COLORS.border}; border-radius: 10px; }}"
        )
        self.text_field = QLineEdit(line.text)
        self.text_field.setMaxLength(300)
        self.text_field.setPlaceholderText("Déposer, casser, avoir 10 membres…" if condition else "Débloque…, +5 % de…")
        self.item_field = compact_combo(editable=True, min_chars=10)
        self.item_field.addItem("Aucun objet", None)
        if condition:
            for key, name in items:
                self.item_field.addItem(name, key)
                self.item_field.setItemData(self.item_field.count() - 1, key, Qt.ItemDataRole.ToolTipRole)
            if line.item_id:
                index = self.item_field.findData(line.item_id)
                if index < 0:
                    self.item_field.addItem(f"{line.item_id} (inconnu)", line.item_id)
                    index = self.item_field.count() - 1
                self.item_field.setCurrentIndex(index)
        self.item_field.lineEdit().setCursorPosition(0)
        self.item_field.setToolTip("Objet du catalogue Craft (facultatif)")
        self.quantity_field = _spin("Quantité")
        self.quantity_field.setValue(line.quantity or 0)
        self.progress_field = _spin("Réunis")
        self.progress_field.setValue(line.progress or 0)
        self.done_field = QCheckBox("Remplie")
        self.done_field.setChecked(line.done)
        up = icon_button("chevron-up", "Monter", 14)
        down = icon_button("chevron-down", "Descendre", 14)
        remove = icon_button("close", "Retirer", 14)
        up.clicked.connect(lambda: self.moveRequested.emit(self, -1))
        down.clicked.connect(lambda: self.moveRequested.emit(self, 1))
        remove.clicked.connect(lambda: self.removeRequested.emit(self))

        grid = QGridLayout(self)
        grid.setContentsMargins(10, 8, 8, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.addWidget(self.text_field, 0, 0, 1, 2)
        tools = QHBoxLayout()
        tools.setSpacing(0)
        tools.addWidget(up)
        tools.addWidget(down)
        tools.addWidget(remove)
        grid.addLayout(tools, 0, 2)
        if condition:
            grid.addWidget(self.item_field, 1, 0)
            grid.addWidget(self.quantity_field, 1, 1)
            follow = QHBoxLayout()
            follow.setSpacing(10)
            follow.addWidget(self.progress_field)
            follow.addWidget(self.done_field)
            follow.addStretch(1)
            grid.addLayout(follow, 2, 0, 1, 3)
        else:
            for field in (self.item_field, self.quantity_field, self.progress_field, self.done_field):
                field.hide()
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)

        for signal in (
            self.text_field.textChanged,
            self.item_field.currentIndexChanged,
            self.quantity_field.valueChanged,
            self.progress_field.valueChanged,
            self.done_field.toggled,
        ):
            signal.connect(self.changed)
        self.quantity_field.valueChanged.connect(self._update)
        self.progress_field.valueChanged.connect(self._update)
        self._update()

    def line(self) -> Line:
        if not self.condition:
            return Line(self.text_field.text().strip(), id=self.line_id)
        quantity = self.quantity_field.value() or None
        progress = self.progress_field.value() if quantity else None
        item_id = self.item_field.currentData() or None
        line = Line(self.text_field.text().strip(), quantity, item_id, False, progress, self.line_id)
        done = self.done_field.isChecked() and line.reached
        return Line(line.text, quantity, item_id, done, progress, self.line_id)

    def is_blank(self) -> bool:
        line = self.line()
        return not line.text and not line.item_id

    def _update(self, *_args) -> None:
        """« Remplie » n'est cochable qu'une fois la quantité atteinte ; elle se décoche si le compte redescend."""
        quantity = self.quantity_field.value()
        self.progress_field.setEnabled(quantity > 0)
        self.progress_field.setSuffix(f" / {format_quantity(quantity)}" if self.condition and quantity else "")
        reached = not quantity or self.progress_field.value() >= quantity
        if not reached and self.done_field.isChecked():
            self.done_field.setChecked(False)
        self.done_field.setEnabled(reached)
        missing = quantity - self.progress_field.value()
        self.done_field.setToolTip(
            "Condition remplie" if reached else f"Il en manque {format_quantity(missing)} pour pouvoir cocher"
        )


class LinesEditor(QWidget):
    """Liste de LineRow avec bouton d'ajout ; `lines()` renvoie les lignes remplies, dans l'ordre."""

    changed = Signal()

    def __init__(self, add_label: str, with_done: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._condition = with_done
        self._items: list[tuple[str, str]] = []
        self._rows: list[LineRow] = []
        self._layout = QVBoxLayout()
        self._layout.setSpacing(6)
        self.empty = label("Aucune pour l'instant.", "faint")
        add = button(add_label, "plus", "ghost")
        add.clicked.connect(lambda: self.add_line(Line("")))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.addWidget(self.empty)
        outer.addLayout(self._layout)
        outer.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)

    @property
    def rows(self) -> list[LineRow]:
        return list(self._rows)

    def set_items(self, items: list[tuple[str, str]]) -> None:
        self._items = items

    def set_lines(self, lines: tuple[Line, ...] | list[Line]) -> None:
        for row in self._rows:
            row.hide()
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        for line in lines:
            self.add_line(line, notify=False)
        self.empty.setVisible(not self._rows)

    def lines(self) -> list[Line]:
        return [row.line() for row in self._rows if not row.is_blank()]

    def add_line(self, line: Line, notify: bool = True) -> LineRow:
        row = LineRow(line, self._items, self._condition)
        row.changed.connect(self.changed)
        row.removeRequested.connect(self._remove)
        row.moveRequested.connect(self._move)
        self._rows.append(row)
        self._layout.addWidget(row)
        self.empty.hide()
        if notify:
            self.changed.emit()
            row.text_field.setFocus()
        return row

    def _remove(self, row: LineRow) -> None:
        self._rows.remove(row)
        row.hide()
        row.setParent(None)
        row.deleteLater()
        self.empty.setVisible(not self._rows)
        self.changed.emit()

    def _move(self, row: LineRow, delta: int) -> None:
        index = self._rows.index(row)
        target = index + delta
        if not 0 <= target < len(self._rows):
            return
        self._rows.insert(target, self._rows.pop(index))
        self._layout.removeWidget(row)
        self._layout.insertWidget(target, row)
        self.changed.emit()


class TierStrip(QWidget):
    """Boutons numérotés des paliers ; couleur = état, liseré = palier renseigné."""

    chosen = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._flow = FlowWidget(spacing=6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.chosen)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._flow)

    def set_domain(self, domain: Domain | None, selected: int | None) -> None:
        for tier_button in self._group.buttons():
            self._group.removeButton(tier_button)
        self._flow.clear()
        if domain is None:
            return
        for tier in domain.tiers:
            status = domain.status(tier.level)
            color, background = TONES[status.tone]
            filled = not tier.is_empty
            tier_button = QPushButton(str(tier.level))
            tier_button.setCheckable(True)
            tier_button.setFixedSize(40, 34)
            tier_button.setCursor(Qt.CursorShape.PointingHandCursor)
            tooltip = f"Palier {tier.level} · {status.label}" + (f" · {tier.name}" if tier.name else "")
            tier_button.setToolTip(tooltip + ("" if filled else " · vide"))
            underline = f"border-bottom: 3px solid {color};" if filled else ""
            tier_button.setStyleSheet(
                f"QPushButton {{ padding: 0; color: {color}; background: {background}; border-radius: 9px;"
                f" border: 1px solid {COLORS.border}; {underline} font-weight: 600; }}"
                f"QPushButton:checked {{ border: 2px solid {COLORS.accent}; {underline} }}"
            )
            self._group.addButton(tier_button, tier.level)
            self._flow.add(tier_button)
        if selected is not None and self._group.button(selected) is not None:
            self._group.button(selected).setChecked(True)

    def select(self, level: int | None) -> None:
        tier_button = self._group.button(level) if level else None
        if tier_button is not None:
            tier_button.setChecked(True)

    def current(self) -> int | None:
        level = self._group.checkedId()
        return level if level > 0 else None


class ResearchAdmin(QWidget):
    changed = Signal(list)  # domaines à jour

    def __init__(self, host: ToolHost, catalog: CatalogService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._catalog = catalog
        self._domains: dict[str, Domain] = {}
        self._current: str | None = None
        self._level: int | None = None
        self._loading = False
        self._domain_dirty = False
        self._tier_dirty = False
        self._pending_level: int | None = None

        self.list = EntityList("DOMAINES", "Rechercher…")
        self.list.selected.connect(self._on_selected)
        self.list.setMinimumWidth(190)

        # -- domaine --
        self.domain_banner = Banner("danger")
        self.domain_banner.hide()
        self.heading = label("", "title")
        new_button = button("Nouveau", "plus")
        new_button.setToolTip("Nouveau domaine de recherche")
        new_button.clicked.connect(lambda: self._confirm_leave() and self.load(None))
        self.name_field = QLineEdit()
        self.name_field.setMaxLength(80)
        self.name_field.setPlaceholderText("Nom")
        self.id_field = QLineEdit()
        self.id_field.setPlaceholderText("identifiant")
        self.icon_field = compact_combo(min_chars=8)
        for icon_name, text in DOMAIN_ICONS:
            self.icon_field.addItem(icons.icon(icon_name, COLORS.accent, 16), text, icon_name)
        self.skill_field = compact_combo(min_chars=10)
        self.skill_field.setToolTip(
            "Les recettes qui exigent cette compétence au niveau N s'affichent sous le palier N."
        )
        self.tier_count_field = QSpinBox()
        self.tier_count_field.setRange(0, 100)
        self.tier_count_field.setSuffix(" palier(s)")
        self.completed_field = QSpinBox()
        self.completed_field.setRange(0, 100)
        self.completed_field.setSuffix(" validé(s)")
        self.completed_field.setToolTip(
            "Pour corriger l'avancement (pays déjà avancé en jeu). Au quotidien, valide les paliers depuis la page R&D."
        )
        self.description_field = QPlainTextEdit()
        self.description_field.setPlaceholderText("Description (facultative)")
        self.description_field.setFixedHeight(56)
        self.delete_button = button("Supprimer", "trash", "ghost")
        self.delete_button.setStyleSheet(f"QPushButton {{ color: {COLORS.danger}; }}")
        self.delete_button.clicked.connect(self._delete)
        self.save_domain_button = button("Enregistrer", "save", "primary")
        self.save_domain_button.setToolTip("Enregistrer le domaine")
        self.save_domain_button.clicked.connect(self.save_domain)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.addWidget(label("Nom", "faint"), 0, 0)
        grid.addWidget(label("Icône", "faint"), 0, 1)
        grid.addWidget(self.name_field, 1, 0)
        grid.addWidget(self.icon_field, 1, 1)
        grid.addWidget(label("Paliers", "faint"), 2, 0)
        grid.addWidget(label("Paliers validés", "faint"), 2, 1)
        grid.addWidget(self.tier_count_field, 3, 0)
        grid.addWidget(self.completed_field, 3, 1)
        grid.addWidget(label("Compétence Craft liée", "faint"), 4, 0)
        self._id_label = label("Identifiant", "faint")
        grid.addWidget(self._id_label, 4, 1)
        grid.addWidget(self.skill_field, 5, 0)
        grid.addWidget(self.id_field, 5, 1)
        grid.addWidget(self.description_field, 6, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        header = QHBoxLayout()
        header.addWidget(self.heading, 1)
        header.addWidget(new_button)
        domain_actions = QHBoxLayout()
        domain_actions.addWidget(self.delete_button)
        domain_actions.addStretch(1)
        domain_actions.addWidget(self.save_domain_button)
        domain_card = Card(padding=18, spacing=10)
        domain_card.body.addLayout(header)
        domain_card.body.addWidget(self.domain_banner)
        domain_card.body.addLayout(grid)
        domain_card.body.addLayout(domain_actions)

        # -- paliers --
        self.strip = TierStrip()
        self.strip.chosen.connect(self._tier_chosen)
        self.tier_banner = Banner("danger")
        self.tier_banner.hide()
        self.tier_title = label("", "heading")
        self.tier_status = Chip("", "neutral")
        self.tier_name_field = QLineEdit()
        self.tier_name_field.setMaxLength(120)
        self.tier_name_field.setPlaceholderText("Nom du palier (facultatif)")
        self.tier_description_field = QPlainTextEdit()
        self.tier_description_field.setPlaceholderText("Description du palier (facultative)")
        self.tier_description_field.setFixedHeight(52)
        self.conditions = LinesEditor("Ajouter une condition", with_done=True)
        self.rewards = LinesEditor("Ajouter une récompense", with_done=False)
        self.copy_previous_button = button("Reprendre le palier précédent", "copy", "ghost")
        self.copy_previous_button.setToolTip("Copie ses conditions et récompenses (sans la progression)")
        self.copy_previous_button.clicked.connect(self.copy_previous)
        self.save_tier_button = button("Enregistrer le palier", "save", "primary")
        self.save_tier_button.clicked.connect(self.save_tier)
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        save_shortcut.activated.connect(self._save_current)
        tier_head = QHBoxLayout()
        tier_head.addWidget(self.tier_title)
        tier_head.addWidget(self.tier_status)
        tier_head.addWidget(self.tier_name_field, 1)
        self._tier_editor = QWidget()
        editor = QVBoxLayout(self._tier_editor)
        editor.setContentsMargins(0, 6, 0, 0)
        editor.setSpacing(10)
        editor.addLayout(tier_head)
        editor.addWidget(self.tier_banner)
        editor.addWidget(self.tier_description_field)
        editor.addWidget(label("CONDITIONS", "overline"))
        editor.addWidget(self.conditions)
        editor.addWidget(label("RÉCOMPENSES", "overline"))
        editor.addWidget(self.rewards)
        tier_actions = QHBoxLayout()
        tier_actions.addWidget(self.copy_previous_button)
        tier_actions.addStretch(1)
        tier_actions.addWidget(self.save_tier_button)
        editor.addLayout(tier_actions)
        self.tiers_hint = label("", "faint", wrap=True)
        tiers_card = Card(padding=18, spacing=10)
        tiers_card.body.addWidget(label("PALIERS", "overline"))
        tiers_card.body.addWidget(self.strip)
        tiers_card.body.addWidget(self.tiers_hint)
        tiers_card.body.addWidget(self._tier_editor)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(14)
        content_layout.addWidget(domain_card)
        content_layout.addWidget(tiers_card)
        content_layout.addStretch(1)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setWidget(content)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        splitter.addWidget(self.list)
        splitter.addWidget(self._scroll)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 980])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        for signal in (
            self.name_field.textChanged,
            self.icon_field.currentIndexChanged,
            self.description_field.textChanged,
            self.tier_count_field.valueChanged,
            self.completed_field.valueChanged,
            self.skill_field.currentIndexChanged,
        ):
            signal.connect(self._mark_domain_dirty)
        for signal in (
            self.tier_name_field.textChanged,
            self.tier_description_field.textChanged,
            self.conditions.changed,
            self.rewards.changed,
        ):
            signal.connect(self._mark_tier_dirty)
        self.tier_count_field.valueChanged.connect(lambda value: self.completed_field.setMaximum(value))
        self.load(None)

    # -- cycle ------------------------------------------------------------------------------

    @property
    def current_id(self) -> str | None:
        return self._current

    @property
    def current_level(self) -> int | None:
        return self._level

    def is_dirty(self) -> bool:
        return self._domain_dirty or self._tier_dirty

    def refresh(self) -> None:
        call_api(self._host, self._host.api.research, lambda document: self.set_domains(parse_domains(document)))

    def set_domains(self, domains: list[Domain]) -> None:
        self._domains = {d.id: d for d in domains}
        entries = [(d.id, d.name, d.progress_text, icons.icon(d.icon, COLORS.accent, 24)) for d in domains]
        self.list.set_entries(entries, keep=self._current)
        if self._current in self._domains and not self.is_dirty():
            self.load(self._current, self._pending_level or self._level)
            self.list.select(self._current, emit=False)
            self._pending_level = None
        elif self._current is None and domains and not self.is_dirty():
            self.load(domains[0].id)
            self.list.select(domains[0].id, emit=False)

    def open_key(self, key: str) -> None:
        """« militaire » ou « militaire:5 »."""
        domain_id, _, level = key.partition(":")
        if not self._confirm_leave():
            return
        self._pending_level = int(level) if level.isdigit() else None
        if domain_id in self._domains:
            self.load(domain_id, self._pending_level)
            self.list.select(domain_id, emit=False)
            self._pending_level = None
        else:
            self._current = domain_id
            self.refresh()

    def load(self, domain_id: str | None, level: int | None = None) -> None:
        domain = self._domains.get(domain_id) if domain_id else None
        self._current = domain.id if domain else None
        self._loading = True
        self.domain_banner.hide()
        self.heading.setText(domain.name if domain else "Nouveau domaine")
        self.name_field.setText(domain.name if domain else "")
        self.id_field.setText(domain.id if domain else "")
        self.id_field.setVisible(domain is None)
        self._id_label.setVisible(domain is None)
        self.icon_field.setCurrentIndex(max(self.icon_field.findData(domain.icon if domain else "flask"), 0))
        self.description_field.setPlainText(domain.description if domain else "")
        self.tier_count_field.setValue(domain.tier_count if domain else 0)
        self.completed_field.setMaximum(domain.tier_count if domain else 0)
        self.completed_field.setValue(domain.completed if domain else 0)
        self._fill_skills(domain.skill_id if domain else None)
        self.delete_button.setVisible(domain is not None)
        items = [(item.id, item.name) for item in self._catalog.list_items()]
        self.conditions.set_items(items)
        self._loading = False
        self._domain_dirty = False
        if domain and domain.tier_count:
            default = min(domain.completed + 1, domain.tier_count)
            chosen = level if level and 1 <= level <= domain.tier_count else default
            self.strip.set_domain(domain, chosen)
            self.tiers_hint.setText(
                "Choisis un palier. Vert : validé, bleu : prochain à valider. Liseré : palier renseigné."
            )
            self._show_tier(domain, domain.tier(chosen))
        else:
            self.strip.set_domain(None, None)
            self.tiers_hint.setText("Indique le nombre de paliers puis enregistre le domaine pour remplir ses paliers.")
            self._show_tier(domain, None)

    # -- enregistrement ----------------------------------------------------------------------

    def domain_payload(self) -> dict[str, Any]:
        return {
            "name": self.name_field.text().strip(),
            "description": self.description_field.toPlainText().strip(),
            "icon": self.icon_field.currentData(),
            "position": self._domains[self._current].position if self._current else len(self._domains),
            "tier_count": self.tier_count_field.value(),
            "completed": self.completed_field.value(),
            "skill_id": self.skill_field.currentData(),
        }

    def save_domain(self) -> None:
        domain_id = self._current or self.id_field.text().strip()
        payload = self.domain_payload()
        if not payload["name"]:
            self._refuse(self.domain_banner, "Le nom est obligatoire.")
            return
        if not DOMAIN_ID.match(domain_id):
            self._refuse(self.domain_banner, "Identifiant : minuscules, chiffres, _ et -, 32 caractères au plus.")
            return
        if self._current is None and domain_id in self._domains:
            self._refuse(self.domain_banner, f"Le domaine « {domain_id} » existe déjà.")
            return
        level = self._level

        def saved(raw: dict[str, Any]) -> None:
            self._domain_dirty = False
            self._current = raw["id"]
            self._after_write(level)

        call_api(
            self._host,
            lambda: self._host.api.put_research_category(domain_id, payload),
            saved,
            banner=self.domain_banner,
            success=f"Domaine « {payload['name']} » enregistré.",
        )

    def tier_payload(self) -> dict[str, Any]:
        return {
            "name": self.tier_name_field.text().strip(),
            "description": self.tier_description_field.toPlainText().strip(),
            "conditions": [line.to_api() for line in self.conditions.lines()],
            "rewards": [line.reward_to_api() for line in self.rewards.lines()],
        }

    def save_tier(self) -> None:
        domain_id, level = self._current, self._level
        if domain_id is None or level is None:
            return
        payload = self.tier_payload()

        def saved(_raw: dict[str, Any]) -> None:
            self._tier_dirty = False
            self._after_write(level)

        call_api(
            self._host,
            lambda: self._host.api.put_research_tier(domain_id, level, payload),
            saved,
            banner=self.tier_banner,
            success=f"Palier {level} enregistré.",
        )

    def copy_previous(self) -> None:
        domain = self._domains.get(self._current or "")
        if domain is None or not self._level or self._level < 2:
            return
        previous = domain.tier(self._level - 1)
        if previous is None or previous.is_empty:
            self._refuse(self.tier_banner, f"Le palier {self._level - 1} est vide.")
            return
        conditions = [Line(line.text, line.quantity, line.item_id) for line in previous.conditions]
        rewards = [Line(line.text) for line in previous.rewards]
        self.conditions.set_lines([*self.conditions.lines(), *conditions])
        self.rewards.set_lines([*self.rewards.lines(), *rewards])
        self._tier_dirty = True

    def _save_current(self) -> None:
        if self._tier_dirty:
            self.save_tier()
        elif self._domain_dirty:
            self.save_domain()

    def _after_write(self, level: int | None) -> None:
        def reloaded(document: dict[str, Any]) -> None:
            domains = parse_domains(document)
            self._pending_level = level
            self.set_domains(domains)
            self._pending_level = None
            self.changed.emit(domains)

        call_api(self._host, self._host.api.research, reloaded)

    def _delete(self) -> None:
        domain = self._domains.get(self._current or "")
        if domain is None:
            return
        if ask(self, "Supprimer", f"Supprimer le domaine « {domain.name} » et tous ses paliers ? C'est définitif."):
            self.delete_domain(domain.id)

    def delete_domain(self, domain_id: str) -> None:
        def deleted(_result: Any) -> None:
            self._current = None
            self._domain_dirty = self._tier_dirty = False
            self._after_write(None)

        call_api(
            self._host,
            lambda: self._host.api.delete_research_category(domain_id),
            deleted,
            banner=self.domain_banner,
            success="Domaine supprimé.",
        )

    # -- interne ----------------------------------------------------------------------------

    def _fill_skills(self, selected: str | None) -> None:
        self.skill_field.clear()
        self.skill_field.addItem("Aucune", None)
        skills = sorted(self._catalog.skills(), key=lambda s: (s.kind is not SkillKind.RESEARCH, normalize(s.name)))
        for skill in skills:
            self.skill_field.addItem(skill.name, skill.id)
            self.skill_field.setItemData(self.skill_field.count() - 1, skill.kind.label, Qt.ItemDataRole.ToolTipRole)
        index = self.skill_field.findData(selected) if selected else 0
        if index < 0:
            self.skill_field.addItem(f"{selected} (inconnue)", selected)
            index = self.skill_field.count() - 1
        self.skill_field.setCurrentIndex(index)

    def _tier_chosen(self, level: int) -> None:
        if level == self._level:
            return
        if self._tier_dirty and not ask(self, "Palier non enregistré", "Abandonner les modifications de ce palier ?"):
            self.strip.select(self._level)
            return
        domain = self._domains.get(self._current or "")
        self._show_tier(domain, domain.tier(level) if domain else None)

    def select_tier(self, level: int) -> None:
        """Comme un clic sur le bouton du palier."""
        self.strip.select(level)
        self._tier_chosen(level)

    def _show_tier(self, domain: Domain | None, tier: Tier | None) -> None:
        self._level = tier.level if tier else None
        self._tier_editor.setVisible(tier is not None)
        self._loading = True
        if tier is not None and domain is not None:
            status = domain.status(tier.level)
            self.tier_title.setText(f"Palier {tier.level}")
            self.tier_status.set_content(status.label, status.tone, status.icon)
            self.copy_previous_button.setEnabled(tier.level > 1)
        self.tier_name_field.setText(tier.name if tier else "")
        self.tier_description_field.setPlainText(tier.description if tier else "")
        self.conditions.set_lines(tier.conditions if tier else ())
        self.rewards.set_lines(tier.rewards if tier else ())
        self.tier_banner.hide()
        self._loading = False
        self._tier_dirty = False

    def _on_selected(self, key: str) -> None:
        if key == self._current:
            return
        if self._confirm_leave():
            self.load(key)
        elif self._current:
            self.list.select(self._current, emit=False)

    def _confirm_leave(self) -> bool:
        if not self.is_dirty():
            return True
        return ask(self, "Modifications non enregistrées", "Abandonner les modifications en cours ?")

    def _refuse(self, banner: Banner, text: str) -> None:
        banner.set_text(text)
        banner.show()

    def _mark_domain_dirty(self, *_args) -> None:
        if not self._loading:
            self._domain_dirty = True

    def _mark_tier_dirty(self, *_args) -> None:
        if not self._loading:
            self._tier_dirty = True
