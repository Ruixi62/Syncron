"""Calendrier du pays : réunions, guerres, événements, économie.

Lecture : tout compte connecté, par période ; les événements qui se répètent
sont déroulés en occurrences (une par date). Gestion : administrateurs et
éditeurs à qui le calendrier est confié ; « prévenir » publie un message
dans la messagerie de tout le pays.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_core.recurrence import Rule, occurrences
from syncron_server import audit
from syncron_server.deps import CalendarManager, SessionDep, UserDep
from syncron_server.messaging import post_message
from syncron_server.models import CalendarEvent, User, utcnow
from syncron_server.schemas import EventIn, EventOut, OverviewStat, SkipIn, SystemOverviewOut
from syncron_server.systems import CALENDAR, SYSTEMS, overview_provider

router = APIRouter(prefix="/api/v1/calendar", tags=["calendrier"])
admin_router = APIRouter(prefix="/api/v1/admin/calendar", tags=["calendrier (gestion)"])
MAX_RANGE = timedelta(days=400)
MAX_RESULTS = 2000
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


# -- règles et occurrences ----------------------------------------------------------------


def rule_of(event: CalendarEvent) -> Rule:
    skipped = frozenset(date.fromisoformat(day) for day in event.skipped_dates or [])
    return Rule(event.recurrence, event.recurrence_interval, event.recurrence_days, event.recurrence_until, skipped)


def _local(moment: datetime) -> datetime:
    return moment.astimezone(GAME_TIMEZONE)


def occurrence_period(event: CalendarEvent, day: date) -> tuple[datetime, datetime | None]:
    """Début et fin de l'occurrence du jour `day`, à la même heure locale que la première."""
    first = _local(event.starts_at)
    start = datetime.combine(day, first.timetz().replace(tzinfo=None), GAME_TIMEZONE)
    end = start + (event.ends_at - event.starts_at) if event.ends_at else None
    return start, end


def expand(event: CalendarEvent, start: datetime, end: datetime) -> list[tuple[date | None, datetime, datetime | None]]:
    """(date d'occurrence ou None, début, fin) des passages de l'événement dans [start, end[."""
    if event.recurrence == "none":
        return [(None, event.starts_at, event.ends_at)]
    duration = (event.ends_at - event.starts_at) if event.ends_at else timedelta(0)
    first_day = _local(event.starts_at).date()
    window_start = (_local(start) - duration).date() - timedelta(days=1)
    window_end = _local(end).date()
    result = []
    for day in occurrences(rule_of(event), first_day, window_start, window_end):
        begins, ends = occurrence_period(event, day)
        if begins < end and (ends or begins) >= start:
            result.append((day, begins, ends))
    return result


def _out(event: CalendarEvent, author: str | None, occurrence=None) -> EventOut:
    day, starts_at, ends_at = occurrence or (None, event.starts_at, event.ends_at)
    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        category=event.category,
        location=event.location,
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=event.all_day,
        recurrence=event.recurrence,
        recurrence_interval=event.recurrence_interval,
        recurrence_days=event.recurrence_days,
        recurrence_until=event.recurrence_until,
        skipped_dates=sorted(date.fromisoformat(d) for d in event.skipped_dates or []),
        occurrence=day,
        author=author,
        updated_at=event.updated_at,
    )


def _candidates(start: datetime, end: datetime):
    """Événements simples qui touchent [start, end[ ; séries commencées avant `end` et pas encore finies."""
    single = and_(
        CalendarEvent.recurrence == "none",
        CalendarEvent.starts_at < end,
        or_(CalendarEvent.ends_at >= start, and_(CalendarEvent.ends_at.is_(None), CalendarEvent.starts_at >= start)),
    )
    series = and_(
        CalendarEvent.recurrence != "none",
        CalendarEvent.starts_at < end,
        or_(CalendarEvent.recurrence_until.is_(None), CalendarEvent.recurrence_until >= _local(start).date()),
    )
    return or_(single, series)


async def _in_range(session: AsyncSession, start: datetime, end: datetime) -> list[tuple[CalendarEvent, str | None]]:
    query = (
        select(CalendarEvent, User.username)
        .outerjoin(User, User.id == CalendarEvent.created_by)
        .where(_candidates(start, end))
        .order_by(CalendarEvent.starts_at, CalendarEvent.title)
    )
    return list((await session.execute(query)).all())


