"""Export JSON structuré."""

from __future__ import annotations

import json
from typing import Any

from syncron_core import __version__
from syncron_core.exporters.base import ExportContext, Exporter
from syncron_core.models.craft_plan import CraftNode, CraftPlan

EXPORT_FORMAT = "syncron.craft.plan"
EXPORT_FORMAT_VERSION = 2


class JsonExporter(Exporter):
    format_id = "json"
    label = "JSON"
    extension = ".json"

    def render(self, plan: CraftPlan, context: ExportContext) -> str:
        return json.dumps(self.to_dict(plan, context), ensure_ascii=False, indent=2) + "\n"

    @staticmethod
    def to_dict(plan: CraftPlan, context: ExportContext) -> dict[str, Any]:
        name = context.item_name

        def node(n: CraftNode) -> dict[str, Any]:
            return {
                "id": n.item_id,
                "name": name(n.item_id),
                "quantity": n.quantity,
                "crafts": n.crafts,
                "children": [node(child) for child in n.children],
            }

        return {
            "format": EXPORT_FORMAT,
            "format_version": EXPORT_FORMAT_VERSION,
            "app_version": __version__,
            "generated_at": context.generated_at.isoformat(timespec="seconds"),
            "target": {
                "id": plan.target_id,
                "name": name(plan.target_id),
                "quantity": plan.quantity,
                "crafts": plan.target_crafts,
            },
            "totals": {
                "raw_units": plan.total_raw_units,
                "crafts": plan.total_crafts,
                "time_seconds": plan.total_time,
            },
            "direct_recipe": [
                {"id": line.item_id, "name": name(line.item_id), "quantity": line.quantity}
                for line in plan.direct_recipe
            ],
            "requirements": [
                {
                    "skill": r.skill_id,
                    "name": context.skill_name(r.skill_id),
                    "level": r.level,
                    "needed_by": list(r.needed_by),
                }
                for r in plan.requirements
            ],
            "stations": [
                {
                    "id": w.station_id,
                    "name": context.station_name(w.station_id),
                    "crafts": w.crafts,
                    "time_seconds": w.total_time,
                    "items": list(w.item_ids),
                }
                for w in plan.workloads
            ],
            "steps": [
                {
                    "id": step.item_id,
                    "name": name(step.item_id),
                    "station": step.station_id,
                    "required": step.required,
                    "from_stock": step.from_stock,
                    "crafts": step.crafts,
                    "produced": step.produced,
                    "surplus": step.surplus,
                    "time_per_craft_seconds": step.time_per_craft,
                    "time_seconds": step.total_time,
                    "requires": {r.skill_id: r.level for r in step.requirements},
                }
                for step in plan.steps
            ],
            "raw_materials": [
                {
                    "id": r.item_id,
                    "name": name(r.item_id),
                    "required": r.required,
                    "from_stock": r.from_stock,
                    "missing": r.missing,
                }
                for r in plan.raw_materials
            ],
            "tree": node(plan.tree),
        }
