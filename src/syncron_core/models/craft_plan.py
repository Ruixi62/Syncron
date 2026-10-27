"""Résultat d'un calcul de craft."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from syncron_core.models.item import Requirement


@dataclass(frozen=True, slots=True)
class MaterialLine:
    item_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class MaterialRequirement:
    """Besoin total en une ressource primaire."""

    item_id: str
    required: int
    from_stock: int = 0

    @property
    def missing(self) -> int:
        return self.required - self.from_stock


@dataclass(frozen=True, slots=True)
class CraftStep:
    """Craft d'un intermédiaire (ou de la cible), besoins de tout le plan fusionnés."""

    item_id: str
    required: int
    from_stock: int
    crafts: int
    output_per_craft: int
    station_id: str | None = None
    time_per_craft: int = 0
    requirements: tuple[Requirement, ...] = ()

    @property
    def to_craft(self) -> int:
        return self.required - self.from_stock

    @property
    def produced(self) -> int:
        return self.crafts * self.output_per_craft

    @property
    def surplus(self) -> int:
        return self.produced - self.to_craft

    @property
    def total_time(self) -> int:
        return self.crafts * self.time_per_craft


@dataclass(frozen=True, slots=True)
class StationWorkload:
    """Charge d'un atelier dans le plan : crafts et temps cumulés."""

    station_id: str | None
    crafts: int
    total_time: int
    item_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RequirementSummary:
    """Niveau maximal exigé pour une compétence, sur l'ensemble du plan."""

    skill_id: str
    level: int
    needed_by: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CraftNode:
    """Nœud de l'arbre de dépendances (vue par branche, arrondi par branche)."""

    item_id: str
    quantity: int
    crafts: int
    children: tuple[CraftNode, ...] = ()

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def walk(self, depth: int = 0) -> Iterator[tuple[CraftNode, int]]:
        yield self, depth
        for child in self.children:
            yield from child.walk(depth + 1)

    def count_nodes(self) -> int:
        return sum(1 for _ in self.walk())


@dataclass(frozen=True, slots=True)
class CraftPlan:
    target_id: str
    quantity: int
    target_crafts: int
    direct_recipe: tuple[MaterialLine, ...]
    tree: CraftNode
    steps: tuple[CraftStep, ...]
    raw_materials: tuple[MaterialRequirement, ...]
    workloads: tuple[StationWorkload, ...] = ()
    requirements: tuple[RequirementSummary, ...] = ()

    @property
    def total_raw_units(self) -> int:
        return sum(requirement.required for requirement in self.raw_materials)

    @property
    def total_missing_units(self) -> int:
        return sum(requirement.missing for requirement in self.raw_materials)

    @property
    def total_crafts(self) -> int:
        return sum(step.crafts for step in self.steps)

    @property
    def total_time(self) -> int:
        """Temps de fabrication des ateliers : somme, pour chaque étape, de crafts × temps par craft."""
        return sum(step.total_time for step in self.steps)