@router.get("/events", response_model=list[EventOut])
async def events(
    session: SessionDep, _user: UserDep, start: datetime = Query(...), end: datetime = Query(...)
) -> list[EventOut]:
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "Les dates doivent préciser leur fuseau horaire.")
    if end <= start or end - start > MAX_RANGE:
        raise HTTPException(422, "Période invalide (400 jours au plus).")
    result = []
    for event, author in await _in_range(session, start, end):
        result += [_out(event, author, occurrence) for occurrence in expand(event, start, end)]
    result.sort(key=lambda e: (e.starts_at, e.title))
    return result[:MAX_RESULTS]


def next_occurrence(event: CalendarEvent, after: datetime) -> tuple[date | None, datetime, datetime | None] | None:
    """Prochain passage (en cours ou à venir) ; None si la série est terminée."""
    if event.recurrence == "none":
        return (None, event.starts_at, event.ends_at) if (event.ends_at or event.starts_at) >= after else None
    upcoming = expand(event, after, after + MAX_RANGE)
    return upcoming[0] if upcoming else None


@router.get("/events/{event_id}", response_model=EventOut)
async def event(event_id: uuid.UUID, session: SessionDep, _user: UserDep) -> EventOut:
    """Pour une série : son prochain passage (ou le premier s'il n'y en a plus)."""
    row = (
        await session.execute(
            select(CalendarEvent, User.username)
            .outerjoin(User, User.id == CalendarEvent.created_by)
            .where(CalendarEvent.id == event_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Événement introuvable.")
    found, author = row
    if found.recurrence == "none":
        return _out(found, author)
    return _out(found, author, next_occurrence(found, utcnow()))


@overview_provider(CALENDAR)
async def overview(session: AsyncSession) -> SystemOverviewOut:
    now = utcnow()
    horizon = now + timedelta(days=30)
    upcoming = []
    for item, _author in await _in_range(session, now, horizon):
        upcoming += [(begins, item) for _day, begins, _ends in expand(item, now, horizon) if begins >= now]
    upcoming.sort(key=lambda pair: pair[0])
    updated = (await session.execute(select(func.max(CalendarEvent.updated_at)))).scalar_one()
    following = upcoming[0] if upcoming else None
    return SystemOverviewOut(
        id=CALENDAR,
        name=SYSTEMS[CALENDAR],
        stats=[
            OverviewStat(label="Dans les 30 jours", value=str(len(upcoming)), detail="date(s) prévue(s)"),
            OverviewStat(
                label="Prochain",
                value=following[1].title if following else "Rien de prévu",
                detail=_when_at(following[0], following[1].all_day) if following else "",
            ),
        ],
        updated_at=updated,
    )


def _when_at(moment: datetime, all_day: bool) -> str:
    """Date lisible pour les messages, à l'heure du serveur de jeu."""
    local = _local(moment)
    day = f"{WEEKDAYS[local.weekday()]} {local.day} {MONTHS[local.month - 1]}"
    return day if all_day else f"{day} à {local:%H:%M}"


def _when(event: CalendarEvent) -> str:
    first = _when_at(event.starts_at, event.all_day)
    if event.recurrence == "none":
        return first
    rule = rule_of(event).describe(_local(event.starts_at).date())
    hour = "" if event.all_day else f" à {_local(event.starts_at):%H:%M}"
    return f"{rule}{hour} (à partir du {first})"


# -- gestion ------------------------------------------------------------------------------


def _apply(event: CalendarEvent, payload: EventIn) -> None:
    event.title = payload.title
    event.description = payload.description
    event.category = payload.category
    event.location = payload.location
    event.starts_at = payload.starts_at
    event.ends_at = payload.ends_at
    event.all_day = payload.all_day
    event.recurrence = payload.recurrence
    event.recurrence_interval = payload.recurrence_interval
    event.recurrence_days = payload.recurrence_days
    event.recurrence_until = payload.recurrence_until
    if payload.recurrence == "none":
        event.skipped_dates = []
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


async def _author_name(session: AsyncSession, event: CalendarEvent) -> str | None:
    author = await session.get(User, event.created_by) if event.created_by else None
    return author.username if author else None


ADMIN_HISTORY = timedelta(days=60)


@admin_router.get("/events", response_model=list[EventOut])
async def series(session: SessionDep, _user: CalendarManager) -> list[EventOut]:
    """Fiches à gérer : événements des 60 derniers jours et à venir, séries en cours (une ligne par série)."""
    since = utcnow() - ADMIN_HISTORY
    query = (
        select(CalendarEvent, User.username)
        .outerjoin(User, User.id == CalendarEvent.created_by)
        .where(
            or_(
                and_(
                    CalendarEvent.recurrence != "none",
                    or_(CalendarEvent.recurrence_until.is_(None), CalendarEvent.recurrence_until >= since.date()),
                ),
                func.coalesce(CalendarEvent.ends_at, CalendarEvent.starts_at) >= since,
            )
        )
        .order_by(CalendarEvent.starts_at.desc())
        .limit(500)
    )
    return [_out(event, author) for event, author in (await session.execute(query)).all()]


@admin_router.get("/events/{event_id}", response_model=EventOut)
async def series_event(event_id: uuid.UUID, session: SessionDep, _user: CalendarManager) -> EventOut:
    """La fiche telle qu'enregistrée (pour une série : sa première date et sa règle)."""
    found = await session.get(CalendarEvent, event_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Événement introuvable.")
    return _out(found, await _author_name(session, found))


@admin_router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(payload: EventIn, session: SessionDep, user: CalendarManager) -> EventOut:
    event = CalendarEvent(created_by=user.id, created_at=utcnow(), skipped_dates=[])
    _apply(event, payload)
    session.add(event)
    await session.flush()
    audit.record(session, user.id, CALENDAR, "event.create", "event", str(event.id), f"Événement créé : {event.title}")
    if payload.notify:
        await _notify(session, event, "Nouvel événement", user.id)
    await session.commit()
    return _out(event, user.username)


async def _get(session: AsyncSession, event_id: uuid.UUID) -> CalendarEvent:
    event = await session.get(CalendarEvent, event_id, with_for_update=True)
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
    return _out(event, await _author_name(session, event))


@admin_router.post("/events/{event_id}/skip", response_model=EventOut)
async def skip_occurrence(event_id: uuid.UUID, payload: SkipIn, session: SessionDep, user: CalendarManager) -> EventOut:
    """Annule (ou rétablit) une date d'une série, sans toucher aux autres."""
    event = await _get(session, event_id)
    if event.recurrence == "none":
        raise HTTPException(422, "Cet événement ne se répète pas : modifie-le ou supprime-le.")
    skipped = set(event.skipped_dates or [])
    day = payload.day.isoformat()
    if payload.skipped and day not in skipped:
        if not occurrences(rule_of(event), _local(event.starts_at).date(), payload.day, payload.day):
            raise HTTPException(422, "Cet événement n'a pas lieu ce jour-là.")
        skipped.add(day)
    elif not payload.skipped:
        skipped.discard(day)
    event.skipped_dates = sorted(skipped)
    event.updated_at = utcnow()
    begins, _ends = occurrence_period(event, payload.day)
    action = "annulé" if payload.skipped else "rétabli"
    audit.record(
        session,
        user.id,
        CALENDAR,
        "event.skip",
        "event",
        str(event.id),
        f"Événement {action} le {payload.day:%d/%m/%Y} : {event.title}",
    )
    if payload.notify:
        await post_message(
            session,
            system=CALENDAR,
            title=f"{'Annulé' if payload.skipped else 'Rétabli'} : {event.title}, {_when_at(begins, event.all_day)}",
            body=f"Seule cette date est concernée. {rule_of(event).describe(_local(event.starts_at).date())}.",
            link_tool=CALENDAR,
            link_key=str(event.id),
            author_id=user.id,
        )
    await session.commit()
    return _out(event, await _author_name(session, event))


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
            body=f"{CATEGORY_LABELS[event.category]} prévu : {_when(event)}.",
            author_id=user.id,
        )
    audit.record(
        session, user.id, CALENDAR, "event.delete", "event", str(event.id), f"Événement supprimé : {event.title}"
    )
    await session.delete(event)
    await session.commit()
