"""Page du Convertisseur.

Deux modes :
    Division euclidienne   648 = 1 ligne + 1 stack + 8 objets seuls (contenants au choix)
    Une seule unité        648 = 10 stacks + 8 objets seuls (soit 10,13 stacks)
Plus, pour tout ranger dans un seul type de contenant, le nombre qu'il en faut ;
et l'opération inverse (additionner des contenants).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS, TONES
from syncron_client.ui.widgets import Card, FlowWidget, SegmentedControl, StatTile, button, label
from syncron_core.converter import (
    MAX_QUANTITY,
    STACK_SIZES,
    UNITS,
    Breakdown,
    QuantityError,
    containers_needed,
    decompose,
    express,
    loose_label,
    parse_quantity,
    unit_by_id,
)
from syncron_core.text import format_quantity

EUCLIDEAN, SINGLE = "euclidean", "single"
MODES = ((EUCLIDEAN, "Division euclidienne", "layers"), (SINGLE, "Une seule unité", "box"))
STACK_LABELS = {64: "Pile de 64", 16: "Pile de 16", 1: "Non empilable"}
UNIT_ICONS = {"double_coffre": "database", "coffre": "box", "ligne": "list", "stack": "layers"}
UNIT_TONES = {"double_coffre": "violet", "coffre": "accent", "ligne": "info", "stack": "success"}
SMALL_FIRST = tuple(reversed(UNITS))


def _decimal(value: float) -> str:
    """10.125 -> « 10,125 » ; 2.0 -> « 2 » (trois décimales au plus)."""
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text.replace(",", "\u202f").replace(".", ",")


class ResultRow(QWidget):
    """Une ligne du résultat : icône, nombre, unité."""

    def __init__(self, icon_name: str, tone: str, count: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        color, background = TONES[tone]
        badge = QLabel()
        badge.setFixedSize(32, 32)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icons.pixmap(icon_name, color, 16))
        badge.setStyleSheet(f"background: {background}; border-radius: 9px;")
        value = label(count, "stat")
        value.setMinimumWidth(64)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(12)
        layout.addWidget(badge)
        layout.addWidget(value)
        layout.addWidget(label(text, "heading"), 1)


class ConverterPage(QScrollArea):
    settingsChanged = Signal(dict)

    def __init__(self, preferences: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        preferences = preferences or {}
        stack = preferences.get("stack_size", 64)
        self._stack_size = stack if stack in STACK_SIZES else 64
        mode = preferences.get("mode", EUCLIDEAN)
        self._mode = mode if mode in (EUCLIDEAN, SINGLE) else EUCLIDEAN
        unit = preferences.get("unit", "stack")
        self._unit = unit if unit in {u.id for u in UNITS} else "stack"
        enabled = preferences.get("units")
        valid = {u.id for u in UNITS}
        self._enabled = {u for u in enabled if u in valid} if isinstance(enabled, list) else set(valid)
        self._breakdown: Breakdown | None = None

        # -- saisie et mode --
        entry = Card(padding=22, spacing=12)
        entry.body.addWidget(label("QUANTITÉ", "overline"))
        self.input = QLineEdit()
        self.input.setProperty("size", "large")
        self.input.setPlaceholderText("648, 2,5k, 3 coffres + 12, 1 dc 4 stacks…")
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self._recompute)
        self.error = label("", wrap=True)
        self.error.setStyleSheet(f"color: {COLORS.danger};")
        self.error.hide()
        self.stack_choice = SegmentedControl([(STACK_LABELS[size], None) for size in STACK_SIZES])
        self.stack_choice.set_current_index(STACK_SIZES.index(self._stack_size))
        self.stack_choice.currentChanged.connect(self._stack_changed)
        entry.body.addWidget(self.input)
        entry.body.addWidget(self.error)
        entry.body.addWidget(self.stack_choice, 0, Qt.AlignmentFlag.AlignLeft)

        mode_card = Card(padding=22, spacing=12)
        mode_card.body.addWidget(label("MODE", "overline"))
        self.mode_choice = SegmentedControl([(text, icon) for _key, text, icon in MODES])
        self.mode_choice.set_current_index([m[0] for m in MODES].index(self._mode))
        self.mode_choice.currentChanged.connect(self._mode_changed)
        mode_card.body.addWidget(self.mode_choice, 0, Qt.AlignmentFlag.AlignLeft)
        self.mode_hint = label("", "faint", wrap=True)
        mode_card.body.addWidget(self.mode_hint)

        self.unit_boxes: dict[str, QCheckBox] = {}
        self._units_panel = FlowWidget(spacing=14)
        for unit in UNITS:
            box = QCheckBox(unit.plural.capitalize())
            box.setChecked(unit.id in self._enabled)
            box.toggled.connect(self._units_changed)
            self.unit_boxes[unit.id] = box
            self._units_panel.add(box)
        self.unit_choice = SegmentedControl([(unit.plural.capitalize(), None) for unit in SMALL_FIRST])
        self.unit_choice.set_current_index([u.id for u in SMALL_FIRST].index(self._unit))
        self.unit_choice.currentChanged.connect(self._unit_changed)
        mode_card.body.addWidget(self._units_panel)
        mode_card.body.addWidget(self.unit_choice, 0, Qt.AlignmentFlag.AlignLeft)

        # -- résultat --
        result = Card(padding=22, spacing=12)
        head = QHBoxLayout()
        head.addWidget(label("RÉSULTAT", "overline"), 1)
        self.copy_button = button("Copier", "copy", "ghost")
        self.copy_button.clicked.connect(self.copy)
        head.addWidget(self.copy_button)
        self.summary = label("—", "title", wrap=True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = label("", "muted", wrap=True)
        self._rows = QVBoxLayout()
        self._rows.setSpacing(6)
        result.body.addLayout(head)
        result.body.addWidget(self.summary)
        result.body.addLayout(self._rows)
        result.body.addWidget(self.detail)

        storage = Card(padding=22, spacing=12)
        storage.body.addWidget(label("POUR TOUT RANGER DANS UN SEUL TYPE DE CONTENANT", "overline"))
        self._tiles: dict[str, StatTile] = {}
        tiles = QGridLayout()
        tiles.setSpacing(12)
        for index, unit in enumerate(UNITS):
            tile = StatTile(UNIT_ICONS[unit.id], unit.plural.capitalize(), UNIT_TONES[unit.id])
            self._tiles[unit.id] = tile
            tiles.addWidget(tile, index // 2, index % 2)
        tiles.setColumnStretch(0, 1)
        tiles.setColumnStretch(1, 1)
        storage.body.addLayout(tiles)

        # -- composition --
        compose = Card(padding=22, spacing=12)
        compose.body.addWidget(label("COMPOSER UNE QUANTITÉ", "overline"))
        compose.body.addWidget(label("Additionne des contenants pour obtenir un nombre d'objets.", "muted", wrap=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self._spins: dict[str, QSpinBox] = {}
        rows = [(unit.id, unit.plural.capitalize()) for unit in UNITS] + [("unit", "Objets seuls")]
        for row, (key, text) in enumerate(rows):
            spin = QSpinBox()
            spin.setRange(0, 1_000_000)
            spin.setGroupSeparatorShown(True)
            spin.setMinimumWidth(110)
            spin.valueChanged.connect(self._compose_changed)
            self._spins[key] = spin
            grid.addWidget(label(text), row, 0)
            grid.addWidget(spin, row, 1)
        grid.setColumnStretch(2, 1)
        self.composed = label("= 0 objet", "heading")
        use = button("Convertir ce total", "arrow-right")
        use.clicked.connect(self._use_composed)
        reset = button("Zéro", None, "ghost")
        reset.setToolTip("Remettre à zéro")
        reset.clicked.connect(self._reset_composer)
        actions = QHBoxLayout()
        actions.addWidget(self.composed, 1)
        actions.addWidget(reset)
        actions.addWidget(use)
        compose.body.addLayout(grid)
        compose.body.addLayout(actions)

        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(entry)
        left.addWidget(mode_card)
        left.addWidget(compose)
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(result)
        right.addWidget(storage)
        right.addStretch(1)
        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(left, 1)
        layout.addLayout(right, 1)
        self.setWidget(content)
        self._apply_mode()

    # -- API de la page ---------------------------------------------------------------

    @property
    def breakdown(self) -> Breakdown | None:
        return self._breakdown

    @property
    def stack_size(self) -> int:
        return self._stack_size

    @property
    def mode(self) -> str:
        return self._mode

    def preferences(self) -> dict:
        return {
            "stack_size": self._stack_size,
            "mode": self._mode,
            "unit": self._unit,
            "units": sorted(self._enabled),
        }

    def set_quantity(self, text: str) -> None:
        self.input.setText(text)

    def set_mode(self, mode: str, unit: str | None = None) -> None:
        self.mode_choice.set_current_index([m[0] for m in MODES].index(mode))
        if unit is not None:
            self.unit_choice.set_current_index([u.id for u in SMALL_FIRST].index(unit))

    def focus_input(self) -> None:
        self.input.setFocus()
        self.input.selectAll()

    def result_text(self) -> str | None:
        if self._breakdown is None:
            return None
        return f"{format_quantity(self._breakdown.quantity)} = {self._breakdown.text()}"

    def copy(self) -> bool:
        text = self.result_text()
        if text:
            QGuiApplication.clipboard().setText(text)
        return bool(text)

    # -- interne ------------------------------------------------------------------------

    def _units(self) -> tuple:
        if self._mode == SINGLE:
            return (unit_by_id(self._unit),)
        return tuple(unit for unit in UNITS if unit.id in self._enabled)

    def _stack_changed(self, index: int) -> None:
        self._stack_size = STACK_SIZES[index]
        self._changed()
        self._compose_changed()

    def _mode_changed(self, index: int) -> None:
        self._mode = MODES[index][0]
        self._apply_mode()
        self._changed()

    def _unit_changed(self, index: int) -> None:
        self._unit = SMALL_FIRST[index].id
        self._changed()

    def _units_changed(self, *_args) -> None:
        self._enabled = {unit_id for unit_id, box in self.unit_boxes.items() if box.isChecked()}
        self._changed()

    def _apply_mode(self) -> None:
        euclidean = self._mode == EUCLIDEAN
        self._units_panel.setVisible(euclidean)
        self.unit_choice.setVisible(not euclidean)
        self.mode_hint.setText(
            "Du plus grand contenant au plus petit, puis les objets seuls. Décoche ceux que tu n'utilises pas."
            if euclidean
            else "Tout en une seule unité : nombre entier de contenants et objets seuls qui restent."
        )
        self._recompute()

    def _changed(self) -> None:
        self.settingsChanged.emit(self.preferences())
        self._recompute()

    def _recompute(self, *_args) -> None:
        text = self.input.text()
        self._breakdown = None
        self.error.hide()
        if text.strip():
            try:
                quantity = parse_quantity(text, self._stack_size)
                self._breakdown = decompose(quantity, self._stack_size, self._units())
            except QuantityError as exc:
                self.error.setText(str(exc))
                self.error.show()
        self.copy_button.setEnabled(self._breakdown is not None)
        self._show(self._breakdown)

    def _show(self, breakdown: Breakdown | None) -> None:
        while self._rows.count():
            widget = self._rows.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        if breakdown is None:
            self.summary.setText("Saisis une quantité.")
            self.detail.setText("")
            for tile in self._tiles.values():
                tile.set_value("—")
            return
        quantity = breakdown.quantity
        self.summary.setText(f"{format_quantity(quantity)} objets =")
        for unit, count in breakdown.parts:
            if count:
                self._rows.addWidget(
                    ResultRow(UNIT_ICONS[unit.id], UNIT_TONES[unit.id], format_quantity(count), unit.label(count))
                )
        if breakdown.remainder or not any(count for _unit, count in breakdown.parts):
            remainder = loose_label(breakdown.remainder).split(" ", 1)
            self._rows.addWidget(ResultRow("gem", "neutral", remainder[0], remainder[1]))
        details = [f"{format_quantity(breakdown.slots)} emplacement(s) d'inventaire."]
        if self._mode == SINGLE:
            unit = unit_by_id(self._unit)
            value = express(quantity, unit, self._stack_size)
            details.insert(0, f"Soit {_decimal(value)} {unit.name if value < 2 else unit.plural}.")
        self.detail.setText(" ".join(details))
        for unit in UNITS:
            needed = containers_needed(quantity, unit, self._stack_size)
            exact = _decimal(express(quantity, unit, self._stack_size))
            self._tiles[unit.id].set_value(
                format_quantity(needed),
                f"{exact} exactement · {format_quantity(unit.size(self._stack_size))} par {unit.name}",
            )

    def _compose_total(self) -> int:
        total = self._spins["unit"].value()
        for unit in UNITS:
            total += self._spins[unit.id].value() * unit.size(self._stack_size)
        return min(total, MAX_QUANTITY)

    def _compose_changed(self, *_args) -> None:
        total = self._compose_total()
        self.composed.setText(f"= {format_quantity(total)} objet{'s' if total > 1 else ''}")

    def _use_composed(self) -> None:
        self.input.setText(str(self._compose_total()))

    def _reset_composer(self) -> None:
        for spin in self._spins.values():
            spin.setValue(0)
