"""Outils intégrés à la plateforme, dans l'ordre d'affichage.

Ajouter un outil = l'ajouter à builtin_tools(). Un outil avec `min_role`
n'est chargé que pour les comptes qui ont ce rôle ; `placement` décide de sa
place dans la barre latérale ; `system` relie l'outil à son système côté
serveur (droits de gestion, écrans dans l'Administration) ; `parent` le range
dans l'onglet d'une rubrique (Pays). Un outil au stade PLANNED affiche
seulement sa page « en développement » et son programme."""

from __future__ import annotations

from syncron_client.platform.tool import Tool
from syncron_client.tools.admin import AdminTool
from syncron_client.tools.alerts import AlertsTool
from syncron_client.tools.bank import BankTool
from syncron_client.tools.calendar import CalendarTool
from syncron_client.tools.converter import ConverterTool
from syncron_client.tools.country import CountryTool
from syncron_client.tools.craft import CraftTool
from syncron_client.tools.images import ImagesTool
from syncron_client.tools.intel import IntelTool
from syncron_client.tools.mailbox import MailboxTool
from syncron_client.tools.members import MembersTool
from syncron_client.tools.research import ResearchTool


def builtin_tools() -> list[Tool]:
    return [
        MailboxTool(),
        CountryTool(),
        ResearchTool(),
        MembersTool(),
        BankTool(),
        CraftTool(),
        CalendarTool(),
        IntelTool(),
        ConverterTool(),
        ImagesTool(),
        AlertsTool(),
        AdminTool(),
    ]
