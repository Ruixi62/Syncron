"""Outils intégrés à la plateforme, dans l'ordre d'affichage.

Ajouter un outil = l'ajouter à builtin_tools(). Un outil avec `min_role`
n'est chargé que pour les comptes qui ont ce rôle ; `placement` décide de sa
place dans la barre latérale ; `system` relie l'outil à son système côté
serveur (droits de gestion, écrans dans l'Administration)."""

from __future__ import annotations

from syncron_client.platform.tool import Tool
from syncron_client.tools.admin import AdminTool
from syncron_client.tools.calendar import CalendarTool
from syncron_client.tools.converter import ConverterTool
from syncron_client.tools.craft import CraftTool
from syncron_client.tools.mailbox import MailboxTool
from syncron_client.tools.research import ResearchTool


def builtin_tools() -> list[Tool]:
    return [MailboxTool(), CraftTool(), ResearchTool(), CalendarTool(), ConverterTool(), AdminTool()]
