"""Données de la carte NationsGlory (https://iris.nationsglory.fr), récupérées par le serveur.

Un seul collecteur pour tout le pays, au lieu de chaque logiciel :
- météo et état du jeu toutes les minutes (alertes : météorite, faille, volcan…) ;
- territoires, atlas, frontières, régions toutes les 30 minutes ;
- membres de chaque pays deux fois par jour, avec une pause entre deux pays.

Chaque donnée est gardée en base (`iris_snapshots`, la dernière réponse) ; si le site ne
répond pas, l'ancienne est conservée. Les événements météo sont suivis dans `iris_events`
(début, dernière vue, fin). Plusieurs processus de l'API peuvent tourner : un verrou
PostgreSQL garantit qu'un seul interroge Iris à la fois.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server.db import Database
from syncron_server.models import IrisEvent, IrisSnapshot, utcnow

log = logging.getLogger("syncron.iris")

MAX_RESPONSE_BYTES = 40 * 1024 * 1024
MAP_KINDS = ("territories", "atlas", "frontiers", "regions")
JOBS = ("weather", "map", "members")
LOCK_KEY = 0x5359_4E49  # « SYNI » : verrous du collecteur (un par tâche)
TICK_SECONDS = 10
EVENT_LABELS = {"meteor": "Météorite", "rift": "Faille", "volcano": "Volcan", "other": "Événement"}
KEYWORDS = {
    "meteor": ("meteor", "asteroid", "asteroide", "comet", "comete"),
    "rift": ("rift", "faille", "fissure", "crack", "breach", "brèche", "breche"),
    "volcano": ("volcan", "volcano", "eruption", "lava", "lave", "magma"),
}
VOLATILE = re.compile(
    r"(remaining|progress|percent|countdown|timeleft|time_left|elapsed|health|ttl|expire|until)", re.I
)
START_KEYS = (
    "start",
    "startedAt",
    "started_at",
    "startTime",
    "start_time",
    "since",
    "createdAt",
    "created_at",
    "spawn",
)


class IrisError(Exception):
    pass


class IrisClient:
    def __init__(
        self,
        base_url: str,
        world: str = "earth",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.world = world
        self._timeout = timeout
        self._transport = transport

    def path(self, kind: str) -> str:
        return "/api/state" if kind == "state" else f"/api/{kind}/{self.world}"

    async def get(self, path: str) -> tuple[Any, int]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Syncron (outil interne d'un pays NationsGlory)",
            "Referer": self.base_url + "/",
        }
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self._timeout, follow_redirects=False, transport=self._transport
        ) as http:
            try:
                async with http.stream("GET", path, headers=headers) as response:
                    if response.status_code != 200:
                        raise IrisError(f"Iris a répondu {response.status_code} sur {path}.")
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise IrisError(f"Réponse trop volumineuse sur {path}.")
                        chunks.append(chunk)
            except httpx.HTTPError as exc:
                raise IrisError(f"Iris injoignable ({exc.__class__.__name__}) sur {path}.") from exc
        body = b"".join(chunks)
        try:
            return json.loads(body), len(body)
        except ValueError as exc:
            raise IrisError(f"Réponse illisible (JSON attendu) sur {path}.") from exc


# -- événements météo -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WeatherEvent:
    key: str
    kind: str
    title: str
    x: int | None
    z: int | None
    raw: Any


def _plain(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return folded.lower()


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for key, item in value.items() for s in (_strings(key) + _strings(item))]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


def _kind(raw: Any) -> str:
    words = _plain(" ".join(_strings(raw)))
    for kind, keywords in KEYWORDS.items():
        if any(_plain(word) in words for word in keywords):
            return kind
    return "other"


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(value)
    if isinstance(value, str):
        try:
            return round(float(value))
        except ValueError:
            return None
    return None


def _coordinates(raw: Any) -> tuple[int | None, int | None]:
    if not isinstance(raw, dict):
        return None, None
    x, z = _number(raw.get("x")), _number(raw.get("z"))
    if x is not None and z is not None:
        return x, z
    for key in ("pos", "position", "location", "loc", "center", "coords", "coordinates", "block"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            found = _coordinates(nested)
            if found != (None, None):
                return found
        if isinstance(nested, list) and len(nested) in (2, 3) and all(_number(v) is not None for v in nested):
            return _number(nested[0]), _number(nested[-1])
    return None, None


def _stable(raw: Any) -> Any:
    """L'événement sans ses champs qui changent à chaque minute (temps restant, progression…)."""
    if isinstance(raw, dict):
        return {k: _stable(v) for k, v in sorted(raw.items()) if not VOLATILE.search(str(k))}
    if isinstance(raw, list):
        return [_stable(item) for item in raw]
    return raw


