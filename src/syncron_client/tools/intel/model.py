"""Données de la carte Iris, prêtes à dessiner et à chercher.

Les formes (territoires, frontières, régions) sont en chunks : 1 chunk = 16 blocs.
Les marqueurs de biome, les maisons, l'atlas et les événements sont en blocs.
Chaque anneau d'un polygone est une liste plate [x0, z0, x1, z1, …].
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath

CHUNK = 16
DEFAULT_COLOR = "#8892a6"
HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
EVENT_COLORS = {"meteor": "#f97316", "rift": "#a855f7", "volcano": "#ef4444", "other": "#38bdf8"}
EVENT_ICONS = {"meteor": "comet", "rift": "zap", "volcano": "flame", "other": "alert"}
EVENT_NAMES = {"meteor": "Météorite", "rift": "Faille", "volcano": "Volcan", "other": "Autre événement"}


def color(value: Any) -> str:
    match = HEX.match(str(value or ""))
    return f"#{match.group(1).lower()}" if match else DEFAULT_COLOR


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def build_path(polygons: Any) -> tuple[QPainterPath, QRectF | None]:
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    for polygon in polygons if isinstance(polygons, list) else []:
        for ring in polygon if isinstance(polygon, list) else []:
            if not isinstance(ring, list) or len(ring) < 4:
                continue
            points = [(_number(ring[i]), _number(ring[i + 1])) for i in range(0, len(ring) - 1, 2)]
            points = [(x, z) for x, z in points if x is not None and z is not None]
            if len(points) < 2:
                continue
            path.moveTo(*points[0])
            for x, z in points[1:]:
                path.lineTo(x, z)
            path.closeSubpath()
    if path.isEmpty():
        return path, None
    return path, path.boundingRect()


def _point(value: Any, scale: float = 1.0) -> QPointF | None:
    if isinstance(value, list) and len(value) >= 2:
        x, z = _number(value[0]), _number(value[1])
        if x is not None and z is not None:
            return QPointF(x / scale, z / scale)
    return None


@dataclass
class Home:
    name: str
    x: int
    z: int


@dataclass
class Faction:
    """Pays d'après ses claims (territoires)."""

    name: str
    id: str
    color: str
    chunks: int
    kind: str
    flag: bool
    homes: list[Home]
    label: QPointF | None
    path: QPainterPath
    bbox: QRectF | None


@dataclass
class Frontier:
    name: str
    chunks: int
    color: str
    path: QPainterPath
    bbox: QRectF | None


@dataclass
class Region:
    key: str
    path: QPainterPath
    bbox: QRectF | None


@dataclass
class Marker:
    x: float
    z: float
    biome: str
    region: str


@dataclass
class Event:
    id: int
    kind: str
    title: str
    x: int | None
    z: int | None
    active: bool = True


@dataclass
class World:
    factions: list[Faction] = field(default_factory=list)
    frontiers: list[Frontier] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    atlas: dict[str, Any] = field(default_factory=dict)
    countries: dict[str, dict[str, Any]] = field(default_factory=dict)  # atlas, par nom
    biomes: dict[str, dict[str, Any]] = field(default_factory=dict)
    atlas_regions: dict[str, dict[str, Any]] = field(default_factory=dict)  # par slug en minuscules
    fetched: dict[str, str | None] = field(default_factory=dict)
    members: dict[str, dict[str, Any]] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    weather_raw: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.reindex()

    def reindex(self) -> None:
        self._factions = {f.name: f for f in self.factions}
        self._frontiers = {f.name: f for f in self.frontiers}
        names = {f.name for f in self.factions} | {f.name for f in self.frontiers}
        self.names = sorted(names, key=lambda n: (-self.chunks_of(n), n.lower()))

    @property
    def empty(self) -> bool:
        return not self.factions and not self.frontiers

    def faction(self, name: str) -> Faction | None:
        return self._factions.get(name)

    def frontier(self, name: str) -> Frontier | None:
        return self._frontiers.get(name)

    def chunks_of(self, name: str) -> int:
        faction = self._factions.get(name)
        return faction.chunks if faction else 0

    def color_of(self, name: str) -> str:
        faction = self._factions.get(name)
        if faction is not None and faction.color != DEFAULT_COLOR:
            return faction.color
        return color(self.countries.get(name, {}).get("color"))

    def region_of(self, name: str) -> dict[str, Any] | None:
        slug = str(self.countries.get(name, {}).get("region") or "").lower()
        return self.atlas_regions.get(slug) if slug else None

    def bounds(self) -> QRectF:
        """Limites du monde, en chunks."""
        bounds = self.atlas.get("bounds")
        if isinstance(bounds, list) and len(bounds) == 4 and all(_number(v) is not None for v in bounds):
            x0, z0, x1, z1 = (float(v) / CHUNK for v in bounds)
            if x1 > x0 and z1 > z0:
                return QRectF(x0, z0, x1 - x0, z1 - z0)
        rect = QRectF()
        for shape in [*self.frontiers, *self.factions]:
            if shape.bbox is not None:
                rect = rect.united(shape.bbox) if not rect.isNull() else QRectF(shape.bbox)
        return rect if not rect.isNull() else QRectF(-100, -100, 200, 200)

    def matches(self, query: str) -> list[str]:
        needle = query.strip().lower()
        if not needle:
            return list(self.names)
        found = [n for n in self.names if needle in n.lower()]
        players = [
            country
            for country, data in self.members.items()
            if country not in found
            and any(needle in str(m.get("name", "")).lower() for m in data.get("members", []) if isinstance(m, dict))
        ]
        return found + [n for n in self.names if n in players]

    def country_of_player(self, query: str) -> str | None:
        needle = query.strip().lower()
        for country, data in self.members.items():
            for member in data.get("members", []):
                if isinstance(member, dict) and str(member.get("name", "")).lower() == needle:
                    return country
        return None

    def game_time(self) -> str:
        worlds = self.state.get("worlds") if isinstance(self.state, dict) else None
        first = worlds[0] if isinstance(worlds, list) and worlds and isinstance(worlds[0], dict) else None
        day_time = _number(first.get("dayTime")) if first else None
        if day_time is None:
            return ""
        hours = (day_time / 1000 + 6) % 24
        text = f"{int(hours):02d}:{int((hours - int(hours)) * 60):02d}"
        weather = "orage" if first.get("thundering") else "pluie" if first.get("raining") else "beau temps"
        return f"{text} · {weather}"


