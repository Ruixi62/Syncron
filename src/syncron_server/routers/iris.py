"""Iris : la carte NationsGlory gardée par le serveur, pour l'outil Recherche et les alertes.

Lecture (tout membre) :
- `/iris/map` : territoires, atlas, frontières, régions (change toutes les 30 minutes) ;
- `/iris/live` : heure et météo du jeu, événements en cours (change chaque minute) ;
- `/iris/members` : membres de chaque pays ;
- `/iris/events` : événements météo en cours et récents (alertes).
Les trois premières répondent 304 si le logiciel a déjà la même version (ETag).

Gestion (système « nationsglory ») : état de la collecte, relance d'une tâche.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server import audit
from syncron_server.deps import SessionDep, SettingsDep, UserDep, manager
from syncron_server.iris import MAP_KINDS, IrisCollector
from syncron_server.models import IRIS_KINDS, IrisEvent, IrisSnapshot, User, utcnow
from syncron_server.schemas import (
    IrisEventOut,
    IrisEventsOut,
    IrisKindOut,
    IrisRefreshIn,
    IrisRefreshOut,
    IrisStatusOut,
)
from syncron_server.systems import NATIONSGLORY

router = APIRouter(prefix="/api/v1/iris", tags=["Iris"])
admin_router = APIRouter(prefix="/api/v1/admin/iris", tags=["Iris (gestion)"])
IrisManager = Annotated[User, Depends(manager(NATIONSGLORY))]
RECENT_DAYS = 7
RECENT_LIMIT = 60
LIVE_KINDS = ("state", "weather")


def _collector(request: Request) -> IrisCollector:
    return request.app.state.iris


async def _snapshots(session: AsyncSession, kinds: tuple[str, ...]) -> dict[str, IrisSnapshot]:
    rows = (await session.execute(select(IrisSnapshot).where(IrisSnapshot.kind.in_(kinds)))).scalars()
    return {row.kind: row for row in rows}


def _etag(parts: list[str]) -> str:
    return '"' + hashlib.sha256("|".join(parts).encode()).hexdigest()[:32] + '"'


async def _bundle(
    request: Request, session: AsyncSession, kinds: tuple[str, ...], extra: dict | None = None
) -> Response:
    """Les dernières réponses d'Iris pour `kinds`, avec ETag (304 si le logiciel les a déjà).

    Le JSON assemblé est gardé en mémoire tant que rien ne change, pour ne pas relire
    plusieurs Mo en base à chaque demande."""
    stamps = (
        await session.execute(select(IrisSnapshot.kind, IrisSnapshot.fetched_at).where(IrisSnapshot.kind.in_(kinds)))
    ).all()
    extra_text = json.dumps(extra, sort_keys=True, default=str) if extra is not None else ""
    tag = _etag([f"{kind}={fetched}" for kind, fetched in sorted(stamps, key=lambda s: s[0])] + [extra_text])
    headers = {"ETag": tag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == tag:
        await session.commit()
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    cache: dict[tuple[str, ...], tuple[str, bytes]] = request.app.state.iris_cache
    cached = cache.get(kinds)
    if cached is not None and cached[0] == tag:
        await session.commit()
        return Response(cached[1], media_type="application/json", headers=headers)
    rows = await _snapshots(session, kinds)
    await session.commit()
    body = {
        "fetched": {kind: row.fetched_at.isoformat() if row.fetched_at else None for kind, row in rows.items()},
        **{kind: rows[kind].payload if kind in rows else None for kind in kinds},
        **(extra or {}),
    }
    content = json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    cache[kinds] = (tag, content)
    return Response(content, media_type="application/json", headers=headers)


def _event_out(row: IrisEvent) -> IrisEventOut:
    return IrisEventOut(
        id=row.id,
        kind=row.kind,
        title=row.title,
        x=row.x,
        z=row.z,
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        ended_at=row.ended_at,
        active=row.ended_at is None,
    )


async def _events(session: AsyncSession) -> list[IrisEvent]:
    since = utcnow() - timedelta(days=RECENT_DAYS)
    query = (
        select(IrisEvent)
        .where(or_(IrisEvent.ended_at.is_(None), IrisEvent.first_seen >= since))
        .order_by(IrisEvent.first_seen.desc())
        .limit(RECENT_LIMIT)
    )
    return list((await session.execute(query)).scalars())


def _check_enabled(request: Request) -> None:
    if not request.app.state.settings.iris_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La carte Iris est désactivée sur ce serveur.")


# -- lecture ------------------------------------------------------------------------------


@router.get("/map")
async def iris_map(request: Request, session: SessionDep, _user: UserDep) -> Response:
    """Territoires, atlas, frontières et régions."""
    _check_enabled(request)
    return await _bundle(request, session, MAP_KINDS)


@router.get("/live")
async def iris_live(request: Request, session: SessionDep, _user: UserDep) -> Response:
    """Heure et météo du jeu, avec les événements en cours."""
    _check_enabled(request)
    active = (await session.execute(select(IrisEvent).where(IrisEvent.ended_at.is_(None)))).scalars().all()
    events = [_event_out(row).model_dump(mode="json") for row in sorted(active, key=lambda r: r.id)]
    return await _bundle(request, session, LIVE_KINDS, {"events": events})


@router.get("/members")
async def iris_members(request: Request, session: SessionDep, _user: UserDep) -> Response:
    """Membres de chaque pays (nom, grade, chef)."""
    _check_enabled(request)
    return await _bundle(request, session, ("members",))


@router.get("/events", response_model=IrisEventsOut)
async def iris_events(request: Request, session: SessionDep, settings: SettingsDep, _user: UserDep) -> IrisEventsOut:
    """Événements météo en cours et des 7 derniers jours (météorites, failles, volcans…)."""
    rows = await _events(session)
    weather = await session.get(IrisSnapshot, "weather")
    await session.commit()
    return IrisEventsOut(
        enabled=settings.iris_enabled,
        checked_at=weather.attempted_at if weather else None,
        events=[_event_out(row) for row in rows],
    )


# -- gestion ------------------------------------------------------------------------------


@admin_router.get("", response_model=IrisStatusOut)
async def iris_status(session: SessionDep, settings: SettingsDep, _user: IrisManager) -> IrisStatusOut:
    rows = await _snapshots(session, IRIS_KINDS)
    total, active = (
        await session.execute(
            select(func.count(IrisEvent.id), func.count(IrisEvent.id).filter(IrisEvent.ended_at.is_(None)))
        )
    ).one()
    await session.commit()
    return IrisStatusOut(
        enabled=settings.iris_enabled,
        url=settings.iris_url,
        world=settings.iris_world,
        weather_seconds=settings.iris_weather_seconds,
        map_minutes=settings.iris_map_minutes,
        members_hours=settings.iris_members_hours,
        kinds=[
            IrisKindOut(
                kind=kind,
                fetched_at=rows[kind].fetched_at if kind in rows else None,
                attempted_at=rows[kind].attempted_at if kind in rows else None,
                size_bytes=rows[kind].size_bytes if kind in rows else 0,
                error=rows[kind].error if kind in rows else "",
            )
            for kind in IRIS_KINDS
        ],
        events_total=total,
        events_active=active,
    )


@admin_router.post("/refresh", response_model=IrisRefreshOut)
async def iris_refresh(
    payload: IrisRefreshIn, request: Request, session: SessionDep, user: IrisManager
) -> IrisRefreshOut:
    """Relance tout de suite une tâche de collecte (les membres tournent en arrière-plan)."""
    _check_enabled(request)
    if not request.app.state.iris_refreshes.allow(str(user.id)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Trop de relances : attends quelques minutes.")
    labels = {"weather": "météo et heure du jeu", "map": "carte", "members": "membres des pays"}
    audit.record(session, user.id, NATIONSGLORY, "iris.refresh", "iris", payload.job, f"Iris : {labels[payload.job]}")
    await session.commit()
    collector = _collector(request)
    if payload.job == "members":
        tasks: set[asyncio.Task] = request.app.state.iris_tasks
        task = asyncio.create_task(collector.run("members", force=True))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return IrisRefreshOut(
            job=payload.job, started=True, detail="Mise à jour des membres lancée (quelques minutes)."
        )
    started = await collector.run(payload.job, force=True)
    detail = "Données mises à jour." if started else "Une collecte est déjà en cours : réessaie dans un instant."
    return IrisRefreshOut(job=payload.job, started=started, detail=detail)