def _title(raw: Any, kind: str) -> str:
    label = EVENT_LABELS[kind]
    if isinstance(raw, dict):
        for key in ("name", "title", "label", "type", "kind", "event"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                name = value.strip().replace("_", " ")
                return name[:1].upper() + name[1:] if kind == "other" else f"{label} : {name}"[:160]
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:160]
    return label


def normalize_events(payload: Any) -> list[WeatherEvent]:
    """Événements de `/api/weather/<monde>` sous une forme commune.

    Le format exact d'Iris n'est pas documenté : le type est reconnu d'après les mots de
    l'événement (meteor, faille, volcan…), la position d'après x / z (ou pos, location…),
    et l'identité d'après son id, sinon sa position et son heure de début."""
    events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        return []
    result = []
    for raw in events:
        kind = _kind(raw)
        x, z = _coordinates(raw)
        identity: Any
        if isinstance(raw, dict) and raw.get("id") not in (None, ""):
            identity = ["id", raw["id"]]
        elif isinstance(raw, dict) and (x is not None or any(raw.get(k) for k in START_KEYS)):
            identity = [kind, x, z, [raw.get(k) for k in START_KEYS]]
        else:
            identity = _stable(raw)
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()[:40]
        result.append(WeatherEvent(key, kind, _title(raw, kind), x, z, raw))
    return result


# -- synchronisation ------------------------------------------------------------------------


async def _store(session: AsyncSession, kind: str, payload: Any, size: int) -> None:
    row = await session.get(IrisSnapshot, kind, with_for_update=True)
    if row is None:
        row = IrisSnapshot(kind=kind)
        session.add(row)
    row.payload = payload
    row.size_bytes = size
    row.fetched_at = utcnow()
    row.attempted_at = utcnow()
    row.error = ""


async def _failed(session: AsyncSession, kind: str, error: Exception) -> None:
    row = await session.get(IrisSnapshot, kind, with_for_update=True)
    if row is None:
        row = IrisSnapshot(kind=kind, size_bytes=0)
        session.add(row)
    row.attempted_at = utcnow()
    row.error = str(error)[:300]


async def track_events(session: AsyncSession, events: list[WeatherEvent]) -> list[IrisEvent]:
    """Met à jour le suivi : nouveaux événements, toujours là, terminés. Renvoie les nouveaux."""
    now = utcnow()
    seen = {event.key for event in events}
    open_rows = {
        row.key: row for row in (await session.execute(select(IrisEvent).where(IrisEvent.ended_at.is_(None)))).scalars()
    }
    created = []
    for event in events:
        row = open_rows.get(event.key)
        if row is None:
            row = (await session.execute(select(IrisEvent).where(IrisEvent.key == event.key))).scalar_one_or_none()
        if row is None:
            row = IrisEvent(
                key=event.key,
                kind=event.kind,
                title=event.title[:160],
                x=event.x,
                z=event.z,
                payload=event.raw,
                first_seen=now,
                last_seen=now,
            )
            session.add(row)
            created.append(row)
        else:
            row.last_seen = now
            row.ended_at = None
            row.payload = event.raw
    for key, row in open_rows.items():
        if key not in seen:
            row.ended_at = now
    return created


