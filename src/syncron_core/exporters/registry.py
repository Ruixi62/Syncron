"""Registre des formats d'export (point d'extension pour de futurs formats : CSV, Markdown…)."""

from __future__ import annotations

from syncron_core.exporters.base import Exporter
from syncron_core.exporters.json_exporter import JsonExporter
from syncron_core.exporters.txt_exporter import TxtExporter


class ExporterRegistry:
    def __init__(self) -> None:
        self._exporters: dict[str, Exporter] = {}

    def register(self, exporter: Exporter) -> None:
        if exporter.format_id in self._exporters:
            raise ValueError(f"Format d'export déjà enregistré : {exporter.format_id}")
        self._exporters[exporter.format_id] = exporter

    def get(self, format_id: str) -> Exporter:
        try:
            return self._exporters[format_id]
        except KeyError:
            raise KeyError(f"Format d'export inconnu : {format_id}") from None

    def all(self) -> tuple[Exporter, ...]:
        return tuple(self._exporters.values())

    def by_filter(self, file_filter: str) -> Exporter | None:
        return next((e for e in self._exporters.values() if e.file_filter == file_filter), None)


def default_registry() -> ExporterRegistry:
    registry = ExporterRegistry()
    registry.register(TxtExporter())
    registry.register(JsonExporter())
    return registry
