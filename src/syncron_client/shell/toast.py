"""Notifications éphémères en bas à droite de la fenêtre."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from syncron_client.platform.tool import NotifyLevel
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS

_LEVELS = {
    NotifyLevel.INFO: ("info", COLORS.info),
    NotifyLevel.SUCCESS: ("check", COLORS.success),
    NotifyLevel.WARNING: ("alert", COLORS.warning),
    NotifyLevel.ERROR: ("alert", COLORS.danger),
}
DISPLAY_MS = 3800
MARGIN = 20


class Toast(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._glyph = QLabel()
        self._text = QLabel()
        self._text.setWordWrap(True)
        self._text.setMaximumWidth(420)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 16, 11)
        layout.setSpacing(10)
        layout.addWidget(self._glyph, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._text, 1)
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, message: str, level: NotifyLevel) -> None:
        icon_name, color = _LEVELS.get(level, _LEVELS[NotifyLevel.INFO])
        self._glyph.setPixmap(icons.pixmap(icon_name, color, 18))
        self._text.setText(message)
        self._text.setMinimumWidth(min(self._text.fontMetrics().horizontalAdvance(message) + 4, 420))
        self.setStyleSheet(
            f"Toast {{ background: {COLORS.surface_alt}; border: 1px solid {COLORS.border_strong};"
            f" border-left: 3px solid {color}; border-radius: 12px; }}"
        )
        start = self._opacity.opacity() if self.isVisible() else 0.0
        self.adjustSize()
        self.reposition()
        self.raise_()
        self.show()
        self._fade.stop()
        self._fade.setStartValue(start)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(DISPLAY_MS)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.move(parent.width() - self.width() - MARGIN, parent.height() - self.height() - MARGIN)

    def message(self) -> str:
        return self._text.text()

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._hide_after_fade)
        self._fade.start()

    def _hide_after_fade(self) -> None:
        self._fade.finished.disconnect(self._hide_after_fade)
        if self._opacity.opacity() <= 0.01:
            self.hide()
