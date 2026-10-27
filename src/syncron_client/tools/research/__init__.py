"""Outil R&D — en attente de développement."""

from __future__ import annotations

from syncron_client.platform.tool import ToolInfo, ToolStage
from syncron_client.tools.planned import PlannedTool

RESEARCH_INFO = ToolInfo(
    id="research",
    name="R&D",
    description="Arbre de recherche & développement, coûts, durées et progression.",
    icon="flask",
    version="0.0.0",
    stage=ToolStage.PLANNED,
    roadmap=(
        "Arbre des recherches avec leurs prérequis et ce qu'elles débloquent.",
        "Suivi de tes niveaux de R&D, utilisé par Craft pour savoir ce que tu peux fabriquer.",
        "Coût et durée cumulés pour atteindre un niveau de recherche.",
        "Les mêmes fichiers JSON éditables à la main que Craft (data/research/).",
    ),
)


def create_research_tool() -> PlannedTool:
    return PlannedTool(RESEARCH_INFO)
