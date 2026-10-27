from __future__ import annotations

import pytest

from syncron_core.calculator import CraftCalculator
from syncron_core.catalog import CraftData, CraftRepository
from syncron_core.errors import InvalidQuantityError, RecipeCycleError, UnknownItemError
from syncron_core.models.inventory import Inventory
from syncron_core.models.item import Ingredient, Item, ItemType, Recipe


def raws(plan) -> dict[str, int]:
    return {r.item_id: r.required for r in plan.raw_materials}


def crafts(plan) -> dict[str, int]:
    return {s.item_id: s.crafts for s in plan.steps}


def test_spec_example_machine_x(context):
    plan = context.calculator.calculate("machine_x")
    assert [(line.item_id, line.quantity) for line in plan.direct_recipe] == [("circuit_avance", 6), ("quartz", 10)]
    assert raws(plan) == {"lingot_etain": 18, "bois": 6, "quartz": 28, "pierre": 12, "redstone": 6}


def test_quantity_multiplies_everything(context):
    plan = context.calculator.calculate("machine_x", 10)
    assert raws(plan) == {"lingot_etain": 180, "bois": 60, "quartz": 280, "pierre": 120, "redstone": 60}


def test_yield_rounds_up(context):
    plan = context.calculator.calculate("vis", 6)
    assert plan.target_crafts == 2
    assert raws(plan) == {"fer": 2}
    assert plan.steps[-1].produced == 8 and plan.steps[-1].surplus == 2


def test_shared_intermediate_is_aggregated_before_rounding(context):
    # 2 châssis : 6 vis (supports) + 6 vis (cadres) = 12 vis -> 3 crafts -> 3 fer.
    # Arrondir par branche donnerait 2 + 2 = 4 fer : l'arbre le montre, le plan agrégé non.
    plan = context.calculator.calculate("chassis", 2)
    assert crafts(plan)["vis"] == 3
    assert raws(plan) == {"fer": 3}
    assert sum(node.quantity for node, _ in plan.tree.walk() if node.item_id == "fer") == 4


def test_steps_are_in_craft_order(context):
    order = [s.item_id for s in context.calculator.calculate("machine_x").steps]
    assert order.index("repeteur_redstone") < order.index("circuit_avance") < order.index("machine_x")


def test_times_and_station_workloads(context):
    plan = context.calculator.calculate("machine_x", 2)
    # 2 × 1 h (atelier d'énergie) + 12 × 3 min (table de craft, station par défaut) + 12 répéteurs instantanés
    assert plan.total_time == 2 * 3600 + 12 * 180
    loads = {w.station_id: (w.crafts, w.total_time) for w in plan.workloads}
    assert loads == {"atelier_energie": (2, 7200), "table_craft": (24, 2160)}
    assert plan.workloads[0].station_id == "atelier_energie"


def test_requirements_keep_highest_level(context):
    plan = context.calculator.calculate("machine_x")
    summary = {r.skill_id: (r.level, set(r.needed_by)) for r in plan.requirements}
    assert summary == {"ingenieur": (20, {"machine_x", "circuit_avance"}), "rd_energie": (3, {"machine_x"})}


def test_raw_target(context):
    plan = context.calculator.calculate("quartz", 5)
    assert plan.direct_recipe == () and plan.target_crafts == 0 and plan.total_time == 0
    assert raws(plan) == {"quartz": 5}
    assert plan.tree.is_leaf and plan.workloads == () and plan.requirements == ()


def test_inventory_is_deducted_except_on_target(context):
    stock = Inventory({"repeteur_redstone": 4, "quartz": 20, "machine_x": 99})
    plan = context.calculator.calculate("machine_x", 1, stock)
    assert crafts(plan)["repeteur_redstone"] == 2
    assert crafts(plan)["machine_x"] == 1
    quartz = next(r for r in plan.raw_materials if r.item_id == "quartz")
    assert (quartz.required, quartz.from_stock, quartz.missing) == (16, 16, 0)


def test_stock_covering_a_step_removes_its_requirements(context):
    plan = context.calculator.calculate("machine_x", 1, Inventory({"circuit_avance": 6}))
    assert {r.skill_id: r.level for r in plan.requirements} == {"ingenieur": 20, "rd_energie": 3}
    assert {r.skill_id: r.needed_by for r in plan.requirements}["ingenieur"] == ("machine_x",)


@pytest.mark.parametrize("quantity", [0, -3, True, 2.5])
def test_invalid_quantity(context, quantity):
    with pytest.raises(InvalidQuantityError):
        context.calculator.calculate("machine_x", quantity)


def test_unknown_target(context):
    with pytest.raises(UnknownItemError):
        context.calculator.calculate("nope")


def _calculator(*items: Item) -> CraftCalculator:
    return CraftCalculator(CraftRepository(CraftData(items=items)))


def _crafted(item_id: str, **recipe: int) -> Item:
    ingredients = tuple(Ingredient(key, value) for key, value in recipe.items())
    return Item(item_id, item_id, ItemType.CRAFTED, Recipe(1, ingredients))


def test_unknown_ingredient_names_the_consumer():
    with pytest.raises(UnknownItemError) as info:
        _calculator(_crafted("a", ghost=1)).calculate("a")
    assert info.value.item_id == "ghost" and info.value.referenced_by == "a"


def test_cycle_is_detected():
    with pytest.raises(RecipeCycleError) as info:
        _calculator(_crafted("a", b=1), _crafted("b", c=1), _crafted("c", a=1)).calculate("a")
    assert info.value.cycle == ("a", "b", "c", "a")


def test_deep_chain():
    items = [Item("r", "r", ItemType.RAW)]
    previous = "r"
    for index in range(300):
        current = f"i{index}"
        items.append(_crafted(current, **{previous: 2 if index < 20 else 1}))
        previous = current
    assert raws(_calculator(*items).calculate(previous)) == {"r": 2**20}
