"""Démarrage du client : connexion, synchronisation, ouverture de la plateforme, déconnexion.

lancement ─▶ écran de connexion
             ├─ session enregistrée ? ─▶ reprise silencieuse ─▶ plateforme
             ├─ « Se connecter avec Discord » ─▶ navigateur ─▶ plateforme
             └─ serveur injoignable + catalogue en cache ─▶ plateforme hors ligne
déconnexion / session expirée ─▶ fermeture de la plateforme ─▶ écran de connexion
"""

from __future__ import annotations

import contextlib
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QLocale, QObject
from PySide6.QtWidgets import QApplication

from syncron_client import updater
from syncron_client.api.client import ApiClient
from syncron_client.api.discord_login import DiscordLoginFlow, LoginCancelled
from syncron_client.api.errors import NetworkError
from syncron_client.api.token_store import TokenStore
from syncron_client.catalog_store import CatalogStore
from syncron_client.config import SERVER_URL_KEY, is_safe_server_url, resolve_server_url, version_tuple
from syncron_client.notifications import NotificationCenter
from syncron_client.paths import AppPaths
from syncron_client.platform.registry import ToolRegistry
from syncron_client.platform.tool import NotifyLevel, Tool
from syncron_client.session import Session
from syncron_client.settings import JsonSettingsStore
from syncron_client.shell.host import ShellHost
from syncron_client.shell.login_window import LoginWindow
from syncron_client.shell.window import ShellWindow
from syncron_client.tasks import TaskRunner
from syncron_client.tools import builtin_tools
from syncron_client.ui.brand import app_icon
from syncron_client.ui.theme import apply_theme
from syncron_core import APP_DISPLAY_NAME, APP_NAME, __version__


def configure_application(app: QApplication) -> None:
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.France))
    apply_theme(app)
    app.setWindowIcon(app_icon())


@dataclass(slots=True)
class Shell:
    registry: ToolRegistry
    host: ShellHost
    window: ShellWindow


