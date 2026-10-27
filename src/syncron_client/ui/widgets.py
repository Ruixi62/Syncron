"""Composants réutilisables du design system (plateforme et outils)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS, TONES


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    if role == "overline":
        font = widget.font()
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        widget.setFont(font)
    widget.setWordWrap(wrap)
    return widget


class ElidedLabel(QLabel):
    """Libellé sur une ligne qui se termine par « … » quand la place manque."""

    def __init__(self, text: str = "", role: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        if role:
            self.setProperty("role", role)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)
        self._refresh()

    def setText(self, text: str) -> None:
        self._full_text = text
        self._refresh()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        elided = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, max(self.width(), 40))
        super().setText(elided)
        self.setToolTip(self._full_text if elided != self._full_text else "")


def button(text: str, icon_name: str | None = None, variant: str | None = None) -> QPushButton:
    widget = QPushButton(text)
    if variant:
        widget.setProperty("variant", variant)
    if icon_name:
        color = COLORS.accent_text if variant == "primary" else COLORS.text_muted
        widget.setIcon(icons.icon(icon_name, color, 16))
        widget.setIconSize(QSize(16, 16))
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def icon_button(icon_name: str, tooltip: str, size: int = 18) -> QToolButton:
    widget = QToolButton()
    widget.setProperty("variant", "icon")
    widget.setIcon(icons.icon(icon_name, COLORS.text_muted, size))
    widget.setIconSize(QSize(size, size))
    widget.setToolTip(tooltip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    return line


class Card(QFrame):
    """Surface arrondie et bordée. `flat=True` : surface secondaire."""

    def __init__(self, parent: QWidget | None = None, flat: bool = False, padding: int = 18, spacing: int = 12):
        super().__init__(parent)
        self.setProperty("card", "flat" if flat else "true")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)


class Chip(QFrame):
    """Pastille d'information colorée, avec icône optionnelle."""

    def __init__(self, text: str, tone: str = "neutral", icon_name: str | None = None, parent=None):
        super().__init__(parent)
        self._icon = QLabel()
        self._text = QLabel()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 9, 3)
        layout.setSpacing(5)
        layout.addWidget(self._icon)
        layout.addWidget(self._text)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_content(text, tone, icon_name)

    def set_content(self, text: str, tone: str = "neutral", icon_name: str | None = None) -> None:
        color, background = TONES.get(tone, TONES["neutral"])
        self.setStyleSheet(f"Chip {{ background: {background}; border-radius: 8px; }}")
        self._text.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600; background: transparent;")
        self._text.setText(text)
        self._icon.setVisible(bool(icon_name))
        if icon_name:
            self._icon.setPixmap(icons.pixmap(icon_name, color, 13))

    def text(self) -> str:
        return self._text.text()