class IrisCollector:
    def __init__(
        self,
        database: Database,
        client: IrisClient,
        weather_seconds: int,
        map_minutes: int,
        members_hours: int,
        pause: float,
    ) -> None:
        self._db = database
        self.client = client
        self.intervals = {
            "weather": timedelta(seconds=weather_seconds),
            "map": timedelta(minutes=map_minutes),
            "members": timedelta(hours=members_hours),
        }
        self._pause = pause
        self._task: asyncio.Task | None = None
        self._jobs: dict[str, asyncio.Task] = {}

    # -- tâches ----------------------------------------------------------------------------

    async def weather(self) -> list[IrisEvent]:
        created: list[IrisEvent] = []
        async with self._db.sessions() as session:
            for kind in ("weather", "state"):
                try:
                    payload, size = await self.client.get(self.client.path(kind))
                except IrisError as exc:
                    await _failed(session, kind, exc)
                    continue
                await _store(session, kind, payload, size)
                if kind == "weather":
                    created = await track_events(session, normalize_events(payload))
            await session.commit()
        return created

    async def map(self) -> None:
        for kind in MAP_KINDS:
            try:
                payload, size = await self.client.get(self.client.path(kind))
            except IrisError as exc:
                async with self._db.sessions() as session:
                    await _failed(session, kind, exc)
                    await session.commit()
                continue
            async with self._db.sessions() as session:
                await _store(session, kind, payload, size)
                await session.commit()

    async def members(self) -> int:
        async with self._db.sessions() as session:
            territories = await session.get(IrisSnapshot, "territories")
            previous = await session.get(IrisSnapshot, "members")
            factions = ((territories.payload or {}) if territories else {}).get("factions", [])
            old = (previous.payload or {}) if previous else {}
            await session.commit()
        countries = [f for f in factions if isinstance(f, dict) and f.get("members") and f.get("id")]
        result: dict[str, Any] = {}
        for faction in countries:
            name = str(faction.get("name") or faction["id"])
            try:
                data, _size = await self.client.get(f"/api/countries/{_segment(str(faction['id']))}/members")
            except IrisError:
                data = None
            if isinstance(data, dict) and isinstance(data.get("members"), list):
                result[name] = {
                    "total": data.get("total", len(data["members"])),
                    "complete": data.get("complete", True),
                    "members": data["members"],
                }
            elif name in old:
                result[name] = old[name]
            await asyncio.sleep(self._pause)
        if not countries:
            return 0
        async with self._db.sessions() as session:
            if result:
                await _store(session, "members", result, len(json.dumps(result)))
            else:
                await _failed(session, "members", IrisError("Aucune liste de membres reçue."))
            await session.commit()
        return len(result)

    # -- planification ---------------------------------------------------------------------

    async def run(self, job: str, force: bool = False) -> bool:
        """Lance une tâche si elle est due (ou forcée) et si aucun autre processus ne la fait déjà."""
        async with self._db.engine.connect() as connection:
            key = LOCK_KEY + JOBS.index(job)
            locked = (await connection.execute(text("select pg_try_advisory_lock(:k)"), {"k": key})).scalar()
            if not locked:
                return False
            try:
                if not force and not await self._due(job):
                    return False
                if job == "weather":
                    await self.weather()
                elif job == "map":
                    await self.map()
                elif job == "members":
                    await self.members()
                return True
            finally:
                await connection.execute(text("select pg_advisory_unlock(:k)"), {"k": key})
                await connection.commit()

    async def _due(self, job: str) -> bool:
        kinds = {"weather": ("weather",), "map": MAP_KINDS, "members": ("members",)}[job]
        async with self._db.sessions() as session:
            rows = (await session.execute(select(IrisSnapshot).where(IrisSnapshot.kind.in_(kinds)))).scalars().all()
            await session.commit()
        if len(rows) < len(kinds):
            return True
        last = min(row.attempted_at for row in rows)
        return utcnow() - last >= self.intervals[job] * 0.95

    async def _guarded(self, job: str) -> None:
        try:
            await self.run(job)
        except Exception:  # le collecteur ne doit jamais arrêter l'API
            log.exception("Collecteur Iris : échec de la tâche %s", job)

    async def loop(self) -> None:
        """Chaque tâche tourne à part : la longue mise à jour des membres ne retarde pas la météo."""
        while True:
            for job in JOBS:
                running = self._jobs.get(job)
                if running is None or running.done():
                    self._jobs[job] = asyncio.create_task(self._guarded(job), name=f"iris-{job}")
            await asyncio.sleep(TICK_SECONDS)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.loop(), name="iris-collector")

    async def stop(self) -> None:
        tasks = [task for task in (self._task, *self._jobs.values()) if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._task = None
        self._jobs = {}


def _segment(value: str) -> str:
    return quote(value, safe="")
