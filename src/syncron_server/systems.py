"""Systèmes de Syncron et leur part dans l'administration.

Chaque système (Craft, R&D, Calendrier, Messagerie…) a :
- un identifiant, utilisé pour les droits des éditeurs (`users.permissions`)
  et pour classer le journal (`audit_log.system`) ;
- ses routes de lecture (`/api/v1/<système>`) et de gestion
  (`/api/v1/admin/<système>/…`, protégées par `deps.manager(<système>)`) ;
- un résumé pour la vue d'ensemble de l'administration, déclaré avec
  `@overview_provider("<système>")`.

Ajouter un système : l'ajouter à SYSTEMS, écrire son routeur, déclarer son résumé.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server.schemas import SystemOverviewOut

CRAFT = "craft"
RESEARCH = "research"
CALENDAR = "calendar"
MESSAGES = "messages"
ACCOUNTS = "accounts"

SYSTEMS: dict[str, str] = {
    CRAFT: "Craft",
    RESEARCH: "R&D",
    CALENDAR: "Calendrier",
    MESSAGES: "Messagerie",
}
LABELS: dict[str, str] = {**SYSTEMS, ACCOUNTS: "Comptes"}

OverviewProvider = Callable[[AsyncSession], Awaitable[SystemOverviewOut]]
_providers: dict[str, OverviewProvider] = {}


def overview_provider(system: str) -> Callable[[OverviewProvider], OverviewProvider]:
    if system not in SYSTEMS:
        raise ValueError(f"Système inconnu : {system}")

    def register(provider: OverviewProvider) -> OverviewProvider:
        _providers[system] = provider
        return provider

    return register


def overview_providers() -> dict[str, OverviewProvider]:
    """Dans l'ordre de SYSTEMS."""
    return {system: _providers[system] for system in SYSTEMS if system in _providers}


def clean_permissions(permissions: list[str]) -> list[str]:
    unknown = sorted(set(permissions) - SYSTEMS.keys())
    if unknown:
        raise ValueError(f"Système(s) inconnu(s) : {', '.join(unknown)}")
    return sorted(set(permissions))
