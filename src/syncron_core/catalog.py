"""Catalogue en mémoire : objets, ateliers, compétences, et son index.

`CraftData` est la forme d'échange (immuable) ; `CraftRepository` l'indexe pour
les recherches rapides. Le client le remplit depuis l'API, le serveur depuis la
base, les tests depuis des listes.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from syncron_core.models.item import Item
from syncron_core.models.reference import Skill, Station

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,79}$")
ID_RULE = "minuscules, chiffres, « _ », « - » ou « . » ; 80 caractères maximum ; commence par une lettre ou un chiffre"


def is_valid_id(value: str) -> bool:
    return bool(ID_PATTERN.match(value))


@dataclass(frozen=True, slots=True)
class CraftData:
    items: tuple[Item, ...] = ()
    stations: tuple[Station, ...] = ()
    skills: tuple[Skill, ...] = ()


@runtime_checkable
class ItemLookup(Protocol):
    """Ce dont le calculateur a besoin, et rien de plus."""

    def get(self, item_id: str) -> Item | None: ...


class CraftRepository:
    def __init__(self, data: CraftData | None = None) -> None:
        self._items: dict[str, Item] = {}
        self._stations: dict[str, Station] = {}
        self._skills: dict[str, Skill] = {}
        self._consumers: dict[str, tuple[str, ...]] = {}
        self.replace(data or CraftData())

    def replace(self, data: CraftData) -> None:
        self._items = {item.id: item for item in data.items}
        self._stations = {station.id: station for station in data.stations}
        self._skills = {skill.id: skill for skill in data.skills}
        reverse: dict[str, list[str]] = {}
        for item in self._items.values():
            for ingredient_id in item.ingredient_ids:
                reverse.setdefault(ingredient_id, []).append(item.id)
        self._consumers = {key: tuple(value) for key, value in reverse.items()}

    def snapshot(self) -> CraftData:
        return CraftData(tuple(self._items.values()), tuple(self._stations.values()), tuple(self._skills.values()))

    def get(self, item_id: str) -> Item | None:
        return self._items.get(item_id)

    def all(self) -> tuple[Item, ...]:
        return tuple(self._items.values())

    def consumers_of(self, item_id: str) -> tuple[str, ...]:
        return self._consumers.get(item_id, ())

    def station(self, station_id: str) -> Station | None:
        return self._stations.get(station_id)

    def stations(self) -> tuple[Station, ...]:
        return tuple(self._stations.values())

    def skill(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def skills(self) -> tuple[Skill, ...]:
        return tuple(self._skills.values())

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._items

    def __iter__(self) -> Iterator[Item]:
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)
