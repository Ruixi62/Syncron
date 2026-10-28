"""Écrans de gestion du Craft, regroupés sous « Craft » dans l'Administration."""

from __future__ import annotations

from syncron_client.platform.admin import AdminSection
from syncron_client.tools.craft.admin.context import CraftAdminContext
from syncron_client.tools.craft.admin.editors import ItemEditor, SkillEditor, StationEditor
from syncron_client.tools.craft.admin.transfer import ImportExportView

ITEMS = "craft.items"
STATIONS = "craft.stations"
SKILLS = "craft.skills"
TRANSFER = "craft.transfer"


class CraftAdmin:
    """Crée les écrans à la demande et les tient à jour quand le catalogue change."""

    def __init__(self, context: CraftAdminContext) -> None:
        self.context = context
        self.items: ItemEditor | None = None
        self.stations: StationEditor | None = None
        self.skills: SkillEditor | None = None
        self.transfer: ImportExportView | None = None

    def sections(self) -> list[AdminSection]:
        return [
            AdminSection(ITEMS, "Objets", "box", self._items),
            AdminSection(STATIONS, "Ateliers", "station", self._stations),
            AdminSection(SKILLS, "Compétences", "award", self._skills),
            AdminSection(TRANSFER, "Import / export", "database", self._transfer),
        ]

    def data_changed(self) -> None:
        self.context.refresh_data()
        for editor in (self.items, self.stations, self.skills):
            if editor is not None:
                editor.reload()

    def _items(self) -> ItemEditor:
        self.items = ItemEditor(self.context, "OBJETS")
        self.items.reload()
        return self.items

    def _stations(self) -> StationEditor:
        self.stations = StationEditor(self.context, "ATELIERS")
        self.stations.reload()
        return self.stations

    def _skills(self) -> SkillEditor:
        self.skills = SkillEditor(self.context, "COMPÉTENCES")
        self.skills.reload()
        return self.skills

    def _transfer(self) -> ImportExportView:
        self.transfer = ImportExportView(self.context)
        return self.transfer
