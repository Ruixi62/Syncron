"""Export texte lisible, prêt à coller (Discord, bloc-notes…)."""

from __future__ import annotations

from syncron_core import APP_DISPLAY_NAME
from syncron_core.duration import format_duration
from syncron_core.exporters.base import ExportContext, Exporter
from syncron_core.models.craft_plan import CraftNode, CraftPlan
from syncron_core.text import format_quantity


class TxtExporter(Exporter):
    format_id = "txt"
    label = "Texte"
    extension = ".txt"

    def render(self, plan: CraftPlan, context: ExportContext) -> str:
        name = context.item_name
        lines = [
            f"{APP_DISPLAY_NAME} · Craft — analyse",
            f"Objet   : {name(plan.target_id)} × {format_quantity(plan.quantity)}",
            f"Généré  : {context.generated_at:%d/%m/%Y %H:%M}",
            f"Temps   : {format_duration(plan.total_time)} (temps de fabrication des ateliers)",
            "",
            "=== Recette directe ===",
        ]
        if plan.direct_recipe:
            lines.append(f"({format_quantity(plan.target_crafts)} craft(s))")
            lines += _aligned((line.quantity, name(line.item_id)) for line in plan.direct_recipe)
        else:
            lines.append("Ressource primaire : aucune recette.")

        if plan.requirements:
            lines += ["", "=== Prérequis ==="]
            lines += [f"  {context.skill_name(r.skill_id)} : niveau {r.level}" for r in plan.requirements]

        if plan.workloads:
            lines += ["", "=== Ateliers ==="]
            for workload in plan.workloads:
                lines.append(
                    f"  {context.station_name(workload.station_id)} : {format_quantity(workload.crafts)} craft(s), "
                    f"{format_duration(workload.total_time)}"
                )

        lines += ["", "=== Étapes de fabrication (dans l'ordre) ==="]
        for index, step in enumerate(plan.steps, start=1):
            surplus = f", surplus {format_quantity(step.surplus)}" if step.surplus else ""
            lines.append(
                f"{index:>3}. {name(step.item_id)} — {format_quantity(step.crafts)} craft(s) → "
                f"{format_quantity(step.produced)}{surplus} · {context.station_name(step.station_id)} · "
                f"{format_duration(step.total_time)}"
            )

        lines += ["", "=== Arbre des dépendances ==="]
        lines += _tree_lines(plan.tree, name)

        lines += ["", "=== Ressources finales ==="]
        lines += _aligned((r.missing, name(r.item_id)) for r in plan.raw_materials)
        lines += [
            "",
            f"Total : {format_quantity(plan.total_missing_units)} unité(s), "
            f"{len(plan.raw_materials)} ressource(s) différente(s).",
        ]
        return "\n".join(lines) + "\n"


def _aligned(rows) -> list[str]:
    rows = list(rows)
    width = max((len(format_quantity(quantity)) for quantity, _ in rows), default=1)
    return [f"  {format_quantity(quantity):>{width}} × {label}" for quantity, label in rows]


def _tree_lines(root: CraftNode, name) -> list[str]:
    lines = [_node_label(root, name)]

    def visit(node: CraftNode, prefix: str) -> None:
        for index, child in enumerate(node.children):
            last = index == len(node.children) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{_node_label(child, name)}")
            visit(child, prefix + ("    " if last else "│   "))

    visit(root, "")
    return lines


def _node_label(node: CraftNode, name) -> str:
    crafts = f"  [{format_quantity(node.crafts)} craft(s)]" if node.crafts else ""
    return f"{name(node.item_id)} × {format_quantity(node.quantity)}{crafts}"
