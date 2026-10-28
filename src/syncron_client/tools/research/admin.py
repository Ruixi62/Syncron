"""Gestion de la R&D : domaines (paliers, progression, recherche en cours) et contenu de chaque palier."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.tools.research.model import Domain, Line, Tier, parse_domains
from syncron_client.ui import icons
from syncron_client.ui.entity_list import EntityList
from syncron_client.ui.tables import ROW_HEIGHT
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Banner, Card, button, icon_button, label
from syncron_core.catalog_service import CatalogService
from syncron_core.models.reference import SkillKind
from syncron_core.text import normalize

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


class LinesEditor(QWidget):
    """Lignes éditables d'un palier : texte, objet du catalogue (facultatif), quantité, réalisée."""

    changed = Signal()

    def __init__(self, add_label: str, with_done: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._with_done = with_done
        self._items: list[tuple[str, str]] = []
        headers = ["TEXTE", "OBJET (FACULTATIF)", "QUANTITÉ"] + (["FAIT"] if with_done else []) + [""]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 180)
        for column in range(2, len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 112)
        if with_done:
            self.table.setColumnWidth(3, 56)
        self.table.setColumnWidth(len(headers) - 1, 44)
        add = button(add_label, "plus", "ghost")
        add.clicked.connect(lambda: self.add_line(Line("")))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.table)
        layout.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)
        self._fit()

    def set_items(self, items: list[tuple[str, str]]) -> None:
        self._items = items

    def set_lines(self, lines: tuple[Line, ...]) -> None:
        self.table.setRowCount(0)
        for line in lines:
            self.add_line(line, notify=False)
        self._fit()

    def lines(self) -> list[Line]:
        result = []
        for row in range(self.table.rowCount()):
            text: QLineEdit = self.table.cellWidget(row, 0)
            item: QComboBox = self.table.cellWidget(row, 1)
            quantity: QSpinBox = self.table.cellWidget(row, 2)
            done = self._done_box(row)
            line = Line(
                text.text().strip(),
                quantity.value() or None,
                item.currentData() or None,
                bool(done and done.isChecked()),
            )
            if line.text or line.item_id:
                result.append(line)
        return result

    def add_line(self, line: Line, notify: bool = True) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        text = QLineEdit(line.text)
        text.setMaxLength(300)
        text.setPlaceholderText("Avoir 10 membres, déposer…")
        item = QComboBox()
        item.setEditable(True)
        item.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        item.addItem("—", None)
        for key, name in self._items:
            item.addItem(name, key)
            item.setItemData(item.count() - 1, key, Qt.ItemDataRole.ToolTipRole)
        if line.item_id:
            index = item.findData(line.item_id)
            if index < 0:
                item.addItem(f"{line.item_id} (inconnu)", line.item_id)
                index = item.count() - 1
            item.setCurrentIndex(index)
        item.lineEdit().setCursorPosition(0)
        item.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        item.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        quantity = QSpinBox()
        quantity.setRange(0, 2_000_000_000)
        quantity.setGroupSeparatorShown(True)
        quantity.setSpecialValueText("—")
        quantity.setValue(line.quantity or 0)
        remove: QToolButton = icon_button("close", "Retirer la ligne", 14)
        remove.clicked.connect(lambda: self._remove(text))
        self.table.setCellWidget(row, 0, text)
        self.table.setCellWidget(row, 1, item)
        self.table.setCellWidget(row, 2, quantity)
        if self._with_done:
            done = QCheckBox()
            done.setChecked(line.done)
            done.setToolTip("Condition remplie")
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(14, 0, 0, 0)
            holder_layout.addWidget(done)
            self.table.setCellWidget(row, 3, holder)
            done.toggled.connect(self.changed)
        self.table.setCellWidget(row, self.table.columnCount() - 1, remove)
        text.textChanged.connect(self.changed)
        item.currentIndexChanged.connect(self.changed)
        quantity.valueChanged.connect(self.changed)
        self._fit()
        if notify:
            self.changed.emit()
            text.setFocus()

    def _done_box(self, row: int) -> QCheckBox | None:
        if not self._with_done:
            return None
        holder = self.table.cellWidget(row, 3)
        return holder.findChild(QCheckBox) if holder is not None else None

    def _remove(self, text: QLineEdit) -> None:
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 0) is text:
                self.table.removeRow(row)
                break
        self._fit()
        self.changed.emit()

    def _fit(self) -> None:
        rows = max(self.table.rowCount(), 1)
        self.table.setFixedHeight(self.table.horizontalHeader().height() + rows * ROW_HEIGHT + 6)


