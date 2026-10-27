"""Identité Syncron : logo vectoriel (assets/logo.svg) et icône de l'application."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_SVG = ASSETS_DIR / "logo.svg"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

_cache: dict[tuple[int, float], QPixmap] = {}


def logo_pixmap(size: int) -> QPixmap:
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if app else 1.0
    key = (size, ratio)
    if key not in _cache:
        image = QPixmap(round(size * ratio), round(size * ratio))
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(str(LOGO_SVG)).render(painter, QRectF(0, 0, image.width(), image.height()))
        painter.end()
        image.setDevicePixelRatio(ratio)
        _cache[key] = image
    return _cache[key]


def app_icon() -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(logo_pixmap(size))
    return icon
