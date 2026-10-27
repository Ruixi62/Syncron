"""Paramètres : compte, serveur, stockage local, outils, à propos."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from syncron_client.config import SERVER_URL_KEY
from syncron_client.platform.registry import ToolRegistry
from syncron_client.platform.tool import NotifyLevel, ToolHost, ToolStage
from syncron_client.settings import JsonSettingsStore
from syncron_client.ui.widgets import Card, Chip, button, divider, label
from syncron_core import APP_DISPLAY_NAME, __version__


class SettingsPage(QScrollArea):
    logoutRequested = Signal()

    def __init__(self, host: ToolHost, registry: ToolRegistry, settings: JsonSettingsStore, parent=None) -> None:
        super().__init__(parent)
        self._host = host
        self._settings = settings
        self.setWidgetResizable(True)

        account = Card(padding=20, spacing=12)
        account.body.addWidget(label("COMPTE", "overline"))
        self._account_name = label("", "heading")
        self._account_details = label("", "faint")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self._account_name)
        texts.addWidget(self._account_details)
        self._role_chip = Chip("", "accent", "shield")
        logout = button("Se déconnecter", "logout")
        logout.clicked.connect(self.logoutRequested)
        row = QHBoxLayout()
        row.addLayout(texts, 1)
        row.addWidget(self._role_chip)
        row.addSpacing(8)
        row.addWidget(logout)
        account.body.addLayout(row)

        server = Card(padding=20, spacing=12)
        server.body.addWidget(label("SERVEUR", "overline"))
        server.body.addWidget(
            label(
                "Adresse de l'API Syncron. Ne la change que si l'équipe t'a communiqué une nouvelle adresse.",
                "muted",
                wrap=True,
            )
        )
        self._server_url = QLineEdit(host.api.base_url)
        self._server_url.setPlaceholderText("https://api.exemple.fr")
        apply_server = button("Appliquer", "check")
        apply_server.clicked.connect(self._apply_server)
        self._server_status = Chip("", "neutral")
        server_row = QHBoxLayout()
        server_row.addWidget(self._server_url, 1)
        server_row.addWidget(apply_server)
        server.body.addLayout(server_row)
        server.body.addWidget(self._server_status, 0, Qt.AlignmentFlag.AlignLeft)

        storage = Card(padding=20, spacing=12)
        storage.body.addWidget(label("STOCKAGE LOCAL", "overline"))
        storage.body.addWidget(
            label(
                "Tes préférences et une copie du catalogue (pour démarrer vite et consulter hors ligne) "
                "sont gardées sur ce PC. Les données de jeu, elles, sont sur le serveur.",
                "muted",
                wrap=True,
            )
        )
        storage.body.addLayout(self._path_row("Dossier Syncron", host.app_paths.user_dir))
        storage.body.addWidget(divider())
        self._cache_info = label("", "faint")
        clear = button("Vider le cache", "trash")
        clear.clicked.connect(self._clear_cache)
        cache_row = QHBoxLayout()
        cache_texts = QVBoxLayout()
        cache_texts.setSpacing(2)
        cache_texts.addWidget(label("Cache du catalogue et des images", "heading"))
        cache_texts.addWidget(self._cache_info)
        cache_row.addLayout(cache_texts, 1)
        cache_row.addWidget(clear)
        storage.body.addLayout(cache_row)

        tools = Card(padding=20, spacing=12)
        tools.body.addWidget(label("OUTILS", "overline"))
        for tool in registry:
            tool_row = QHBoxLayout()
            tool_texts = QVBoxLayout()
            tool_texts.setSpacing(2)
            tool_texts.addWidget(label(tool.info.name, "heading"))
            tool_texts.addWidget(label(tool.info.description, "faint", wrap=True))
            tool_row.addLayout(tool_texts, 1)
            if tool.info.stage is ToolStage.PLANNED:
                tool_row.addWidget(Chip("En développement", "violet", "clock"))
            else:
                tool_row.addWidget(Chip(f"v{tool.info.version}", "neutral"))
            tools.body.addLayout(tool_row)

        about = Card(flat=True, padding=20, spacing=6)
        about.body.addWidget(label("À PROPOS", "overline"))
        about.body.addWidget(label(f"{APP_DISPLAY_NAME} {__version__}", "heading"))
        about.body.addWidget(
            label(
                "Connexion avec Discord : Syncron ne reçoit que ton identifiant, ton pseudo et ton avatar.",
                "muted",
                wrap=True,
            )
        )

        content = QWidget()
        content.setMaximumWidth(920)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)
        for card in (account, server, storage, tools, about):
            layout.addWidget(card)
        layout.addStretch(1)
        wrapper = QWidget()
        outer = QHBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(content, 1)
        self.setWidget(wrapper)
        self.refresh()

    def refresh(self) -> None:
        session = self._host.session
        user = session.user or {}
        self._account_name.setText(session.display_name)
        details = f"@{user['username']} · Discord {user['discord_id']}" if user.get("username") else "Non connecté"
        self._account_details.setText(details)
        self._role_chip.set_content(session.role.label, "accent" if session.role.rank else "neutral", "shield")
        online = "en ligne" if session.online else "hors ligne"
        revision = self._host.catalog.revision
        self._server_status.set_content(
            f"{online} · catalogue révision {revision if revision >= 0 else '—'}",
            "success" if session.online else "warning",
            "check" if session.online else "wifi-off",
        )
        self._cache_info.setText(f"{_folder_size(self._host.app_paths.cache_dir) // 1024} Ko")

    def _apply_server(self) -> None:
        url = self._server_url.text().strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            self._host.notify("Adresse invalide : elle doit commencer par https://", NotifyLevel.ERROR)
            return
        if url == self._host.api.base_url:
            return
        self._settings.set(SERVER_URL_KEY, url)
        self._settings.save()
        self._host.notify("Nouvelle adresse enregistrée : reconnexion…", NotifyLevel.INFO)
        self.logoutRequested.emit()

    def _clear_cache(self) -> None:
        self._host.catalog.clear_cache()
        self.refresh()
        self._host.notify("Cache vidé : il sera reconstruit à la prochaine synchronisation.", NotifyLevel.SUCCESS)

    @staticmethod
    def _path_row(title: str, path: Path) -> QHBoxLayout:
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(title, "heading"))
        location = label(str(path), "faint")
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        texts.addWidget(location)
        open_button = button("Ouvrir", "folder")

        def open_folder() -> None:
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

        open_button.clicked.connect(open_folder)
        row = QHBoxLayout()
        row.addLayout(texts, 1)
        row.addWidget(open_button)
        return row


def _folder_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
