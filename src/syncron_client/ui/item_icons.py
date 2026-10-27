"""Images des objets et ateliers : image téléchargée depuis le serveur (cache local) ou vignette générée.

- Cache par (type, id, taille).
- Pixel-art agrandi sans flou (16×16 / 32×32 Minecraft), lissage en réduction.
- Facteur d'échelle Windows pris en compte (125 %, 150 %…).
"""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QLinearGradient, QPainter, QPen, QPixmap

from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_core.catalog_service import CatalogService

_STOPWORDS = frozenset({"de", "d", "du", "des", "la", "le", "l", "les", "en", "a", "à", "of", "the"})


class ImageSource(Protocol):
    def image_path(self, url: str | None) -> Path | None: ...


class IconProvider:
    def __init__(self, catalog: CatalogService, images: ImageSource) -> None:
        self._catalog = catalog
        self._images = images
        self._cache: dict[tuple[str, str, int], QPixmap] = {}

    def item_pixmap(self, item_id: str, size: int) -> QPixmap:
        key = ("item", item_id, size)
        if key not in self._cache:
            item = self._catalog.get(item_id)
            path = self._images.image_path(item.image) if item else None
            image = _load(path, size)
            if image is None:
                if item is None:
                    image = _placeholder("?", "#484f58", False, size)
                else:
                    image = _placeholder(_initials(item.name), _hue_color(item_id, item.is_raw), item.is_raw, size)
            self._cache[key] = image
        return self._cache[key]

    def item_icon(self, item_id: str, size: int = 32) -> QIcon:
        return QIcon(self.item_pixmap(item_id, size))

    def station_pixmap(self, station_id: str | None, size: int) -> QPixmap:
        key = ("station", station_id or "", size)
        if key not in self._cache:
            station = self._catalog.station(station_id)
            image = _load(self._images.image_path(station.image), size) if station else None
            self._cache[key] = image or icons.pixmap("station", COLORS.info, size)
        return self._cache[key]

    def station_icon(self, station_id: str | None, size: int = 20) -> QIcon:
        return QIcon(self.station_pixmap(station_id, size))

    def clear(self) -> None:
        self._cache.clear()


def _ratio() -> float:
    app = QGuiApplication.instance()
    return app.devicePixelRatio() if app else 1.0


def _load(path: Path | None, size: int) -> QPixmap | None:
    if path is None:
        return None
    source = QPixmap(str(path))
    if source.isNull():
        return None
    ratio = _ratio()
    target = round(size * ratio)
    upscale = max(source.width(), source.height()) < target
    mode = Qt.TransformationMode.FastTransformation if upscale else Qt.TransformationMode.SmoothTransformation
    scaled = source.scaled(target, target, Qt.AspectRatioMode.KeepAspectRatio, mode)
    scaled.setDevicePixelRatio(ratio)
    return scaled


def _hue_color(seed: str, is_raw: bool) -> QColor:
    hue = zlib.crc32(seed.encode("utf-8")) % 360
    return QColor.fromHsl(hue, 150 if is_raw else 110, 110 if is_raw else 100)


def _initials(name: str) -> str:
    words = [
        word
        for word in name.replace("_", " ").replace("'", " ").replace("’", " ").split()
        if word[0].isalnum() and word.casefold() not in _STOPWORDS
    ]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].capitalize()
    return (words[0][0] + words[1][0]).upper()


def _placeholder(text: str, color: QColor | str, round_shape: bool, size: int) -> QPixmap:
    ratio = _ratio()
    image = QPixmap(round(size * ratio), round(size * ratio))
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    base = QColor(color)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    rect = QRectF(1, 1, size - 2, size - 2)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, base.lighter(125))
    gradient.setColorAt(1, base.darker(135))
    painter.setPen(QPen(base.lighter(150), max(1.0, size / 28)))
    painter.setBrush(gradient)
    if round_shape:
        painter.drawEllipse(rect)
    else:
        painter.drawRoundedRect(rect, size * 0.26, size * 0.26)
    font = QFont(QGuiApplication.font())
    font.setBold(True)
    font.setPixelSize(max(7, round(size * (0.44 if len(text) == 1 else 0.38))))
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return image
