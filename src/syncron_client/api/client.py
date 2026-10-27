"""Client HTTP de l'API Syncron (synchrone : toujours appelé depuis un thread de travail).

Gère les jetons : l'accès expiré est renouvelé automatiquement avec le jeton de
rafraîchissement (une seule fois, sous verrou), puis la requête est rejouée.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from syncron_client.api.errors import ApiError, Issue, NetworkError, SessionExpired

TIMEOUT = httpx.Timeout(15.0, connect=6.0)
TokensChanged = Callable[[str | None], None]


@dataclass(frozen=True, slots=True)
class CatalogResponse:
    document: dict[str, Any] | None
    etag: str | None
    not_modified: bool


class ApiClient:
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=TIMEOUT, transport=transport, follow_redirects=False)
        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self.on_refresh_token_changed: TokensChanged | None = None

    # -- jetons --------------------------------------------------------------------

    @property
    def has_session(self) -> bool:
        return bool(self._refresh_token)

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    def set_tokens(self, access_token: str | None, refresh_token: str | None) -> None:
        with self._lock:
            self._access_token = access_token
            self._refresh_token = refresh_token
        if self.on_refresh_token_changed is not None:
            self.on_refresh_token_changed(refresh_token)

    def _apply_token_pair(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.set_tokens(payload["access_token"], payload["refresh_token"])
        return payload["user"]

    # -- authentification ------------------------------------------------------------

    def meta(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/meta", auth=False).json()

    def exchange_login_code(self, code: str, verifier: str) -> dict[str, Any]:
        response = self._request(
            "POST", "/api/v1/auth/token", json={"code": code, "code_verifier": verifier}, auth=False
        )
        return self._apply_token_pair(response.json())

    def dev_login(self, username: str, role: str = "player") -> dict[str, Any]:
        response = self._request(
            "POST", "/api/v1/auth/dev-login", json={"username": username, "role": role}, auth=False
        )
        return self._apply_token_pair(response.json())

    def resume(self, refresh_token: str) -> dict[str, Any]:
        """Reprend une session enregistrée : renouvelle les jetons, retourne l'utilisateur."""
        with self._lock:
            self._refresh_token = refresh_token
        self._refresh()
        return self.me()

    def me(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/auth/me").json()

    def logout(self) -> None:
        token = self._refresh_token
        self.set_tokens(None, None)
        if token:
            try:
                self._request("POST", "/api/v1/auth/logout", json={"refresh_token": token}, auth=False)
            except ApiError:
                return

    def login_start_url(self, redirect_uri: str, state: str, challenge: str) -> str:
        query = httpx.QueryParams(
            {"redirect_uri": redirect_uri, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
        )
        return f"{self.base_url}/api/v1/auth/discord/start?{query}"

    # -- catalogue ---------------------------------------------------------------------

    def catalog(self, etag: str | None = None) -> CatalogResponse:
        headers = {"If-None-Match": etag} if etag else {}
        response = self._request("GET", "/api/v1/catalog", headers=headers, expected=(200, 304))
        if response.status_code == 304:
            return CatalogResponse(None, etag, True)
        return CatalogResponse(response.json(), response.headers.get("ETag"), False)

    def download(self, url: str) -> bytes:
        return self._request("GET", url, auth=False).content

    # -- administration ------------------------------------------------------------------

    def dashboard(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/admin/dashboard").json()

    def put_entity(self, section: str, entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/api/v1/admin/{section}/{entity_id}", json=payload).json()

    def delete_entity(self, section: str, entity_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/api/v1/admin/{section}/{entity_id}").json()

    def put_image(self, section: str, entity_id: str, path: Path) -> dict[str, Any]:
        with path.open("rb") as handle:
            files = {"file": (path.name, handle.read(), "application/octet-stream")}
        return self._request("PUT", f"/api/v1/admin/{section}/{entity_id}/image", files=files).json()

    def delete_image(self, section: str, entity_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/api/v1/admin/{section}/{entity_id}/image").json()

    def export_catalog(self) -> bytes:
        return self._request("GET", "/api/v1/admin/export").content

    def import_catalog(self, document: dict[str, Any], mode: str, dry_run: bool) -> dict[str, Any]:
        params = {"mode": mode, "dry_run": "true" if dry_run else "false"}
        return self._request("POST", "/api/v1/admin/import", params=params, json=document).json()

    def audit(self, limit: int = 50, before: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            params["before"] = before
        return self._request("GET", "/api/v1/admin/audit", params=params).json()

    def users(self, query: str = "") -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/admin/users", params={"q": query}).json()

    def patch_user(self, user_id: str, **changes: Any) -> dict[str, Any]:
        return self._request("PATCH", f"/api/v1/admin/users/{user_id}", json=changes).json()

    # -- transport -------------------------------------------------------------------------

    def _request(
        self, method: str, url: str, auth: bool = True, expected: tuple[int, ...] = (200, 204), **kwargs: Any
    ) -> httpx.Response:
        response = self._send(method, url, auth, **kwargs)
        if response.status_code == 401 and auth and self._refresh_token:
            self._refresh()
            response = self._send(method, url, auth, **kwargs)
        if response.status_code == 401 and auth:
            raise SessionExpired("Session expirée : reconnecte-toi.", 401)
        if response.status_code not in expected:
            raise _error_from(response)
        return response

    def _send(self, method: str, url: str, auth: bool, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if auth and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        try:
            return self._http.request(method, url, headers=headers, **kwargs)
        except httpx.TransportError as exc:
            raise NetworkError(f"Serveur injoignable ({self.base_url}).", 0) from exc

    def _refresh(self) -> None:
        with self._lock:
            token = self._refresh_token
        if not token:
            raise SessionExpired("Connexion requise.", 401)
        response = self._send("POST", "/api/v1/auth/refresh", auth=False, json={"refresh_token": token})
        if response.status_code in (400, 401, 403):
            self.set_tokens(None, None)
            raise SessionExpired("Session expirée : reconnecte-toi.", response.status_code)
        if response.status_code != 200:
            raise _error_from(response)
        self._apply_token_pair(response.json())

    def close(self) -> None:
        self._http.close()


def _error_from(response: httpx.Response) -> ApiError:
    message = f"Erreur du serveur ({response.status_code})."
    issues: list[Issue] = []
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            message = detail
        elif isinstance(detail, list) and detail:
            message = "Données refusées : " + "; ".join(
                f"{'.'.join(str(p) for p in entry.get('loc', [])[1:])} — {entry.get('msg', '')}" for entry in detail
            )
        for raw in payload.get("issues", []) or []:
            issues.append(
                Issue(
                    raw.get("severity", "error"), raw.get("message", ""), raw.get("entity_id"), raw.get("section", "")
                )
            )
    return ApiError(message, response.status_code, issues)
