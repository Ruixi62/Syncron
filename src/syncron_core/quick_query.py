"""Saisie rapide : « Machine X x10 », « machine x ×10 », « 10 Machine X », « 10x Machine X »."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SUFFIX = re.compile(r"^(?P<name>.+?)\s*[x×*]\s*(?P<qty>\d+)\s*$", re.IGNORECASE)
_PREFIX = re.compile(r"^(?P<qty>\d+)\s*(?:[x×*]\s*|\s+)(?P<name>\D.*?)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class QuickQuery:
    text: str
    quantity: int | None


def parse_quick_query(raw: str) -> QuickQuery:
    stripped = raw.strip()
    for pattern in (_SUFFIX, _PREFIX):
        match = pattern.match(stripped)
        if match:
            quantity = int(match.group("qty"))
            if quantity >= 1:
                return QuickQuery(match.group("name").strip(), quantity)
    return QuickQuery(stripped, None)
