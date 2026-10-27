"""Durées de fabrication : saisie souple dans les JSON, affichage lisible.

Saisie acceptée :
    0, "instant", "instantané"         -> 0 s
    45                                 -> 45 s (entier = secondes)
    "30s", "5m", "5min", "2h", "1j"    -> unités s / m|min / h / j|d
    "1h30", "1h 30m", "2h15m10s"       -> combinaisons (un nombre nu après "h" = minutes)
"""

from __future__ import annotations

import re

_UNITS = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "j": 86_400, "d": 86_400}
_INSTANT = {"0", "instant", "instantane", "instantané", "immediat", "immédiat"}
_TOKEN = re.compile(r"(\d+)\s*(min|sec|[smhjd])?", re.IGNORECASE)
_VALID = re.compile(r"^(\s*\d+\s*(min|sec|[smhjd])?)+\s*$", re.IGNORECASE)
_NEXT_UNIT = {"j": "h", "d": "h", "h": "m", "m": "s", "min": "s"}


class DurationError(ValueError):
    pass


def parse_duration(value: object) -> int:
    """Convertit une saisie en secondes. Lève DurationError si illisible."""
    if isinstance(value, bool):
        raise DurationError(f"Durée invalide : {value!r}")
    if isinstance(value, int):
        if value < 0:
            raise DurationError(f"Durée négative : {value}")
        return value
    if not isinstance(value, str):
        raise DurationError(f"Durée invalide : {value!r}")
    text = value.strip().casefold()
    if text in _INSTANT:
        return 0
    if not text or not _VALID.match(text):
        raise DurationError(f"Durée illisible : « {value} » (ex. : 30s, 5m, 1h30, 2h15m).")
    total, previous_unit = 0, None
    for number, unit in _TOKEN.findall(text):
        unit = unit.casefold()
        if not unit:
            if previous_unit is None:
                unit = "s"
            elif previous_unit in _NEXT_UNIT:
                unit = _NEXT_UNIT[previous_unit]
            else:
                raise DurationError(f"Durée ambiguë : « {value} ».")
        total += int(number) * _UNITS[unit]
        previous_unit = unit
    return total


def format_duration(seconds: int, compact: bool = False) -> str:
    """0 -> 'Instantané' ; 90 -> '1 min 30 s' ; 5400 -> '1 h 30 min' ; 93600 -> '1 j 2 h'."""
    if seconds <= 0:
        return "Instantané"
    days, rest = divmod(seconds, 86_400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    parts = [(days, "j"), (hours, "h"), (minutes, "min"), (secs, "s")]
    shown = [f"{amount} {unit}" for amount, unit in parts if amount]
    limit = 2 if compact or days else 3
    return " ".join(shown[:limit])
