"""Administration découpée par système.

Chaque outil déclare ses écrans de gestion avec `Tool.admin_sections()` ;
l'outil Administration les regroupe sous le nom du système et ne les montre
qu'aux comptes qui gèrent ce système (`Session.can_manage(ToolInfo.system)`).

Un écran (QWidget) peut proposer :
    refresh()        rechargé à chaque affichage ;
    open_key(clé)    affichage d'un élément précis (lien depuis un outil ou un message) ;
    is_dirty()       modifications non enregistrées (confirmation avant de quitter).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtWidgets import QWidget

from syncron_client.api.errors import ApiError, NetworkError, SessionExpired
from syncron_client.platform.tool import NotifyLevel, ToolHost
from syncron_client.ui.widgets import Banner


@dataclass(frozen=True, slots=True)
class AdminSection:
    key: str
    title: str
    icon: str
    factory: Callable[[], QWidget]


def admin_link(section_key: str, item_key: str = "") -> str:
    """Clé à passer à host.open_tool("admin", …) pour ouvrir un écran de gestion (et un élément)."""
    return f"{section_key}|{item_key}" if item_key else section_key


def call_api(
    host: ToolHost,
    fn: Callable[[], Any],
    on_done: Callable[[Any], None] | None = None,
    banner: Banner | None = None,
    success: str | None = None,
    on_failed: Callable[[Exception], None] | None = None,
) -> None:
    """Appel API en arrière-plan. Refus métier -> bannière locale (ou notification) ;
    réseau et session -> traitement global de la plateforme."""
    if banner is not None:
        banner.hide()

    def done(result: Any) -> None:
        if success:
            host.notify(success, NotifyLevel.SUCCESS)
        if on_done is not None:
            on_done(result)

    def failed(error: Exception) -> None:
        if on_failed is not None:
            on_failed(error)
        if isinstance(error, (NetworkError, SessionExpired)) or not isinstance(error, ApiError):
            host.handle_error(error)
        elif banner is not None:
            banner.set_text(str(error))
            banner.show()
        else:
            host.notify(error.message, NotifyLevel.ERROR)

    host.runner.run(fn, done, failed)