class SearchField(QLineEdit):
    def __init__(self, placeholder: str, large: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(icons.icon("search", COLORS.text_faint, 16), QLineEdit.ActionPosition.LeadingPosition)
        if large:
            self.setProperty("size", "large")


class SegmentedControl(QFrame):
    """Onglets modernes : une rangée de segments exclusifs."""

    currentChanged = Signal(int)

    def __init__(self, segments: Sequence[tuple[str, str | None]] = (), parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self._layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.currentChanged)
        self._buttons: list[QPushButton] = []
        self._texts: list[str] = []
        self._compact = False
        for text, icon_name in segments:
            self.add_segment(text, icon_name)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def add_segment(self, text: str, icon_name: str | None = None) -> int:
        segment = QPushButton(text.replace("&", "&&"))
        segment.setObjectName("Segment")
        segment.setCheckable(True)
        segment.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            segment.setIcon(icons.icon(icon_name, COLORS.text_faint, 15, active_color=COLORS.accent))
            segment.setIconSize(QSize(15, 15))
        index = len(self._buttons)
        self._group.addButton(segment, index)
        self._layout.addWidget(segment)
        self._buttons.append(segment)
        self._texts.append(text)
        if index == 0:
            segment.setChecked(True)
        return index

    def set_text(self, index: int, text: str) -> None:
        self._texts[index] = text
        self._apply_text(index)

    def set_compact(self, compact: bool) -> None:
        """Mode compact : icônes seules (libellés en info-bulle), pour les zones étroites."""
        if compact == self._compact:
            return
        self._compact = compact
        for index in range(len(self._buttons)):
            self._apply_text(index)

    def _apply_text(self, index: int) -> None:
        button, text = self._buttons[index], self._texts[index]
        compact = self._compact and not button.icon().isNull()
        button.setText("" if compact else text.replace("&", "&&"))
        button.setToolTip(text if compact else "")

    def current_index(self) -> int:
        return self._group.checkedId()

    def set_current_index(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
            self.currentChanged.emit(index)


class StatTile(QFrame):
    def __init__(self, icon_name: str, caption: str, tone: str = "accent", parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("card", "flat")
        color, background = TONES[tone]
        badge = QLabel()
        badge.setFixedSize(36, 36)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icons.pixmap(icon_name, color, 18))
        badge.setStyleSheet(f"background: {background}; border-radius: 10px;")
        self._value = ElidedLabel("—", "stat")
        self._caption = ElidedLabel(caption, "faint")
        self._detail = ElidedLabel(" ", "faint")
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(self._caption)
        text.addWidget(self._value)
        text.addWidget(self._detail)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)

    def set_value(self, value: str, detail: str = "") -> None:
        self._value.setText(value)
        self._detail.setText(detail or " ")


class QuantityStepper(QWidget):
    """−  [ 10 ]  +  — saisie directe, molette, ou boutons (Maj+clic = ×10)."""

    valueChanged = Signal(int)

    def __init__(self, maximum: int = 1_000_000, parent: QWidget | None = None):
        super().__init__(parent)
        self._spin = QSpinBox()
        self._spin.setObjectName("Quantity")
        self._spin.setRange(1, maximum)
        self._spin.setGroupSeparatorShown(True)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin.setMinimumWidth(96)
        self._spin.setAccelerated(True)
        minus = icon_button("minus", "Diminuer (Maj : −10)", 16)
        plus = icon_button("plus", "Augmenter (Maj : +10)", 16)
        minus.clicked.connect(lambda: self._step(-1))
        plus.clicked.connect(lambda: self._step(1))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(minus)
        layout.addWidget(self._spin)
        layout.addWidget(plus)
        self._spin.valueChanged.connect(self.valueChanged)

    def value(self) -> int:
        return self._spin.value()

    def set_value(self, value: int, emit: bool = True) -> None:
        self._spin.blockSignals(not emit)
        self._spin.setValue(max(self._spin.minimum(), min(value, self._spin.maximum())))
        self._spin.blockSignals(False)

    def focus_input(self) -> None:
        self._spin.setFocus()
        self._spin.selectAll()

    def _step(self, direction: int) -> None:
        factor = 10 if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        self._spin.setValue(self._spin.value() + direction * factor)


class Banner(QFrame):
    def __init__(self, tone: str = "danger", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Banner")
        self.setProperty("tone", tone)
        color = TONES[tone][0]
        glyph = QLabel()
        glyph.setPixmap(icons.pixmap("alert", color, 18))
        self._text = label("", wrap=True)
        self._text.setStyleSheet(f"color: {color};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._text, 1)

    def set_text(self, text: str) -> None:
        self._text.setText(text)

    def text(self) -> str:
        return self._text.text()


EMPTY_STATE_TEXT_WIDTH = 380


def reserve_wrapped_height(widget: QLabel, width: int) -> None:
    """Fixe la largeur d'un texte sur plusieurs lignes et réserve sa hauteur réelle.

    Un QLabel à retour à la ligne centré par le layout ne reçoit sinon que la
    hauteur d'une ligne, et le texte est coupé (selon la police et le zoom Windows)."""
    widget.ensurePolished()
    widget.setFixedWidth(width)
    widget.setMinimumHeight(widget.heightForWidth(width))


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        badge = QLabel()
        badge.setFixedSize(64, 64)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icons.pixmap(icon_name, COLORS.accent, 28))
        badge.setStyleSheet(f"background: {COLORS.accent_soft}; border-radius: 20px;")
        heading = label(title, "heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = label(text, "muted", wrap=True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reserve_wrapped_height(body, EMPTY_STATE_TEXT_WIDTH)
        self.body_label = body
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        layout.addWidget(heading, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(body, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(2)


class FlowLayout(QLayout):
    """Disposition qui passe à la ligne (rangées de pastilles)."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def add(self, widget: QWidget) -> None:
        self.addChildWidget(widget)
        self.addItem(QWidgetItem(widget))

    def clear(self) -> None:
        while self._items:
            widget = self._items.pop().widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.invalidate()

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins: QMargins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect: QRect, apply: bool) -> int:
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self._items:
            if item.widget() and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and line_height > 0:
                x, y = rect.x(), y + line_height + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class FlowWidget(QWidget):
    """Conteneur de pastilles qui passent à la ligne et réservent leur hauteur réelle."""

    def __init__(self, spacing: int = 6, parent: QWidget | None = None):
        super().__init__(parent)
        self.flow = FlowLayout(self, spacing=spacing)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def add(self, widget: QWidget) -> None:
        self.flow.add(widget)
        self.updateGeometry()

    def clear(self) -> None:
        self.flow.clear()
        self.updateGeometry()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.flow.heightForWidth(width)

    def sizeHint(self) -> QSize:
        width = max(self.width(), 200)
        return QSize(width, self.flow.heightForWidth(width))
