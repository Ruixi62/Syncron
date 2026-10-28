"""Gestion du Craft : éditeurs des objets, ateliers et compétences.

Même schéma pour les trois : liste à gauche, fiche à droite, enregistrement
validé par le serveur (une recette incohérente est refusée avec la liste des
problèmes, affichée dans la fiche).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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

from syncron_client.tools.craft.admin.context import CraftAdminContext
from syncron_client.ui.entity_list import EntityList
from syncron_client.ui.tables import ROW_HEIGHT
from syncron_client.ui.widgets import Banner, Card, SegmentedControl, button, icon_button, label
from syncron_core.catalog import ID_PATTERN, ID_RULE
from syncron_core.duration import DurationError, format_duration, parse_duration
from syncron_core.models.item import Item
from syncron_core.models.reference import SkillKind
from syncron_core.text import normalize

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"
PREVIEW_SIZE = 64


def _id_validator(parent: QWidget) -> QRegularExpressionValidator:
    return QRegularExpressionValidator(QRegularExpression(ID_PATTERN.pattern), parent)


class EntityEditor(QWidget):
    """Base : liste + fiche + barre d'actions.

    Chaque sous-classe fournit :
        build_form(layout)   champs spécifiques
        entries()            [(clé, titre, sous-titre, icône)] pour la liste
        entity(clé)          entité du catalogue ou None
        fill(entité | None)  remplit les champs spécifiques
        payload()            corps JSON envoyé à l'API
    """

    section = ""
    noun = "élément"
    new_label = "Nouveau"

    def __init__(self, context: CraftAdminContext, list_title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self._current: str | None = None
        self._dirty = False
        self._loading = False

        self.list = EntityList(list_title, "Rechercher…")
        self.list.selected.connect(self._on_selected)

        self.form_card = Card(padding=20, spacing=14)
        self._title = label("", "title")
        self._subtitle = label("", "faint")
        self.banner = Banner("danger")
        self.banner.hide()
        self.id_field = QLineEdit()
        self.id_field.setValidator(_id_validator(self))
        self.id_field.setPlaceholderText("identifiant_unique")
        self.id_field.setToolTip(f"Identifiant technique ({ID_RULE}). Non modifiable après création.")
        self.name_field = QLineEdit()
        self.name_field.setMaxLength(120)
        self.name_field.setPlaceholderText("Nom affiché")
        self.name_field.textEdited.connect(self._suggest_id)
        self.description_field = QPlainTextEdit()
        self.description_field.setPlaceholderText("Description (facultative)")
        self.description_field.setFixedHeight(72)

        self.delete_button = button("Supprimer", "trash", "ghost")
        self.delete_button.setStyleSheet("QPushButton { color: #f2555a; }")
        self.delete_button.clicked.connect(self._delete)
        self.revert_button = button("Annuler les modifications", None, "ghost")
        self.revert_button.clicked.connect(lambda: self.load(self._current))
        self.save_button = button("Enregistrer", "save", "primary")
        self.save_button.clicked.connect(self._save)
        new_button = button(self.new_label, "plus")
        new_button.clicked.connect(lambda: self._confirm_leave() and self.load(None))

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self._title)
        titles.addWidget(self._subtitle)
        header.addLayout(titles, 1)
        header.addWidget(new_button, 0, Qt.AlignmentFlag.AlignTop)

        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.form.setHorizontalSpacing(14)
        self.form.setVerticalSpacing(10)
        self.form.addRow("Nom", self.name_field)
        self.form.addRow("Identifiant", self.id_field)

        actions = QHBoxLayout()
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        actions.addWidget(self.revert_button)
        actions.addWidget(self.save_button)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(14)
        inner_layout.addLayout(header)
        inner_layout.addWidget(self.banner)
        inner_layout.addLayout(self.form)
        self.build_form(inner_layout)
        inner_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        self.form_card.body.addWidget(scroll, 1)
        self.form_card.body.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        splitter.addWidget(self.list)
        splitter.addWidget(self.form_card)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 900])
        self.list.setMinimumWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self.watch(self.name_field.textChanged, self.id_field.textChanged, self.description_field.textChanged)

    # -- cycle -------------------------------------------------------------------------

    def watch(self, *signals) -> None:
        for signal in signals:
            signal.connect(self._mark_dirty)

    def reload(self) -> None:
        self.list.set_entries(self.entries(), keep=self._current)
        if self._current and self.entity(self._current) is None:
            self.load(None)
        elif not self._dirty:
            self.load(self._current)

    def refresh(self) -> None:
        self.reload()

    def open_key(self, key: str) -> None:
        if self._confirm_leave():
            self.load(key)
            self.list.select(key, emit=False)

    def is_dirty(self) -> bool:
        return self._dirty

    def load(self, key: str | None) -> None:
        entity = self.entity(key) if key else None
        self._current = key if entity is not None else None
        self._loading = True
        self.banner.hide()
        self.id_field.setText(key or "" if entity is not None else "")
        self.id_field.setReadOnly(entity is not None)
        self.name_field.setText(entity.name if entity is not None else "")
        self.description_field.setPlainText(entity.description if entity is not None else "")
        self.fill(entity)
        self._loading = False
        self._dirty = False
        self.delete_button.setVisible(entity is not None)
        self._title.setText(entity.name if entity is not None else f"{self.new_label}")
        self._subtitle.setText(key if entity is not None else f"Création d'un {self.noun}")
        if entity is None:
            self.list.clear_selection()
            self.name_field.setFocus()
        self._update_buttons()

    @property
    def current_key(self) -> str | None:
        return self._current

    @property
    def dirty(self) -> bool:
        return self._dirty

    def _mark_dirty(self, *_args) -> None:
        if not self._loading:
            self._dirty = True
            self._update_buttons()

    def _update_buttons(self) -> None:
        self.revert_button.setEnabled(self._dirty)

    def _suggest_id(self, text: str) -> None:
        if self._current is None and not self.id_field.isModified():
            suggestion = prettify_slug(text)
            self.id_field.setText(suggestion)

    def _confirm_leave(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(self, "Modifications non enregistrées", "Abandonner les modifications en cours ?")
        return answer == QMessageBox.StandardButton.Yes

    def _on_selected(self, key: str) -> None:
        if key == self._current:
            return
        if self._confirm_leave():
            self.load(key)
        else:
            self.list.select(self._current, emit=False) if self._current else self.list.clear_selection()

    def _save(self) -> None:
        key = self.id_field.text().strip()
        if not ID_PATTERN.match(key):
            self.banner.set_text(f"Identifiant invalide : {ID_RULE}.")
            self.banner.show()
            return
        if self._current is None and self.entity(key) is not None:
            self.banner.set_text(f"L'identifiant « {key} » existe déjà.")
            self.banner.show()
            return
        payload = self.payload()
        if not payload.get("name"):
            self.banner.set_text("Le nom est obligatoire.")
            self.banner.show()
            return

        def saved(_result) -> None:
            self._current = key
            self._dirty = False
            self._update_buttons()

        self.ctx.call(
            lambda: self.ctx.api.put_entity(self.section, key, payload),
            saved,
            banner=self.banner,
            success=f"« {payload['name']} » enregistré.",
            sync=True,
        )

    def _delete(self) -> None:
        key = self._current
        if key is None:
            return
        answer = QMessageBox.question(self, "Supprimer", f"Supprimer définitivement « {key} » ?")
        if answer != QMessageBox.StandardButton.Yes:
            return

        def deleted(_result) -> None:
            self._dirty = False
            self.load(None)

        self.ctx.call(
            lambda: self.ctx.api.delete_entity(self.section, key),
            deleted,
            banner=self.banner,
            success=f"« {key} » supprimé.",
            sync=True,
        )


def prettify_slug(text: str) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in normalize(text).replace(" ", "_"))
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")[:80]


class ImageField(QWidget):
    """Aperçu + choix / retrait de l'image (disponible une fois l'élément enregistré)."""

    def __init__(self, editor: EntityEditor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._preview = QLabel()
        self._preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._choose = button("Choisir…", "upload")
        self._remove = button("Retirer", "trash", "ghost")
        self._hint = label("", "faint")
        self._choose.clicked.connect(self._pick)
        self._remove.clicked.connect(self._clear)
        buttons = QVBoxLayout()
        buttons.setSpacing(6)
        row = QHBoxLayout()
        row.addWidget(self._choose)
        row.addWidget(self._remove)
        row.addStretch(1)
        buttons.addLayout(row)
        buttons.addWidget(self._hint)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._preview)
        layout.addLayout(buttons, 1)

    def show_for(self, pixmap: QPixmap | None, has_image: bool, saved: bool) -> None:
        self._preview.setPixmap(pixmap if pixmap is not None else QPixmap())
        self._choose.setEnabled(saved)
        self._remove.setEnabled(saved and has_image)
        if not saved:
            self._hint.setText("Enregistre d'abord pour ajouter une image.")
        else:
            self._hint.setText("PNG, JPEG, WEBP… 2 Mo maximum, fond transparent conseillé.")

    def _pick(self) -> None:
        key = self._editor.current_key
        if key is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une image", "", IMAGE_FILTER)
        if path:
            self.upload(Path(path))

    def upload(self, path: Path) -> None:
        key = self._editor.current_key
        ctx = self._editor.ctx
        ctx.call(
            lambda: ctx.api.put_image(self._editor.section, key, path),
            banner=self._editor.banner,
            success="Image mise à jour.",
            sync=True,
        )

    def _clear(self) -> None:
        key = self._editor.current_key
        ctx = self._editor.ctx
        ctx.call(
            lambda: ctx.api.delete_image(self._editor.section, key),
            banner=self._editor.banner,
            success="Image retirée.",
            sync=True,
        )


class LinesTable(QWidget):
    """Lignes « référence + nombre » éditables (ingrédients, prérequis)."""

    def __init__(self, value_label: str, add_label: str, maximum: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._choices: list[tuple[str, str]] = []
        self._maximum = maximum
        self._on_change = None
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ÉLÉMENT", value_label.upper(), ""])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 44)
        add = button(add_label, "plus", "ghost")
        add.clicked.connect(lambda: self.add_line())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.table)
        layout.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)
        self._fit()

    def set_change_callback(self, callback) -> None:
        self._on_change = callback

    def set_choices(self, choices: list[tuple[str, str]]) -> None:
        self._choices = choices

    def set_lines(self, lines: list[tuple[str, int]]) -> None:
        self.table.setRowCount(0)
        for key, value in lines:
            self.add_line(key, value, notify=False)
        self._fit()

    def lines(self) -> list[tuple[str, int]]:
        result = []
        for row in range(self.table.rowCount()):
            combo: QComboBox = self.table.cellWidget(row, 0)
            spin: QSpinBox = self.table.cellWidget(row, 1)
            key = combo.currentData()
            if key:
                result.append((key, spin.value()))
        return result

    def add_line(self, key: str | None = None, value: int = 1, notify: bool = True) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.addItem("— choisir —", None)
        for choice_key, text in self._choices:
            combo.addItem(f"{text}  ·  {choice_key}", choice_key)
        if key is not None:
            index = combo.findData(key)
            if index < 0:
                combo.addItem(f"{key} (inconnu)", key)
                index = combo.count() - 1
            combo.setCurrentIndex(index)
        combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        combo.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        spin = QSpinBox()
        spin.setRange(1, self._maximum)
        spin.setValue(value)
        remove: QToolButton = icon_button("close", "Retirer la ligne", 14)
        remove.clicked.connect(lambda: self._remove(combo))
        self.table.setCellWidget(row, 0, combo)
        self.table.setCellWidget(row, 1, spin)
        self.table.setCellWidget(row, 2, remove)
        combo.currentIndexChanged.connect(self._changed)
        spin.valueChanged.connect(self._changed)
        self._fit()
        if notify:
            self._changed()

    def _remove(self, combo: QComboBox) -> None:
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 0) is combo:
                self.table.removeRow(row)
                break
        self._fit()
        self._changed()

    def _changed(self, *_args) -> None:
        if self._on_change is not None:
            self._on_change()

    def _fit(self) -> None:
        rows = max(self.table.rowCount(), 1)
        self.table.setFixedHeight(self.table.horizontalHeader().height() + rows * ROW_HEIGHT + 6)


# -- objets --------------------------------------------------------------------------------


class ItemEditor(EntityEditor):
    section = "items"
    noun = "objet"
    new_label = "Nouvel objet"

    def build_form(self, layout: QVBoxLayout) -> None:
        self.type_field = SegmentedControl([("Ressource primaire", "gem"), ("Craftable", "hammer")])
        self.category_field = QComboBox()
        self.category_field.setEditable(True)
        self.category_field.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.image_field = ImageField(self)
        self.form.addRow("Type", self.type_field)
        self.form.addRow("Catégorie", self.category_field)
        self.form.addRow("Description", self.description_field)
        self.form.addRow("Image", self.image_field)

        self.recipe_card = Card(flat=True, padding=16, spacing=12)
        self.recipe_card.body.addWidget(label("FABRICATION", "overline"))
        recipe_form = QFormLayout()
        recipe_form.setHorizontalSpacing(14)
        recipe_form.setVerticalSpacing(10)
        self.station_field = QComboBox()
        self.time_field = QLineEdit()
        self.time_field.setPlaceholderText("instant, 30s, 5m, 1h30…")
        self.time_preview = label("", "faint")
        self.time_preview.setMinimumWidth(110)
        time_row = QHBoxLayout()
        time_row.addWidget(self.time_field, 1)
        time_row.addWidget(self.time_preview)
        self.output_field = QSpinBox()
        self.output_field.setRange(1, 1_000_000)
        self.output_field.setSuffix(" par craft")
        recipe_form.addRow("Atelier", self.station_field)
        recipe_form.addRow("Temps par craft", time_row)
        recipe_form.addRow("Rendement", self.output_field)
        self.recipe_card.body.addLayout(recipe_form)
        self.recipe_card.body.addWidget(label("INGRÉDIENTS (PAR CRAFT)", "overline"))
        self.ingredients = LinesTable("Quantité", "Ajouter un ingrédient", 1_000_000)
        self.recipe_card.body.addWidget(self.ingredients)
        self.recipe_card.body.addWidget(label("PRÉREQUIS", "overline"))
        self.requirements = LinesTable("Niveau min.", "Ajouter un prérequis", 1_000_000)
        self.recipe_card.body.addWidget(self.requirements)
        layout.addWidget(self.recipe_card)

        self.type_field.currentChanged.connect(self._type_changed)
        self.time_field.textChanged.connect(self._time_changed)
        self.ingredients.set_change_callback(self._mark_dirty)
        self.requirements.set_change_callback(self._mark_dirty)
        self.watch(
            self.type_field.currentChanged,
            self.category_field.currentTextChanged,
            self.station_field.currentIndexChanged,
            self.time_field.textChanged,
            self.output_field.valueChanged,
        )

    def entries(self):
        result = []
        for item in self.ctx.catalog.list_items():
            subtitle = "Ressource primaire" if item.recipe is None else self.ctx.catalog.station_name(item.station_id)
            result.append((item.id, item.name, subtitle, self.ctx.icons.item_icon(item.id, 28)))
        return result

    def entity(self, key: str) -> Item | None:
        return self.ctx.catalog.get(key)

    def fill(self, item: Item | None) -> None:
        catalog = self.ctx.catalog
        self.category_field.clear()
        self.category_field.addItems(["", *catalog.categories()])
        self.category_field.setCurrentText(item.category if item else "")
        self.station_field.clear()
        self.station_field.addItem("Aucun atelier", None)
        for station in catalog.stations():
            self.station_field.addItem(station.name, station.id)
        self.ingredients.set_choices([(i.id, i.name) for i in catalog.list_items() if not item or i.id != item.id])
        self.requirements.set_choices([(s.id, s.name) for s in catalog.skills()])
        recipe = item.recipe if item else None
        self.type_field.set_current_index(1 if recipe else 0)
        self.station_field.setCurrentIndex(max(self.station_field.findData(recipe.station_id), 0) if recipe else 0)
        self.time_field.setText(
            format_duration(recipe.time_seconds, compact=True) if recipe and recipe.time_seconds else ""
        )
        self.output_field.setValue(recipe.output if recipe else 1)
        self.ingredients.set_lines([(i.item_id, i.quantity) for i in recipe.ingredients] if recipe else [])
        self.requirements.set_lines([(r.skill_id, r.level) for r in recipe.requirements] if recipe else [])
        pixmap = self.ctx.icons.item_pixmap(item.id, PREVIEW_SIZE) if item else None
        self.image_field.show_for(pixmap, bool(item and item.image), item is not None)
        self._type_changed(self.type_field.current_index())

    def payload(self) -> dict[str, Any]:
        crafted = self.type_field.current_index() == 1
        payload: dict[str, Any] = {
            "name": self.name_field.text().strip(),
            "type": "crafted" if crafted else "raw",
            "category": self.category_field.currentText().strip(),
            "description": self.description_field.toPlainText().strip(),
        }
        if crafted:
            payload.update(
                {
                    "station_id": self.station_field.currentData(),
                    "time": self.time_field.text().strip() or 0,
                    "output": self.output_field.value(),
                    "recipe": dict(self.ingredients.lines()),
                    "requires": dict(self.requirements.lines()),
                }
            )
        return payload

    def _type_changed(self, index: int) -> None:
        self.recipe_card.setVisible(index == 1)

    def _time_changed(self, text: str) -> None:
        try:
            seconds = parse_duration(text.strip() or 0)
        except DurationError:
            self.time_preview.setText("illisible")
            self.time_preview.setStyleSheet("color: #f2555a;")
            return
        self.time_preview.setStyleSheet("")
        self.time_preview.setText(format_duration(seconds))


# -- ateliers -------------------------------------------------------------------------------


class StationEditor(EntityEditor):
    section = "stations"
    noun = "atelier"
    new_label = "Nouvel atelier"

    def build_form(self, layout: QVBoxLayout) -> None:
        self.image_field = ImageField(self)
        self.form.addRow("Description", self.description_field)
        self.form.addRow("Image", self.image_field)
        self.usage = label("", "faint", wrap=True)
        layout.addWidget(self.usage)

    def entries(self):
        counts: dict[str, int] = {}
        for item in self.ctx.catalog.list_items():
            if item.station_id:
                counts[item.station_id] = counts.get(item.station_id, 0) + 1
        return [
            (s.id, s.name, f"{counts.get(s.id, 0)} recette(s)", self.ctx.icons.station_icon(s.id, 28))
            for s in self.ctx.catalog.stations()
        ]

    def entity(self, key: str):
        return self.ctx.catalog.station(key)

    def fill(self, station) -> None:
        pixmap = self.ctx.icons.station_pixmap(station.id, PREVIEW_SIZE) if station else None
        self.image_field.show_for(pixmap, bool(station and station.image), station is not None)
        if station is None:
            self.usage.setText("")
            return
        users = [i.name for i in self.ctx.catalog.list_items() if i.station_id == station.id]
        self.usage.setText("Utilisé par : " + ", ".join(users) if users else "Aucune recette n'utilise cet atelier.")

    def payload(self) -> dict[str, Any]:
        return {"name": self.name_field.text().strip(), "description": self.description_field.toPlainText().strip()}


# -- compétences ------------------------------------------------------------------------------


KIND_LABELS = (("job", "Métier"), ("research", "Recherche & Développement"), ("other", "Autre"))


class SkillEditor(EntityEditor):
    section = "skills"
    noun = "compétence"
    new_label = "Nouvelle compétence"

    def build_form(self, layout: QVBoxLayout) -> None:
        self.kind_field = QComboBox()
        for value, text in KIND_LABELS:
            self.kind_field.addItem(text, value)
        self.max_level_field = QSpinBox()
        self.max_level_field.setRange(0, 1_000_000)
        self.max_level_field.setSpecialValueText("Pas de maximum")
        self.form.addRow("Type", self.kind_field)
        self.form.addRow("Niveau maximum", self.max_level_field)
        self.form.addRow("Description", self.description_field)
        self.usage = label("", "faint", wrap=True)
        layout.addWidget(self.usage)
        self.watch(self.kind_field.currentIndexChanged, self.max_level_field.valueChanged)

    def entries(self):
        return [(s.id, s.name, SkillKind(s.kind).label, None) for s in self.ctx.catalog.skills()]

    def entity(self, key: str):
        return self.ctx.catalog.skill(key)

    def fill(self, skill) -> None:
        self.kind_field.setCurrentIndex(max(self.kind_field.findData(skill.kind.value if skill else "job"), 0))
        self.max_level_field.setValue(skill.max_level or 0 if skill else 0)
        if skill is None:
            self.usage.setText("")
            return
        users = [
            i.name
            for i in self.ctx.catalog.list_items()
            if i.recipe and skill.id in {r.skill_id for r in i.recipe.requirements}
        ]
        self.usage.setText(
            "Prérequis de : " + ", ".join(users) if users else "Aucune recette n'exige cette compétence."
        )

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name_field.text().strip(),
            "kind": self.kind_field.currentData(),
            "max_level": self.max_level_field.value() or None,
            "description": self.description_field.toPlainText().strip(),
        }
