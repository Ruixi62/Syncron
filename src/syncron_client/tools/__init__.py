"""Outils intégrés à la plateforme, dans l'ordre d'affichage.

Ajouter un outil = l'ajouter à builtin_tools(). Un outil avec `min_role`
n'est chargé que pour les comptes qui ont ce rôle ; `placement` décide de sa
place dans la barre latérale ; `system` relie l'outil à son système côté
serveur (droits de gestion, écrans dans l'Administration) ; `parent` le range
dans l'onglet d'une rubrique (Pays). Un outil au stade PLANNED affiche
seulement sa page « en développement » et son programme."""

from __future__ import annotations

from syncron_client.platform.tool import Tool, ToolInfo, ToolStage
from syncron_client.tools.admin import AdminTool
from syncron_client.tools.bank import BankTool
from syncron_client.tools.calendar import CalendarTool
from syncron_client.tools.converter import ConverterTool
from syncron_client.tools.country import CountryTool
from syncron_client.tools.craft import CraftTool
from syncron_client.tools.images import ImagesTool
from syncron_client.tools.mailbox import MailboxTool
from syncron_client.tools.members import MembersTool
from syncron_client.tools.planned import PlannedTool
from syncron_client.tools.research import ResearchTool

ALERTS = ToolInfo(
    id="alerts",
    name="Mes alertes",
    description="Tes alertes en direct, grâce à l'API NationsGlory. Page en travaux.",
    icon="alert",
    version="0.0.0",
    stage=ToolStage.PLANNED,
    roadmap=(
        "Brancher Syncron sur l'API NationsGlory.",
        "Recevoir en direct les alertes qui concernent le pays.",
        "Être prévenu par une notification du bureau et la pastille de la barre des tâches.",
        "Choisir les alertes que chacun veut recevoir.",
    ),
)

INTELLIGENCE = ToolInfo(
    id="intel",
    name="Recherche",
    description="Les informations des autres pays, récupérées sur NationsGlory. Page en travaux.",
    icon="search",
    version="0.0.0",
    stage=ToolStage.PLANNED,
    roadmap=(
        "Fiche de chaque pays : dirigeant, membres, claims, puissance.",
        "Notations hebdomadaires et classement MMR des pays.",
        "Historique pour suivre l'évolution d'un pays dans le temps.",
        "Recherche par nom de pays ou de joueur.",
    ),
)


def builtin_tools() -> list[Tool]:
    return [
        MailboxTool(),
        CountryTool(),
        ResearchTool(),
        MembersTool(),
        BankTool(),
        CraftTool(),
        CalendarTool(),
        PlannedTool(INTELLIGENCE),
        ConverterTool(),
        ImagesTool(),
        PlannedTool(ALERTS),
        AdminTool(),
    ]
