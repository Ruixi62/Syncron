"""R&D : domaines de recherche, paliers, conditions et récompenses, progression du pays.

Lecture : tout compte connecté. Gestion : administrateurs et éditeurs à qui la R&D est confiée.

Les conditions de tous les paliers peuvent être suivies à tout moment (cochées, quantités
réunies). Une condition chiffrée ne se coche qu'une fois sa quantité atteinte. Les paliers,
eux, se valident dans l'ordre : le palier N ne peut l'être (et donner ses récompenses)
qu'après le palier N-1, et seulement si toutes ses conditions sont remplies.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_core.text import format_quantity
from syncron_server import audit
from syncron_server.deps import ResearchManager, SessionDep, UserDep
from syncron_server.models import ResearchCategory, ResearchLine, ResearchTier, utcnow
from syncron_server.schemas import (
    OverviewStat,
    OverviewTodo,
    ResearchCategoryIn,
    ResearchCategoryOut,
    ResearchLineIn,
    ResearchLineOut,
    ResearchLinePatch,
    ResearchOut,
    ResearchRewardIn,
    ResearchRewardOut,
    ResearchTierIn,
    ResearchTierOut,
    SystemOverviewOut,
)
from syncron_server.systems import RESEARCH, SYSTEMS, overview_provider

router = APIRouter(prefix="/api/v1/research", tags=["R&D"])
admin_router = APIRouter(prefix="/api/v1/admin/research", tags=["R&D (gestion)"])
CATEGORY_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,31}$")


async def _categories(session: AsyncSession) -> list[ResearchCategory]:
    query = select(ResearchCategory).order_by(ResearchCategory.position, ResearchCategory.name)
    return list((await session.execute(query)).scalars())


def _line_out(line: ResearchLine) -> ResearchLineOut:
    return ResearchLineOut(
        id=line.id,
        text=line.text,
        quantity=line.quantity,
        progress=line.progress,
        item_id=line.item_id,
        done=line.done,
    )


def _reached(quantity: int | None, progress: int | None) -> bool:
    """Une condition sans quantité peut toujours être cochée ; une condition chiffrée, une fois le compte atteint."""
    return quantity is None or (progress or 0) >= quantity


def _conditions(category: ResearchCategory, level: int) -> list[ResearchLine]:
    tier = next((t for t in category.tiers if t.level == level), None)
    return [line for line in tier.lines if line.kind == "condition"] if tier else []


def _tier_out(level: int, tier: ResearchTier | None) -> ResearchTierOut:
    lines = tier.lines if tier else []
    return ResearchTierOut(
        level=level,
        name=tier.name if tier else "",
        description=tier.description if tier else "",
        conditions=[_line_out(line) for line in lines if line.kind == "condition"],
        rewards=[ResearchRewardOut(id=line.id, text=line.text) for line in lines if line.kind == "reward"],
    )


def category_out(category: ResearchCategory) -> ResearchCategoryOut:
    tiers = {tier.level: tier for tier in category.tiers}
    return ResearchCategoryOut(
        id=category.id,
        name=category.name,
        description=category.description,
        icon=category.icon,
        position=category.position,
        tier_count=category.tier_count,
        completed=category.completed,
        skill_id=category.skill_id,
        updated_at=category.updated_at,
        tiers=[_tier_out(level, tiers.get(level)) for level in range(1, category.tier_count + 1)],
    )


@router.get("", response_model=ResearchOut)
async def research(session: SessionDep, _user: UserDep) -> ResearchOut:
    categories = await _categories(session)
    await session.commit()
    return ResearchOut(categories=[category_out(category) for category in categories])


@overview_provider(RESEARCH)
async def overview(session: AsyncSession) -> SystemOverviewOut:
    categories = await _categories(session)
    total = sum(c.tier_count for c in categories)
    validated = sum(c.completed for c in categories)
    filled = {(t.category_id, t.level): t for c in categories for t in c.tiers}
    missing_conditions = missing_rewards = ready = conditions_done = conditions_total = 0
    for category in categories:
        for level in range(1, category.tier_count + 1):
            lines = filled[(category.id, level)].lines if (category.id, level) in filled else []
            conditions = [line for line in lines if line.kind == "condition"]
            missing_conditions += not conditions
            missing_rewards += not any(line.kind == "reward" for line in lines)
            if level > category.completed:
                conditions_total += len(conditions)
                conditions_done += sum(line.done for line in conditions)
            if level == category.completed + 1 and conditions and all(line.done for line in conditions):
                ready += 1
    return SystemOverviewOut(
        id=RESEARCH,
        name=SYSTEMS[RESEARCH],
        stats=[
            OverviewStat(
                label="Paliers validés", value=f"{validated} / {total}", detail=f"{len(categories)} domaine(s)"
            ),
            OverviewStat(
                label="Conditions remplies",
                value=f"{conditions_done} / {conditions_total}",
                detail="sur les paliers pas encore validés",
            ),
        ],
        todo=[
            OverviewTodo(label="Paliers prêts à valider", count=ready),
            OverviewTodo(label="Paliers sans conditions", count=missing_conditions),
            OverviewTodo(label="Paliers sans récompenses", count=missing_rewards),
        ],
        updated_at=max((c.updated_at for c in categories), default=None),
    )


# -- gestion ------------------------------------------------------------------------------


async def _locked(session: AsyncSession, category_id: str) -> ResearchCategory | None:
    query = select(ResearchCategory).where(ResearchCategory.id == category_id).with_for_update()
    return (await session.execute(query)).scalar_one_or_none()


async def _existing(session: AsyncSession, category_id: str) -> ResearchCategory:
    category = await _locked(session, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Domaine « {category_id} » introuvable.")
    return category


async def _reloaded(session: AsyncSession, category_id: str) -> ResearchCategory:
    query = select(ResearchCategory).where(ResearchCategory.id == category_id).execution_options(populate_existing=True)
    return (await session.execute(query)).scalar_one()


@admin_router.put("/categories/{category_id}", response_model=ResearchCategoryOut)
async def put_category(
    category_id: str, payload: ResearchCategoryIn, session: SessionDep, user: ResearchManager
) -> ResearchCategoryOut:
    """Fiche du domaine. `completed` permet de corriger l'avancement (reprise d'un pays déjà avancé en jeu)."""
    if not CATEGORY_ID.match(category_id):
        raise HTTPException(422, "Identifiant invalide (minuscules, chiffres, _ et -, 32 caractères au plus).")
    if payload.completed > payload.tier_count:
        raise HTTPException(422, "Le nombre de paliers validés dépasse le nombre de paliers.")
    category = await _locked(session, category_id)
    created = category is None
    before_completed = 0 if created else category.completed
    if created:
        category = ResearchCategory(id=category_id, updated_at=utcnow())
        session.add(category)
    else:
        filled = sorted(t.level for t in category.tiers if t.level > payload.tier_count and (t.lines or t.name))
        if filled:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Les paliers {', '.join(map(str, filled))} ont du contenu : vide-les avant de réduire le nombre de "
                "paliers.",
            )
        for tier in [t for t in category.tiers if t.level > payload.tier_count]:
            category.tiers.remove(tier)
    category.name = payload.name
    category.description = payload.description
    category.icon = payload.icon or "flask"
    category.position = payload.position
    category.tier_count = payload.tier_count
    category.completed = payload.completed
    category.skill_id = payload.skill_id or None
    category.updated_at = utcnow()

    changes = []
    if created:
        changes.append("créé")
    if payload.completed != before_completed:
        changes.append(f"paliers validés {before_completed} → {payload.completed}")
    audit.record(
        session,
        user.id,
        RESEARCH,
        "research.category",
        "research",
        category_id,
        f"R&D {payload.name} : " + (", ".join(changes) or "modifié"),
    )
    await session.commit()
    return category_out(await _reloaded(session, category_id))


@admin_router.put("/categories/{category_id}/tiers/{level}", response_model=ResearchCategoryOut)
async def put_tier(
    category_id: str, level: int, payload: ResearchTierIn, session: SessionDep, user: ResearchManager
) -> ResearchCategoryOut:
    category = await _existing(session, category_id)
    if not 1 <= level <= category.tier_count:
        raise HTTPException(422, f"Palier hors limites : {category.name} a {category.tier_count} palier(s).")
    values = {"name": payload.name, "description": payload.description, "updated_at": utcnow()}
    statement = insert(ResearchTier).values(category_id=category_id, level=level, **values)
    await session.execute(
        statement.on_conflict_do_update(index_elements=[ResearchTier.category_id, ResearchTier.level], set_=values)
    )
    existing = {
        line.id: line
        for line in (
            await session.execute(
                select(ResearchLine).where(ResearchLine.category_id == category_id, ResearchLine.level == level)
            )
        ).scalars()
    }
    kept: set[int] = set()
    for kind, lines in (("condition", payload.conditions), ("reward", payload.rewards)):
        for position, data in enumerate(lines):
            line = existing.get(data.id) if data.id is not None and data.id not in kept else None
            if line is None:
                line = ResearchLine(category_id=category_id, level=level)
                session.add(line)
            else:
                kept.add(line.id)
            if kind == "condition":
                _fill_condition(line, position, data)
            else:
                _fill_reward(line, position, data)
    removed = [line_id for line_id in existing if line_id not in kept]
    if removed:
        await session.execute(delete(ResearchLine).where(ResearchLine.id.in_(removed)))
    category.updated_at = utcnow()
    audit.record(
        session,
        user.id,
        RESEARCH,
        "research.tier",
        "research",
        f"{category_id}:{level}",
        f"R&D {category.name}, palier {level} : {len(payload.conditions)} condition(s), "
        f"{len(payload.rewards)} récompense(s)",
    )
    await session.commit()
    return category_out(await _reloaded(session, category_id))


def _fill_condition(line: ResearchLine, position: int, data: ResearchLineIn) -> None:
    line.kind = "condition"
    line.position = position
    line.text = data.text
    line.quantity = data.quantity
    line.item_id = data.item_id
    line.progress = data.progress
    line.done = data.done and _reached(data.quantity, data.progress)


def _fill_reward(line: ResearchLine, position: int, data: ResearchRewardIn) -> None:
    line.kind = "reward"
    line.position = position
    line.text = data.text
    line.quantity = None
    line.item_id = None
    line.progress = None
    line.done = False


@admin_router.patch("/lines/{line_id}", response_model=ResearchCategoryOut)
async def patch_line(
    line_id: int, payload: ResearchLinePatch, session: SessionDep, user: ResearchManager
) -> ResearchCategoryOut:
    """Met à jour le compteur d'une condition (380 / 1 000) ou la coche, sans rouvrir tout le palier.

    Une condition chiffrée ne peut pas être cochée tant que sa quantité n'est pas atteinte ;
    si son compteur redescend sous la quantité, elle est décochée.
    """
    line = await session.get(ResearchLine, line_id, with_for_update=True)
    if line is None or line.kind != "condition":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Condition introuvable.")
    category = await _existing(session, line.category_id)
    if payload.progress is not None:
        if line.quantity is None:
            raise HTTPException(422, "Cette condition n'a pas de quantité à suivre.")
        line.progress = payload.progress
    done = line.done if payload.done is None else payload.done
    if done and not _reached(line.quantity, line.progress):
        if payload.done:
            missing = format_quantity(line.quantity - (line.progress or 0))
            raise HTTPException(422, f"Quantité pas encore atteinte : il en manque {missing}.")
        done = False
    line.done = done
    category.updated_at = utcnow()
    label = line.text or line.item_id or "condition"
    state = "remplie" if line.done else "à faire"
    if line.quantity is not None:
        state = f"{line.progress or 0} / {line.quantity}, {state}"
    audit.record(
        session,
        user.id,
        RESEARCH,
        "research.progress",
        "research",
        f"{line.category_id}:{line.level}",
        f"R&D {category.name}, palier {line.level} : {label} — {state}",
    )
    await session.commit()
    return category_out(await _reloaded(session, line.category_id))


@admin_router.post("/categories/{category_id}/tiers/{level}/validate", response_model=ResearchCategoryOut)
async def validate_tier(
    category_id: str, level: int, session: SessionDep, user: ResearchManager
) -> ResearchCategoryOut:
    """Le palier a été fait en jeu : il est validé, ses récompenses sont acquises."""
    category = await _existing(session, category_id)
    if not 1 <= level <= category.tier_count:
        raise HTTPException(422, f"Palier hors limites : {category.name} a {category.tier_count} palier(s).")
    if level <= category.completed:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Le palier {level} est déjà validé.")
    if level > category.completed + 1:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Valide d'abord le palier {category.completed + 1}.")
    conditions = _conditions(category, level)
    remaining = sum(not line.done for line in conditions)
    if remaining:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Conditions pas toutes remplies : {len(conditions) - remaining} / {len(conditions)}.",
        )
    category.completed = level
    category.updated_at = utcnow()
    audit.record(
        session,
        user.id,
        RESEARCH,
        "research.validate",
        "research",
        f"{category_id}:{level}",
        f"R&D {category.name} : palier {level} validé",
    )
    await session.commit()
    return category_out(await _reloaded(session, category_id))


@admin_router.delete("/categories/{category_id}/tiers/{level}/validate", response_model=ResearchCategoryOut)
async def unvalidate_tier(
    category_id: str, level: int, session: SessionDep, user: ResearchManager
) -> ResearchCategoryOut:
    """Annule la validation du dernier palier validé (erreur de clic)."""
    category = await _existing(session, category_id)
    if level != category.completed or level < 1:
        detail = (
            f"Seul le dernier palier validé ({category.completed}) peut être annulé."
            if category.completed
            else "Aucun palier n'est validé."
        )
        raise HTTPException(status.HTTP_409_CONFLICT, detail)
    category.completed = level - 1
    category.updated_at = utcnow()
    audit.record(
        session,
        user.id,
        RESEARCH,
        "research.validate",
        "research",
        f"{category_id}:{level}",
        f"R&D {category.name} : validation du palier {level} annulée",
    )
    await session.commit()
    return category_out(await _reloaded(session, category_id))


@admin_router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: str, session: SessionDep, user: ResearchManager) -> None:
    category = await _existing(session, category_id)
    name = category.name
    await session.delete(category)
    audit.record(session, user.id, RESEARCH, "research.delete", "research", category_id, f"R&D supprimé : {name}")
    await session.commit()
