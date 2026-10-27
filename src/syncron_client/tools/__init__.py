"""Outils intégrés à la plateforme, dans l'ordre d'affichage.

Ajouter un outil = l'ajouter à builtin_tools(). Un outil avec `min_role`
n'est chargé que pour les comptes qui ont ce rôle (section « Gestion »)."""

from __future__ import annotations

from syncron_client.platform.tool import Tool
from syncron_client.tools.admin import AdminTool
from syncron_client.tools.calendar import create_calendar_tool
from syncron_client.tools.craft import CraftTool
from syncron_client.tools.research import create_research_tool


def builtin_tools() -> list[Tool]:
    return [CraftTool(), create_calendar_tool(), create_research_tool(), AdminTool()]
