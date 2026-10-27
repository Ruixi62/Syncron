"""Barre latérale : marque, accueil, outils, gestion (rôles éditeur/admin), paramètres, compte."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from syncron_client.platform.tool import StatusLevel, ToolStatus
from syncron_client.ui import icons
from syncron_client.ui.brand import logo_pixmap
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import ElidedLabel, icon_button, label
from syncron_core import APP_DISPLAY_NAME, __version__

HOME_ID = "home"
SETTINGS_ID = "settings"
SIDEBAR_WIDTH = 236
AVATAR_SIZE = 34


class NavButton(QPushButton):
    def __init__(self, page_id: str, text: str, icon_name: str, parent: QWidget | None = None):
        super().__init__(text.replace("&", "&&"), parent)
        self.page_id = page_id
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(icons.icon(icon_name, COLORS.text_muted, 18, active_color=COLORS.accent))
        self.setIconSize(QSize(18, 18))
        self._badge = QLabel(self)
        self._badge.setObjectName("NavBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.hide()

    def set_planned(self) -> None:
        self._badge.setText("Bientôt")
        self._badge.setStyleSheet(f"background: {COLORS.violet_soft}; color: {COLORS.violet};")
        self._badge.adjustSize()
        self._badge.show()
        self.setToolTip("Outil en attente de développement")
        self._place_badge()

    def set_status(self, status: ToolStatus) -> None:
        if self._badge.text() == "Bientôt":
            return
        if status.level is StatusLevel.OK or not status.badge:
            self._badge.hide()
            self.setToolTip(status.message)
            return
        color = COLORS.danger if status.level is StatusLevel.ERROR else COLORS.warning
        self._badge.setStyleSheet(f"background: {color};")
        self._badge.setText(status.badge)
        self._badge.adjustSize()
        self._badge.show()
        self.setToolTip(status.message)
        self._place_badge()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_badge()

    def _place_badge(self) -> None:
        self._badge.move(self.width() - self._badge.width() - 10, (self.height() - self._badge.height()) // 2)


def initials_avatar(name: str, size: int) -> QPixmap:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(COLORS.accent_soft.replace("0.13", "0.35")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(0, 0, size, size))
    font = QFont()
    font.setBold(True)
    font.setPixelSize(round(size * 0.42))
    painter.setFont(font)
    painter.setPen(QColor(COLORS.accent))
    letters = "".join(word[0] for word in name.split()[:2]).upper() or "?"
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, letters[:2])
    painter.end()
    return pixmap


def round_avatar(source: QPixmap, size: int) -> QPixmap:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(path)
    painter.drawPixmap(QRectF(0, 0, size, size), source, QRectF(source.rect()))
    painter.end()
    return pixmap


class AccountCard(QFrame):
    logoutRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", "flat")
        self._avatar = QLabel()
        self._avatar.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self._name = ElidedLabel("", None)
        self._name.setStyleSheet("font-weight: 600;")
        self._role = ElidedLabel("", "faint")
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(self._name)
        texts.addWidget(self._role)
        self.logout_button: QToolButton = icon_button("logout", "Se déconnecter", 16)
        self.logout_button.clicked.connect(self.logoutRequested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 6, 8)
        layout.setSpacing(10)
        layout.addWidget(self._avatar)
        layout.addLayout(texts, 1)
        layout.addWidget(self.logout_button)

    def set_account(self, name: str, role: str, online: bool) -> None:
        self._name.setText(name)
        self._role.setText(role if online else f"{role} · hors ligne")
        self._avatar.setPixmap(initials_avatar(name, AVATAR_SIZE))

    def set_avatar(self, pixmap: QPixmap) -> None:
        if not pixmap.isNull():
            self._avatar.setPixmap(round_avatar(pixmap, AVATAR_SIZE))


class Sidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self._buttons: dict[str, NavButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        logo = QLabel()
        logo.setFixedSize(38, 38)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(logo_pixmap(34))
        name = label(APP_DISPLAY_NAME, "heading")
        version = label(f"v{__version__}", "faint")
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(name)
        brand_text.addWidget(version)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(logo)
        brand.addLayout(brand_text, 1)

        self._tools_layout = QVBoxLayout()
        self._tools_layout.setSpacing(2)
        self._manage_layout = QVBoxLayout()
        self._manage_layout.setSpacing(2)
        self._manage_title = label("GESTION", "overline")
        self._manage_title.setContentsMargins(12, 0, 0, 4)
        self._manage_title.hide()
        self.account = AccountCard()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)
        layout.addLayout(brand)
        layout.addSpacing(18)
        layout.addWidget(self._add_button(HOME_ID, "Accueil", "home"))
        layout.addSpacing(14)
        tools_title = label("OUTILS", "overline")
        tools_title.setContentsMargins(12, 0, 0, 4)
        layout.addWidget(tools_title)
        layout.addLayout(self._tools_layout)
        layout.addSpacing(14)
        layout.addWidget(self._manage_title)
        layout.addLayout(self._manage_layout)
        layout.addStretch(1)
        layout.addWidget(self._add_button(SETTINGS_ID, "Paramètres", "settings"))
        layout.addSpacing(8)
        layout.addWidget(self.account)

    def add_tool(self, tool_id: str, name: str, icon_name: str, planned: bool = False, manage: bool = False) -> None:
        button = self._add_button(tool_id, name, icon_name)
        if planned:
            button.set_planned()
        if manage:
            self._manage_title.show()
            self._manage_layout.addWidget(button)
        else:
            self._tools_layout.addWidget(button)

    def set_current(self, page_id: str) -> None:
        button = self._buttons.get(page_id)
        if button is not None:
            button.setChecked(True)

    def set_status(self, tool_id: str, status: ToolStatus) -> None:
        button = self._buttons.get(tool_id)
        if button is not None:
            button.set_status(status)

    def _add_button(self, page_id: str, text: str, icon_name: str) -> NavButton:
        button = NavButton(page_id, text, icon_name)
        button.clicked.connect(lambda: self.navigate.emit(page_id))
        self._group.addButton(button)
        self._buttons[page_id] = button
        return button
