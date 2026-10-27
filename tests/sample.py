"""Catalogue d'exemple partagé par les tests du noyau, du serveur et du client."""

from __future__ import annotations

import copy
from typing import Any

from syncron_core.catalog import CraftData
from syncron_core.catalog_format import parse_catalog

STATIONS: dict[str, Any] = {
    "table_craft": {"name": "Table de craft"},
    "atelier_energie": {"name": "Atelier d'énergie"},
    "atelier_debutant": {"name": "Atelier du débutant"},
}
SKILLS: dict[str, Any] = {
    "ingenieur": {"name": "Ingénieur", "kind": "job", "max_level": 50},
    "rd_energie": {"name": "R&D Énergie", "kind": "research", "max_level": 10},
}
ITEMS: dict[str, Any] = {
    "quartz": {"name": "Quartz", "type": "raw", "category": "Minerais"},
    "pierre": {"name": "Pierre", "type": "raw"},
    "redstone": {"name": "Redstone", "type": "raw"},
    "bois": {"name": "Bois", "type": "raw"},
    "lingot_etain": {"name": "Lingot d'étain", "type": "raw"},
    "fer": {"name": "Fer", "type": "raw"},
    "repeteur_redstone": {
        "name": "Répéteur Redstone",
        "type": "crafted",
        "recipe": {"quartz": 3, "pierre": 2, "redstone": 1},
    },
    "circuit_avance": {
        "name": "Circuit avancé",
        "type": "crafted",
        "category": "Électronique",
        "time": "3m",
        "requires": {"ingenieur": 10},
        "recipe": {"lingot_etain": 3, "bois": 1, "repeteur_redstone": 1},
    },
    "circuit_basique": {"name": "Circuit basique", "type": "crafted", "category": "Électronique", "recipe": {"fer": 1}},
    "circuit_industriel": {
        "name": "Circuit industriel",
        "type": "crafted",
        "category": "Électronique",
        "recipe": {"circuit_avance": 1},
    },
    "machine_x": {
        "name": "Machine X",
        "type": "crafted",
        "station": "atelier_energie",
        "time": "1h",
        "requires": {"ingenieur": 20, "rd_energie": 3},
        "recipe": {"circuit_avance": 6, "quartz": 10},
    },
    "vis": {
        "name": "Vis",
        "type": "crafted",
        "station": "atelier_debutant",
        "time": "10s",
        "output": 4,
        "recipe": {"fer": 1},
    },
    "support": {"name": "Support", "type": "crafted", "recipe": {"vis": 3}},
    "cadre": {"name": "Cadre", "type": "crafted", "recipe": {"vis": 3}},
    "chassis": {"name": "Châssis", "type": "crafted", "recipe": {"support": 1, "cadre": 1}},
}


def sample_document() -> dict[str, Any]:
    return copy.deepcopy(
        {
            "schema_version": 2,
            "default_station": "table_craft",
            "stations": STATIONS,
            "skills": SKILLS,
            "items": ITEMS,
        }
    )


def sample_data() -> CraftData:
    result = parse_catalog(sample_document(), "sample.json")
    assert not result.issues, result.issues
    return result.data
