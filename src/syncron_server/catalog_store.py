"""Lecture et écriture du catalogue en base.

Toute écriture suit le même chemin, qu'il s'agisse d'un objet, d'un atelier,
d'une image ou d'un import complet :

    1. verrou sur catalog_state (les écritures sont sérialisées)
    2. lecture du catalogue courant -> CraftData
    3. calcul du catalogue cible (fonction pure)
    4. validation complète (références, niveaux, cycles, longueurs)
       -> refus avec la liste des problèmes : rien n'est écrit
    5. application du différentiel, révision +1, entrée de journal, commit

Le catalogue enregistré est donc toujours cohérent.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_core.catalog import CraftData
from syncron_core.catalog_format import dump_catalog
from syncron_core.errors import AppError
from syncron_core.models.item import Ingredient, ItemType, Recipe, Requirement
from syncron_core.models.item import Item as CoreItem
from syncron_core.models.reference import Skill as CoreSkill
from syncron_core.models.reference import SkillKind
from syncron_core.models.reference import Station as CoreStation
from syncron_core.models.validation import Severity, ValidationIssue
from syncron_core.validator import RecipeValidator
from syncron_server.models import (
    AuditEntry,
    CatalogState,
    Item,
    ItemRequirement,
    RecipeIngredient,
    Skill,
    Station,
    utcnow,
)

STATE_ID = 1
SOURCE = "base"
LIMITS = {"name": 120, "category": 80, "description": 4000}


class CatalogValidationError(AppError):
    def __init__(self, issues: tuple[ValidationIssue, ...], message: str = "Modification refusée.") -> None:
        self.issues = issues
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SectionDiff:
    added: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    unchanged: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)


@dataclass(frozen=True, slots=True)
class CatalogDiff:
    stations: SectionDiff = field(default_factory=SectionDiff)
    skills: SectionDiff = field(default_factory=SectionDiff)
    items: SectionDiff = field(default_factory=SectionDiff)

    @property
    def changed(self) -> bool:
        return self.stations.changed or self.skills.changed or self.items.changed


@dataclass(frozen=True, slots=True)
class WriteResult:
    revision: int
    diff: CatalogDiff
    previous: CraftData
    current: CraftData


# -- lecture -----------------------------------------------------------------------


async def get_state(session: AsyncSession, lock: bool = False) -> CatalogState:
    query = select(CatalogState).where(CatalogState.id == STATE_ID)
    if lock:
        query = query.with_for_update()
    state = (await session.execute(query)).scalar_one_or_none()
    if state is None:
        state = CatalogState(id=STATE_ID, revision=0, updated_at=utcnow())
        session.add(state)
        await session.flush()
        if lock:
            state = (await session.execute(query)).scalar_one()
    return state


async def load_catalog(session: AsyncSession) -> CraftData:
    stations = (await session.execute(select(Station).order_by(Station.id))).scalars().all()
    skills = (await session.execute(select(Skill).order_by(Skill.id))).scalars().all()
    items = (await session.execute(select(Item).order_by(Item.id))).scalars().all()
    return CraftData(
        items=tuple(_item_to_core(row) for row in items),
        stations=tuple(CoreStation(s.id, s.name, s.description or "", s.image_url, source=SOURCE) for s in stations),
        skills=tuple(
            CoreSkill(s.id, s.name, SkillKind(s.kind), s.max_level, s.description or "", source=SOURCE) for s in skills
        ),
    )


def _item_to_core(row: Item) -> CoreItem:
    recipe = None
    if row.type == ItemType.CRAFTED.value:
        recipe = Recipe(
            output=row.output or 1,
            ingredients=tuple(Ingredient(i.ingredient_id, i.quantity) for i in row.ingredients),
            station_id=row.station_id,
            time_seconds=row.time_seconds,
            requirements=tuple(Requirement(r.skill_id, r.level) for r in row.requirements),
        )
    return CoreItem(
        id=row.id,
        name=row.name,
        type=ItemType(row.type),
        recipe=recipe,
        category=row.category or "",
        image=row.image_url,
        description=row.description or "",
        source=SOURCE,
    )


# -- validation ------------------------------------------------------------------


def validate_catalog(data: CraftData) -> tuple[ValidationIssue, ...]:
    issues = list(RecipeValidator().validate(data).issues)
    for section, entities in (("items", data.items), ("stations", data.stations), ("skills", data.skills)):
        for entity in entities:
            for field_name, limit in LIMITS.items():
                value = getattr(entity, field_name, "") or ""
                if len(value) > limit:
                    issues.append(
                        ValidationIssue(
                            Severity.ERROR,
                            f"« {field_name} » dépasse {limit} caractères.",
                            entity.id,
                            entity.source,
                            section,
                        )
                    )
            if not entity.name.strip():
                issues.append(
                    ValidationIssue(Severity.ERROR, "Le nom est obligatoire.", entity.id, entity.source, section)
                )
    return tuple(issues)


def compute_diff(current: CraftData, target: CraftData) -> CatalogDiff:
    def section(old_entities, new_entities) -> SectionDiff:
        old = {e.id: e for e in old_entities}
        new = {e.id: e for e in new_entities}
        added = tuple(sorted(new.keys() - old.keys()))
        removed = tuple(sorted(old.keys() - new.keys()))
        common = old.keys() & new.keys()
        updated = tuple(sorted(key for key in common if old[key] != new[key]))
        return SectionDiff(added, updated, removed, len(common) - len(updated))

    return CatalogDiff(
        stations=section(current.stations, target.stations),
        skills=section(current.skills, target.skills),
        items=section(current.items, target.items),
    )


# -- écriture --------------------------------------------------------------------


DescribeFn = Callable[[CraftData, CraftData, CatalogDiff], Any]


@dataclass(frozen=True, slots=True)
class AuditInfo:
    """Entrée de journal. `summary` et `details` peuvent être calculés à partir
    du catalogue avant/après et du différentiel (fonctions)."""

    action: str
    entity_type: str
    entity_id: str
    summary: str | DescribeFn
    details: dict[str, Any] | DescribeFn | None = None

    def describe(self, previous: CraftData, current: CraftData, diff: CatalogDiff) -> tuple[str, Any]:
        summary = self.summary(previous, current, diff) if callable(self.summary) else self.summary
        details = self.details(previous, current, diff) if callable(self.details) else self.details
        return summary, details


async def write_catalog(
    session: AsyncSession,
    user_id: uuid.UUID | None,
    mutate: Callable[[CraftData], CraftData],
    audit: AuditInfo,
    dry_run: bool = False,
) -> WriteResult:
    revision = (await get_state(session, lock=True)).revision
    current = await load_catalog(session)
    target = mutate(current)
    issues = validate_catalog(target)
    if any(issue.severity is Severity.ERROR for issue in issues):
        await session.rollback()
        raise CatalogValidationError(tuple(i for i in issues if i.severity is Severity.ERROR))
    diff = compute_diff(current, target)
    if dry_run or not diff.changed:
        await session.rollback()
        return WriteResult(revision, diff, current, target)
    await _apply(session, current, target, user_id)
    revision += 1
    await session.execute(
        update(CatalogState).where(CatalogState.id == STATE_ID).values(revision=revision, updated_at=utcnow())
    )
    summary, details = audit.describe(current, target, diff)
    session.add(
        AuditEntry(
            user_id=user_id,
            action=audit.action,
            entity_type=audit.entity_type,
            entity_id=audit.entity_id,
            summary=summary,
            details=details,
            created_at=utcnow(),
        )
    )
    await session.commit()
    session.expunge_all()
    return WriteResult(revision, diff, current, target)


async def _apply(session: AsyncSession, current: CraftData, target: CraftData, user_id: uuid.UUID | None) -> None:
    now = utcnow()
    old_stations = {s.id: s for s in current.stations}
    old_skills = {s.id: s for s in current.skills}
    old_items = {i.id: i for i in current.items}
    new_items = {i.id: i for i in target.items}

    for station in target.stations:
        values = {
            "name": station.name,
            "description": station.description,
            "image_url": station.image,
            "updated_at": now,
        }
        if station.id not in old_stations:
            await session.execute(insert(Station).values(id=station.id, **values))
        elif old_stations[station.id] != station:
            await session.execute(update(Station).where(Station.id == station.id).values(**values))

    for skill in target.skills:
        values = {
            "name": skill.name,
            "kind": skill.kind.value,
            "max_level": skill.max_level,
            "description": skill.description,
            "updated_at": now,
        }
        if skill.id not in old_skills:
            await session.execute(insert(Skill).values(id=skill.id, **values))
        elif old_skills[skill.id] != skill:
            await session.execute(update(Skill).where(Skill.id == skill.id).values(**values))

    for item in target.items:
        recipe = item.recipe
        values = {
            "name": item.name,
            "type": item.type.value,
            "category": item.category,
            "description": item.description,
            "image_url": item.image,
            "output": recipe.output if recipe else None,
            "station_id": recipe.station_id if recipe else None,
            "time_seconds": recipe.time_seconds if recipe else 0,
            "updated_at": now,
            "updated_by": user_id,
        }
        if item.id not in old_items:
            await session.execute(insert(Item).values(id=item.id, created_at=now, **values))
        elif old_items[item.id] != item:
            await session.execute(update(Item).where(Item.id == item.id).values(**values))

    removed_items = old_items.keys() - new_items.keys()
    rewritten = {
        item_id
        for item_id, item in new_items.items()
        if item_id not in old_items or old_items[item_id].recipe != item.recipe
    } | removed_items
    if rewritten:
        await session.execute(delete(RecipeIngredient).where(RecipeIngredient.item_id.in_(rewritten)))
        await session.execute(delete(ItemRequirement).where(ItemRequirement.item_id.in_(rewritten)))
    ingredient_rows, requirement_rows = [], []
    for item_id in sorted(rewritten - removed_items):
        recipe = new_items[item_id].recipe
        if recipe is None:
            continue
        ingredient_rows += [
            {"item_id": item_id, "ingredient_id": i.item_id, "quantity": i.quantity, "position": position}
            for position, i in enumerate(recipe.ingredients)
        ]
        requirement_rows += [
            {"item_id": item_id, "skill_id": r.skill_id, "level": r.level, "position": position}
            for position, r in enumerate(recipe.requirements)
        ]
    if ingredient_rows:
        await session.execute(insert(RecipeIngredient), ingredient_rows)
    if requirement_rows:
        await session.execute(insert(ItemRequirement), requirement_rows)

    if removed_items:
        await session.execute(delete(Item).where(Item.id.in_(removed_items)))
    removed_stations = old_stations.keys() - {s.id for s in target.stations}
    if removed_stations:
        await session.execute(delete(Station).where(Station.id.in_(removed_stations)))
    removed_skills = old_skills.keys() - {s.id for s in target.skills}
    if removed_skills:
        await session.execute(delete(Skill).where(Skill.id.in_(removed_skills)))


# -- transformations pures (utilisées par les routes) -----------------------------


def with_item(data: CraftData, item: CoreItem) -> CraftData:
    items = [existing for existing in data.items if existing.id != item.id] + [item]
    return replace(data, items=tuple(items))


def without_item(data: CraftData, item_id: str) -> CraftData:
    return replace(data, items=tuple(item for item in data.items if item.id != item_id))


def with_station(data: CraftData, station: CoreStation) -> CraftData:
    stations = [s for s in data.stations if s.id != station.id] + [station]
    return replace(data, stations=tuple(stations))


def without_station(data: CraftData, station_id: str) -> CraftData:
    return replace(data, stations=tuple(s for s in data.stations if s.id != station_id))


def with_skill(data: CraftData, skill: CoreSkill) -> CraftData:
    return replace(data, skills=tuple([s for s in data.skills if s.id != skill.id] + [skill]))


def without_skill(data: CraftData, skill_id: str) -> CraftData:
    return replace(data, skills=tuple(s for s in data.skills if s.id != skill_id))


def merge_catalog(current: CraftData, incoming: CraftData) -> CraftData:
    """Fusion : les entrées importées remplacent ou complètent l'existant ; rien n'est supprimé.
    Une image déjà hébergée est conservée si l'import n'en fournit pas."""
    items = {i.id: i for i in current.items}
    for item in incoming.items:
        previous = items.get(item.id)
        items[item.id] = item if item.image or previous is None else replace(item, image=previous.image)
    stations = {s.id: s for s in current.stations}
    for station in incoming.stations:
        previous = stations.get(station.id)
        stations[station.id] = station if station.image or previous is None else replace(station, image=previous.image)
    skills = {s.id: s for s in current.skills} | {s.id: s for s in incoming.skills}
    return CraftData(tuple(items.values()), tuple(stations.values()), tuple(skills.values()))


def replace_catalog(current: CraftData, incoming: CraftData) -> CraftData:
    """Remplacement : le catalogue devient exactement le fichier importé (images hébergées conservées)."""
    kept = merge_catalog(CraftData(), incoming)
    images = {i.id: i.image for i in current.items}
    station_images = {s.id: s.image for s in current.stations}
    return CraftData(
        items=tuple(i if i.image else replace(i, image=images.get(i.id)) for i in kept.items),
        stations=tuple(s if s.image else replace(s, image=station_images.get(s.id)) for s in kept.stations),
        skills=kept.skills,
    )


def entity_snapshot(data: CraftData, section: str, entity_id: str) -> dict[str, Any] | None:
    return dump_catalog(data)[section].get(entity_id)
