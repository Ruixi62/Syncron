"""Référentiels : ateliers de fabrication et compétences (prérequis)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Station:
    """Lieu où s'effectue un craft : table de craft, atelier d'énergie…"""

    id: str
    name: str
    description: str = ""
    image: str | None = None
    source: str = field(default="", compare=False)


class SkillKind(StrEnum):
    JOB = "job"
    RESEARCH = "research"
    OTHER = "other"

    @property
    def label(self) -> str:
        return {"job": "Métier", "research": "Recherche & Développement", "other": "Autre"}[self.value]


@dataclass(frozen=True, slots=True)
class Skill:
    """Compétence à niveaux servant de prérequis : un métier, une branche de R&D…
    `max_level` à None = pas de plafond connu."""

    id: str
    name: str
    kind: SkillKind = SkillKind.OTHER
    max_level: int | None = None
    description: str = ""
    source: str = field(default="", compare=False)