class Launcher(QObject):
    """Orchestre la vie de l'application. Toutes les dépendances sont injectables (tests)."""

    def __init__(
        self,
        paths: AppPaths,
        runner: TaskRunner | None = None,
        open_browser: Callable[[str], Any] = webbrowser.open,
        tools_factory: Callable[[], Sequence[Tool]] = builtin_tools,
        use_keyring: bool = True,
        api_transport=None,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.runner = runner or TaskRunner()
        self._open_browser = open_browser
        self._tools_factory = tools_factory
        self._use_keyring = use_keyring
        self._transport = api_transport
        self.settings = JsonSettingsStore(paths.settings_file)
        self.session = Session()
        self.session.expired.connect(self._on_session_expired)
        self.shell: Shell | None = None
        self._flow: DiscordLoginFlow | None = None
        self._minimum = "0"
        self._connect(resolve_server_url(self.settings))
        self.login = LoginWindow(self.api.base_url)
        self.login.discordRequested.connect(self.login_with_discord)
        self.login.cancelRequested.connect(self._cancel_login)
        self.login.offlineRequested.connect(self.open_offline)
        self.login.devLoginRequested.connect(self.dev_login)
        self.login.serverChangeRequested.connect(self.change_server)

    def _connect(self, server_url: str) -> None:
        self.api = ApiClient(server_url, transport=self._transport)
        self.tokens = TokenStore(server_url, self.paths.session_fallback, self._use_keyring)
        self.api.on_refresh_token_changed = self.tokens.save
        self.catalog = CatalogStore(self.api, self.paths.catalog_cache, self.paths.media_cache, self.runner)
        self.catalog.load_cache()

    # -- démarrage ---------------------------------------------------------------------

    def start(self) -> None:
        self.login.show()
        self.login.set_offline_available(False)
        self.login.set_busy("Connexion au serveur…")
        self.runner.run(self.api.meta, self._on_meta, self._on_meta_failed)

    def _on_meta(self, meta: dict) -> None:
        self.session.set_meta(meta)
        self.login.set_nation(self.session.nation_name)
        self.login.set_dev_login(bool(meta.get("dev_login")))
        self._minimum = str(meta.get("min_client_version", "0"))
        self.login.set_busy("Recherche de mises à jour…")
        self.runner.run(updater.check_for_update, self._on_update_checked, lambda _error: self._after_update_check())

    def _on_update_checked(self, info: updater.UpdateInfo | None) -> None:
        if info is None:
            self._after_update_check()
            return
        self.login.set_busy(f"Téléchargement de la version {info.version}…")
        self.runner.run(
            lambda: updater.download_and_stage(info),
            self._install_update,
            self._on_update_failed,
        )

    def _install_update(self, workdir) -> None:
        self.login.set_busy("Installation de la mise à jour…")
        updater.apply_and_restart(workdir)
        QApplication.quit()

    def _on_update_failed(self, error: Exception) -> None:
        self.login.show_error(f"Mise à jour impossible : {error}")
        self._after_update_check()

    def _after_update_check(self) -> None:
        if version_tuple(__version__) < version_tuple(self._minimum):
            self.login.show_update_required(self._minimum)
            self.login.set_idle()
            return
        stored = self.tokens.load()
        if not stored:
            self.login.set_idle()
            return
        self.login.set_busy("Reprise de ta session…")
        self.runner.run(lambda: self.api.resume(stored), self._signed_in, self._on_resume_failed)

    def _on_meta_failed(self, error: Exception) -> None:
        self.login.show_error(f"{error}\nVérifie ta connexion Internet ou l'adresse du serveur.")
        self.login.set_offline_available(self.catalog.loaded)

    def _on_resume_failed(self, error: Exception) -> None:
        if isinstance(error, NetworkError):
            self._on_meta_failed(error)
        else:
            self.tokens.save(None)
            self.login.set_idle("Ta session a expiré : reconnecte-toi.")

    # -- connexion ---------------------------------------------------------------------

    def login_with_discord(self) -> None:
        self._flow = DiscordLoginFlow(self.api, self._open_browser)
        flow = self._flow
        self.login.set_busy("Termine la connexion dans ton navigateur…", cancellable=True)
        self.runner.run(flow.run, self._signed_in, self._on_login_failed)

    def _cancel_login(self) -> None:
        if self._flow is not None:
            self._flow.cancel()

    def dev_login(self, username: str, role: str) -> None:
        if len(username) < 2:
            self.login.show_error("Pseudo trop court.")
            return
        self.login.set_busy("Connexion…")
        self.runner.run(lambda: self.api.dev_login(username, role), self._signed_in, self._on_login_failed)

    def _on_login_failed(self, error: Exception) -> None:
        self._flow = None
        if isinstance(error, LoginCancelled):
            self.login.set_idle(str(error))
        else:
            self.login.show_error(str(error))

    def _signed_in(self, user: dict) -> None:
        self._flow = None
        self.session.set_user(user)
        self.session.set_online(True)
        self.login.set_busy("Synchronisation des données…")

        def synced(_changed: bool) -> None:
            if not self.catalog.loaded:
                self.login.show_error("Le catalogue n'a pas pu être téléchargé. Réessaie dans un instant.")
                return
            self.open_shell()

        self.catalog.sync(synced)

    def open_offline(self) -> None:
        self.session.set_user(None)
        self.session.set_online(False)
        self.open_shell()

    # -- plateforme ----------------------------------------------------------------------

    def open_shell(self) -> None:
        registry = ToolRegistry()
        notifications = NotificationCenter(self.api, self.runner, self.session, self.settings)
        host = ShellHost(self.paths, self.api, self.session, self.runner, self.catalog, notifications, registry)
        tools = [tool for tool in self._tools_factory() if self.session.has_role(tool.info.min_role)]
        for tool in tools:
            registry.register(tool)
        for tool in tools:
            tool.setup(host)
        window = ShellWindow(registry, host, self.settings)
        window.logoutRequested.connect(self.logout)
        self.catalog.syncFailed.connect(lambda error: host.handle_error(error, "Synchronisation"))
        self.shell = Shell(registry, host, window)
        self.login.hide()
        window.show()
        if self.session.online:
            notifications.start()
        else:
            host.notify("Mode hors ligne : dernières données reçues, en lecture seule.", NotifyLevel.WARNING)

    def logout(self, message: str = "") -> None:
        api = self.api
        self.runner.run(api.logout, None, lambda _error: None)
        self.tokens.save(None)
        self.session.set_user(None)
        self._close_shell()
        self._reconnect_if_server_changed()
        self.login.set_idle(message or "Tu es déconnecté.")
        self.login.show()

    def _on_session_expired(self, message: str) -> None:
        self.tokens.save(None)
        self.session.set_user(None)
        self._close_shell()
        self.login.set_idle(message or "Session expirée : reconnecte-toi.")
        self.login.show()

    def _close_shell(self) -> None:
        if self.shell is not None:
            self.shell.host.notifications.stop()
            with contextlib.suppress(RuntimeError, TypeError):
                self.catalog.syncFailed.disconnect()
            self.shell.window.close()
            self.shell.window.deleteLater()
            self.shell = None

    def change_server(self, url: str) -> None:
        if not is_safe_server_url(url):
            self.login.show_error("Adresse refusée : elle doit commencer par https:// (connexion chiffrée).")
            return
        self.settings.set(SERVER_URL_KEY, url)
        self.settings.save()
        self._reconnect_if_server_changed()
        self.start()

    def _reconnect_if_server_changed(self) -> None:
        url = resolve_server_url(self.settings)
        if url != self.api.base_url:
            self.api.close()
            self._connect(url)
            self.login.set_server(url)
