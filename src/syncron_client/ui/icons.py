"""Jeu d'icônes vectorielles (trait 24×24), colorables et nettes à toute échelle.

Utilisation : `icon("hammer")`, `icon("clock", COLORS.accent, 16)`, `pixmap("box", size=48)`.
Ajouter une icône = ajouter une entrée à ICONS (contenu SVG intérieur).
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from syncron_client.ui.theme import COLORS

ICONS: dict[str, str] = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h5v-6h4v6h5V9.5"/>',
    "hammer": '<path d="m15 12-8.5 8.5a2.1 2.1 0 0 1-3-3L12 9"/><path d="M17.6 15 22 10.6"/>'
    '<path d="m20.9 11.7-1.3-1.3c-.6-.6-.9-1.3-.9-2.1V7.1L16.3 4.7A6 6 0 0 0 12 3l-.9.9a6 6 0 0 1 4.2 1.9'
    'l.7.7v1.4c0 .8.3 1.6.9 2.1l1.3 1.3"/>',
    "settings": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/>'
    '<circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "download": '<path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/>'
    '<path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "alert": '<path d="M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
    '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "station": '<path d="M3 21V11l5 3v-3l5 3V8l8 4v9z"/><path d="M3 21h18"/><path d="M7 17h2M12 17h2M17 17h1"/>',
    "award": '<circle cx="12" cy="9" r="6"/><path d="m8.5 14-1.5 7 5-3 5 3-1.5-7"/>',
    "box": '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z"/><path d="M3 7.5 12 12l9-4.5"/><path d="M12 12v9"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    "tree": '<rect x="3" y="3" width="6" height="5" rx="1"/><rect x="15" y="9.5" width="6" height="5" rx="1"/>'
    '<rect x="15" y="16" width="6" height="5" rx="1"/><path d="M6 8v10.5h9M6 12h9"/>',
    "recipe": '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/>'
    '<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
    '<rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "gem": '<path d="M6 3h12l3 6-9 12L3 9z"/><path d="M3 9h18"/><path d="m9 3 3 6 3-6"/><path d="M12 9v12"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4 11 13"/>'
    '<path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'
    '<path d="M8 14h.01M12 14h.01M16 14h.01M8 17.5h.01M12 17.5h.01"/>',
    "logout": '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 17l-5-5 5-5"/><path d="M5 12h11"/>',
    "shield": '<path d="M12 3 4 6v6c0 4.6 3.4 8.4 8 9 4.6-.6 8-4.4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
    "upload": '<path d="M12 20V9"/><path d="m7 14 5-5 5 5"/><path d="M5 4h14"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/>'
    '<path d="m21 16-5-5-9 9"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "save": '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/>'
    '<path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6.5 6.5 0 0 1 3.5 6"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3 2"/>',
    "wifi-off": '<path d="M2 8.8a15 15 0 0 1 4.2-2.5M10.7 5.1A15 15 0 0 1 22 8.8"/>'
    '<path d="M5 12.6a10 10 0 0 1 5.2-2.5M14.6 10.3A10 10 0 0 1 19 12.6M8.5 16.4a5 5 0 0 1 7 0"/>'
    '<path d="M12 20h.01M3 3l18 18"/>',
    "discord": '<path d="M8 8.5c2.6-1 5.4-1 8 0M7.5 16c2.8 1.2 6.2 1.2 9 0"/>'
    '<path d="M8.5 5.5 7 4 4 5.5C2.5 9 2 12.5 2.5 16c1.3 1.5 3 2.5 5 3l1-2M15.5 5.5 17 4l3 1.5'
    'c1.5 3.5 2 7 1.5 10.5-1.3 1.5-3 2.5-5 3l-1-2"/>'
    '<circle cx="9" cy="12.5" r="1.2"/><circle cx="15" cy="12.5" r="1.2"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "flask": '<path d="M9 3h6M10 3v6L4.6 18.9A1.5 1.5 0 0 0 5.9 21h12.2a1.5 1.5 0 0 0 1.3-2.1L14 9V3"/>'
    '<path d="M7 15h10"/>',
    "database": '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/>'
    '<path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2"/>'
    '<path d="M6.5 10h.01M10 10h.01M14 10h.01M17.5 10h.01M8 14h8"/>',
    "sparkles": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m6 6 2 2M16 16l2 2M6 18l2-2M16 8l2-2"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 7 8.5 6 8.5-6"/>',
    "inbox": '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5.5 5h13L21 13v6H3v-6z"/>',
    "megaphone": '<path d="M4 10v4h3l8 4V6L7 10z"/><path d="M18 9.5a3.5 3.5 0 0 1 0 5"/>'
    '<path d="M7 14l1 5h2.5l-1-4.5"/>',
    "convert": '<path d="M4 8h14l-3.5-3.5"/><path d="M20 16H6l3.5 3.5"/>',
    "chevron-left": '<path d="m15 6-6 6 6 6"/>',
    "chevron-up": '<path d="m6 15 6-6 6 6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18z"/>',
    "sword": '<path d="M14.5 3H21v6.5L10 20.5 3.5 14z"/><path d="m6 17-3 3M8 13l3 3"/>',
    "pickaxe": '<path d="M4 7.5C8 3.5 14 3 19.5 4.5 21 10 20.5 16 16.5 20"/><path d="m14 10-10 10"/>',
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5"/>'
    '<path d="M9 2.5V6M15 2.5V6M9 18v3.5M15 18v3.5M2.5 9H6M2.5 15H6M18 9h3.5M18 15h3.5"/>',
    "flag": '<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>',
    "gift": '<rect x="3.5" y="8" width="17" height="4" rx="1"/><path d="M5 12v8h14v-8M12 8v12"/>'
    '<path d="M12 8C10.5 4.5 7 4 7 6.2S10 8 12 8zM12 8c1.5-3.5 5-4 5-1.8S14 8 12 8z"/>',
    "map-pin": '<path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "circle": '<circle cx="12" cy="12" r="9"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="m10 8.5 5 3.5-5 3.5z"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "today": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'
    '<rect x="10" y="13" width="4" height="4" rx="1"/>',
}

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
    'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)
_cache: dict[tuple[str, str, int, float], QPixmap] = {}


def pixmap(name: str, color: str = COLORS.text_muted, size: int = 18, stroke: float = 1.8) -> QPixmap:
    ratio = _device_ratio()
    key = (name, color, size, ratio)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    body = ICONS.get(name, ICONS["box"])
    svg = _SVG.format(color=color, width=stroke, body=body)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    image = QPixmap(round(size * ratio), round(size * ratio))
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, image.width(), image.height()))
    painter.end()
    image.setDevicePixelRatio(ratio)
    _cache[key] = image
    return image


def icon(name: str, color: str = COLORS.text_muted, size: int = 18, active_color: str | None = None) -> QIcon:
    """`active_color` : couleur à l'état coché/survolé (navigation, segments)."""
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(pixmap(name, COLORS.text_faint, size), QIcon.Mode.Disabled, QIcon.State.Off)
    if active_color:
        result.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Normal, QIcon.State.On)
        result.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Active, QIcon.State.On)
    return result


def _device_ratio() -> float:
    app = QGuiApplication.instance()
    return app.devicePixelRatio() if app else 1.0
