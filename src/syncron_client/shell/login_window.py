"""Écran de connexion : Discord, reprise hors ligne, version minimale, connexion de développement."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from syncron_client.ui import icons
from syncron_client.ui.brand import logo_pixmap
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Banner, Card, button, label, reserve_wrapped_height
from syncron_core import APP_DISPLAY_NAME, APP_TAGLINE, __version__

DISCORD_BLURPLE = "#5865f2"
FORM_WIDTH = 380


class LoginWindow(QWidget):
    discordRequested = Signal()
    cancelRequested = Signal()
    offlineRequested = Signal()
    devLoginRequested = Signal(str, str)
    serverChangeRequested = Signal(str)

    def __init__(self, server_url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Connexion")
        self.setMinimumSize(920, 600)
        self.resize(1040, 660)

        brand = QFrame()
        brand.setObjectName("LoginBrand")
        brand.setStyleSheet(
            "#LoginBrand { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f2a25, stop:0.6 #0d1520,"
            f" stop:1 #0b1a2a); border-right: 1px solid {COLORS.border}; }}"
        )
        logo = QLabel()
        logo.setPixmap(logo_pixmap(120))
        logo.setFixedSize(120, 120)
        title = label(APP_DISPLAY_NAME, "display")
        tagline = label(APP_TAGLINE + ".", "muted", wrap=True)
        tagline.setMaximumWidth(340)
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(48, 48, 48, 40)
        brand_layout.addStretch(1)
        brand_layout.addWidget(logo)
        brand_layout.addSpacing(18)
        brand_layout.addWidget(title)
        brand_layout.addWidget(tagline)
        brand_layout.addStretch(2)
        brand_layout.addWidget(label(f"Version {__version__}", "faint"))

        self._status = label("", "muted", wrap=True)
        self._error = Banner("danger")
        self._error.hide()
        self._update = Banner("warning")
        self._update.hide()

        self.discord_button = QPushButton("  Se connecter avec Discord")
        self.discord_button.setIcon(icons.icon("discord", "#ffffff", 20))
        self.discord_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.discord_button.setStyleSheet(
            f"QPushButton {{ background: {DISCORD_BLURPLE}; color: white; border: none; border-radius: 11px;"
            " padding: 12px; font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background: #4752c4; } QPushButton:disabled { background: #3a3f73; color: #c9ccf5; }"
        )
        self.discord_button.clicked.connect(self.discordRequested)
        self.cancel_button = button("Annuler", "close", "ghost")
        self.cancel_button.clicked.connect(self.cancelRequested)
        self.cancel_button.hide()
        self.offline_button = button("Continuer hors ligne", "wifi-off")
        self.offline_button.clicked.connect(self.offlineRequested)
        self.offline_button.hide()

        self._dev_box = Card(flat=True, padding=14, spacing=8)
        self._dev_box.body.addWidget(label("CONNEXION DE DÉVELOPPEMENT", "overline"))
        self._dev_user = QLineEdit()
        self._dev_user.setPlaceholderText("pseudo")
        self._dev_role = QComboBox()
        for value, text in (("admin", "Administrateur"), ("editor", "Éditeur"), ("player", "Joueur")):
            self._dev_role.addItem(text, value)
        dev_go = button("Entrer", "arrow-right")
        dev_go.clicked.connect(
            lambda: self.devLoginRequested.emit(self._dev_user.text().strip(), self._dev_role.currentData())
        )
        dev_row = QHBoxLayout()
        dev_row.addWidget(self._dev_user, 1)
        dev_row.addWidget(self._dev_role)
        dev_row.addWidget(dev_go)
        self._dev_box.body.addLayout(dev_row)
        self._dev_box.hide()

        self._server = label("", "faint")
        change = QPushButton("Changer")
        change.setProperty("variant", "ghost")
        change.setCursor(Qt.CursorShape.PointingHandCursor)
        change.clicked.connect(self._ask_server)
        server_row = QHBoxLayout()
        server_row.addWidget(self._server, 1)
        server_row.addWidget(change)
        self.set_server(server_url)

        heading = label("Connexion", "title")
        intro = label("Connecte-toi avec ton compte Discord pour accéder à Syncron.", "muted", wrap=True)
        reserve_wrapped_height(intro, FORM_WIDTH)
        form = QWidget()
        form.setFixedWidth(FORM_WIDTH)
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        form_layout.addWidget(heading)
        form_layout.addWidget(intro)
        form_layout.addSpacing(10)
        form_layout.addWidget(self._update)
        form_layout.addWidget(self._error)
        form_layout.addWidget(self.discord_button)
        form_layout.addWidget(self._status)
        form_layout.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignLeft)
        form_layout.addWidget(self.offline_button)
        form_layout.addWidget(self._dev_box)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(48, 40, 48, 28)
        right_layout.addStretch(1)
        right_layout.addWidget(form, 0, Qt.AlignmentFlag.AlignHCenter)
        right_layout.addStretch(1)
        right_layout.addLayout(server_row)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(brand, 5)
        layout.addWidget(right, 6)

    # -- états ---------------------------------------------------------------------

    def set_server(self, url: str) -> None:
        self._server.setText(f"Serveur : {url}")

    def set_busy(self, message: str, cancellable: bool = False) -> None:
        self._error.hide()
        self._status.setText(message)
        self.discord_button.setEnabled(False)
        self.cancel_button.setVisible(cancellable)

    def set_idle(self, message: str = "") -> None:
        self._status.setText(message)
        self.discord_button.setEnabled(not self._update.isVisibleTo(self))
        self.cancel_button.hide()

    def show_error(self, message: str) -> None:
        self.set_idle()
        self._error.set_text(message)
        self._error.show()

    def error_text(self) -> str:
        return self._error.text() if not self._error.isHidden() else ""

    def status_text(self) -> str:
        return self._status.text()

    def show_update_required(self, minimum: str) -> None:
        self._update.set_text(
            f"Cette version ({__version__}) n'est plus acceptée par le serveur. "
            f"Télécharge Syncron {minimum} ou plus récent pour continuer."
        )
        self._update.show()
        self.discord_button.setEnabled(False)

    def set_offline_available(self, available: bool) -> None:
        self.offline_button.setVisible(available)

    def set_dev_login(self, enabled: bool) -> None:
        self._dev_box.setVisible(enabled)

    def _ask_server(self) -> None:
        current = self._server.text().removeprefix("Serveur : ")
        url, ok = QInputDialog.getText(self, "Serveur Syncron", "Adresse de l'API :", text=current)
        if ok and url.strip():
            self.serverChangeRequested.emit(url.strip().rstrip("/"))
