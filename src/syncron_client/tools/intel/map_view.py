"""Carte interactive du monde NationsGlory (QPainter) : déplacer, zoomer, cliquer un pays.

Couches : frontières (pays de l'atlas), claims (territoires réellement revendiqués),
régions, marqueurs de biome, noms, événements météo. Les formes sont en chunks ;
les tailles de traits, pastilles et textes restent fixes à l'écran.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QLabel, QWidget

from syncron_client.tools.intel.model import CHUNK, EVENT_COLORS, Event, Marker, World
from syncron_client.ui.theme import COLORS

LAYERS = {
    "frontiers": ("Frontières", True),
    "claims": ("Claims", True),
    "regions": ("Régions", False),
    "markers": ("Marqueurs", False),
    "names": ("Noms", True),
    "events": ("Événements", True),
}
MAX_SCALE = 80.0
SMALL_CLAIM_PX = 10
PICK_RADIUS = 9


def _rgba(hex_color: str, alpha: float) -> QColor:
    result = QColor(hex_color)
    result.setAlphaF(alpha)
    return result


class MapView(QWidget):
    countryClicked = Signal(str)  # "" : clic dans le vide
    markerClicked = Signal(object)
    eventClicked = Signal(object)
    viewChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.world = World()
        self.layers = {key: default for key, (_label, default) in LAYERS.items()}
        self.selected = ""
        self.center = QPointF(0, 0)
        self.scale = 1.0
        self.min_scale = 0.05
        self._fitted = False
        self._drag: tuple[QPointF, QPointF] | None = None
        self._moved = False
        self._phase = 0.0
        self._pulse = QTimer(self)
        self._pulse.setInterval(60)
        self._pulse.timeout.connect(self._tick)
        self._dark = COLORS.dark
        self._background = QColor("#0d1624" if self._dark else "#d6dee8")
        self._halo = QColor(13, 22, 36, 230) if self._dark else QColor(255, 255, 255, 230)
        self._text = QColor("#e6edf7" if self._dark else "#1b2433")
        self.tip = QLabel(self)
        self.tip.setTextFormat(Qt.TextFormat.PlainText)
        self.tip.setStyleSheet(
            f"background: {COLORS.surface}; color: {COLORS.text}; border: 1px solid {COLORS.border_strong};"
            "border-radius: 8px; padding: 6px 9px; font-size: 12px;"
        )
        self.tip.hide()
        self.status = QLabel(self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setStyleSheet(
            f"background: {_rgba(COLORS.surface, 0.85).name(QColor.NameFormat.HexArgb)}; color: {COLORS.text_muted};"
            "border-radius: 7px; padding: 4px 8px; font-size: 11px;"
        )
        self._cursor_text = ""

    # -- données et vue ------------------------------------------------------------------

    def set_world(self, world: World) -> None:
        first = self.world.empty and not world.empty
        self.world = world
        self._brushes = {
            "frontier": {f.name: (_rgba(f.color, 0.30), QColor(f.color)) for f in world.frontiers},
            "claim": {f.name: _rgba(f.color, 0.9) for f in world.factions},
        }
        if first or not self._fitted:
            self.fit()
        self._update_pulse()
        self.update()
        self._update_status()

    def set_layer(self, key: str, visible: bool) -> None:
        self.layers[key] = visible
        self._update_pulse()
        self.update()

    def select(self, name: str) -> None:
        self.selected = name
        self.update()

    def fit(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        bounds = self.world.bounds()
        self.center = bounds.center()
        self.scale = min(self.width() / max(bounds.width(), 1), self.height() / max(bounds.height(), 1)) * 0.95
        self.min_scale = self.scale * 0.5
        self._fitted = not self.world.empty
        self._changed()

    def fly_to(self, name: str) -> None:
        faction = self.world.faction(name)
        shape = faction if faction is not None and faction.bbox is not None else self.world.frontier(name)
        if shape is not None and shape.bbox is not None:
            box = shape.bbox
            self.center = box.center()
            fit = min(self.width() / max(box.width(), 2), self.height() / max(box.height(), 2)) * 0.5
            self.scale = min(60.0, max(self.min_scale, fit))
        elif faction is not None and faction.label is not None:
            self.center = QPointF(faction.label)
            self.scale = max(self.scale, 12.0)
        self._changed()

    def show_block(self, x: float, z: float, scale: float = 10.0) -> None:
        self.center = QPointF(x / CHUNK, z / CHUNK)
        self.scale = max(self.scale, scale)
        self._changed()

    def zoom_ratio(self) -> float:
        bounds = self.world.bounds()
        base = min(self.width() / max(bounds.width(), 1), self.height() / max(bounds.height(), 1)) * 0.95
        return self.scale / base if base > 0 else 1.0

    def to_world(self, point: QPointF) -> QPointF:
        return QPointF(
            (point.x() - self.width() / 2) / self.scale + self.center.x(),
            (point.y() - self.height() / 2) / self.scale + self.center.y(),
        )

    def to_screen(self, x: float, z: float) -> QPointF:
        return QPointF(
            (x - self.center.x()) * self.scale + self.width() / 2,
            (z - self.center.y()) * self.scale + self.height() / 2,
        )

    def _visible(self) -> QRectF:
        top_left = self.to_world(QPointF(0, 0))
        return QRectF(top_left.x(), top_left.y(), self.width() / self.scale, self.height() / self.scale)

    def _changed(self) -> None:
        self.update()
        self._update_status()
        self.viewChanged.emit()

    # -- dessin --------------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._background)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, self._drag is None or not self._moved)
        visible = self._visible()
        world = self.world
        painter.save()
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(self.scale, self.scale)
        painter.translate(-self.center.x(), -self.center.y())
        if self.layers["regions"]:
            pen = QPen(_rgba("#94a3b8", 0.45), 1.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for region in world.regions:
                if region.bbox is not None and region.bbox.intersects(visible):
                    painter.drawPath(region.path)
        if self.layers["frontiers"]:
            for frontier in world.frontiers:
                if frontier.bbox is None or not frontier.bbox.intersects(visible):
                    continue
                fill, stroke = self._brushes["frontier"][frontier.name]
                pen = QPen(stroke, 1.2)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(fill)
                painter.drawPath(frontier.path)
        if self.layers["claims"]:
            pen = QPen(QColor("#ffffff"), 1.2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            for faction in world.factions:
                if faction.bbox is None or not faction.bbox.intersects(visible):
                    continue
                painter.setBrush(self._brushes["claim"][faction.name])
                painter.drawPath(faction.path)
        selected = self._selected_path()
        if selected is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for color, width in ((QColor("#ffffff"), 3.0), (QColor(world.color_of(self.selected)), 1.5)):
                pen = QPen(color, width)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawPath(selected)
        painter.restore()

        if self.layers["markers"]:
            painter.setPen(QPen(QColor(0, 0, 0, 150), 1))
            for marker in world.markers:
                point = self.to_screen(marker.x / CHUNK, marker.z / CHUNK)
                if self.rect().adjusted(-5, -5, 5, 5).contains(point.toPoint()):
                    painter.setBrush(QColor(str(world.biomes.get(marker.biome, {}).get("color") or "#fbbf24")))
                    painter.drawEllipse(point, 3.5, 3.5)
        if self.layers["claims"]:
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            for faction in world.factions:
                if faction.label is None or self._claim_size(faction) >= SMALL_CLAIM_PX:
                    continue
                point = self.to_screen(faction.label.x(), faction.label.y())
                if self.rect().adjusted(-10, -10, 10, 10).contains(point.toPoint()):
                    painter.setBrush(QColor(faction.color))
                    painter.drawEllipse(point, 4.5, 4.5)
        if self.layers["names"]:
            self._draw_names(painter)
        if self.layers["events"]:
            self._draw_events(painter)
        painter.end()

    def _selected_path(self) -> QPainterPath | None:
        if not self.selected:
            return None
        faction = self.world.faction(self.selected)
        if faction is not None and faction.bbox is not None:
            return faction.path
        frontier = self.world.frontier(self.selected)
        return frontier.path if frontier is not None and frontier.bbox is not None else None

    def _claim_size(self, faction) -> float:
        if faction.bbox is None:
            return 0.0
        return max(faction.bbox.width(), faction.bbox.height()) * self.scale

    def _label(self, painter: QPainter, text: str, point: QPointF, metrics: QFontMetricsF) -> None:
        width = metrics.horizontalAdvance(text)
        origin = QPointF(point.x() - width / 2, point.y() + metrics.ascent() / 2 - 1)
        path = QPainterPath()
        path.addText(origin, painter.font(), text)
        painter.strokePath(
            path, QPen(self._halo, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.fillPath(path, self._text)

    def _draw_names(self, painter: QPainter) -> None:
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        area = self.rect().adjusted(-50, -20, 50, 20)
        named: set[str] = set()
        for frontier in self.world.frontiers:
            if frontier.bbox is None or max(frontier.bbox.width(), frontier.bbox.height()) * self.scale < 70:
                continue
            label = self.world.countries.get(frontier.name, {}).get("label")
            if isinstance(label, list) and len(label) >= 2:
                point = self.to_screen(float(label[0]) / CHUNK, float(label[1]) / CHUNK)
            else:
                center = frontier.bbox.center()
                point = self.to_screen(center.x(), center.y())
            if area.contains(point.toPoint()):
                self._label(painter, frontier.name, point, metrics)
                named.add(frontier.name)
        if self.scale >= 4:
            for faction in self.world.factions:
                if faction.label is None or faction.name in named:
                    continue
                point = self.to_screen(faction.label.x(), faction.label.y())
                if area.contains(point.toPoint()):
                    self._label(painter, faction.name, QPointF(point.x(), point.y() + 14), metrics)

    def _draw_events(self, painter: QPainter) -> None:
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        for event in self.world.events:
            if not event.active or event.x is None or event.z is None:
                continue
            point = self.to_screen(event.x / CHUNK, event.z / CHUNK)
            if not self.rect().adjusted(-40, -40, 40, 40).contains(point.toPoint()):
                continue
            color = QColor(EVENT_COLORS[event.kind])
            ring = _rgba(EVENT_COLORS[event.kind], 0.7 * (1 - self._phase))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 2.5))
            radius = 8 + 16 * self._phase
            painter.drawEllipse(point, radius, radius)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(color)
            painter.drawEllipse(point, 7, 7)
            self._label(painter, event.title, QPointF(point.x(), point.y() - 18), metrics)

    # -- souris --------------------------------------------------------------------------

    def pick_country(self, point: QPointF) -> str:
        world_point = self.to_world(point)
        if self.layers["claims"]:
            for faction in self.world.factions:
                if faction.label is not None and self._claim_size(faction) < SMALL_CLAIM_PX:
                    screen = self.to_screen(faction.label.x(), faction.label.y())
                    if math.hypot(screen.x() - point.x(), screen.y() - point.y()) < PICK_RADIUS:
                        return faction.name
            for faction in self.world.factions:
                if (
                    faction.bbox is not None
                    and faction.bbox.contains(world_point)
                    and faction.path.contains(world_point)
                ):
                    return faction.name
        if self.layers["frontiers"]:
            for frontier in self.world.frontiers:
                if (
                    frontier.bbox is not None
                    and frontier.bbox.contains(world_point)
                    and frontier.path.contains(world_point)
                ):
                    return frontier.name
        return ""

    def pick_marker(self, point: QPointF) -> Marker | None:
        if not self.layers["markers"]:
            return None
        best, distance = None, float(PICK_RADIUS)
        for marker in self.world.markers:
            screen = self.to_screen(marker.x / CHUNK, marker.z / CHUNK)
            gap = math.hypot(screen.x() - point.x(), screen.y() - point.y())
            if gap < distance:
                best, distance = marker, gap
        return best

    def pick_event(self, point: QPointF) -> Event | None:
        if not self.layers["events"]:
            return None
        for event in self.world.events:
            if event.active and event.x is not None and event.z is not None:
                screen = self.to_screen(event.x / CHUNK, event.z / CHUNK)
                if math.hypot(screen.x() - point.x(), screen.y() - point.y()) < 12:
                    return event
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = (event.position(), QPointF(self.center))
            self._moved = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        position = event.position()
        if self._drag is not None:
            start, center = self._drag
            delta = position - start
            if abs(delta.x()) + abs(delta.y()) > 4:
                self._moved = True
            if self._moved:
                self.center = QPointF(center.x() - delta.x() / self.scale, center.y() - delta.y() / self.scale)
                self.tip.hide()
                self._changed()
                return
        world_point = self.to_world(position)
        self._cursor_text = f"x {round(world_point.x() * CHUNK)} · z {round(world_point.y() * CHUNK)}"
        self._update_status()
        self._show_tip(position)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._drag is None:
            return
        moved = self._moved
        self._drag = None
        self._moved = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if moved:
            self.update()
            return
        position = event.position()
        weather = self.pick_event(position)
        if weather is not None:
            self.eventClicked.emit(weather)
            return
        marker = self.pick_marker(position)
        if marker is not None:
            self.markerClicked.emit(marker)
            return
        self.countryClicked.emit(self.pick_country(position))

    def wheelEvent(self, event: QWheelEvent) -> None:
        position = event.position()
        anchor = self.to_world(position)
        steps = event.angleDelta().y()
        self.scale = min(MAX_SCALE, max(self.min_scale, self.scale * math.pow(1.0015, steps)))
        self.center = QPointF(
            anchor.x() - (position.x() - self.width() / 2) / self.scale,
            anchor.y() - (position.y() - self.height() / 2) / self.scale,
        )
        self._changed()

    def leaveEvent(self, _event) -> None:
        self.tip.hide()
        self._cursor_text = ""
        self._update_status()

    def resizeEvent(self, _event) -> None:
        if not self._fitted:
            self.fit()
        self._update_status()

    # -- infos ---------------------------------------------------------------------------

    def _show_tip(self, position: QPointF) -> None:
        text = ""
        weather = self.pick_event(position)
        marker = None if weather else self.pick_marker(position)
        if weather is not None:
            text = f"{weather.title}\nx {weather.x} · z {weather.z}"
        elif marker is not None:
            biome = self.world.biomes.get(marker.biome, {})
            text = f"{biome.get('nameFr') or marker.biome or 'Biome'}\nCliquer pour les ressources"
        else:
            name = self.pick_country(position)
            if name:
                parts = []
                faction = self.world.faction(name)
                if faction is not None:
                    parts.append(f"{faction.chunks} chunks claim")
                members = self.world.members.get(name)
                if members is not None:
                    parts.append(f"{members.get('total', 0)} membres")
                text = f"{name}\n{' · '.join(parts) or 'frontière'}"
        if not text:
            self.tip.hide()
            return
        self.tip.setText(text)
        self.tip.adjustSize()
        x = min(int(position.x()) + 14, self.width() - self.tip.width() - 4)
        y = min(int(position.y()) + 14, self.height() - self.tip.height() - 4)
        self.tip.move(max(4, x), max(4, y))
        self.tip.show()
        self.tip.raise_()

    def _update_status(self) -> None:
        parts = [f"Zoom ×{self.zoom_ratio():.1f}"]
        game = self.world.game_time()
        if game:
            parts.append(f"jeu {game}")
        if self._cursor_text:
            parts.append(self._cursor_text)
        self.status.setText(" · ".join(parts))
        self.status.adjustSize()
        self.status.move(10, self.height() - self.status.height() - 10)

    def _update_pulse(self) -> None:
        active = self.layers["events"] and any(e.active and e.x is not None for e in self.world.events)
        if active and not self._pulse.isActive():
            self._pulse.start()
        elif not active:
            self._pulse.stop()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.04) % 1.0
        self.update()

    def hideEvent(self, _event) -> None:
        self._pulse.stop()

    def showEvent(self, _event) -> None:
        self._update_pulse()
