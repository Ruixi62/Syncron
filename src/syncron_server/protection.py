"""Protections au niveau HTTP, indépendantes du reverse proxy.

- Limite de débit par adresse IP sur la connexion (`/api/v1/auth/…`) : freine
  les essais en rafale de codes ou de jetons. Compteur en mémoire, par processus.
- Taille maximale du corps des requêtes : refuse les envois démesurés avant
  qu'ils n'atteignent l'application (Caddy applique aussi sa propre limite).
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
App = Callable[[Scope, Receive, Send], Awaitable[None]]

AUTH_PREFIX = "/api/v1/auth/"
WINDOW_SECONDS = 60.0
MAX_TRACKED_CLIENTS = 10_000


async def _reject(send: Send, status: int, detail: str, headers: list[tuple[bytes, bytes]] = ()) -> None:
    body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *headers],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AuthRateLimit:
    """`limit` requêtes par minute et par adresse sur la connexion (0 = désactivé)."""

    def __init__(self, app: App, limit: Callable[[], int], clock: Callable[[], float] = time.monotonic) -> None:
        self.app = app
        self._limit = limit
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self._limit()
        if scope["type"] != "http" or limit <= 0 or not scope["path"].startswith(AUTH_PREFIX):
            await self.app(scope, receive, send)
            return
        client = (scope.get("client") or ("inconnu", 0))[0]
        now = self._clock()
        hits = self._hits.setdefault(client, deque())
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= limit:
            retry = max(1, int(WINDOW_SECONDS - (now - hits[0])) + 1)
            await _reject(
                send,
                429,
                "Trop de tentatives de connexion : réessaie dans une minute.",
                [(b"retry-after", str(retry).encode())],
            )
            return
        hits.append(now)
        if len(self._hits) > MAX_TRACKED_CLIENTS:
            self._forget_idle(now)
        await self.app(scope, receive, send)

    def _forget_idle(self, now: float) -> None:
        for key in [key for key, hits in self._hits.items() if not hits or now - hits[-1] > WINDOW_SECONDS]:
            del self._hits[key]


class BodySizeLimit:
    """Refuse (413) un corps plus gros que `limit` octets, annoncé ou réellement envoyé."""

    def __init__(self, app: App, limit: Callable[[], int]) -> None:
        self.app = app
        self._limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit()
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _reject(send, 413, f"Requête trop volumineuse ({limit // (1024 * 1024)} Mo au plus).")
            return
        received = 0
        started = False

        async def guarded_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge
            return message

        async def tracking_send(message: dict[str, Any]) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, guarded_receive, tracking_send)
        except _TooLarge:
            if not started:
                await _reject(send, 413, f"Requête trop volumineuse ({limit // (1024 * 1024)} Mo au plus).")


class _TooLarge(Exception):
    pass
