"""Contrat commun des exporteurs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from syncron_core.io import atomic_write_text
from syncron_core.models.craft_plan import CraftPlan

NameOf = Callable[[str], str]
StationNameOf = Callable[[str | None], str]


@dataclass(frozen=True, slots=True)
class ExportContext:
    item_name: NameOf
    station_name: StationNameOf
    skill_name: NameOf
    generated_at: datetime = field(default_factory=lambda: datetime.now().astimezone())

    @classmethod
    def from_catalog(cls, catalog) -> ExportContext:
        return cls(catalog.display_name, catalog.station_name, catalog.skill_name)


class Exporter(ABC):
    format_id: ClassVar[str]
    label: ClassVar[str]
    extension: ClassVar[str]

    @abstractmethod
    def render(self, plan: CraftPlan, context: ExportContext) -> str:
        """Produit le contenu texte de l'export."""

    def export(self, plan: CraftPlan, context: ExportContext, path: Path) -> Path:
        if path.suffix.lower() != self.extension:
            path = path.with_suffix(self.extension)
        atomic_write_text(path, self.render(plan, context))
        return path

    @property
    def file_filter(self) -> str:
        return f"{self.label} (*{self.extension})"
