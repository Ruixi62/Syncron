"""Événements qui se répètent : chaque jour, chaque semaine (jours choisis), chaque mois.

Les dates sont calculées en heure locale du serveur de jeu : une réunion
« chaque samedi à 21 h » reste à 21 h, heure d'été comme heure d'hiver.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta

NONE, DAILY, WEEKLY, MONTHLY = "none", "daily", "weekly", "monthly"
WEEKDAY_NAMES = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MAX_OCCURRENCES = 1000


def days_mask(weekdays: list[int] | tuple[int, ...]) -> int:
    """[5] (samedi) -> 0b0100000. Lundi = 0."""
    mask = 0
    for weekday in weekdays:
        mask |= 1 << weekday
    return mask


def mask_days(mask: int) -> list[int]:
    return [weekday for weekday in range(7) if mask & (1 << weekday)]


@dataclass(frozen=True, slots=True)
class Rule:
    kind: str = NONE
    interval: int = 1
    days: int = 0
    until: date | None = None
    skipped: frozenset[date] = field(default_factory=frozenset)

    @property
    def repeats(self) -> bool:
        return self.kind != NONE

    def weekdays(self, first: date) -> list[int]:
        """Jours de la semaine d'une répétition hebdomadaire (par défaut : celui du premier événement)."""
        return mask_days(self.days) or [first.weekday()]

    def describe(self, first: date) -> str:
        """« Chaque samedi », « Un mardi et jeudi sur deux », « Chaque mois, le 14 »…"""
        if self.kind == DAILY:
            text = "Chaque jour" if self.interval == 1 else f"Tous les {self.interval} jours"
        elif self.kind == WEEKLY:
            names = [WEEKDAY_NAMES[d] for d in self.weekdays(first)]
            joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " et " + names[-1]
            if self.interval == 1:
                text = f"Chaque {joined}"
            elif self.interval == 2:
                text = f"Un {joined} sur deux"
            else:
                text = f"Toutes les {self.interval} semaines, le {joined}"
        elif self.kind == MONTHLY:
            every = "Chaque mois" if self.interval == 1 else f"Tous les {self.interval} mois"
            text = f"{every}, le {first.day}"
        else:
            return ""
        if self.until is not None:
            text += f", jusqu'au {self.until:%d/%m/%Y}"
        return text


def _candidates(rule: Rule, first: date, start: date, end: date) -> Iterator[date]:
    if rule.kind == DAILY:
        offset = max((start - first).days, 0)
        day = first + timedelta(days=offset - offset % rule.interval)
        while day <= end:
            yield day
            day += timedelta(days=rule.interval)
    elif rule.kind == WEEKLY:
        weekdays = rule.weekdays(first)
        first_monday = first - timedelta(days=first.weekday())
        monday = max(start, first) - timedelta(days=max(start, first).weekday())
        while monday <= end:
            if ((monday - first_monday).days // 7) % rule.interval == 0:
                for weekday in weekdays:
                    yield monday + timedelta(days=weekday)
            monday += timedelta(days=7)
    elif rule.kind == MONTHLY:
        months = max((start.year - first.year) * 12 + start.month - first.month, 0)
        months -= months % rule.interval
        while True:
            index = first.year * 12 + first.month - 1 + months
            year, month = divmod(index, 12)
            if date(year, month + 1, 1) > end:
                return
            with contextlib.suppress(ValueError):  # pas de 31 dans ce mois : on passe
                yield date(year, month + 1, first.day)
            months += rule.interval


def occurrences(rule: Rule, first: date, start: date, end: date) -> list[date]:
    """Dates (incluses) entre `start` et `end` où l'événement a lieu, `first` étant sa première date."""
    if not rule.repeats:
        return [first] if start <= first <= end and first not in rule.skipped else []
    last = min(end, rule.until) if rule.until else end
    result = []
    for day in _candidates(rule, first, start, last):
        if first <= day and start <= day <= last and day not in rule.skipped:
            result.append(day)
            if len(result) >= MAX_OCCURRENCES:
                break
    return sorted(set(result))
