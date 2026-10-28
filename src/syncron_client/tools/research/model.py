"""R&D côté client : domaines, paliers, conditions et récompenses, état d'avancement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from syncron_core.catalog_service import CatalogService
from syncron_core.text import format_quantity


class TierStatus(StrEnum):
    DONE = "done"
    ACTIVE = "active"
    NEXT = "next"
    LOCKED = "locked"

    @property
    def label(self) -> str:
        return {"done": "Terminé", "active": "En cours", "next": "Prochain", "locked": "À venir"}[self.value]

    @property
    def tone(self) -> str:
        return {"done": "success", "active": "accent", "next": "info", "locked": "neutral"}[self.value]

    @property
    def icon(self) -> str:
        return {"done": "check-circle", "active": "play", "next": "flag", "locked": "lock"}[self.value]


@dataclass(frozen=True, slots=True)
class Line:
    text: str
    quantity: int | None = None
    item_id: str | None = None
    done: bool = False

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Line:
        return cls(raw.get("text") or "", raw.get("quantity"), raw.get("item_id"), bool(raw.get("done")))

    def to_api(self) -> dict[str, Any]:
        return {"text": self.text, "quantity": self.quantity, "item_id": self.item_id, "done": self.done}

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
            rewards=tuple(Line.from_api(line) for line in raw.get("rewards", [])),
        )

    @property
    def title(self) -> str:
        return f"Palier {self.level}" + (f" · {self.name}" if self.name else "")

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
    active: bool
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
            active=bool(raw["active"]),
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
            "active": self.active,
            "skill_id": self.skill_id,
        }

    @property
    def finished(self) -> bool:
        return self.tier_count > 0 and self.completed >= self.tier_count

    @property
    def progress_text(self) -> str:
        return f"{self.completed} / {self.tier_count} paliers"

    def tier(self, level: int) -> Tier | None:
        return next((tier for tier in self.tiers if tier.level == level), None)

    def status(self, level: int) -> TierStatus:
        if level <= self.completed:
            return TierStatus.DONE
        if level == self.completed + 1:
            return TierStatus.ACTIVE if self.active else TierStatus.NEXT
        return TierStatus.LOCKED


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
