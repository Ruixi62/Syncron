"""R&D côté client : domaines, paliers, conditions et récompenses, état d'avancement.

Les conditions se suivent sur tous les paliers à la fois ; les paliers se valident dans
l'ordre (le palier N après le N-1), une fois faits en jeu.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from syncron_core.catalog_service import CatalogService
from syncron_core.text import format_quantity


class TierStatus(StrEnum):
    DONE = "done"
    NEXT = "next"
    LOCKED = "locked"

    @property
    def label(self) -> str:
        return {"done": "Validé", "next": "Prochain", "locked": "À venir"}[self.value]

    @property
    def tone(self) -> str:
        return {"done": "success", "next": "info", "locked": "neutral"}[self.value]

    @property
    def icon(self) -> str:
        return {"done": "check-circle", "next": "flag", "locked": "lock"}[self.value]


@dataclass(frozen=True, slots=True)
class Line:
    """Condition ou récompense (texte seul). `progress` : quantité déjà réunie (380 sur 1 000)."""

    text: str
    quantity: int | None = None
    item_id: str | None = None
    done: bool = False
    progress: int | None = None
    id: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Line:
        return cls(
            raw.get("text") or "",
            raw.get("quantity"),
            raw.get("item_id"),
            bool(raw.get("done")),
            raw.get("progress"),
            raw.get("id"),
        )

    def to_api(self) -> dict[str, Any]:
        """Condition."""
        return {
            "id": self.id,
            "text": self.text,
            "quantity": self.quantity,
            "progress": self.progress if self.quantity else None,
            "item_id": self.item_id,
            "done": self.done and self.reached,
        }

    def reward_to_api(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text}

    @property
    def tracked(self) -> bool:
        """Condition chiffrée : on suit combien on en a réuni."""
        return self.quantity is not None

    @property
    def reached(self) -> bool:
        """La case peut être cochée : pas de quantité à réunir, ou quantité atteinte."""
        return self.quantity is None or (self.progress or 0) >= self.quantity

    @property
    def missing(self) -> int:
        return max((self.quantity or 0) - (self.progress or 0), 0)

    @property
    def fraction(self) -> float:
        if self.done:
            return 1.0
        if not self.quantity:
            return 0.0
        return min((self.progress or 0) / self.quantity, 1.0)

    def progress_text(self) -> str:
        return f"{format_quantity(self.progress or 0)} / {format_quantity(self.quantity or 0)}"

    def describe(self, catalog: CatalogService | None = None) -> str:
        """« 2 000 × Lingot de fer — à déposer au QG », « Avoir 10 membres »."""
        subject = self.text
        if self.item_id:
            item = catalog.get(self.item_id) if catalog is not None else None
            name = item.name if item is not None else self.item_id
            subject = f"{name} — {self.text}" if self.text else name
        return f"{format_quantity(self.quantity)} × {subject}" if self.quantity else subject


@dataclass(frozen=True, slots=True)
class Tier:
    level: int
    name: str
    description: str
    conditions: tuple[Line, ...]
    rewards: tuple[Line, ...]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Tier:
        return cls(
            level=int(raw["level"]),
            name=raw.get("name") or "",
            description=raw.get("description") or "",
            conditions=tuple(Line.from_api(line) for line in raw.get("conditions", [])),
            rewards=tuple(Line(line.get("text") or "", id=line.get("id")) for line in raw.get("rewards", [])),
        )

    @property
    def title(self) -> str:
        return f"Palier {self.level}" + (f" · {self.name}" if self.name else "")

    @property
    def done_count(self) -> int:
        return sum(1 for line in self.conditions if line.done)

    @property
    def complete(self) -> bool:
        """Toutes les conditions sont remplies (vrai aussi pour un palier sans condition)."""
        return all(line.done for line in self.conditions)

    @property
    def is_empty(self) -> bool:
        return not (self.conditions or self.rewards or self.description)


@dataclass(frozen=True, slots=True)
class Domain:
    id: str
    name: str
    description: str
    icon: str
    position: int
    tier_count: int
    completed: int
    skill_id: str | None
    tiers: tuple[Tier, ...]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Domain:
        return cls(
            id=raw["id"],
            name=raw["name"],
            description=raw.get("description") or "",
            icon=raw.get("icon") or "flask",
            position=int(raw.get("position", 0)),
            tier_count=int(raw["tier_count"]),
            completed=int(raw["completed"]),
            skill_id=raw.get("skill_id"),
            tiers=tuple(Tier.from_api(tier) for tier in raw.get("tiers", [])),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "position": self.position,
            "tier_count": self.tier_count,
            "completed": self.completed,
            "skill_id": self.skill_id,
        }

    @property
    def finished(self) -> bool:
        return self.tier_count > 0 and self.completed >= self.tier_count

    @property
    def progress_text(self) -> str:
        return f"{self.completed} / {self.tier_count} paliers"

    @property
    def next_level(self) -> int | None:
        return None if self.finished or not self.tier_count else self.completed + 1

    def tier(self, level: int) -> Tier | None:
        return next((tier for tier in self.tiers if tier.level == level), None)

    def status(self, level: int) -> TierStatus:
        if level <= self.completed:
            return TierStatus.DONE
        if level == self.completed + 1:
            return TierStatus.NEXT
        return TierStatus.LOCKED

    def can_validate(self, level: int) -> bool:
        """Le palier suit le dernier validé et toutes ses conditions sont remplies."""
        tier = self.tier(level)
        return level == self.next_level and tier is not None and tier.complete

    def ready(self) -> bool:
        """Le prochain palier a des conditions, toutes remplies : il n'attend plus que sa validation."""
        if self.next_level is None:
            return False
        tier = self.tier(self.next_level)
        return tier is not None and bool(tier.conditions) and tier.complete


def parse_domains(document: dict[str, Any]) -> list[Domain]:
    domains = [Domain.from_api(raw) for raw in document.get("categories", [])]
    return sorted(domains, key=lambda d: (d.position, d.name))


def unlocked_recipes(catalog: CatalogService, skill_id: str | None, level: int) -> list[str]:
    """Objets dont la recette exige exactement ce niveau de la compétence liée au domaine."""
    if not skill_id:
        return []
    names = []
    for item in catalog.list_items():
        if item.recipe and any(r.skill_id == skill_id and r.level == level for r in item.recipe.requirements):
            names.append(item.name)
    return sorted(names)
