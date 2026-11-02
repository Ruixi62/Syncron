"""NationsGlory : appels à l'API publique, gardés en base (historique et lecture par les outils).

Gestion (système « nationsglory ») : état de la connexion, appel d'une route connue,
historique des réponses. Lecture (tout membre) : dernières données du pays, sans appel
direct à l'API (rien ne part de NationsGlory tant que l'équipe ne l'a pas demandé).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server import audit
from syncron_server.deps import SessionDep, SettingsDep, UserDep, manager
from syncron_server.models import NationsGlorySnapshot, User, utcnow
from syncron_server.nationsglory import Fetched, NationsGloryClient, NationsGloryError, build_request
from syncron_server.schemas import (
    NationsGloryFetchIn,
    NationsGlorySnapshotOut,
    NationsGloryStatusOut,
    OverviewStat,
    SystemOverviewOut,
)
from syncron_server.systems import NATIONSGLORY, SYSTEMS, overview_provider

router = APIRouter(prefix="/api/v1/nationsglory", tags=["NationsGlory"])
admin_router = APIRouter(prefix="/api/v1/admin/nationsglory", tags=["NationsGlory (gestion)"])
NationsGloryManager = Annotated[User, Depends(manager(NATIONSGLORY))]
KINDS = ["playercount", "country", "countries", "notations", "mmr", "hdv", "planning", "user"]
KEEP_PER_TARGET = 100
KEEP_TOTAL = 5000


def _client(request: Request) -> NationsGloryClient:
    return request.app.state.nationsglory


def _out(snapshot: NationsGlorySnapshot, with_payload: bool = False) -> NationsGlorySnapshotOut:
    return NationsGlorySnapshotOut(
        id=snapshot.id,
        kind=snapshot.kind,
        target=snapshot.target,
        status=snapshot.status,
        error=snapshot.error,
        size_bytes=snapshot.size_bytes,
        duration_ms=snapshot.duration_ms,
        fetched_at=snapshot.fetched_at,
        payload=snapshot.payload if with_payload else None,
    )


async def _latest(session: AsyncSession) -> list[NationsGlorySnapshot]:
    ranked = (
        select(
            NationsGlorySnapshot.id,
            func.row_number()
            .over(partition_by=NationsGlorySnapshot.kind, order_by=NationsGlorySnapshot.fetched_at.desc())
            .label("rank"),
        )
    ).subquery()
    query = (
        select(NationsGlorySnapshot)
        .join(ranked, ranked.c.id == NationsGlorySnapshot.id)
        .where(ranked.c.rank == 1)
        .order_by(NationsGlorySnapshot.kind)
    )
    return list((await session.execute(query)).scalars())


# -- lecture ------------------------------------------------------------------------------


@router.get("/country", response_model=NationsGlorySnapshotOut)
async def our_country(session: SessionDep, settings: SettingsDep, _user: UserDep) -> NationsGlorySnapshotOut:
    """Dernières données du pays récupérées par l'équipe."""
    if not (settings.ng_server and settings.ng_country):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Le pays n'est pas encore relié à NationsGlory.")
    target = build_request("country", settings.ng_server, settings.ng_country).target
    query = (
        select(NationsGlorySnapshot)
        .where(
            NationsGlorySnapshot.kind == "country",
            NationsGlorySnapshot.target == target,
            NationsGlorySnapshot.status == 200,
        )
        .order_by(NationsGlorySnapshot.fetched_at.desc())
        .limit(1)
    )
    snapshot = (await session.execute(query)).scalar_one_or_none()
    await session.commit()
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pas encore de données NationsGlory pour le pays.")
    return _out(snapshot, with_payload=True)


# -- gestion ------------------------------------------------------------------------------


@admin_router.get("", response_model=NationsGloryStatusOut)
async def nationsglory_status(
    request: Request, session: SessionDep, settings: SettingsDep, _user: NationsGloryManager
) -> NationsGloryStatusOut:
    latest = await _latest(session)
    await session.commit()
    return NationsGloryStatusOut(
        configured=_client(request).configured,
        api_url=settings.ng_api_url,
        auth_header=settings.ng_api_auth_header,
        key_set=bool(settings.ng_api_key.get_secret_value()),
        server=settings.ng_server,
        country=settings.ng_country,
        cache_seconds=settings.ng_cache_seconds,
        kinds=KINDS,
        latest=[_out(snapshot) for snapshot in latest],
    )


