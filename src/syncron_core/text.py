"""Utilitaires texte : normalisation pour la recherche, formatage des quantités."""

from __future__ import annotations

import unicodedata


def normalize(text: str) -> str:
    """Minuscule, sans accents, '_' et '-' traités comme des espaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = stripped.casefold().replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def prettify_id(item_id: str) -> str:
    """'circuit_avance' -> 'Circuit avance' (nom par défaut si 'name' est absent)."""
    words = item_id.replace("_", " ").replace("-", " ").split()
    if not words:
        return item_id
    sentence = " ".join(words)
    return sentence[0].upper() + sentence[1:]


def format_quantity(value: int) -> str:
    """12345 -> '12 345' (espace fine insécable, typographie française)."""
    return f"{value:,}".replace(",", " ")


def ceil_div(numerator: int, denominator: int) -> int:
    """Division entière arrondie au supérieur, sans passer par les flottants."""
    return -(-numerator // denominator)
