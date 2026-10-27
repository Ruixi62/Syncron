from __future__ import annotations

import json

from syncron_core.catalog import CraftRepository, is_valid_id
from syncron_core.catalog_format import dump_catalog, parse_catalog, parse_catalog_text
from syncron_core.catalog_service import CatalogService
from syncron_core.models.reference import SkillKind
from syncron_core.models.validation import Severity
from syncron_core.validator import RecipeValidator

from ..sample import sample_data, sample_document


def test_sample_parses_cleanly():
    data = sample_data()
    assert len(data.items) == 15 and len(data.stations) == 3 and len(data.skills) == 2
    machine = next(i for i in data.items if i.id == "machine_x").recipe
    assert (machine.station_id, machine.time_seconds) == ("atelier_energie", 3600)
    assert next(s for s in data.skills if s.id == "rd_energie").kind is SkillKind.RESEARCH


def test_default_station_applies_only_without_explicit_station():
    by_id = {i.id: i for i in sample_data().items}
    assert by_id["circuit_avance"].station_id == "table_craft"
    assert by_id["vis"].station_id == "atelier_debutant"
    assert by_id["quartz"].station_id is None


def test_dump_then_parse_is_lossless():
    data = sample_data()
    again = parse_catalog(json.loads(json.dumps(dump_catalog(data)))).data
    key = lambda d: sorted((i.id, i.name, i.type, i.recipe, i.category) for i in d.items)  # noqa: E731
    assert key(again) == key(data)
    assert sorted(s.id for s in again.stations) == sorted(s.id for s in data.stations)


def test_invalid_json_reports_line():
    result = parse_catalog_text('{\n  "items": {\n    "a": {"type": "raw",}\n  }\n}')
    assert result.has_errors and "ligne 3" in result.issues[0].message


def test_invalid_ids_and_entries_are_rejected_individually():
    result = parse_catalog(
        {
            "items": {
                "ok": {"type": "raw"},
                "Pas Bon": {"type": "raw"},
                "bad_type": {"type": "craft"},
                "bad_time": {"type": "crafted", "time": "deux heures", "recipe": {"ok": 1}},
                "bool_qty": {"type": "crafted", "recipe": {"ok": True}},
            }
        }
    )
    assert [i.id for i in result.data.items] == ["ok"]
    assert len([i for i in result.issues if i.severity is Severity.ERROR]) == 4


def test_validator_detects_references_levels_and_cycles():
    document = sample_document()
    document["items"]["a"] = {"type": "crafted", "station": "fantome", "recipe": {"b": 1}}
    document["items"]["b"] = {"type": "crafted", "requires": {"rd_energie": 11}, "recipe": {"a": 1}}
    document["items"]["c"] = {"type": "crafted", "requires": {"pilote": 1}, "recipe": {"ghost": 1}}
    report = RecipeValidator().validate(parse_catalog(document).data)
    assert report.item_ids_with_errors == {"a", "b", "c"}
    text = " ".join(str(i) for i in report.issues)
    assert "fantome" in text and "maximum" in text and "pilote" in text and "ghost" in text and "circulaire" in text


def test_id_rule():
    assert is_valid_id("circuit_avance") and is_valid_id("lingot-or.2")
    assert not is_valid_id("Circuit") and not is_valid_id("a b") and not is_valid_id("_x") and not is_valid_id("")


def test_search_and_resolve():
    catalog = CatalogService(CraftRepository(sample_data()))
    assert [i.name for i in catalog.search("circuit")] == ["Circuit avancé", "Circuit basique", "Circuit industriel"]
    assert catalog.resolve("machine x").id == "machine_x"
    assert [i.id for i in catalog.used_in("circuit_avance")] == ["circuit_industriel", "machine_x"]
