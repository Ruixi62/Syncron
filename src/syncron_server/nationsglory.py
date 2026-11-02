"""Client de l'API publique NationsGlory (https://publicapi.nationsglory.fr).

Préparé pour exploiter les données du serveur dans Syncron (alertes, pays, notations…) :

- la clé reste sur le serveur Syncron, jamais envoyée au client ;
- chaque route est construite à partir de paramètres vérifiés (pas de chemin libre) ;
- réponses JSON uniquement, 2 Mo au plus, sans suivre de redirection ;
- cache en mémoire par adresse, deux appels simultanés au plus ;
- erreurs traduites en messages clairs.

Routes documentées (https://nationsglory.readme.io) : nombre de joueurs, pays, liste des pays,
notations, MMR, HDV, planning, utilisateur. Le nom de l'en-tête d'authentification n'y est pas
précisé : il se règle avec SYNCRON_NG_API_AUTH_HEADER et SYNCRON_NG_API_AUTH_SCHEME.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from syncron_core.errors import AppError

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CONCURRENT = 2


class NationsGloryError(AppError):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class Request:
    kind: str
    path: str
    params: dict[str, str | int] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return self.path + (f"?{urlencode(self.params)}" if self.params else "")

    @property
    def target(self) -> str:
        """Ce qui est demandé, pour l'historique : « blue/corse », « MisterSand »…"""
        return self.url.removeprefix("/")[:160]


def _segment(value: str) -> str:
    return quote(value, safe="")


def build_request(
    kind: str,
    server: str = "",
    country: str = "",
    username: str = "",
    week: int | None = None,
    month: int | None = None,
    year: int | None = None,
) -> Request:
    """Adresse d'une route connue. Les valeurs sont déjà validées par le schéma d'entrée ;
    elles sont encodées une seconde fois ici, par prudence."""

    def need(name: str, value: Any) -> None:
        if value in ("", None):
            raise NationsGloryError(f"Paramètre manquant pour « {kind} » : {name}.", 422)

    if kind == "playercount":
        return Request(kind, "/playercount")
    if kind == "country":
        need("server", server)
        need("country", country)
        return Request(kind, f"/country/{_segment(server)}/{_segment(country)}")
    if kind == "countries":
        need("server", server)
        return Request(kind, f"/country/list/{_segment(server)}")
    if kind == "notations":
        params: dict[str, str | int] = {}
        if week is not None:
            params["week"] = week
        if country:
            params["country"] = country
        if server:
            params["server"] = server
        return Request(kind, "/notations", params)
    if kind == "mmr":
        return Request(kind, "/mmr", {"server": server} if server else {})
    if kind == "hdv":
        need("server", server)
        return Request(kind, f"/hdv/{_segment(server)}")
    if kind == "planning":
        need("month", month)
        need("year", year)
        return Request(kind, "/planning", {"server": server or "all", "month": month, "year": year})
    if kind == "user":
        need("username", username)
        return Request(kind, f"/user/{_segment(username)}")
    raise NationsGloryError(f"Route inconnue : {kind}.", 422)


@dataclass(frozen=True, slots=True)
class Fetched:
    request: Request
    payload: Any
    size_bytes: int
    duration_ms: int
    from_cache: bool = False


class NationsGloryClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
        timeout: float = 10.0,
        cache_seconds: int = 300,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._key = api_key
        self._header = auth_header
        self._scheme = auth_scheme
        self._timeout = timeout
        self._cache_seconds = cache_seconds
        self._transport = transport
        self._clock = clock
        self._cache: dict[str, tuple[float, Fetched]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._slots = asyncio.Semaphore(MAX_CONCURRENT)

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "Syncron (outil interne d'un pays)"}
        if self._key:
            headers[self._header] = f"{self._scheme} {self._key}".strip() if self._scheme else self._key
        return headers

    async def fetch(self, request: Request, refresh: bool = False) -> Fetched:
        if not self.configured:
            raise NationsGloryError(
                "API NationsGlory non configurée : renseigne SYNCRON_NG_API_KEY sur le serveur.", 503
            )
        key = request.url
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._cache.get(key)
            if cached and not refresh and cached[0] > self._clock():
                fetched = cached[1]
                return Fetched(fetched.request, fetched.payload, fetched.size_bytes, 0, from_cache=True)
            fetched = await self._call(request)
            if self._cache_seconds:
                self._cache[key] = (self._clock() + self._cache_seconds, fetched)
            return fetched

    async def _call(self, request: Request) -> Fetched:
        started = time.perf_counter()
        async with (
            self._slots,
            httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self._timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as http,
        ):
            try:
                async with http.stream("GET", request.url, headers=self._headers()) as response:
                    body = await _read_limited(response)
                    status = response.status_code
            except httpx.TimeoutException as exc:
                raise NationsGloryError("L'API NationsGlory ne répond pas (délai dépassé).", 504) from exc
            except httpx.HTTPError as exc:
                raise NationsGloryError("API NationsGlory injoignable.", 502) from exc
        duration = round((time.perf_counter() - started) * 1000)
        if status in (401, 403):
            raise NationsGloryError("Clé API NationsGlory refusée.", status)
        if status == 404:
            raise NationsGloryError("Introuvable sur NationsGlory (serveur, pays ou joueur inconnu).", 404)
        if status == 429:
            raise NationsGloryError("Trop d'appels à l'API NationsGlory : réessaie plus tard.", 429)
        if 300 <= status < 400:
            raise NationsGloryError("L'API NationsGlory a répondu par une redirection, ignorée.", 502)
        if status >= 400:
            raise NationsGloryError(f"L'API NationsGlory a répondu {status}.", 502)
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise NationsGloryError("Réponse de l'API NationsGlory illisible (JSON attendu).", 502) from exc
        return Fetched(request, payload, len(body), duration)


async def _read_limited(response: httpx.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
        raise NationsGloryError("Réponse de l'API NationsGlory trop volumineuse.", 502)
    chunks, size = [], 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise NationsGloryError("Réponse de l'API NationsGlory trop volumineuse.", 502)
        chunks.append(chunk)
    return b"".join(chunks)
