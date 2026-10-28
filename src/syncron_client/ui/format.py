"""Mise en forme française des dates et des durées relatives."""

from __future__ import annotations

from datetime import date, datetime

WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
WEEKDAYS_SHORT = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
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


def parse_datetime(value: str | None) -> datetime | None:
    """ISO 8601 de l'API -> datetime à l'heure locale."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def format_datetime(value: str | None) -> str:
    moment = parse_datetime(value)
    return moment.strftime("%d/%m/%Y %H:%M") if moment else (value or "—")


def long_date(day: date) -> str:
    """samedi 14 novembre 2026"""
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]} {day.year}"


def month_title(year: int, month: int) -> str:
    name = MONTHS[month - 1]
    return f"{name[0].upper()}{name[1:]} {year}"


def relative_time(value: str | None, now: datetime | None = None) -> str:
    """« à l'instant », « il y a 5 min », « hier à 21:04 », « 14/11 à 21:04 »."""
    moment = parse_datetime(value)
    if moment is None:
        return "—"
    now = now or datetime.now().astimezone()
    seconds = (now - moment).total_seconds()
    if seconds < 60:
        return "à l'instant"
    if seconds < 3600:
        return f"il y a {int(seconds // 60)} min"
    if moment.date() == now.date():
        return f"aujourd'hui à {moment:%H:%M}"
    if (now.date() - moment.date()).days == 1:
        return f"hier à {moment:%H:%M}"
    if moment.year == now.year:
        return f"{moment:%d/%m} à {moment:%H:%M}"
    return f"{moment:%d/%m/%Y}"
