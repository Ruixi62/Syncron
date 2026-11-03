"""Neige qui tombe doucement (thème Noël) : calque transparent posé sur un widget."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

FRAME_MS = 40
FLAKES_PER_100PX = 3


@dataclass(slots=True)
class Flake:
    x: float
    y: float
    radius: float
    speed: float
    sway: float
    phase: float


class Snowfall(QWidget):
    """Calque enfant de `host`, à sa taille, qui ne capte pas la souris ; anime seulement quand il est visible."""

    def __init__(self, host: QWidget, seed: int | None = None) -> None:
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._random = random.Random(seed)
        self._flakes: list[Flake] = []
        self._tick = 0
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self.advance)
        host.installEventFilter(self)
        self.setGeometry(host.rect())
        self.raise_()

    @property
    def flakes(self) -> list[Flake]:
        return self._flakes

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
            self._fill()
        elif event.type() == QEvent.Type.Show:
            self._timer.start()
        elif event.type() == QEvent.Type.Hide:
            self._timer.stop()
        return False

    def _target(self) -> int:
        return max(8, self.width() * FLAKES_PER_100PX // 100)

    def _fill(self) -> None:
        while len(self._flakes) < self._target():
            self._flakes.append(self._new(top=False))
        del self._flakes[self._target() :]

    def _new(self, top: bool) -> Flake:
        return Flake(
            x=self._random.uniform(0, max(self.width(), 1)),
            y=-6.0 if top else self._random.uniform(0, max(self.height(), 1)),
            radius=self._random.uniform(1.2, 3.2),
            speed=self._random.uniform(0.35, 1.1),
            sway=self._random.uniform(0.4, 1.4),
            phase=self._random.uniform(0, 2 * math.pi),
        )

    def advance(self) -> None:
        self._tick += 1
        for index, flake in enumerate(self._flakes):
            flake.y += flake.speed
            flake.x += math.sin(flake.phase + self._tick / 30) * flake.sway * 0.3
            if flake.y > self.height() + 6:
                self._flakes[index] = self._new(top=True)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for flake in self._flakes:
            color = QColor("#ffffff")
            color.setAlphaF(0.35 + flake.radius / 8)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(flake.x, flake.y), flake.radius, flake.radius)
        painter.end()