def parse_map(data: dict[str, Any] | None) -> World:
    data = data or {}
    atlas = data.get("atlas") if isinstance(data.get("atlas"), dict) else {}
    countries = {str(c.get("name")): c for c in atlas.get("countries", []) if isinstance(c, dict) and c.get("name")}
    factions = []
    for raw in (data.get("territories") or {}).get("factions", []) if isinstance(data.get("territories"), dict) else []:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        path, bbox = build_path(raw.get("polygons"))
        homes = [
            Home(str(h.get("name") or "maison"), int(h["x"]), int(h["z"]))
            for h in raw.get("homes") or []
            if isinstance(h, dict) and _number(h.get("x")) is not None and _number(h.get("z")) is not None
        ]
        label = _point(raw.get("label"))
        if label is None and homes:
            label = QPointF(homes[0].x / CHUNK, homes[0].z / CHUNK)
        factions.append(
            Faction(
                name=str(raw["name"]),
                id=str(raw.get("id") or ""),
                color=color(raw.get("color")),
                chunks=int(_number(raw.get("chunks")) or 0),
                kind=str(raw.get("kind") or ""),
                flag=bool(raw.get("flag")),
                homes=homes,
                label=label,
                path=path,
                bbox=bbox,
            )
        )
    frontiers = []
    raw_frontiers = data.get("frontiers") if isinstance(data.get("frontiers"), dict) else {}
    for raw in raw_frontiers.get("countries", []):
        if not isinstance(raw, dict) or not raw.get("key"):
            continue
        name = str(raw["key"])
        path, bbox = build_path(raw.get("polygons"))
        frontiers.append(
            Frontier(
                name, int(_number(raw.get("chunks")) or 0), color(countries.get(name, {}).get("color")), path, bbox
            )
        )
    regions = []
    raw_regions = data.get("regions") if isinstance(data.get("regions"), dict) else {}
    for raw in raw_regions.get("regions", []):
        if isinstance(raw, dict):
            path, bbox = build_path(raw.get("polygons"))
            if bbox is not None:
                regions.append(Region(str(raw.get("key") or ""), path, bbox))
    markers = [
        Marker(float(m["x"]), float(m["z"]), str(m.get("biome") or ""), str(m.get("region") or ""))
        for m in atlas.get("markers", [])
        if isinstance(m, dict) and _number(m.get("x")) is not None and _number(m.get("z")) is not None
    ]
    return World(
        factions=factions,
        frontiers=frontiers,
        regions=regions,
        markers=markers,
        atlas=atlas,
        countries=countries,
        biomes={str(b.get("name")): b for b in atlas.get("biomes", []) if isinstance(b, dict)},
        atlas_regions={
            str(r.get("slug")).lower(): r for r in atlas.get("regions", []) if isinstance(r, dict) and r.get("slug")
        },
        fetched={k: v for k, v in (data.get("fetched") or {}).items() if isinstance(k, str)},
    )


def parse_events(raw: Any) -> list[Event]:
    events = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or "id" not in item:
            continue
        kind = item.get("kind") if item.get("kind") in EVENT_COLORS else "other"
        events.append(
            Event(
                id=int(item["id"]),
                kind=kind,
                title=str(item.get("title") or EVENT_NAMES[kind]),
                x=item.get("x") if isinstance(item.get("x"), int) else None,
                z=item.get("z") if isinstance(item.get("z"), int) else None,
                active=bool(item.get("active", True)),
            )
        )
    return events


def apply_live(world: World, live: dict[str, Any] | None) -> None:
    live = live or {}
    world.state = live.get("state") if isinstance(live.get("state"), dict) else {}
    weather = live.get("weather") if isinstance(live.get("weather"), dict) else {}
    world.weather_raw = weather.get("events") if isinstance(weather.get("events"), list) else []
    world.events = parse_events(live.get("events"))
    for kind, stamp in (live.get("fetched") or {}).items():
        world.fetched[kind] = stamp


def apply_members(world: World, members: dict[str, Any] | None) -> None:
    raw = (members or {}).get("members")
    world.members = {str(k): v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}
    for kind, stamp in ((members or {}).get("fetched") or {}).items():
        world.fetched[kind] = stamp
    world.reindex()


def dots(count: Any, total: int = 5) -> str:
    filled = max(0, min(total, int(_number(count) or 0)))
    return "●" * filled + "○" * (total - filled)


def thousands(value: Any) -> str:
    number = _number(value)
    return f"{int(number):,}".replace(",", " ") if number is not None else "—"
