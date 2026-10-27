"""Format JSON d'échange du catalogue (import / export par les admins).

Parseur tolérant : une entrée invalide est ignorée et signalée avec un message
précis, les autres sont conservées. Les références croisées (ingrédients,
ateliers, compétences, cycles) sont vérifiées ensuite par `RecipeValidator`.

Versions acceptées :
    1 — objets seuls (NGCraft 1.x)
    2 — + "stations", "skills", "default_station", et par recette
        "station", "time", "requires"
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from syncron_core.catalog import ID_RULE, CraftData, is_valid_id
from syncron_core.duration import DurationError, parse_duration
from syncron_core.models.item import Ingredient, Item, ItemType, Recipe, Requirement
from syncron_core.models.reference import Skill, SkillKind, Station
from syncron_core.models.validation import Severity, ValidationIssue
from syncron_core.text import prettify_id

SCHEMA_VERSION = 2
_ROOT_KEYS = frozenset({"$schema", "schema_version", "default_station", "stations", "skills", "items"})
_COMMON_ITEM_KEYS = frozenset({"name", "type", "category", "image", "description"})
_CRAFTED_ITEM_KEYS = _COMMON_ITEM_KEYS | {"output", "recipe", "station", "time", "requires"}
_STATION_KEYS = frozenset({"name", "description", "image"})
_SKILL_KEYS = frozenset({"name", "kind", "max_level", "description"})

Report = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ParseResult:
    data: CraftData
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def has_errors(self) -> bool:
        return any(issue.severity is Severity.ERROR for issue in self.issues)


def parse_catalog_text(text: str, label: str = "import.json") -> ParseResult:
    try:
        document = json.loads(text.lstrip("﻿"))
    except json.JSONDecodeError as exc:
        message = f"JSON invalide ligne {exc.lineno}, colonne {exc.colno} : {exc.msg}"
        return ParseResult(CraftData(), (ValidationIssue(Severity.ERROR, message, None, label),))
    return parse_catalog(document, label)


def parse_catalog(document: Any, label: str = "import.json") -> ParseResult:
    return _Parser(label).parse(document)


def dump_catalog(data: CraftData) -> dict[str, Any]:
    """Document v2 canonique : réimportable tel quel, trié par identifiant."""
    stations = {
        station.id: _without_empty({"name": station.name, "description": station.description, "image": station.image})
        for station in sorted(data.stations, key=lambda s: s.id)
    }
    skills = {
        skill.id: _without_empty(
            {
                "name": skill.name,
                "kind": skill.kind.value,
                "max_level": skill.max_level,
                "description": skill.description,
            }
        )
        for skill in sorted(data.skills, key=lambda s: s.id)
    }
    items: dict[str, Any] = {}
    for item in sorted(data.items, key=lambda i: i.id):
        entry: dict[str, Any] = {"name": item.name, "type": item.type.value}
        entry.update(_without_empty({"category": item.category, "description": item.description, "image": item.image}))
        if item.recipe is not None:
            recipe = item.recipe
            if recipe.station_id:
                entry["station"] = recipe.station_id
            if recipe.time_seconds:
                entry["time"] = recipe.time_seconds
            if recipe.requirements:
                entry["requires"] = {r.skill_id: r.level for r in recipe.requirements}
            entry["output"] = recipe.output
            entry["recipe"] = {i.item_id: i.quantity for i in recipe.ingredients}
        items[item.id] = entry
    return {"schema_version": SCHEMA_VERSION, "stations": stations, "skills": skills, "items": items}


def _without_empty(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "")}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class _Parser:
    def __init__(self, label: str) -> None:
        self._label = label
        self._issues: list[ValidationIssue] = []

    def parse(self, document: Any) -> ParseResult:
        if not isinstance(document, dict):
            self._issue(Severity.ERROR, "La racine du fichier doit être un objet { … }.")
            return self._result()
        version = document.get("schema_version", 1)
        if not _is_int(version) or not 1 <= version <= SCHEMA_VERSION:
            self._issue(Severity.ERROR, f"schema_version {version!r} non supportée (1 à {SCHEMA_VERSION}).")
            return self._result()
        for key in sorted(document.keys() - _ROOT_KEYS):
            self._issue(Severity.WARNING, f"Clé racine inconnue ignorée : « {key} ».")
        if "items" not in document:
            self._issue(Severity.ERROR, "La clé « items » est obligatoire.")

        stations = self._section(document, "stations", self._station)
        skills = self._section(document, "skills", self._skill)
        default_station = self._default_station(document)
        items = self._section(
            document, "items", lambda key, entry, err, warn: self._item(key, entry, default_station, err, warn)
        )
        return self._result(CraftData(tuple(items), tuple(stations), tuple(skills)))

    def _result(self, data: CraftData | None = None) -> ParseResult:
        return ParseResult(data or CraftData(), tuple(self._issues))

    def _issue(self, severity: Severity, message: str, entity_id: str | None = None, section: str = "items") -> None:
        self._issues.append(ValidationIssue(severity, message, entity_id, self._label, section))

    def _default_station(self, document: dict[str, Any]) -> str | None:
        value = document.get("default_station")
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            self._issue(Severity.ERROR, "« default_station » doit être l'id d'un atelier.")
            return None
        return value.strip()

    def _section(self, document: dict[str, Any], section: str, parse_entry) -> list:
        raw = document.get(section)
        if raw is None:
            return []
        if not isinstance(raw, dict):
            self._issue(Severity.ERROR, f'« {section} » doit être un objet {{ "id": {{…}} }}.')
            return []
        parsed = []
        for key, value in raw.items():

            def error(message: str, key: str = key) -> None:
                self._issue(Severity.ERROR, message, key, section)

            def warning(message: str, key: str = key) -> None:
                self._issue(Severity.WARNING, message, key, section)

            if not is_valid_id(key):
                error(f"Identifiant invalide ({ID_RULE}).")
                continue
            if not isinstance(value, dict):
                error("La définition doit être un objet { … }.")
                continue
            entity = parse_entry(key, value, error, warning)
            if entity is not None:
                parsed.append(entity)
        return parsed

    def _station(self, station_id: str, entry: dict, error: Report, warning: Report) -> Station | None:
        texts = _text_fields(entry, ("name", "description", "image"), error)
        if texts is None:
            return None
        _warn_unknown_keys(entry, _STATION_KEYS, warning)
        return Station(
            id=station_id,
            name=texts["name"] or prettify_id(station_id),
            description=texts["description"] or "",
            image=texts["image"],
            source=self._label,
        )

    def _skill(self, skill_id: str, entry: dict, error: Report, warning: Report) -> Skill | None:
        texts = _text_fields(entry, ("name", "description"), error)
        if texts is None:
            return None
        raw_kind = entry.get("kind", SkillKind.OTHER.value)
        try:
            kind = SkillKind(raw_kind)
        except ValueError:
            error(f'« kind » doit valoir "job", "research" ou "other" (reçu : {raw_kind!r}).')
            return None
        max_level = entry.get("max_level")
        if max_level is not None and (not _is_int(max_level) or max_level < 1):
            error(f"« max_level » doit être un entier ≥ 1 (reçu : {max_level!r}).")
            return None
        _warn_unknown_keys(entry, _SKILL_KEYS, warning)
        return Skill(
            id=skill_id,
            name=texts["name"] or prettify_id(skill_id),
            kind=kind,
            max_level=max_level,
            description=texts["description"] or "",
            source=self._label,
        )

    def _item(self, item_id: str, entry: dict, default_station: str | None, error: Report, warning: Report):
        raw_type = entry.get("type")
        try:
            item_type = ItemType(raw_type)
        except ValueError:
            error(f'« type » doit valoir "raw" ou "crafted" (reçu : {raw_type!r}).')
            return None
        texts = _text_fields(entry, ("name", "category", "image", "description"), error)
        if texts is None:
            return None
        _warn_unknown_keys(entry, _CRAFTED_ITEM_KEYS, warning)
        if item_type is ItemType.RAW:
            for key in sorted(entry.keys() & (_CRAFTED_ITEM_KEYS - _COMMON_ITEM_KEYS)):
                warning(f"« {key} » ignoré : une ressource primaire ne se fabrique pas.")
            recipe = None
        else:
            recipe = _recipe(entry, default_station, error)
            if recipe is None:
                return None
        return Item(
            id=item_id,
            name=texts["name"] or prettify_id(item_id),
            type=item_type,
            recipe=recipe,
            category=texts["category"] or "",
            image=texts["image"],
            description=texts["description"] or "",
            source=self._label,
        )


def _recipe(entry: dict, default_station: str | None, error: Report) -> Recipe | None:
    output = entry.get("output", 1)
    if not _is_int(output) or output < 1:
        error(f"« output » doit être un entier ≥ 1 (reçu : {output!r}).")
        return None
    ingredients = _positive_int_mapping(entry.get("recipe"), "recipe", "ingrédient", error, required=True)
    if ingredients is None:
        return None
    requirements = _positive_int_mapping(entry.get("requires"), "requires", "compétence", error, required=False)
    if requirements is None:
        return None
    station = entry.get("station", default_station)
    if station is not None and (not isinstance(station, str) or not station.strip()):
        error("« station » doit être l'id d'un atelier déclaré dans « stations ».")
        return None
    try:
        time_seconds = parse_duration(entry.get("time", 0))
    except DurationError as exc:
        error(f"« time » : {exc}")
        return None
    return Recipe(
        output=output,
        ingredients=tuple(Ingredient(key, value) for key, value in ingredients.items()),
        station_id=station.strip() if station else None,
        time_seconds=time_seconds,
        requirements=tuple(Requirement(key, value) for key, value in requirements.items()),
    )


def _text_fields(entry: dict, keys: tuple[str, ...], error: Report) -> dict[str, str | None] | None:
    values: dict[str, str | None] = {}
    for key in keys:
        value = entry.get(key)
        if value is not None and not isinstance(value, str):
            error(f"« {key} » doit être une chaîne de caractères.")
            return None
        values[key] = (value.strip() or None) if isinstance(value, str) else None
    return values


def _warn_unknown_keys(entry: dict, allowed: frozenset[str], warning: Report) -> None:
    for key in sorted(entry.keys() - allowed):
        warning(f"Clé inconnue ignorée : « {key} » (faute de frappe ?).")


def _positive_int_mapping(value: Any, field: str, what: str, error: Report, required: bool) -> dict[str, int] | None:
    if value is None and not required:
        return {}
    if not isinstance(value, dict) or (required and not value):
        error(f'« {field} » doit être un objet non vide : {{ "id_{what}": nombre }}.')
        return None
    for key, quantity in value.items():
        if not key.strip():
            error(f"Identifiant de {what} vide dans « {field} ».")
            return None
        if not _is_int(quantity) or quantity < 1:
            error(f"« {field} » → « {key} » : {quantity!r} invalide (entier ≥ 1 attendu).")
            return None
    return dict(value)
