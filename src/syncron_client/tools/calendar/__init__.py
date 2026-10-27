"""Outil Calendrier — en attente de développement."""

from __future__ import annotations

from syncron_client.platform.tool import ToolInfo, ToolStage
from syncron_client.tools.planned import PlannedTool

CALENDAR_INFO = ToolInfo(
    id="calendar",
    name="Calendrier",
    description="Événements, rappels et planning de ta nation, au même endroit.",
    icon="calendar",
    version="0.0.0",
    stage=ToolStage.PLANNED,
    roadmap=(
        "Événements du serveur et de ta nation, en vue jour, semaine et mois.",
        "Rappels de fin de fabrication, reliés aux temps de l'outil Craft.",
        "Planning des sessions de farm, de construction et de recherche.",
        "Export et partage du planning (texte prêt pour Discord).",
    ),
)


def create_calendar_tool() -> PlannedTool:
    return PlannedTool(CALENDAR_INFO)
