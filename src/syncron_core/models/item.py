"""Objet du jeu et sa recette."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ItemType(StrEnum):
    RAW = "raw"
    CRAFTED = "crafted"


@dataclass(frozen=True, slots=True)
class Ingredient:
    item_id: str
    quantity: int

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError(f"Quantité d'ingrédient invalide pour « {self.item_id} » : {self.quantity}")


@dataclass(frozen=True, slots=True)
class Requirement:
    """Prérequis pour lancer un craft : niveau minimum dans une compétence
    (métier, recherche & développement, grade…)."""

    skill_id: str
    level: int

    def __post_init__(self) -> None:
        if self.level < 1:
            raise ValueError(f"Niveau requis invalide pour « {self.skill_id} » : {self.level}")


@dataclass(frozen=True, slots=True)
class Recipe:
    """Une exécution de la recette :
    - consomme `ingredients` et produit `output` unités ;
    - se fait dans l'atelier `station_id` (None = non précisé) ;
    - dure `time_seconds` (0 = instantané) ;
    - exige `requirements`."""

    output: int
    ingredients: tuple[Ingredient, ...]
    station_id: str | None = None
    time_seconds: int = 0
    requirements: tuple[Requirement, ...] = ()

    def __post_init__(self) -> None:
        if self.output < 1:
            raise ValueError(f"Rendement de recette invalide : {self.output}")
        if not self.ingredients:
            raise ValueError("Une recette doit contenir au moins un ingrédient")
        if self.time_seconds < 0:
            raise ValueError(f"Temps de fabrication négatif : {self.time_seconds}")

    @property
    def ingredient_ids(self) -> tuple[str, ...]:
        return tuple(ingredient.item_id for ingredient in self.ingredients)


@dataclass(frozen=True, slots=True)
class Item:
    id: str
    name: str
    type: ItemType
    recipe: Recipe | None = None
    category: str = ""
    image: str | None = None
    description: str = ""
    source: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if self.type is ItemType.CRAFTED and self.recipe is None:
            raise ValueError(f"L'objet craftable « {self.id} » n'a pas de recette")
        if self.type is ItemType.RAW and self.recipe is not None:
            raise ValueError(f"La ressource primaire « {self.id} » ne doit pas avoir de recette")

    @property
    def is_raw(self) -> bool:
        return self.type is ItemType.RAW

    @property
    def ingredient_ids(self) -> tuple[str, ...]:
        return self.recipe.ingredient_ids if self.recipe else ()

    @property
    def station_id(self) -> str | None:
        return self.recipe.station_id if self.recipe else None
