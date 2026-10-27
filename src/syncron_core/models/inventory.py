"""Stock de l'utilisateur.

En V1 le calcul utilise un inventaire vide. Le moteur sait déjà déduire un
stock, ce qui rend la V2 (stock personnel, ressources manquantes, liste de
courses) branchable sans toucher à l'algorithme.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


class Inventory:
    __slots__ = ("_quantities",)

    def __init__(self, quantities: Mapping[str, int] | None = None) -> None:
        cleaned: dict[str, int] = {}
        for item_id, quantity in (quantities or {}).items():
            if quantity < 0:
                raise ValueError(f"Stock négatif pour « {item_id} » : {quantity}")
            if quantity:
                cleaned[item_id] = quantity
        self._quantities = MappingProxyType(cleaned)

    @classmethod
    def empty(cls) -> Inventory:
        return cls()

    def available(self, item_id: str) -> int:
        return self._quantities.get(item_id, 0)

    def as_dict(self) -> dict[str, int]:
        return dict(self._quantities)

    def __bool__(self) -> bool:
        return bool(self._quantities)

    def __len__(self) -> int:
        return len(self._quantities)
