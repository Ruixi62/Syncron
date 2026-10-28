"""Contexte partagé par les écrans de gestion du Craft : catalogue courant, icônes, appels API."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.ui.item_icons import IconProvider
from syncron_client.ui.widgets import Banner
from syncron_core.catalog import CraftRepository
from syncron_core.catalog_service import CatalogService


class CraftAdminContext:
    def __init__(self, host: ToolHost) -> None:
        self.host = host
        self.repository = CraftRepository(host.catalog.data)
        self.catalog = CatalogService(self.repository)
        self.icons = IconProvider(self.catalog, host.catalog)

    @property
    def api(self):
        return self.host.api

    @property
    def is_admin(self) -> bool:
        return self.host.session.has_role("admin")

    def refresh_data(self) -> None:
        self.repository.replace(self.host.catalog.data)
        self.icons.clear()

    def call(
        self,
        fn: Callable[[], Any],
        on_done: Callable[[Any], None] | None = None,
        banner: Banner | None = None,
        success: str | None = None,
        sync: bool = False,
    ) -> None:
        """Appel API ; `sync=True` : le catalogue est resynchronisé ensuite (écritures)."""

        def done(result: Any) -> None:
            if sync:
                self.host.catalog.sync()
            if on_done is not None:
                on_done(result)

        call_api(self.host, fn, done, banner, success)
