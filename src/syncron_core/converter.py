"""Convertisseur : une quantité d'objets exprimée dans les grandeurs de NationsGlory.

Les contenants se comptent en emplacements d'inventaire :
    stack          1 emplacement        64 objets
    ligne          9 emplacements      576 objets
    coffre        27 emplacements    1 728 objets
    double coffre 54 emplacements    3 456 objets
Pour les objets qui s'empilent par 16 (perles de l'Ender…) ou pas du tout
(outils, armures…), la taille de pile change et tout le reste suit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from syncron_core.text import ceil_div, format_quantity, normalize

STACK_SIZES = (64, 16, 1)
MAX_QUANTITY = 10**15


class QuantityError(ValueError):
    """Saisie illisible."""


@dataclass(frozen=True, slots=True)
class Unit:
    id: str
    name: str
    plural: str
    slots: int

    def size(self, stack_size: int = 64) -> int:
        return self.slots * stack_size

    def label(self, count: int) -> str:
        return self.name if count == 1 else self.plural


STACK = Unit("stack", "stack", "stacks", 1)
LINE = Unit("ligne", "ligne", "lignes", 9)
CHEST = Unit("coffre", "coffre", "coffres", 27)
DOUBLE_CHEST = Unit("double_coffre", "double coffre", "doubles coffres", 54)
UNITS: tuple[Unit, ...] = (DOUBLE_CHEST, CHEST, LINE, STACK)


@dataclass(frozen=True, slots=True)
class Breakdown:
    """`quantity` = Σ count × taille + `remainder` (objets seuls, moins d'un stack)."""

    quantity: int
    stack_size: int
    parts: tuple[tuple[Unit, int], ...]
    remainder: int

    @property
    def slots(self) -> int:
        """Emplacements d'inventaire occupés."""
        return ceil_div(self.quantity, self.stack_size)

    def text(self) -> str:
        pieces = [f"{format_quantity(count)} {unit.label(count)}" for unit, count in self.parts if count]
        if self.remainder or not pieces:
            pieces.append(format_quantity(self.remainder))
        return " + ".join(pieces)


def _check(quantity: int, stack_size: int) -> None:
    if stack_size < 1:
        raise QuantityError("La taille de pile doit être au moins 1.")
    if quantity < 0:
        raise QuantityError("La quantité ne peut pas être négative.")
    if quantity > MAX_QUANTITY:
        raise QuantityError("Quantité trop grande.")


def decompose(quantity: int, stack_size: int = 64, units: tuple[Unit, ...] = UNITS) -> Breakdown:
    """Du plus grand contenant au plus petit : 5 000 → 1 double coffre + 2 lignes + 6 stacks + 8."""
    _check(quantity, stack_size)
    rest = quantity
    parts = []
    for unit in sorted(units, key=lambda u: u.slots, reverse=True):
        count, rest = divmod(rest, unit.size(stack_size))
        parts.append((unit, count))
    return Breakdown(quantity, stack_size, tuple(parts), rest)


def express(quantity: int, unit: Unit, stack_size: int = 64) -> float:
    """5 000 objets = 1,45 double coffre."""
    _check(quantity, stack_size)
    return quantity / unit.size(stack_size)


def containers_needed(quantity: int, unit: Unit, stack_size: int = 64) -> int:
    """Nombre de contenants pour tout ranger : 5 000 objets → 2 doubles coffres."""
    _check(quantity, stack_size)
    return ceil_div(quantity, unit.size(stack_size))


_ALIASES: dict[str, Unit | None] = {
    "": None,
    "u": None,
    "unite": None,
    "unites": None,
    "objet": None,
    "objets": None,
    "x": None,
    "s": STACK,
    "st": STACK,
    "stack": STACK,
    "stacks": STACK,
    "pile": STACK,
    "piles": STACK,
    "l": LINE,
    "ligne": LINE,
    "lignes": LINE,
    "c": CHEST,
    "coffre": CHEST,
    "coffres": CHEST,
    "dc": DOUBLE_CHEST,
    "double": DOUBLE_CHEST,
    "doubles": DOUBLE_CHEST,
    "double coffre": DOUBLE_CHEST,
    "doubles coffres": DOUBLE_CHEST,
    "double coffres": DOUBLE_CHEST,
}
_TERM = re.compile(r"(\d+(?:[.,]\d+)?)\s*([km]?)\s*([a-z ]*)")
_MULTIPLIERS = {"": 1, "k": 1_000, "m": 1_000_000}


def parse_quantity(text: str, stack_size: int = 64) -> int:
    """Saisie libre : « 5000 », « 5 000 », « 2,5k », « 3 coffres + 12 », « 1 dc 4 stacks »."""
    cleaned = normalize(text).replace(" ", "").replace(" ", "")
    cleaned = re.sub(r"(?<=\d) (?=\d{3}\b)", "", cleaned)
    if not cleaned.strip(" +"):
        raise QuantityError("Saisis une quantité.")
    total = 0
    position = 0
    for match in _TERM.finditer(cleaned):
        if cleaned[position : match.start()].strip(" +"):
            raise QuantityError(f"« {cleaned[position : match.start()].strip()} » n'est pas compris.")
        number, multiplier, unit_name = match.groups()
        unit_name = unit_name.strip()
        if unit_name not in _ALIASES:
            raise QuantityError(f"Unité inconnue : « {unit_name} ».")
        unit = _ALIASES[unit_name]
        value = float(number.replace(",", ".")) * _MULTIPLIERS[multiplier] * (unit.size(stack_size) if unit else 1)
        if value != int(value):
            raise QuantityError(f"« {match.group(0).strip()} » ne fait pas un nombre entier d'objets.")
        total += int(value)
        position = match.end()
    if cleaned[position:].strip(" +"):
        raise QuantityError(f"« {cleaned[position:].strip()} » n'est pas compris.")
    _check(total, stack_size)
    return total
