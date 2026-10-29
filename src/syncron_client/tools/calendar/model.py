"""Événements du calendrier côté client (heure locale), catégories et grille du mois."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from syncron_client.ui.format import parse_datetime
from syncron_client.ui.theme import COLORS
from syncron_core.recurrence import NONE, Rule


@dataclass(frozen=True, slots=True)
class Category:
    id: str
    label: str
    tone: str
    color: str


CATEGORIES: dict[str, Category] = {
    "meeting": Category("meeting", "Réunion", "info", COLORS.info),
    "war": Category("war", "Guerre", "danger", COLORS.danger),
    "event": Category("event", "Événement", "accent", COLORS.accent),
    "economy": Category("economy", "Économie", "success", COLORS.success),
    "other": Category("other", "Autre", "violet", COLORS.violet),
}


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    title: str
    description: str
    category: Category
    location: str
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    author: str | None
    rule: Rule = field(default_factory=Rule)
    occurrence: date | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Event:
        return cls(
            id=str(raw["id"]),
            title=raw["title"],
            description=raw.get("description") or "",
            category=CATEGORIES.get(raw.get("category", "other"), CATEGORIES["other"]),
            location=raw.get("location") or "",
            starts_at=parse_datetime(raw["starts_at"]),
            ends_at=parse_datetime(raw.get("ends_at")),
            all_day=bool(raw.get("all_day")),
            author=raw.get("author"),
            rule=Rule(
                raw.get("recurrence") or NONE,
                int(raw.get("recurrence_interval") or 1),
                int(raw.get("recurrence_days") or 0),
                date.fromisoformat(raw["recurrence_until"]) if raw.get("recurrence_until") else None,
                frozenset(date.fromisoformat(day) for day in raw.get("skipped_dates") or []),
            ),
            occurrence=date.fromisoformat(raw["occurrence"]) if raw.get("occurrence") else None,
        )

    @property
    def key(self) -> str:
        """Identifiant d'affichage : une série a une clé par date."""
        return f"{self.id}:{self.occurrence.isoformat()}" if self.occurrence else self.id

    @property
    def recurring(self) -> bool:
        return self.rule.repeats

    @property
    def recurrence_text(self) -> str:
        return self.rule.describe(self.first_day)

    @property
    def first_day(self) -> date:
        return self.starts_at.date()

    @property
    def last_day(self) -> date:
        return (self.ends_at or self.starts_at).date()

    def occurs_on(self, day: date) -> bool:
        return self.first_day <= day <= self.last_day

    def time_text(self, day: date | None = None) -> str:
        if self.all_day:
            if self.first_day == self.last_day:
                return "Journée entière"
            return f"Du {self.first_day:%d/%m} au {self.last_day:%d/%m}"
        start = f"{self.starts_at:%H:%M}"
        if self.ends_at is None:
            return start
        if self.first_day == self.last_day:
            return f"{start} – {self.ends_at:%H:%M}"
        return f"{self.starts_at:%d/%m} {start} → {self.ends_at:%d/%m} {self.ends_at:%H:%M}"


def month_grid(year: int, month: int) -> list[date]:
    """42 jours (6 semaines, lundi en premier) qui couvrent le mois."""
    first = date(year, month, 1)
    start = first - timedelta(days=first.weekday())
    return [start + timedelta(days=offset) for offset in range(42)]


def grid_range(year: int, month: int) -> tuple[datetime, datetime]:
    days = month_grid(year, month)
    start = datetime.combine(days[0], time.min).astimezone()
    end = datetime.combine(days[-1] + timedelta(days=1), time.min).astimezone()
    return start, end


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def events_on(events: list[Event], day: date) -> list[Event]:
    return sorted((e for e in events if e.occurs_on(day)), key=lambda e: (not e.all_day, e.starts_at, e.title))
