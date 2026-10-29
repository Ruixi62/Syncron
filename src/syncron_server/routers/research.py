"""R&D : domaines de recherche, paliers, conditions et récompenses, progression du pays.

Lecture : tout compte connecté. Gestion : administrateurs et éditeurs à qui la R&D est confiée.
Une seule recherche est en cours à la fois (index unique partiel sur `active`).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_core.text import format_quantity
from syncron_server import audit
from syncron_server.deps import ResearchManager, SessionDep, UserDep
from syncron_server.messaging import post_message
from syncron_server.models import Item, ResearchCategory, ResearchLine, ResearchTier, utcnow
from syncron_server.schemas import (
    OverviewStat,
    OverviewTodo,
    ResearchCategoryIn,
    ResearchCategoryOut,
    ResearchLineIn,
    ResearchLineOut,
    ResearchLinePatch,
    ResearchOut,
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


def _is_done(kind: str, quantity: int | None, progress: int | None, done: bool) -> bool:
    """Une récompense n'est jamais « faite » ; une condition chiffrée l'est dès que le compte est atteint."""
    if kind != "condition":
        return False
    return done or (quantity is not None and progress is not None and progress >= quantity)


def _tier_out(level: int, tier: ResearchTier | None) -> ResearchTierOut:
    lines = tier.lines if tier else []
    return ResearchTierOut(
        level=level,
        name=tier.name if tier else "",
        description=tier.description if tier else "",
        conditions=[_line_out(line) for line in lines if line.kind == "condition"],
        rewards=[_line_out(line) for line in lines if line.kind == "reward"],
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
        active=category.active,
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
    done = sum(c.completed for c in categories)
    active = next((c for c in categories if c.active), None)
    filled = {(t.category_id, t.level): t for c in categories for t in c.tiers}
    missing_conditions = missing_rewards = 0
    for category in categories:
        for level in range(1, category.tier_count + 1):
            lines = filled[(category.id, level)].lines if (category.id, level) in filled else []
            missing_conditions += not any(line.kind == "condition" for line in lines)
            missing_rewards += not any(line.kind == "reward" for line in lines)
    return SystemOverviewOut(
        id=RESEARCH,
        name=SYSTEMS[RESEARCH],
        stats=[
            OverviewStat(label="Paliers terminés", value=f"{done} / {total}", detail=f"{len(categories)} domaine(s)"),
            OverviewStat(
                label="Recherche en cours",
                value=active.name if active else "Aucune",
                detail=f"palier {active.completed + 1} / {active.tier_count}" if active else "",
            ),
        ],
        todo=[
            OverviewTodo(label="Paliers sans conditions", count=missing_conditions),
            OverviewTodo(label="Paliers sans récompenses", count=missing_rewards),
        ],
        updated_at=max((c.updated_at for c in categories), default=None),
    )


# -- gestion ------------------------------------------------------------------------------


async def _locked(session: AsyncSession, category_id: str) -> ResearchCategory | None:
    query = select(ResearchCategory).where(ResearchCategory.id == category_id).with_for_update()
    return (await session.execute(query)).scalar_one_or_none()


async def _describe(session: AsyncSession, lines: list[ResearchLine]) -> str:
    """Liste à puces : « 2 000 × Lingot de fer », « Avoir 10 membres »…"""
    ids = {line.item_id for line in lines if line.item_id}
    names = dict((await session.execute(select(Item.id, Item.name).where(Item.id.in_(ids)))).all()) if ids else {}
    bullets = []
    for line in lines:
        text = line.text or names.get(line.item_id, line.item_id or "")
        if line.text and line.item_id:
            text = f"{names.get(line.item_id, line.item_id)} — {line.text}"
        bullets.append(f"• {format_quantity(line.quantity)} × {text}" if line.quantity else f"• {text}")
    return "\n".join(bullets)


@admin_router.put("/categories/{category_id}", response_model=ResearchCategoryOut)
async def put_category(
    category_id: str, payload: ResearchCategoryIn, session: SessionDep, user: ResearchManager
) -> ResearchCategoryOut:
    if not CATEGORY_ID.match(category_id):
        raise HTTPException(422, "Identifiant invalide (minuscules, chiffres, _ et -, 32 caractères au plus).")
    if payload.completed > payload.tier_count:
        raise HTTPException(422, "Le nombre de paliers terminés dépasse le nombre de paliers.")
    if payload.active and payload.completed >= payload.tier_count:
        raise HTTPException(422, "Tous les paliers sont terminés : rien à rechercher dans ce domaine.")
    category = await _locked(session, category_id)
    created = category is None
    before_completed = 0 if created else category.completed
    was_active = False if created else category.active
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
    if payload.active and not was_active:
        await session.execute(
            update(ResearchCategory)
            .where(ResearchCategory.active, ResearchCategory.id != category_id)
            .values(active=False, updated_at=utcnow())
        )
        await session.flush()
    category.name = payload.name
    category.description = payload.description
    category.icon = payload.icon or "flask"
    category.position = payload.position
    category.tier_count = payload.tier_count
    category.completed = payload.completed
    category.active = payload.active
    category.skill_id = payload.skill_id or None
    category.updated_at = utcnow()

    changes = []
    if created:
        changes.append("créé")
    if payload.completed != before_completed:
        changes.append(f"paliers terminés {before_completed} → {payload.completed}")
    if payload.active != was_active:
        changes.append("recherche lancée" if payload.active else "recherche arrêtée")
    audit.record(
        session,
        user.id,
        RESEARCH,
        "research.category",
        "research",
        category_id,
        f"R&D {payload.name} : " + (", ".join(changes) or "modifié"),
    )
    if payload.notify:
        await _announce(session, category, before_completed, was_active, user.id)
    await session.commit()
    return category_out(await _reloaded(session, category_id))


async def _announce(
    session: AsyncSession, category: ResearchCategory, before_completed: int, was_active: bool, author_id
) -> None:
    tiers = {tier.level: tier for tier in category.tiers}
    if category.completed > before_completed:
        rewards = [
            line
            for level in range(before_completed + 1, category.completed + 1)
            for line in (tiers[level].lines if level in tiers else [])
            if line.kind == "reward"
        ]
        if category.completed - before_completed == 1:
            title = f"R&D {category.name} : palier {category.completed} terminé"
        else:
            title = f"R&D {category.name} : paliers {before_completed + 1} à {category.completed} terminés"
        body = "Récompenses :\n" + await _describe(session, rewards) if rewards else ""
        await post_message(
            session,
            system=RESEARCH,
            title=title,
            body=body,
            link_tool=RESEARCH,
            link_key=category.id,
            author_id=author_id,
        )
    if category.active and not was_active:
        level = category.completed + 1
        conditions = [line for line in (tiers[level].lines if level in tiers else []) if line.kind == "condition"]
        await post_message(
            session,
            system=RESEARCH,
            title=f"Recherche lancée : {category.name}, palier {level}",
            body="Conditions :\n" + await _describe(session, conditions) if conditions else "",
            link_tool=RESEARCH,
            link_key=f"{category.id}:{level}",
            author_id=author_id,
        )


@admin_router.put("/categories/{category_id}/tiers/{level}", response_model=ResearchCategoryOut)
async def put_tier(
    category_id: str, level: int, payload: ResearchTierIn, session: SessionDep, user: ResearchManager
) -> ResearchCategoryOut:
    category = await _locked(session, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Domaine « {category_id} » introuvable.")
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
            _fill(line, kind, position, data)
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


async def _reloaded(session: AsyncSession, category_id: str) -> ResearchCategory:
    query = select(ResearchCategory).where(ResearchCategory.id == category_id).execution_options(populate_existing=True)
    return (await session.execute(query)).scalar_one()


def _fill(line: ResearchLine, kind: str, position: int, data: ResearchLineIn) -> None:
    line.kind = kind
    line.position = position
    line.text = data.text
    line.quantity = data.quantity
    line.item_id = data.item_id
    line.progress = data.progress if kind == "condition" else None
    line.done = _is_done(kind, data.quantity, line.progress, data.done)


@admin_router.patch("/lines/{line_id}", response_model=ResearchCategoryOut)
async def patch_line(
    line_id: int, payload: ResearchLinePatch, session: SessionDep, user: ResearchManager
) -> ResearchCategoryOut:
    """Coche une condition ou met à jour son compteur (380 / 1 000) sans rouvrir tout le palier."""
    line = await session.get(ResearchLine, line_id, with_for_update=True)
    if line is None or line.kind != "condition":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Condition introuvable.")
    category = await _locked(session, line.category_id)
    tier_lines = (
        await session.execute(
            select(ResearchLine).where(
                ResearchLine.category_id == line.category_id,
                ResearchLine.level == line.level,
                ResearchLine.kind == "condition",
            )
        )
    ).scalars()
    conditions = list(tier_lines)
    was_complete = all(c.done for c in conditions)
    if payload.progress is not None:
        if line.quantity is None:
            raise HTTPException(422, "Cette condition n'a pas de quantité à suivre.")
        line.progress = payload.progress
        line.done = _is_done("condition", line.quantity, line.progress, payload.done or False)
    if payload.done is not None and payload.progress is None:
        line.done = payload.done
    category.updated_at = utcnow()
    label = line.text or line.item_id or "condition"
    if line.quantity is not None and line.progress is not None:
        state = f"{line.progress} / {line.quantity}"
    else:
        state = "remplie" if line.done else "à faire"
    audit.record(
        session,
        user.id,
        RESEARCH,
        "research.progress",
        "research",
        f"{line.category_id}:{line.level}",
        f"R&D {category.name}, palier {line.level} : {label} — {state}",
    )
    if conditions and not was_complete and all(c.done for c in conditions):
        await post_message(
            session,
            system=RESEARCH,
            title=f"R&D {category.name}, palier {line.level} : toutes les conditions sont remplies",
            body="Le palier peut être validé en jeu, puis marqué comme terminé dans Syncron.",
            audience="staff",
            link_tool=RESEARCH,
            link_key=f"{line.category_id}:{line.level}",
            author_id=user.id,
        )
    await session.commit()
    return category_out(await _reloaded(session, line.category_id))


@admin_router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: str, session: SessionDep, user: ResearchManager) -> None:
    category = await _locked(session, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Domaine « {category_id} » introuvable.")
    name = category.name
    await session.delete(category)
    audit.record(session, user.id, RESEARCH, "research.delete", "research", category_id, f"R&D supprimé : {name}")
    await session.commit()
