"""Exceptions métier partagées par le serveur et le client.

Leur message est destiné à l'utilisateur final : il est affiché tel quel.
"""

from __future__ import annotations

from collections.abc import Sequence


class AppError(Exception):
    """Erreur métier attendue."""


class CraftError(AppError):
    pass


class UnknownItemError(CraftError):
    def __init__(self, item_id: str, referenced_by: str | None = None) -> None:
        self.item_id = item_id
        self.referenced_by = referenced_by
        if referenced_by:
            message = f"L'objet « {item_id} » (utilisé par « {referenced_by} ») n'existe pas dans les données."
        else:
            message = f"L'objet « {item_id} » n'existe pas dans les données."
        super().__init__(message)


class RecipeCycleError(CraftError):
    def __init__(self, cycle: Sequence[str]) -> None:
        self.cycle = tuple(cycle)
        super().__init__("Recette circulaire détectée : " + " → ".join(self.cycle))


class InvalidQuantityError(CraftError):
    def __init__(self, quantity: object) -> None:
        self.quantity = quantity
        super().__init__(f"Quantité invalide : {quantity!r}. Elle doit être un entier ≥ 1.")
