"""Neige qui tombe doucement (thème Noël) : calque transparent posé sur un widget."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

FRAME_MS = 40
FLAKES_PER_100PX = 5.0


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

    def __init__(self, host: QWidget, seed: int | None = None, density: float = FLAKES_PER_100PX) -> None:
        super().__init__(host)
        self._density = density
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
        return max(8, int(self.width() * self._density / 100 * max(1, self.height() / 160)))

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


GARLAND_COLORS = ("#ff4b4b", "#ffd166", "#4cd98a", "#5fb4ff", "#ff7bd1")
GARLAND_HEIGHT = 24
SPAN = 150
BULB_GAP = 26
TWINKLE_MS = 650


class Garland(QWidget):
    """Guirlande lumineuse : un fil qui pend entre des crochets, des ampoules qui clignotent en alternance."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(GARLAND_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.setInterval(TWINKLE_MS)
        self._timer.timeout.connect(self.twinkle)

    @property
    def phase(self) -> int:
        return self._phase

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def twinkle(self) -> None:
        self._phase = (self._phase + 1) % 2
        self.update()

    def bulbs(self) -> list[tuple[QPointF, str, bool]]:
        """Position, couleur et état (allumée) de chaque ampoule."""
        result = []
        x, index = BULB_GAP / 2, 0
        while x < self.width():
            offset = x % SPAN
            sag = 4 * (offset / SPAN) * (1 - offset / SPAN)
            point = QPointF(x, 4 + sag * 9)
            result.append((point, GARLAND_COLORS[index % len(GARLAND_COLORS)], (index + self._phase) % 2 == 0))
            x += BULB_GAP
            index += 1
        return result

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        wire = QColor("#2f4a39")
        painter.setPen(wire)
        x = 0
        while x < self.width():
            steps = 20
            previous = QPointF(x, 3)
            for step in range(1, steps + 1):
                t = step / steps
                point = QPointF(x + SPAN * t, 3 + 4 * t * (1 - t) * 9)
                painter.drawLine(previous, point)
                previous = point
            x += SPAN
        painter.setPen(Qt.PenStyle.NoPen)
        for point, color, lit in self.bulbs():
            bulb = QColor(color)
            if lit:
                glow = QColor(color)
                glow.setAlphaF(0.28)
                painter.setBrush(glow)
                painter.drawEllipse(QPointF(point.x(), point.y() + 6), 8, 8)
            else:
                bulb = bulb.darker(220)
            painter.setBrush(QColor("#5a6b5f"))
            painter.drawRect(int(point.x()) - 2, int(point.y()), 4, 3)
            painter.setBrush(bulb)
            painter.drawEllipse(QPointF(point.x(), point.y() + 7), 4, 5.5)
        painter.end()
