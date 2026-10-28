"""Page du Convertisseur : une quantité -> stacks, lignes, coffres, doubles coffres (et l'inverse)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from syncron_client.ui.widgets import Card, SegmentedControl, StatTile, button, label
from syncron_core.converter import (
    MAX_QUANTITY,
    STACK_SIZES,
    UNITS,
    Breakdown,
    QuantityError,
    containers_needed,
    decompose,
    express,
    parse_quantity,
)
from syncron_core.text import format_quantity

STACK_LABELS = {64: "Pile de 64", 16: "Pile de 16", 1: "Non empilable"}
UNIT_ICONS = {"double_coffre": "database", "coffre": "box", "ligne": "list", "stack": "layers"}
UNIT_TONES = {"double_coffre": "violet", "coffre": "accent", "ligne": "info", "stack": "success"}


def _decimal(value: float) -> str:
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return text.removesuffix(",00")


class ConverterPage(QScrollArea):
    stackSizeChanged = Signal(int)

    def __init__(self, stack_size: int = 64, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._stack_size = stack_size if stack_size in STACK_SIZES else 64
        self._breakdown: Breakdown | None = None

        # -- saisie --
        entry = Card(padding=22, spacing=12)
        entry.body.addWidget(label("QUANTITÉ", "overline"))
        self.input = QLineEdit()
        self.input.setProperty("size", "large")
        self.input.setPlaceholderText("5000, 2,5k, 3 coffres + 12, 1 dc 4 stacks…")
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self._recompute)
        self.error = label("", wrap=True)
        self.error.setStyleSheet("color: #f2555a;")
        self.error.hide()
        self.stack_choice = SegmentedControl([(STACK_LABELS[size], None) for size in STACK_SIZES])
        self.stack_choice.set_current_index(STACK_SIZES.index(self._stack_size))
        self.stack_choice.currentChanged.connect(self._stack_changed)
        hint = label(
            "Un stack = 1 emplacement, une ligne = 9, un coffre = 27, un double coffre = 54. "
            "Les outils et les armures ne s'empilent pas ; les perles de l'Ender, les œufs ou les panneaux "
            "s'empilent par 16.",
            "faint",
            wrap=True,
        )
        entry.body.addWidget(self.input)
        entry.body.addWidget(self.error)
        entry.body.addWidget(self.stack_choice, 0, Qt.AlignmentFlag.AlignLeft)
        entry.body.addWidget(hint)

        # -- résultat --
        result = Card(padding=22, spacing=14)
        head = QHBoxLayout()
        head.addWidget(label("RANGEMENT", "overline"), 1)
        self.copy_button = button("Copier", "copy", "ghost")
        self.copy_button.clicked.connect(self.copy)
        head.addWidget(self.copy_button)
        self.summary = label("—", "title", wrap=True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.slots = label("", "muted")
        self._tiles: dict[str, StatTile] = {}
        tiles = QGridLayout()
        tiles.setSpacing(12)
        for index, unit in enumerate(UNITS):
            tile = StatTile(UNIT_ICONS[unit.id], unit.plural.capitalize(), UNIT_TONES[unit.id])
            self._tiles[unit.id] = tile
            tiles.addWidget(tile, index // 2, index % 2)
        tiles.setColumnStretch(0, 1)
        tiles.setColumnStretch(1, 1)
        result.body.addLayout(head)
        result.body.addWidget(self.summary)
        result.body.addWidget(self.slots)
        result.body.addLayout(tiles)

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
            spin.setMinimumWidth(120)
            spin.valueChanged.connect(self._compose_changed)
            self._spins[key] = spin
            grid.addWidget(label(text), row, 0)
            grid.addWidget(spin, row, 1)
        grid.setColumnStretch(2, 1)
        self.composed = label("= 0 objet", "heading")
        use = button("Convertir ce total", "arrow-right")
        use.clicked.connect(self._use_composed)
        reset = button("Remettre à zéro", None, "ghost")
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
        left.addWidget(compose)
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(result)
        right.addStretch(1)
        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(left, 5)
        layout.addLayout(right, 6)
        self.setWidget(content)
        self._recompute()

    # -- API de la page ---------------------------------------------------------------

    @property
    def breakdown(self) -> Breakdown | None:
        return self._breakdown

    @property
    def stack_size(self) -> int:
        return self._stack_size

    def set_quantity(self, text: str) -> None:
        self.input.setText(text)

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

    def _stack_changed(self, index: int) -> None:
        self._stack_size = STACK_SIZES[index]
        self.stackSizeChanged.emit(self._stack_size)
        self._recompute()
        self._compose_changed()

    def _recompute(self, *_args) -> None:
        text = self.input.text()
        self._breakdown = None
        self.error.hide()
        if text.strip():
            try:
                self._breakdown = decompose(parse_quantity(text, self._stack_size), self._stack_size)
            except QuantityError as exc:
                self.error.setText(str(exc))
                self.error.show()
        self.copy_button.setEnabled(self._breakdown is not None)
        self._show(self._breakdown)

    def _show(self, breakdown: Breakdown | None) -> None:
        if breakdown is None:
            self.summary.setText("Saisis une quantité pour voir comment la ranger.")
            self.slots.setText("")
            for tile in self._tiles.values():
                tile.set_value("—")
            return
        quantity = breakdown.quantity
        self.summary.setText(f"{format_quantity(quantity)} = {breakdown.text()}")
        self.slots.setText(f"{format_quantity(breakdown.slots)} emplacement(s) d'inventaire")
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
