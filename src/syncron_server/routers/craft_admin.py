"""Gestion du Craft : objets, ateliers, compétences, images, import / export.

Accès : administrateurs et éditeurs à qui le Craft est confié. Le remplacement
total du catalogue reste réservé aux administrateurs.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Literal

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_core.catalog import ID_RULE, CraftData, is_valid_id
from syncron_core.catalog_format import dump_catalog, parse_catalog
from syncron_core.duration import DurationError, parse_duration
from syncron_core.errors import AppError
from syncron_core.models.item import Ingredient, ItemType, Recipe, Requirement
from syncron_core.models.item import Item as CoreItem
from syncron_core.models.reference import Skill as CoreSkill
from syncron_core.models.reference import SkillKind
from syncron_core.models.reference import Station as CoreStation
from syncron_core.models.validation import Severity, ValidationIssue
from syncron_server.catalog_store import (
    AuditInfo,
    CatalogDiff,
    CatalogValidationError,
    SectionDiff,
    entity_snapshot,
    get_state,
    load_catalog,
    merge_catalog,
    replace_catalog,
    with_item,
    with_skill,
    with_station,
    without_item,
    without_skill,
    without_station,
    write_catalog,
)
from syncron_server.deps import CraftManager, SessionDep, SettingsDep
from syncron_server.media import delete_image, is_hosted, normalize_image, store_image
from syncron_server.models import Role, User
from syncron_server.schemas import (
    ImportOut,
    IssueOut,
    ItemIn,
    OverviewStat,
    OverviewTodo,
    SectionDiffOut,
    SkillIn,
    StationIn,
    SystemOverviewOut,
    WriteOut,
)
from syncron_server.systems import CRAFT, SYSTEMS, overview_provider

router = APIRouter(prefix="/api/v1/admin/craft", tags=["craft (gestion)"])
UNPROCESSABLE = 422


def _check_id(entity_id: str) -> str:
    if not is_valid_id(entity_id):
        raise HTTPException(UNPROCESSABLE, f"Identifiant invalide ({ID_RULE}).")
    return entity_id


def _names(data: CraftData, ids) -> str:
    names = {i.id: i.name for i in data.items}
    return ", ".join(sorted(names.get(i, i) for i in ids))


@overview_provider(CRAFT)
async def overview(session: AsyncSession) -> SystemOverviewOut:
    state = await get_state(session)
    data = await load_catalog(session)
    crafted = [i for i in data.items if i.recipe is not None]
    return SystemOverviewOut(
        id=CRAFT,
        name=SYSTEMS[CRAFT],
        stats=[
            OverviewStat(
                label="Objets",
                value=str(len(data.items)),
                detail=f"{len(data.items) - len(crafted)} ressource(s) primaire(s)",
            ),
            OverviewStat(label="Recettes", value=str(len(crafted)), detail="objets craftables"),
            OverviewStat(label="Ateliers", value=str(len(data.stations))),
            OverviewStat(label="Compétences", value=str(len(data.skills))),
        ],
        todo=[
            OverviewTodo(label="Objets sans image", count=sum(1 for i in data.items if not i.image)),
            OverviewTodo(label="Objets sans catégorie", count=sum(1 for i in data.items if not i.category)),
            OverviewTodo(label="Ateliers sans image", count=sum(1 for s in data.stations if not s.image)),
        ],
        updated_at=state.updated_at,
    )


# -- objets ----------------------------------------------------------------------


def _core_item(item_id: str, payload: ItemIn, previous: CoreItem | None) -> CoreItem:
    recipe = None
    if payload.type == "crafted":
        if not payload.recipe:
            raise HTTPException(UNPROCESSABLE, "Un objet craftable doit avoir au moins un ingrédient.")
        for mapping, what in ((payload.recipe, "Quantité"), (payload.requires, "Niveau")):
            for key, value in mapping.items():
                if value < 1:
                    raise HTTPException(UNPROCESSABLE, f"{what} invalide pour « {key} » : {value}.")
        if item_id in payload.recipe:
            raise HTTPException(UNPROCESSABLE, "Un objet ne peut pas être son propre ingrédient.")
        try:
            seconds = parse_duration(payload.time)
        except DurationError as exc:
            raise HTTPException(UNPROCESSABLE, f"Temps : {exc}") from exc
        recipe = Recipe(
            output=payload.output,
            ingredients=tuple(Ingredient(key, value) for key, value in payload.recipe.items()),
            station_id=payload.station_id or None,
            time_seconds=seconds,
            requirements=tuple(Requirement(key, value) for key, value in payload.requires.items()),
        )
    return CoreItem(
        id=item_id,
        name=payload.name,
        type=ItemType(payload.type),
        recipe=recipe,
        category=payload.category,
        image=previous.image if previous else None,
        description=payload.description,
        source="base",
    )


@router.put("/items/{item_id}", response_model=WriteOut)
async def put_item(item_id: str, payload: ItemIn, session: SessionDep, user: CraftManager) -> WriteOut:
    _check_id(item_id)

    def mutate(data: CraftData) -> CraftData:
        previous = next((i for i in data.items if i.id == item_id), None)
        return with_item(data, _core_item(item_id, payload, previous))

    def summary(before: CraftData, _after: CraftData, _diff: CatalogDiff) -> str:
        created = all(i.id != item_id for i in before.items)
        return f"Objet {'créé' if created else 'modifié'} : {payload.name}"

    def details(before: CraftData, after: CraftData, _diff: CatalogDiff) -> dict:
        return {"before": entity_snapshot(before, "items", item_id), "after": entity_snapshot(after, "items", item_id)}

    result = await write_catalog(session, user.id, mutate, AuditInfo("item.save", "item", item_id, summary, details))
    return WriteOut(revision=result.revision, changed=result.diff.changed)


@router.delete("/items/{item_id}", response_model=WriteOut)
async def delete_item(item_id: str, session: SessionDep, settings: SettingsDep, user: CraftManager) -> WriteOut:
    def mutate(data: CraftData) -> CraftData:
        item = next((i for i in data.items if i.id == item_id), None)
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Objet « {item_id} » introuvable.")
        consumers = [i.id for i in data.items if item_id in i.ingredient_ids]
        if consumers:
            raise AppError(
                f"« {item.name} » est utilisé par : {_names(data, consumers)}. Retire-le de ces recettes d'abord."
            )
        return without_item(data, item_id)

    result = await write_catalog(
        session, user.id, mutate, AuditInfo("item.delete", "item", item_id, f"Objet supprimé : {item_id}")
    )
    previous = next(i for i in result.previous.items if i.id == item_id)
    delete_image(settings.media_dir, previous.image)
    return WriteOut(revision=result.revision, changed=True)


# -- ateliers et compétences ---------------------------------------------------------


@router.put("/stations/{station_id}", response_model=WriteOut)
async def put_station(station_id: str, payload: StationIn, session: SessionDep, user: CraftManager) -> WriteOut:
    _check_id(station_id)

    def mutate(data: CraftData) -> CraftData:
        previous = next((s for s in data.stations if s.id == station_id), None)
        image = previous.image if previous else None
        return with_station(data, CoreStation(station_id, payload.name, payload.description, image, source="base"))

    result = await write_catalog(
        session,
        user.id,
        mutate,
        AuditInfo("station.save", "station", station_id, f"Atelier enregistré : {payload.name}"),
    )
    return WriteOut(revision=result.revision, changed=result.diff.changed)


@router.delete("/stations/{station_id}", response_model=WriteOut)
async def delete_station(station_id: str, session: SessionDep, settings: SettingsDep, user: CraftManager) -> WriteOut:
    def mutate(data: CraftData) -> CraftData:
        station = next((s for s in data.stations if s.id == station_id), None)
        if station is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Atelier « {station_id} » introuvable.")
        users = [i.id for i in data.items if i.station_id == station_id]
        if users:
            raise AppError(f"« {station.name} » est l'atelier de : {_names(data, users)}. Change leur atelier d'abord.")
        return without_station(data, station_id)

    result = await write_catalog(
        session, user.id, mutate, AuditInfo("station.delete", "station", station_id, f"Atelier supprimé : {station_id}")
    )
    delete_image(settings.media_dir, next(s for s in result.previous.stations if s.id == station_id).image)
    return WriteOut(revision=result.revision, changed=True)


@router.put("/skills/{skill_id}", response_model=WriteOut)
async def put_skill(skill_id: str, payload: SkillIn, session: SessionDep, user: CraftManager) -> WriteOut:
    _check_id(skill_id)
    skill = CoreSkill(skill_id, payload.name, SkillKind(payload.kind), payload.max_level, payload.description, "base")
    result = await write_catalog(
        session,
        user.id,
        lambda data: with_skill(data, skill),
        AuditInfo("skill.save", "skill", skill_id, f"Compétence enregistrée : {payload.name}"),
    )
    return WriteOut(revision=result.revision, changed=result.diff.changed)


@router.delete("/skills/{skill_id}", response_model=WriteOut)
async def delete_skill(skill_id: str, session: SessionDep, user: CraftManager) -> WriteOut:
    def mutate(data: CraftData) -> CraftData:
        skill = next((s for s in data.skills if s.id == skill_id), None)
        if skill is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Compétence « {skill_id} » introuvable.")
        users = [i.id for i in data.items if i.recipe and skill_id in {r.skill_id for r in i.recipe.requirements}]
        if users:
            raise AppError(
                f"« {skill.name} » est un prérequis de : {_names(data, users)}. Retire ces prérequis d'abord."
            )
        return without_skill(data, skill_id)

    result = await write_catalog(
        session, user.id, mutate, AuditInfo("skill.delete", "skill", skill_id, f"Compétence supprimée : {skill_id}")
    )
    return WriteOut(revision=result.revision, changed=True)


# -- images ------------------------------------------------------------------------


async def _set_image(
    request: Request,
    session,
    settings,
    user: User,
    kind: Literal["items", "stations"],
    entity_id: str,
    file: UploadFile | None,
) -> WriteOut:
    _check_id(entity_id)
    current = await load_catalog(session)
    if all(e.id != entity_id for e in (current.items if kind == "items" else current.stations)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"« {entity_id} » introuvable.")
    new_url = None
    if file is not None:
        raw = await file.read(settings.max_image_bytes + 1)
        new_url = store_image(settings.media_dir, kind, entity_id, normalize_image(raw, settings.max_image_bytes))

    def mutate(data: CraftData) -> CraftData:
        entities = data.items if kind == "items" else data.stations
        entity = next((e for e in entities if e.id == entity_id), None)
        if entity is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"« {entity_id} » introuvable.")
        updated = replace(entity, image=new_url)
        return with_item(data, updated) if kind == "items" else with_station(data, updated)

    label = "objet" if kind == "items" else "atelier"
    action = "Image mise à jour" if new_url else "Image retirée"
    try:
        result = await write_catalog(
            session, user.id, mutate, AuditInfo("image.set", kind[:-1], entity_id, f"{action} ({label}) : {entity_id}")
        )
    except Exception:
        delete_image(settings.media_dir, new_url)
        raise
    entities = result.previous.items if kind == "items" else result.previous.stations
    old_url = next(e.image for e in entities if e.id == entity_id)
    if old_url != new_url:
        delete_image(settings.media_dir, old_url)
    return WriteOut(revision=result.revision, changed=result.diff.changed)


@router.put("/items/{item_id}/image", response_model=WriteOut)
async def put_item_image(
    item_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: CraftManager,
    file: UploadFile = File(...),
) -> WriteOut:
    return await _set_image(request, session, settings, user, "items", item_id, file)


@router.delete("/items/{item_id}/image", response_model=WriteOut)
async def delete_item_image(
    item_id: str, request: Request, session: SessionDep, settings: SettingsDep, user: CraftManager
) -> WriteOut:
    return await _set_image(request, session, settings, user, "items", item_id, None)


@router.put("/stations/{station_id}/image", response_model=WriteOut)
async def put_station_image(
    station_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: CraftManager,
    file: UploadFile = File(...),
) -> WriteOut:
    return await _set_image(request, session, settings, user, "stations", station_id, file)


@router.delete("/stations/{station_id}/image", response_model=WriteOut)
async def delete_station_image(
    station_id: str, request: Request, session: SessionDep, settings: SettingsDep, user: CraftManager
) -> WriteOut:
    return await _set_image(request, session, settings, user, "stations", station_id, None)


# -- import / export -----------------------------------------------------------------


@router.get("/export")
async def export_catalog(session: SessionDep, _user: CraftManager) -> Response:
    state = await get_state(session)
    data = await load_catalog(session)
    await session.commit()
    body = json.dumps(dump_catalog(data), ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"syncron-catalogue-rev{state.revision}.json"
    return Response(
        body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/import", response_model=ImportOut)
async def import_catalog(
    session: SessionDep,
    user: CraftManager,
    document: dict = Body(...),
    mode: Literal["merge", "replace"] = Query("merge"),
    dry_run: bool = Query(True),
) -> ImportOut:
    if mode == "replace" and user.role_enum is not Role.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Le remplacement total du catalogue est réservé aux administrateurs."
        )
    parsed = parse_catalog(document, "import")
    if parsed.has_errors:
        raise CatalogValidationError(
            tuple(i for i in parsed.issues if i.severity is Severity.ERROR), "Fichier invalide."
        )
    warnings = list(parsed.issues)
    incoming = parsed.data
    stripped = [i.id for i in incoming.items if i.image and not is_hosted(i.image)]
    stripped += [s.id for s in incoming.stations if s.image and not is_hosted(s.image)]
    if stripped:
        warnings.append(
            ValidationIssue(
                Severity.WARNING,
                f"{len(stripped)} chemin(s) d'image local(aux) ignoré(s) : ajoute ces images depuis le mode admin.",
                None,
                "import",
            )
        )
        incoming = CraftData(
            items=tuple(i if is_hosted(i.image) else replace(i, image=None) for i in incoming.items),
            stations=tuple(s if is_hosted(s.image) else replace(s, image=None) for s in incoming.stations),
            skills=incoming.skills,
        )
    combine = merge_catalog if mode == "merge" else replace_catalog
    result = await write_catalog(
        session,
        user.id,
        lambda current: combine(current, incoming),
        AuditInfo("catalog.import", "catalog", mode, lambda _before, _after, diff: _import_summary(mode, diff)),
        dry_run=dry_run,
    )
    applied = not dry_run and result.diff.changed
    return ImportOut(
        dry_run=dry_run,
        applied=applied,
        revision=result.revision,
        stations=_section_out(result.diff.stations),
        skills=_section_out(result.diff.skills),
        items=_section_out(result.diff.items),
        warnings=[IssueOut.of(issue) for issue in warnings],
    )


def _section_out(diff: SectionDiff) -> SectionDiffOut:
    return SectionDiffOut(
        added=list(diff.added), updated=list(diff.updated), removed=list(diff.removed), unchanged=diff.unchanged
    )


def _import_summary(mode: str, diff: CatalogDiff) -> str:
    parts = []
    for label, section in (("objets", diff.items), ("ateliers", diff.stations), ("compétences", diff.skills)):
        if section.changed:
            parts.append(f"{label} +{len(section.added)} ~{len(section.updated)} −{len(section.removed)}")
    return f"Import ({'fusion' if mode == 'merge' else 'remplacement'}) : " + ", ".join(parts)
