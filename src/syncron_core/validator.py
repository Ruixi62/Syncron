"""Validation transverse du catalogue : ingrédients, ateliers, compétences, cycles.

Le serveur l'exécute avant chaque écriture (un catalogue invalide n'est jamais
enregistré) ; l'import l'exécute pour produire un rapport complet.
"""

from __future__ import annotations

from syncron_core.catalog import CraftData
from syncron_core.graph import find_cycles
from syncron_core.models.item import Item
from syncron_core.models.validation import Severity, ValidationIssue, ValidationReport


class RecipeValidator:
    def validate(self, data: CraftData) -> ValidationReport:
        items = {item.id: item for item in data.items}
        stations = {station.id for station in data.stations}
        skills = {skill.id: skill for skill in data.skills}
        issues: list[ValidationIssue] = []

        for item in data.items:
            if item.recipe is None:
                continue

            def error(message: str, item: Item = item) -> None:
                issues.append(ValidationIssue(Severity.ERROR, message, item.id, item.source))

            for ingredient_id in item.ingredient_ids:
                if ingredient_id not in items:
                    error(f"Ingrédient inconnu « {ingredient_id} » : il doit exister dans le catalogue.")
            station_id = item.recipe.station_id
            if station_id and station_id not in stations:
                error(f"Atelier inconnu « {station_id} » : il doit exister dans les ateliers.")
            for requirement in item.recipe.requirements:
                skill = skills.get(requirement.skill_id)
                if skill is None:
                    error(f"Compétence inconnue « {requirement.skill_id} » : elle doit exister dans les compétences.")
                elif skill.max_level is not None and requirement.level > skill.max_level:
                    error(
                        f"Niveau {requirement.level} demandé pour « {skill.name} », "
                        f"au-delà du maximum déclaré ({skill.max_level})."
                    )

        issues += _cycles(items)
        return ValidationReport(tuple(issues))


def _cycles(items: dict[str, Item]) -> list[ValidationIssue]:
    def neighbors(item_id: str) -> tuple[str, ...]:
        item = items.get(item_id)
        return tuple(i for i in item.ingredient_ids if i in items) if item else ()

    issues = []
    for cycle in find_cycles(sorted(items), neighbors):
        for item_id in dict.fromkeys(cycle):
            message = "Recette circulaire : " + " → ".join(cycle)
            issues.append(ValidationIssue(Severity.ERROR, message, item_id, items[item_id].source))
    return issues
