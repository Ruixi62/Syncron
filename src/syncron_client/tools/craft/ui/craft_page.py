"""Page de l'outil Craft : catalogue + fiche d'analyse, exports. Les données viennent du serveur."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QStandardPaths, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QSplitter, QWidget

from syncron_client.platform.tool import NotifyLevel, ToolHost
from syncron_client.settings import JsonSettingsStore
from syncron_client.tools.craft.ui.catalog_panel import CatalogPanel
from syncron_client.tools.craft.ui.detail_panel import DetailPanel
from syncron_client.ui.item_icons import IconProvider
from syncron_core.calculator import CraftCalculator
from syncron_core.catalog_service import CatalogService
from syncron_core.exporters.base import ExportContext
from syncron_core.exporters.registry import ExporterRegistry


class CraftPage(QWidget):
    planChanged = Signal(object)

    def __init__(
        self,
        catalog: CatalogService,
        calculator: CraftCalculator,
        exporters: ExporterRegistry,
        settings: JsonSettingsStore,
        host: ToolHost,
        icon_provider: IconProvider,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._catalog = catalog
        self._exporters = exporters
        self._settings = settings
        self._host = host
        self._icons = icon_provider

        self.catalog_panel = CatalogPanel(catalog, self._icons)
        self.detail_panel = DetailPanel(catalog, calculator, self._icons)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(self.catalog_panel)
        self._splitter.addWidget(self.detail_panel)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setHandleWidth(16)
        self._splitter.setSizes([340, 980])
        self.catalog_panel.setMinimumWidth(280)
        self.detail_panel.setMinimumWidth(500)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.addWidget(self._splitter)

        self.catalog_panel.itemRequested.connect(self.detail_panel.show_item)
        self.detail_panel.navigateRequested.connect(lambda item_id: self.catalog_panel.select_item(item_id))
        self.detail_panel.planChanged.connect(self.planChanged)

        self.catalog_panel.reload()
        self._restore_state()

    @property
    def icons(self) -> IconProvider:
        return self._icons

    # -- données ---------------------------------------------------------------

    def data_changed(self) -> None:
        """Le catalogue a été mis à jour (synchronisation) : on réaffiche sans perdre la sélection."""
        self._icons.clear()
        self.catalog_panel.reload()
        self.detail_panel.refresh()

    def images_changed(self) -> None:
        self._icons.clear()
        self.catalog_panel.reload()
        self.detail_panel.refresh()

    # -- actions ---------------------------------------------------------------

    def export_plan(self, format_id: str) -> None:
        plan = self.detail_panel.plan
        if plan is None:
            return
        exporter = self._exporters.get(format_id)
        directory = Path(
            self._settings.get("last_export_dir")
            or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        )
        suggested = directory / f"{plan.target_id}_x{plan.quantity}{exporter.extension}"
        chosen, _ = QFileDialog.getSaveFileName(
            self, f"Exporter en {exporter.label}", str(suggested), exporter.file_filter
        )
        if not chosen:
            return
        try:
            written = exporter.export(plan, ExportContext.from_catalog(self._catalog), Path(chosen))
        except OSError as exc:
            self._host.notify(f"Export impossible : {exc}", NotifyLevel.ERROR)
            return
        self._settings.set("last_export_dir", str(written.parent))
        self._host.notify(f"Exporté : {written.name}", NotifyLevel.SUCCESS)

    def copy_raw_materials(self) -> None:
        if self.detail_panel.copy_raw_materials():
            self._host.notify("Liste des ressources copiée dans le presse-papiers.", NotifyLevel.SUCCESS)

    def open_item(self, item_id: str, quantity: int = 1) -> None:
        self.catalog_panel.select_item(item_id, quantity)

    # -- état ------------------------------------------------------------------

    def _restore_state(self) -> None:
        splitter = self._settings.get("splitter_state")
        if isinstance(splitter, str):
            self._splitter.restoreState(QByteArray.fromHex(splitter.encode("ascii")))
        last_item = self._settings.get("last_item_id")
        last_quantity = self._settings.get("last_quantity", 1)
        if isinstance(last_item, str) and isinstance(last_quantity, int):
            self.catalog_panel.select_item(last_item, max(1, last_quantity))

    def save_state(self) -> None:
        self._settings.set("splitter_state", bytes(self._splitter.saveState().toHex()).decode("ascii"))
        self._settings.set("last_item_id", self.detail_panel.item_id)
        self._settings.set("last_quantity", self.detail_panel.quantity())
        self._settings.save()
