"""Moteur de calcul des crafts.

1. PLAN AGRÉGÉ (steps, raw_materials, workloads, requirements) — la vérité
   chiffrée. Les besoins d'un même objet venant de plusieurs branches sont
   fusionnés AVANT l'arrondi supérieur (ordre topologique « consommateurs
   d'abord »). Exemple : 6 + 6 vis à 4 par craft -> 3 crafts, pas 2 + 2.

2. ARBRE (tree) — lecture humaine branche par branche, arrondi par branche.
"""

from __future__ import annotations

from collections import defaultdict

from syncron_core.catalog import ItemLookup
from syncron_core.errors import InvalidQuantityError, RecipeCycleError, UnknownItemError
from syncron_core.graph import consumer_first_order, find_cycles
from syncron_core.models.craft_plan import (
    CraftNode,
    CraftPlan,
    CraftStep,
    MaterialLine,
    MaterialRequirement,
    RequirementSummary,
    StationWorkload,
)
from syncron_core.models.inventory import Inventory
from syncron_core.models.item import Item
from syncron_core.text import ceil_div

MAX_QUANTITY = 1_000_000_000


class CraftCalculator:
    def __init__(self, repository: ItemLookup) -> None:
        self._repository = repository

    def calculate(self, item_id: str, quantity: int = 1, inventory: Inventory | None = None) -> CraftPlan:
        """`inventory` : stock déduit des intermédiaires et ressources, jamais de la cible."""
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QUANTITY:
            raise InvalidQuantityError(quantity)
        target = self._require(item_id)
        stock = inventory or Inventory.empty()

        self._ensure_acyclic(item_id)
        demand: dict[str, int] = defaultdict(int)
        demand[item_id] = quantity
        steps: list[CraftStep] = []
        raws: dict[str, MaterialRequirement] = {}

        for current_id in consumer_first_order(item_id, self._ingredients_of):
            needed = demand[current_id]
            if needed == 0:
                continue
            item = self._require(current_id)
            from_stock = 0 if current_id == item_id else min(stock.available(current_id), needed)
            if item.recipe is None:
                raws[current_id] = MaterialRequirement(current_id, needed, from_stock)
                continue
            recipe = item.recipe
            crafts = ceil_div(needed - from_stock, recipe.output)
            steps.append(
                CraftStep(
                    item_id=current_id,
                    required=needed,
                    from_stock=from_stock,
                    crafts=crafts,
                    output_per_craft=recipe.output,
                    station_id=recipe.station_id,
                    time_per_craft=recipe.time_seconds,
                    requirements=recipe.requirements,
                )
            )
            for ingredient in recipe.ingredients:
                demand[ingredient.item_id] += ingredient.quantity * crafts

        ordered_steps = tuple(reversed(steps))
        return CraftPlan(
            target_id=item_id,
            quantity=quantity,
            target_crafts=ceil_div(quantity, target.recipe.output) if target.recipe else 0,
            direct_recipe=self._direct_recipe(target, quantity),
            tree=self._build_tree(item_id, quantity, {}),
            steps=ordered_steps,
            raw_materials=tuple(sorted(raws.values(), key=lambda r: (-r.required, r.item_id))),
            workloads=_workloads(ordered_steps),
            requirements=_requirements(ordered_steps),
        )

    # -- briques -------------------------------------------------------------

    def _require(self, item_id: str, referenced_by: str | None = None) -> Item:
        item = self._repository.get(item_id)
        if item is None:
            raise UnknownItemError(item_id, referenced_by)
        return item

    def _ingredients_of(self, item_id: str) -> tuple[str, ...]:
        item = self._require(item_id)
        for ingredient_id in item.ingredient_ids:
            self._require(ingredient_id, referenced_by=item_id)
        return item.ingredient_ids

    def _ensure_acyclic(self, item_id: str) -> None:
        cycles = find_cycles([item_id], self._ingredients_of)
        if cycles:
            raise RecipeCycleError(cycles[0])

    @staticmethod
    def _direct_recipe(target: Item, quantity: int) -> tuple[MaterialLine, ...]:
        if target.recipe is None:
            return ()
        crafts = ceil_div(quantity, target.recipe.output)
        return tuple(MaterialLine(i.item_id, i.quantity * crafts) for i in target.recipe.ingredients)

    def _build_tree(self, item_id: str, quantity: int, memo: dict[tuple[str, int], CraftNode]) -> CraftNode:
        """Sous-arbres identiques partagés (nœuds immuables)."""
        key = (item_id, quantity)
        cached = memo.get(key)
        if cached is not None:
            return cached
        item = self._require(item_id)
        if item.recipe is None:
            node = CraftNode(item_id, quantity, 0)
        else:
            crafts = ceil_div(quantity, item.recipe.output)
            children = tuple(
                self._build_tree(ingredient.item_id, ingredient.quantity * crafts, memo)
                for ingredient in item.recipe.ingredients
            )
            node = CraftNode(item_id, quantity, crafts, children)
        memo[key] = node
        return node


def _workloads(steps: tuple[CraftStep, ...]) -> tuple[StationWorkload, ...]:
    grouped: dict[str | None, list[CraftStep]] = {}
    for step in steps:
        if step.crafts:
            grouped.setdefault(step.station_id, []).append(step)
    workloads = [
        StationWorkload(
            station_id=station_id,
            crafts=sum(s.crafts for s in group),
            total_time=sum(s.total_time for s in group),
            item_ids=tuple(s.item_id for s in group),
        )
        for station_id, group in grouped.items()
    ]
    return tuple(sorted(workloads, key=lambda w: (-w.total_time, -w.crafts, w.station_id or "")))


def _requirements(steps: tuple[CraftStep, ...]) -> tuple[RequirementSummary, ...]:
    best: dict[str, int] = {}
    users: dict[str, list[str]] = defaultdict(list)
    for step in steps:
        if not step.crafts:
            continue
        for requirement in step.requirements:
            best[requirement.skill_id] = max(best.get(requirement.skill_id, 0), requirement.level)
            users[requirement.skill_id].append(step.item_id)
    summaries = [RequirementSummary(skill_id, level, tuple(users[skill_id])) for skill_id, level in best.items()]
    return tuple(sorted(summaries, key=lambda r: (-r.level, r.skill_id)))
