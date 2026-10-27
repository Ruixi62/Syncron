"""Lecture publique (comptes connectés) : méta, catalogue complet, calcul de craft."""

from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_core import API_VERSION, APP_NAME, __version__
from syncron_core.calculator import CraftCalculator
from syncron_core.catalog import CraftData, CraftRepository
from syncron_core.catalog_format import dump_catalog
from syncron_core.catalog_service import CatalogService
from syncron_core.errors import AppError
from syncron_core.exporters.base import ExportContext
from syncron_core.exporters.json_exporter import JsonExporter
from syncron_server.catalog_store import get_state, load_catalog
from syncron_server.deps import SessionDep, SettingsDep, UserDep
from syncron_server.schemas import CraftPlanRequest, MetaOut

router = APIRouter(prefix="/api/v1", tags=["catalogue"])


@dataclass(slots=True)
class CachedCatalog:
    revision: int
    data: CraftData
    body: bytes
    catalog: CatalogService
    calculator: CraftCalculator


class CatalogCache:
    """Catalogue sérialisé une fois par révision ; chaque requête ne lit que le numéro de révision."""

    def __init__(self) -> None:
        self._cached: CachedCatalog | None = None

    async def get(self, session: AsyncSession) -> CachedCatalog:
        revision = (await get_state(session)).revision
        if self._cached is None or self._cached.revision != revision:
            data = await load_catalog(session)
            document = {"revision": revision, **dump_catalog(data)}
            body = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            repository = CraftRepository(data)
            self._cached = CachedCatalog(revision, data, body, CatalogService(repository), CraftCalculator(repository))
        return self._cached


def etag_for(revision: int) -> str:
    return f'"rev-{revision}"'


@router.get("/meta", response_model=MetaOut)
async def meta(request: Request, settings: SettingsDep, session: SessionDep) -> MetaOut:
    state = await get_state(session)
    await session.commit()
    return MetaOut(
        name=APP_NAME,
        version=__version__,
        api_version=API_VERSION,
        min_client_version=settings.min_client_version,
        catalog_revision=state.revision,
        discord_login=bool(settings.discord_client_id),
        dev_login=settings.dev_login,
    )


@router.get("/catalog")
async def catalog(
    request: Request,
    session: SessionDep,
    _user: UserDep,
    if_none_match: str | None = Header(None),
) -> Response:
    cached = await request.app.state.catalog_cache.get(session)
    etag = etag_for(cached.revision)
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(cached.body, media_type="application/json", headers=headers)


@router.post("/craft/plan")
async def craft_plan(payload: CraftPlanRequest, request: Request, session: SessionDep, _user: UserDep) -> dict:
    """Plan de fabrication calculé côté serveur (même moteur que le client) — pour les intégrations (bot Discord…)."""
    cached = await request.app.state.catalog_cache.get(session)
    try:
        plan = cached.calculator.calculate(payload.item_id, payload.quantity)
    except AppError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return JsonExporter.to_dict(plan, ExportContext.from_catalog(cached.catalog)) | {"revision": cached.revision}
