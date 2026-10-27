"""Connexion Discord depuis l'application de bureau.

1. un mini-serveur HTTP écoute sur 127.0.0.1 (port libre choisi par le système)
2. le navigateur s'ouvre sur l'API Syncron, qui redirige vers Discord
3. après accord, l'API renvoie le navigateur sur 127.0.0.1/callback avec un code à usage unique
4. le client échange ce code + son code_verifier (PKCE) contre ses jetons

Le secret Discord reste sur le serveur ; le code intercepté par un tiers est inutilisable sans le verifier.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from syncron_client.api.client import ApiClient
from syncron_client.api.errors import ApiError

CALLBACK_PATH = "/callback"
DEFAULT_TIMEOUT = 300.0
ERROR_MESSAGES = {
    "access_denied": "Connexion annulée sur Discord.",
    "not_in_guild": "Ce compte Discord n'est pas membre du serveur requis par Syncron.",
    "banned": "Ce compte est suspendu.",
    "discord_unavailable": "Discord n'a pas répondu. Réessaie dans un instant.",
}
PAGE = """<!doctype html><html lang="fr"><meta charset="utf-8"><title>Syncron</title>
<body style="background:#0b0e14;color:#e8ebf2;font-family:system-ui,sans-serif;display:grid;place-items:center;
height:100vh;margin:0"><div style="text-align:center"><h1 style="color:{color}">{title}</h1>
<p style="color:#8d96aa">{text}</p></div></body></html>"""


class LoginCancelled(ApiError):
    pass


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass
class _Result:
    code: str | None = None
    state: str | None = None
    error: str | None = None


class DiscordLoginFlow:
    """À exécuter dans un thread de travail : `run()` bloque jusqu'au retour du navigateur."""

    def __init__(
        self,
        api: ApiClient,
        open_browser: Callable[[str], object] = webbrowser.open,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api = api
        self._open_browser = open_browser
        self._timeout = timeout
        self._received = threading.Event()
        self._result = _Result()
        self._server: HTTPServer | None = None

    def run(self) -> dict:
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        self._server = HTTPServer(("127.0.0.1", 0), self._handler())
        port = self._server.server_address[1]
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()
        try:
            redirect_uri = f"http://127.0.0.1:{port}{CALLBACK_PATH}"
            self._open_browser(self._api.login_start_url(redirect_uri, state, challenge))
            if not self._received.wait(self._timeout):
                raise LoginCancelled("Connexion abandonnée (délai dépassé).")
        finally:
            self._server.shutdown()
            self._server.server_close()
        result = self._result
        if result.error == "cancelled":
            raise LoginCancelled("Connexion annulée.")
        if result.state != state:
            raise ApiError("Réponse de connexion invalide (état différent) : recommence.")
        if result.error or not result.code:
            raise ApiError(ERROR_MESSAGES.get(result.error or "", f"Connexion refusée ({result.error})."))
        return self._api.exchange_login_code(result.code, verifier)

    def cancel(self) -> None:
        self._result = _Result(error="cancelled")
        self._received.set()

    def _handler(self):
        flow = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                if parts.path != CALLBACK_PATH:
                    self.send_error(404)
                    return
                query = {key: values[0] for key, values in parse_qs(parts.query).items()}
                if not flow._received.is_set():
                    flow._result = _Result(query.get("code"), query.get("state"), query.get("error"))
                    flow._received.set()
                ok = "code" in query
                body = PAGE.format(
                    color="#3fcfb8" if ok else "#f2555a",
                    title="Connexion réussie" if ok else "Connexion refusée",
                    text="Tu peux fermer cet onglet et revenir sur Syncron."
                    if ok
                    else ERROR_MESSAGES.get(query.get("error", ""), "Reviens sur Syncron pour réessayer."),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args) -> None:
                return

        return Handler
