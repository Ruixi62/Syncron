"""Répétition des événements : dates produites, exceptions, fin, description."""

from __future__ import annotations

from datetime import date

from syncron_core.recurrence import DAILY, MONTHLY, NONE, WEEKLY, Rule, days_mask, mask_days, occurrences

FIRST = date(2026, 11, 7)  # un samedi


def test_weekly_on_the_first_weekday_by_default():
    rule = Rule(WEEKLY)
    assert occurrences(rule, FIRST, date(2026, 11, 1), date(2026, 11, 30)) == [
        date(2026, 11, 7),
        date(2026, 11, 14),
        date(2026, 11, 21),
        date(2026, 11, 28),
    ]
    assert rule.describe(FIRST) == "Chaque samedi"


def test_weekly_several_days_every_two_weeks_with_skip_and_end():
    rule = Rule(WEEKLY, 2, days_mask([1, 3]), date(2026, 12, 3), frozenset({date(2026, 11, 19)}))
    first = date(2026, 11, 3)
    assert occurrences(rule, first, date(2026, 11, 1), date(2026, 12, 31)) == [
        date(2026, 11, 3),
        date(2026, 11, 5),
        date(2026, 11, 17),
        date(2026, 12, 1),
        date(2026, 12, 3),
    ]
    assert rule.describe(first) == "Un mardi et jeudi sur deux, jusqu'au 03/12/2026"
    assert mask_days(days_mask([1, 3])) == [1, 3]


def test_never_before_the_first_date():
    assert occurrences(Rule(DAILY, 3), FIRST, date(2026, 10, 1), date(2026, 11, 13)) == [
        date(2026, 11, 7),
        date(2026, 11, 10),
        date(2026, 11, 13),
    ]


def test_monthly_skips_short_months():
    first = date(2026, 1, 31)
    days = occurrences(Rule(MONTHLY), first, date(2026, 1, 1), date(2026, 6, 30))
    assert days == [date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31)]
    assert Rule(MONTHLY, 2).describe(first) == "Tous les 2 mois, le 31"


def test_single_event():
    assert occurrences(Rule(NONE), FIRST, date(2026, 11, 1), date(2026, 11, 30)) == [FIRST]
    assert occurrences(Rule(NONE), FIRST, date(2026, 12, 1), date(2026, 12, 30)) == []
    assert Rule(NONE).describe(FIRST) == ""