@admin_router.post("/fetch", response_model=NationsGlorySnapshotOut)
async def fetch(
    payload: NationsGloryFetchIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: NationsGloryManager,
) -> NationsGlorySnapshotOut:
    """Appelle une route de l'API (paramètres vides : ceux du pays) et garde la réponse."""
    try:
        ng_request = build_request(
            payload.kind,
            server=payload.server or settings.ng_server,
            country=payload.country or settings.ng_country,
            username=payload.username,
            week=payload.week,
            month=payload.month,
            year=payload.year,
        )
    except NationsGloryError as exc:
        raise HTTPException(exc.status or 422, str(exc)) from exc
    if payload.refresh and not request.app.state.nationsglory_calls.allow(str(user.id)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Trop d'appels à NationsGlory : attends une minute.")
    try:
        fetched: Fetched = await _client(request).fetch(ng_request, refresh=payload.refresh)
    except NationsGloryError as exc:
        if exc.status != 503:
            _store_error(session, ng_request.kind, ng_request.target, exc, user)
            await session.commit()
        raise HTTPException(exc.status or 502, str(exc)) from exc
    if fetched.from_cache:
        return NationsGlorySnapshotOut(
            id=0,
            kind=ng_request.kind,
            target=ng_request.target,
            status=200,
            error="",
            size_bytes=fetched.size_bytes,
            duration_ms=0,
            fetched_at=utcnow(),
            from_cache=True,
            payload=fetched.payload,
        )
    snapshot = NationsGlorySnapshot(
        kind=ng_request.kind,
        target=ng_request.target,
        status=200,
        payload=fetched.payload,
        error="",
        size_bytes=fetched.size_bytes,
        duration_ms=fetched.duration_ms,
        fetched_by=user.id,
        fetched_at=utcnow(),
    )
    session.add(snapshot)
    summary = f"NationsGlory : {ng_request.target}"
    audit.record(session, user.id, NATIONSGLORY, "ng.fetch", "nationsglory", ng_request.target, summary)
    await session.flush()
    await _prune(session, ng_request.kind, ng_request.target)
    await session.commit()
    return _out(snapshot, with_payload=True)


def _store_error(session: AsyncSession, kind: str, target: str, error: NationsGloryError, user: User) -> None:
    session.add(
        NationsGlorySnapshot(
            kind=kind,
            target=target,
            status=error.status or 502,
            payload=None,
            error=str(error)[:300],
            fetched_by=user.id,
            fetched_at=utcnow(),
        )
    )


async def _prune(session: AsyncSession, kind: str, target: str) -> None:
    keep = (
        select(NationsGlorySnapshot.id)
        .where(NationsGlorySnapshot.kind == kind, NationsGlorySnapshot.target == target)
        .order_by(NationsGlorySnapshot.fetched_at.desc())
        .limit(KEEP_PER_TARGET)
    )
    await session.execute(
        delete(NationsGlorySnapshot).where(
            NationsGlorySnapshot.kind == kind,
            NationsGlorySnapshot.target == target,
            NationsGlorySnapshot.id.not_in(keep),
        )
    )
    newest = select(NationsGlorySnapshot.id).order_by(NationsGlorySnapshot.fetched_at.desc()).limit(KEEP_TOTAL)
    await session.execute(delete(NationsGlorySnapshot).where(NationsGlorySnapshot.id.not_in(newest)))


@admin_router.get("/snapshots", response_model=list[NationsGlorySnapshotOut])
async def snapshots(
    session: SessionDep,
    _user: NationsGloryManager,
    kind: Annotated[str | None, Query(pattern=r"^[a-z]{1,24}$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[NationsGlorySnapshotOut]:
    query = select(NationsGlorySnapshot).order_by(NationsGlorySnapshot.fetched_at.desc()).limit(limit)
    if kind:
        query = query.where(NationsGlorySnapshot.kind == kind)
    rows = list((await session.execute(query)).scalars())
    await session.commit()
    return [_out(row) for row in rows]


@admin_router.get("/snapshots/{snapshot_id}", response_model=NationsGlorySnapshotOut)
async def snapshot(snapshot_id: int, session: SessionDep, _user: NationsGloryManager) -> NationsGlorySnapshotOut:
    row = await session.get(NationsGlorySnapshot, snapshot_id)
    await session.commit()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Réponse introuvable.")
    return _out(row, with_payload=True)


@overview_provider(NATIONSGLORY)
async def overview(session: AsyncSession) -> SystemOverviewOut:
    count, last = (
        await session.execute(select(func.count(NationsGlorySnapshot.id), func.max(NationsGlorySnapshot.fetched_at)))
    ).one()
    errors = (
        await session.execute(select(func.count(NationsGlorySnapshot.id)).where(NationsGlorySnapshot.status != 200))
    ).scalar_one()
    return SystemOverviewOut(
        id=NATIONSGLORY,
        name=SYSTEMS[NATIONSGLORY],
        stats=[
            OverviewStat(label="Réponses gardées", value=str(count), detail="historique des appels à l'API"),
            OverviewStat(label="Erreurs", value=str(errors), detail="clé refusée, délai, introuvable…"),
        ],
        updated_at=last,
    )
