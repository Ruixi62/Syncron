"""Consultation du catalogue : liste, recherche, référentiels, usages."""

from __future__ import annotations

from syncron_core.catalog import CraftRepository
from syncron_core.models.item import Item, ItemType
from syncron_core.models.reference import Skill, Station
from syncron_core.text import normalize

UNSPECIFIED_STATION = "Atelier non précisé"


class CatalogService:
    def __init__(self, repository: CraftRepository) -> None:
        self._repository = repository

    # -- objets ------------------------------------------------------------------

    def get(self, item_id: str) -> Item | None:
        return self._repository.get(item_id)

    def display_name(self, item_id: str) -> str:
        item = self._repository.get(item_id)
        return item.name if item else item_id

    def list_items(self) -> list[Item]:
        return sorted(self._repository.all(), key=lambda item: (normalize(item.name), item.id))

    def categories(self) -> list[str]:
        return sorted({item.category for item in self._repository.all() if item.category}, key=normalize)

    def search(
        self,
        query: str,
        item_type: ItemType | None = None,
        category: str | None = None,
        station_id: str | None = None,
    ) -> list[Item]:
        """Insensible à la casse et aux accents ; chaque mot doit apparaître
        dans le nom ou l'identifiant."""
        tokens = normalize(query).split()
        return [
            item
            for item in self.list_items()
            if (item_type is None or item.type is item_type)
            and (not category or item.category == category)
            and (not station_id or item.station_id == station_id)
            and matches(item, tokens)
        ]

    def resolve(self, text: str) -> Item | None:
        """Correspondance exacte (nom ou id), sinon premier résultat de recherche."""
        wanted = normalize(text)
        if not wanted:
            return None
        for item in self._repository.all():
            if normalize(item.name) == wanted or normalize(item.id) == wanted:
                return item
        results = self.search(text)
        return results[0] if results else None

    def used_in(self, item_id: str) -> list[Item]:
        consumers = (self._repository.get(i) for i in self._repository.consumers_of(item_id))
        return sorted((item for item in consumers if item), key=lambda item: normalize(item.name))

    def count(self) -> int:
        return len(self._repository)

    # -- référentiels --------------------------------------------------------

    def station(self, station_id: str | None) -> Station | None:
        return self._repository.station(station_id) if station_id else None

    def station_name(self, station_id: str | None) -> str:
        if not station_id:
            return UNSPECIFIED_STATION
        station = self._repository.station(station_id)
        return station.name if station else station_id

    def stations(self) -> list[Station]:
        return sorted(self._repository.stations(), key=lambda s: normalize(s.name))

    def stations_in_use(self) -> list[Station]:
        used = {item.station_id for item in self._repository.all() if item.station_id}
        return [station for station in self.stations() if station.id in used]

    def skill(self, skill_id: str) -> Skill | None:
        return self._repository.skill(skill_id)

    def skill_name(self, skill_id: str) -> str:
        skill = self._repository.skill(skill_id)
        return skill.name if skill else skill_id

    def skills(self) -> list[Skill]:
        return sorted(self._repository.skills(), key=lambda s: (s.kind.value, normalize(s.name)))


def search_key(item: Item) -> str:
    return f"{normalize(item.name)} {normalize(item.id)}"


def matches(item: Item, tokens: list[str]) -> bool:
    haystack = search_key(item)
    return all(token in haystack for token in tokens)
