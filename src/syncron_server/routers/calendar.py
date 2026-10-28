"""Calendrier du pays : réunions, guerres, événements, économie.

Lecture : tout compte connecté, par période. Gestion : administrateurs et
éditeurs à qui le calendrier est confié ; « prévenir » publie un message
dans la messagerie de tout le pays.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server import audit
from syncron_server.deps import CalendarManager, SessionDep, UserDep
from syncron_server.messaging import post_message
from syncron_server.models import CalendarEvent, User, utcnow
from syncron_server.schemas import EventIn, EventOut, OverviewStat, SystemOverviewOut
from syncron_server.systems import CALENDAR, SYSTEMS, overview_provider

router = APIRouter(prefix="/api/v1/calendar", tags=["calendrier"])
admin_router = APIRouter(prefix="/api/v1/admin/calendar", tags=["calendrier (gestion)"])
MAX_RANGE = timedelta(days=400)
GAME_TIMEZONE = ZoneInfo("Europe/Paris")  # NationsGlory est un serveur français
CATEGORY_LABELS = {
    "meeting": "Réunion",
    "war": "Guerre",
    "event": "Événement",
    "economy": "Économie",
    "other": "Autre",
}
WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def _out(event: CalendarEvent, author: str | None) -> EventOut:
    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        category=event.category,
        location=event.location,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        all_day=event.all_day,
        author=author,
        updated_at=event.updated_at,
    )


def _overlapping(start: datetime, end: datetime):
    """Événements qui touchent [start, end[ (un événement sans fin dure un instant)."""
    return and_(
        CalendarEvent.starts_at < end,
        or_(CalendarEvent.ends_at >= start, and_(CalendarEvent.ends_at.is_(None), CalendarEvent.starts_at >= start)),
    )


@router.get("/events", response_model=list[EventOut])
async def events(
    session: SessionDep, _user: UserDep, start: datetime = Query(...), end: datetime = Query(...)
) -> list[EventOut]:
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "Les dates doivent préciser leur fuseau horaire.")
    if end <= start or end - start > MAX_RANGE:
        raise HTTPException(422, "Période invalide (400 jours au plus).")
    query = (
        select(CalendarEvent, User.username)
        .outerjoin(User, User.id == CalendarEvent.created_by)
        .where(_overlapping(start, end))
        .order_by(CalendarEvent.starts_at, CalendarEvent.title)
        .limit(2000)
    )
    rows = (await session.execute(query)).all()
    return [_out(event, author) for event, author in rows]


@router.get("/events/{event_id}", response_model=EventOut)
async def event(event_id: uuid.UUID, session: SessionDep, _user: UserDep) -> EventOut:
    row = (
        await session.execute(
            select(CalendarEvent, User.username)
            .outerjoin(User, User.id == CalendarEvent.created_by)
            .where(CalendarEvent.id == event_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Événement introuvable.")
    return _out(*row)


@overview_provider(CALENDAR)
async def overview(session: AsyncSession) -> SystemOverviewOut:
    now = utcnow()
    upcoming = (
        await session.execute(
            select(func.count()).select_from(CalendarEvent).where(_overlapping(now, now + timedelta(days=30)))
        )
    ).scalar_one()
    following = (
        await session.execute(
            select(CalendarEvent).where(CalendarEvent.starts_at >= now).order_by(CalendarEvent.starts_at).limit(1)
        )
    ).scalar_one_or_none()
    updated = (await session.execute(select(func.max(CalendarEvent.updated_at)))).scalar_one()
    return SystemOverviewOut(
        id=CALENDAR,
        name=SYSTEMS[CALENDAR],
        stats=[
            OverviewStat(label="Dans les 30 jours", value=str(upcoming), detail="événement(s)"),
            OverviewStat(
                label="Prochain",
                value=following.title if following else "Rien de prévu",
                detail=_when(following) if following else "",
            ),
        ],
        updated_at=updated,
    )


def _when(event: CalendarEvent) -> str:
    """Date lisible pour les messages, à l'heure du serveur de jeu."""
    moment = event.starts_at.astimezone(GAME_TIMEZONE)
    day = f"{WEEKDAYS[moment.weekday()]} {moment.day} {MONTHS[moment.month - 1]}"
    return day if event.all_day else f"{day} à {moment:%H:%M}"


# -- gestion ------------------------------------------------------------------------------


def _apply(event: CalendarEvent, payload: EventIn) -> None:
    event.title = payload.title
    event.description = payload.description
    event.category = payload.category
    event.location = payload.location
    event.starts_at = payload.starts_at
    event.ends_at = payload.ends_at
    event.all_day = payload.all_day
    event.updated_at = utcnow()


async def _notify(session: AsyncSession, event: CalendarEvent, verb: str, author_id: uuid.UUID) -> None:
    lines = [f"{CATEGORY_LABELS[event.category]} — {_when(event)}"]
    if event.location:
        lines.append(f"Lieu : {event.location}")
    if event.description:
        lines += ["", event.description]
    await post_message(
        session,
        system=CALENDAR,
        title=f"{verb} : {event.title}",
        body="\n".join(lines),
        link_tool=CALENDAR,
        link_key=str(event.id),
        author_id=author_id,
    )


@admin_router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(payload: EventIn, session: SessionDep, user: CalendarManager) -> EventOut:
    event = CalendarEvent(created_by=user.id, created_at=utcnow())
    _apply(event, payload)
    session.add(event)
    await session.flush()
    audit.record(session, user.id, CALENDAR, "event.create", "event", str(event.id), f"Événement créé : {event.title}")
    if payload.notify:
        await _notify(session, event, "Nouvel événement", user.id)
    await session.commit()
    return _out(event, user.username)


async def _get(session: AsyncSession, event_id: uuid.UUID) -> CalendarEvent:
    event = await session.get(CalendarEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Événement introuvable.")
    return event


@admin_router.put("/events/{event_id}", response_model=EventOut)
async def update_event(event_id: uuid.UUID, payload: EventIn, session: SessionDep, user: CalendarManager) -> EventOut:
    event = await _get(session, event_id)
    _apply(event, payload)
    audit.record(
        session, user.id, CALENDAR, "event.update", "event", str(event.id), f"Événement modifié : {event.title}"
    )
    if payload.notify:
        await _notify(session, event, "Événement modifié", user.id)
    await session.commit()
    author = await session.get(User, event.created_by) if event.created_by else None
    return _out(event, author.username if author else None)


@admin_router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID, session: SessionDep, user: CalendarManager, notify: bool = Query(False)
) -> None:
    event = await _get(session, event_id)
    if notify:
        await post_message(
            session,
            system=CALENDAR,
            title=f"Événement annulé : {event.title}",
            body=f"{CATEGORY_LABELS[event.category]} prévu {_when(event)}.",
            author_id=user.id,
        )
    audit.record(
        session, user.id, CALENDAR, "event.delete", "event", str(event.id), f"Événement supprimé : {event.title}"
    )
    await session.delete(event)
    await session.commit()
