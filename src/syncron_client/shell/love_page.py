"""Page cachée : un grand cœur qui bat, des petits cœurs qui s'envolent, et un mot pour Emma-Lou.

On l'ouvre en cliquant sur le petit cœur discret de la carte « À propos » des Paramètres.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QHideEvent, QLinearGradient, QPainter, QPainterPath, QPaintEvent, QShowEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import button, label

LOVE_ID = "emma-lou"
MESSAGE = "Je t'aime Emma-Lou"
FRAME_MS = 33
PINKS = ("#ff4d6d", "#ff758f", "#ff8fa3", "#c9184a", "#ffb3c1")


def heart_path(center: QPointF, size: float) -> QPainterPath:
    """Courbe du cœur (x = 16 sin³ t, y = 13 cos t − 5 cos 2t − 2 cos 3t − cos 4t), mise à l'échelle."""
    scale = size / 34
    path = QPainterPath()
    for step in range(121):
        t = step / 120 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        point = QPointF(center.x() + x * scale, center.y() - y * scale)
        if step == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


@dataclass(slots=True)
class FloatingHeart:
    x: float
    y: float
    size: float
    speed: float
    drift: float
    phase: float
    color: str
    alpha: float = 1.0


class HeartCanvas(QWidget):
    """Le cœur bat (deux pulsations rapprochées, comme un vrai battement) ; de petits cœurs montent."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tick = 0
        self._hearts: list[FloatingHeart] = []
        self._random = random.Random()
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._advance)

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    @property
    def floating(self) -> list[FloatingHeart]:
        return self._hearts

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def beat(self) -> float:
        """Échelle du grand cœur : « boum-boum » puis repos, toutes les 1,2 s."""
        moment = (self._tick * FRAME_MS / 1000) % 1.2
        pulse = math.exp(-(((moment - 0.10) / 0.06) ** 2)) + 0.6 * math.exp(-(((moment - 0.32) / 0.07) ** 2))
        return 1.0 + 0.09 * pulse

    def _advance(self) -> None:
        self._tick += 1
        if self._tick % 6 == 0 and len(self._hearts) < 40 and self.width() > 0:
            self._hearts.append(
                FloatingHeart(
                    x=self._random.uniform(0.08, 0.92) * self.width(),
                    y=self.height() + 20,
                    size=self._random.uniform(10, 26),
                    speed=self._random.uniform(0.8, 2.0),
                    drift=self._random.uniform(8, 22),
                    phase=self._random.uniform(0, 2 * math.pi),
                    color=self._random.choice(PINKS),
                )
            )
        for heart in self._hearts:
            heart.y -= heart.speed
            heart.alpha = max(0.0, min(1.0, heart.y / max(self.height() * 0.7, 1)))
        self._hearts = [heart for heart in self._hearts if heart.y > -30 and heart.alpha > 0.02]
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for heart in self._hearts:
            color = QColor(heart.color)
            color.setAlphaF(heart.alpha * 0.75)
            sway = math.sin(heart.phase + heart.y / 40) * heart.drift
            painter.setBrush(color)
            painter.drawPath(heart_path(QPointF(heart.x + sway, heart.y), heart.size))

        size = min(self.width(), self.height()) * 0.62 * self.beat()
        center = QPointF(self.width() / 2, self.height() / 2 + size * 0.04)
        glow = QColor("#ff4d6d")
        for ring, alpha in ((1.18, 0.07), (1.09, 0.12)):
            glow.setAlphaF(alpha)
            painter.setBrush(glow)
            painter.drawPath(heart_path(center, size * ring))
        top, bottom = QPointF(center.x(), center.y() - size / 2), QPointF(center.x(), center.y() + size / 2)
        gradient = QLinearGradient(top, bottom)
        gradient.setColorAt(0, QColor("#ff758f"))
        gradient.setColorAt(1, QColor("#c9184a"))
        painter.setBrush(gradient)
        painter.drawPath(heart_path(center, size))
        shine = QColor("#ffffff")
        shine.setAlphaF(0.28)
        painter.setBrush(shine)
        painter.drawEllipse(QRectF(center.x() - size * 0.33, center.y() - size * 0.30, size * 0.16, size * 0.10))
        painter.end()


class LovePage(QWidget):
    backRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.canvas = HeartCanvas()
        self.message = label(MESSAGE, "display")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet(f"font-size: 40px; font-weight: 800; color: {COLORS.text};")
        self.signature = QLabel("♥")
        self.signature.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.signature.setStyleSheet("color: #ff4d6d; font-size: 22px;")
        back = button("Retour aux paramètres", "chevron-left", "ghost")
        back.clicked.connect(self.backRequested)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 28)
        layout.setSpacing(10)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.message)
        layout.addWidget(self.signature)
        layout.addSpacing(10)
        layout.addWidget(back, 0, Qt.AlignmentFlag.AlignHCenter)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.canvas.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self.canvas.stop()
        super().hideEvent(event)