class ResearchAdmin(QWidget):
    changed = Signal(list)  # domaines à jour

    def __init__(self, host: ToolHost, catalog: CatalogService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._catalog = catalog
        self._domains: dict[str, Domain] = {}
        self._current: str | None = None
        self._loading = False
        self._domain_dirty = False
        self._tier_dirty = False
        self._pending_level: int | None = None
        self._shown_level: int | None = None

        self.list = EntityList("DOMAINES", "Rechercher un domaine…")
        self.list.selected.connect(self._on_selected)
        self.list.setMinimumWidth(200)

        # -- domaine --
        self.domain_banner = Banner("danger")
        self.domain_banner.hide()
        self.heading = label("", "title")
        new_button = button("Nouveau", "plus")
        new_button.setToolTip("Nouveau domaine de recherche")
        new_button.clicked.connect(lambda: self._confirm_leave() and self.load(None))
        self.name_field = QLineEdit()
        self.name_field.setMaxLength(80)
        self.id_field = QLineEdit()
        self.id_field.setPlaceholderText("identifiant (minuscules)")
        self.icon_field = QComboBox()
        for icon_name, text in DOMAIN_ICONS:
            self.icon_field.addItem(icons.icon(icon_name, COLORS.accent, 16), text, icon_name)
        self.description_field = QPlainTextEdit()
        self.description_field.setFixedHeight(64)
        self.tier_count_field = QSpinBox()
        self.tier_count_field.setRange(0, 100)
        self.tier_count_field.setSuffix(" palier(s)")
        self.completed_field = QSpinBox()
        self.completed_field.setRange(0, 100)
        self.completed_field.setSuffix(" terminé(s)")
        self.active_field = QCheckBox("Recherche en cours")
        self.active_field.setToolTip("Une seule recherche à la fois pour le pays : lancer celle-ci arrête l'autre.")
        self.skill_field = QComboBox()
        self.notify_field = QCheckBox("Prévenir le pays des changements de progression")
        self.notify_field.setToolTip("Palier terminé, recherche lancée : un message part dans la messagerie de chacun.")
        self.notify_field.setChecked(True)
        domain_form = QFormLayout()
        domain_form.setHorizontalSpacing(14)
        domain_form.setVerticalSpacing(10)
        domain_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        domain_form.addRow("Nom", self.name_field)
        domain_form.addRow("Identifiant", self.id_field)
        domain_form.addRow("Icône", self.icon_field)
        domain_form.addRow("Description", self.description_field)
        counts = QHBoxLayout()
        counts.addWidget(self.tier_count_field, 1)
        counts.addWidget(self.completed_field, 1)
        domain_form.addRow("Paliers", counts)
        domain_form.addRow("", self.active_field)
        domain_form.addRow("Compétence Craft", self.skill_field)
        domain_form.addRow("", self.notify_field)
        self.delete_button = button("Supprimer le domaine", "trash", "ghost")
        self.delete_button.setStyleSheet("QPushButton { color: #f2555a; }")
        self.delete_button.clicked.connect(self._delete)
        self.save_domain_button = button("Enregistrer le domaine", "save", "primary")
        self.save_domain_button.clicked.connect(self.save_domain)
        domain_actions = QHBoxLayout()
        domain_actions.addWidget(self.delete_button)
        domain_actions.addStretch(1)
        domain_actions.addWidget(self.save_domain_button)
        header = QHBoxLayout()
        header.addWidget(self.heading, 1)
        header.addWidget(new_button)
        domain_card = Card(padding=20, spacing=12)
        domain_card.body.addLayout(header)
        domain_card.body.addWidget(self.domain_banner)
        domain_card.body.addLayout(domain_form)
        domain_card.body.addLayout(domain_actions)

        # -- palier --
        self.tier_banner = Banner("danger")
        self.tier_banner.hide()
        self.tier_field = QComboBox()
        self.tier_field.currentIndexChanged.connect(self._tier_chosen)
        self.tier_name_field = QLineEdit()
        self.tier_name_field.setMaxLength(120)
        self.tier_name_field.setPlaceholderText("Nom du palier (facultatif)")
        self.tier_description_field = QPlainTextEdit()
        self.tier_description_field.setFixedHeight(56)
        self.conditions = LinesEditor("Ajouter une condition", with_done=True)
        self.rewards = LinesEditor("Ajouter une récompense", with_done=False)
        self.save_tier_button = button("Enregistrer le palier", "save", "primary")
        self.save_tier_button.clicked.connect(self.save_tier)
        tier_head = QHBoxLayout()
        tier_head.addWidget(label("PALIER", "overline"))
        tier_head.addWidget(self.tier_field)
        tier_head.addWidget(self.tier_name_field, 1)
        self.tier_card = Card(padding=20, spacing=10)
        self.tier_card.body.addLayout(tier_head)
        self.tier_card.body.addWidget(self.tier_banner)
        self.tier_card.body.addWidget(self.tier_description_field)
        self.tier_card.body.addWidget(label("CONDITIONS", "overline"))
        self.tier_card.body.addWidget(self.conditions)
        self.tier_card.body.addWidget(label("RÉCOMPENSES", "overline"))
        self.tier_card.body.addWidget(self.rewards)
        tier_actions = QHBoxLayout()
        tier_actions.addWidget(
            label("Les quantités s'affichent aussi en stacks et coffres pour les membres.", "faint"), 1
        )
        tier_actions.addWidget(self.save_tier_button)
        self.tier_card.body.addLayout(tier_actions)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(16)
        content_layout.addWidget(domain_card)
        content_layout.addWidget(self.tier_card)
        content_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        splitter.addWidget(self.list)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 970])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        for signal in (
            self.name_field.textChanged,
            self.icon_field.currentIndexChanged,
            self.description_field.textChanged,
            self.tier_count_field.valueChanged,
            self.completed_field.valueChanged,
            self.active_field.toggled,
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
        return self.tier_field.currentData()

    def is_dirty(self) -> bool:
        return self._domain_dirty or self._tier_dirty

    def refresh(self) -> None:
        call_api(self._host, self._host.api.research, lambda document: self.set_domains(parse_domains(document)))

    def set_domains(self, domains: list[Domain]) -> None:
        self._domains = {d.id: d for d in domains}
        entries = [(d.id, d.name, d.progress_text, icons.icon(d.icon, COLORS.accent, 24)) for d in domains]
        self.list.set_entries(entries, keep=self._current)
        if self._current in self._domains and not self.is_dirty():
            self.load(self._current, self._pending_level or self.current_level)
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
        self.tier_banner.hide()
        self.heading.setText(domain.name if domain else "Nouveau domaine")
        self.name_field.setText(domain.name if domain else "")
        self.id_field.setText(domain.id if domain else "")
        self.id_field.setReadOnly(domain is not None)
        self.icon_field.setCurrentIndex(max(self.icon_field.findData(domain.icon if domain else "flask"), 0))
        self.description_field.setPlainText(domain.description if domain else "")
        self.tier_count_field.setValue(domain.tier_count if domain else 0)
        self.completed_field.setMaximum(domain.tier_count if domain else 0)
        self.completed_field.setValue(domain.completed if domain else 0)
        self.active_field.setChecked(domain.active if domain else False)
        self._fill_skills(domain.skill_id if domain else None)
        self.delete_button.setVisible(domain is not None)
        items = [(item.id, item.name) for item in self._catalog.list_items()]
        self.conditions.set_items(items)
        self.rewards.set_items(items)
        self.tier_field.blockSignals(True)
        self.tier_field.clear()
        for tier in domain.tiers if domain else ():
            self.tier_field.addItem(f"Palier {tier.level}", tier.level)
        self.tier_field.blockSignals(False)
        self.tier_card.setEnabled(bool(domain and domain.tier_count))
        self._loading = False
        self._domain_dirty = False
        if domain and domain.tier_count:
            index = self.tier_field.findData(level) if level else -1
            if index < 0:
                index = min(domain.completed, domain.tier_count - 1)
            self.tier_field.setCurrentIndex(index)
            self._tier_chosen(index)
        else:
            self._show_tier(None)

    # -- enregistrement ----------------------------------------------------------------------

    def domain_payload(self) -> dict[str, Any]:
        return {
            "name": self.name_field.text().strip(),
            "description": self.description_field.toPlainText().strip(),
            "icon": self.icon_field.currentData(),
            "position": self._domains[self._current].position if self._current else len(self._domains),
            "tier_count": self.tier_count_field.value(),
            "completed": self.completed_field.value(),
            "active": self.active_field.isChecked(),
            "skill_id": self.skill_field.currentData(),
            "notify": self.notify_field.isChecked(),
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
        level = self.current_level

        def saved(raw: dict[str, Any]) -> None:
            self._domain_dirty = False
            self._current = raw["id"]
            if payload["notify"]:
                self._host.notifications.poll()
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
            "rewards": [line.to_api() for line in self.rewards.lines()],
        }

    def save_tier(self) -> None:
        domain_id, level = self._current, self.current_level
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
        answer = QMessageBox.question(
            self, "Supprimer", f"Supprimer le domaine « {domain.name} » et tous ses paliers ? C'est définitif."
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
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
            self.skill_field.addItem(f"{skill.name}  ·  {skill.kind.label}", skill.id)
        index = self.skill_field.findData(selected) if selected else 0
        if index < 0:
            self.skill_field.addItem(f"{selected} (inconnue)", selected)
            index = self.skill_field.count() - 1
        self.skill_field.setCurrentIndex(index)
        self.skill_field.setToolTip(
            "Les recettes qui exigent cette compétence au niveau N sont affichées sous le palier N."
        )

    def _tier_chosen(self, _index: int) -> None:
        domain = self._domains.get(self._current or "")
        level = self.current_level
        if not self._loading and self._tier_dirty and not self._confirm_tier_leave():
            self.tier_field.blockSignals(True)
            self.tier_field.setCurrentIndex(self.tier_field.findData(self._shown_level))
            self.tier_field.blockSignals(False)
            return
        self._show_tier(domain.tier(level) if domain and level else None)

    def _show_tier(self, tier: Tier | None) -> None:
        self._shown_level = tier.level if tier else None
        self._loading = True
        self.tier_name_field.setText(tier.name if tier else "")
        self.tier_description_field.setPlainText(tier.description if tier else "")
        self.tier_description_field.setPlaceholderText("Description du palier (facultative)")
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
        answer = QMessageBox.question(self, "Modifications non enregistrées", "Abandonner les modifications en cours ?")
        return answer == QMessageBox.StandardButton.Yes

    def _confirm_tier_leave(self) -> bool:
        answer = QMessageBox.question(self, "Palier non enregistré", "Abandonner les modifications de ce palier ?")
        return answer == QMessageBox.StandardButton.Yes

    def _refuse(self, banner: Banner, text: str) -> None:
        banner.set_text(text)
        banner.show()

    def _mark_domain_dirty(self, *_args) -> None:
        if not self._loading:
            self._domain_dirty = True

    def _mark_tier_dirty(self, *_args) -> None:
        if not self._loading:
            self._tier_dirty = True
