"""Recherche (carte Iris) et Mes alertes, contre le vrai serveur avec des données Iris en base."""

from __future__ import annotations

import asyncio
import json

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from syncron_client.tools.intel.model import parse_map

from .test_end_to_end import admin_section, sign_in

TERRITORIES = {
    "factions": [
        {
            "id": "c1",
            "name": "Syldavie",
            "color": "#e11d48",
            "chunks": 12,
            "kind": "pays",
            "polygons": [[[0, 0, 4, 0, 4, 3, 0, 3]]],
            "label": [2, 1],
            "homes": [{"name": "Capitale", "x": 32, "z": 16}],
            "members": 2,
        },
        {
            "id": "c2",
            "name": "Bordurie",
            "color": "#2563eb",
            "chunks": 1,
            "polygons": [],
            "homes": [{"x": 400, "z": 400}],
        },
    ]
}
ATLAS = {
    "title": "Terre",
    "countries": [{"name": "Syldavie", "color": "#e11d48", "chunks": 20, "region": "europe", "nameEn": "Syldavia"}],
    "biomes": [{"name": "plains", "nameFr": "Plaines", "color": "#84cc16", "solar": 1.2, "solarDots": 3}],
    "regions": [{"slug": "europe", "name": "Europe", "oilMax": 5000, "oilDots": 2, "gasMax": 900, "gasDots": 1}],
    "markers": [{"x": 800, "z": 800, "biome": "plains", "region": "europe"}],
    "bounds": [-1600, -1600, 1600, 1600],
}
MEMBERS = {
    "Syldavie": {
        "total": 2,
        "complete": True,
        "members": [{"name": "Tintin", "rank": "Chef", "rankColor": "#ffaa00", "leader": True}, {"name": "Milou"}],
    }
}


def seed_iris(server, events=()) -> None:
    rows = {
        "territories": TERRITORIES,
        "atlas": ATLAS,
        "frontiers": {"countries": [{"key": "Syldavie", "chunks": 20, "polygons": [[[-1, -1, 6, -1, 6, 5, -1, 5]]]}]},
        "regions": {"regions": [{"key": "europe", "polygons": [[[-10, -10, 10, -10, 10, 10, -10, 10]]]}]},
        "state": {"worlds": [{"dayTime": 6000, "time": 123456, "raining": True}], "config": {"maxPlayers": 200}},
        "weather": {"events": []},
        "members": MEMBERS,
    }
    statements = []
    for kind, payload in rows.items():
        body = json.dumps(payload).replace("'", "''")
        statements.append(
            f"insert into iris_snapshots (kind, payload, size_bytes, fetched_at, attempted_at, error) "
            f"values ('{kind}', '{body}', {len(body)}, now(), now(), '') "
            f"on conflict (kind) do update set payload = excluded.payload, fetched_at = now()"
        )
    for index, (kind, title, x, z) in enumerate(events):
        statements.append(
            "insert into iris_events (key, kind, title, x, z, payload, first_seen, last_seen) "
            f"values ('k{index}{kind}', '{kind}', '{title}', {x}, {z}, '{{}}', now(), now())"
        )
    asyncio.run(server._sql("; ".join(statements), server.db_name))


def test_world_is_parsed_from_iris_data():
    world = parse_map({"territories": TERRITORIES, "atlas": ATLAS, "fetched": {"atlas": "2026-11-01T10:00:00+00:00"}})
    syldavie = world.faction("Syldavie")
    assert syldavie.bbox.width() == 4 and syldavie.path.contains(QPointF(2, 1))
    assert world.faction("Bordurie").bbox is None and world.faction("Bordurie").label == QPointF(25, 25)
    assert world.names == ["Syldavie", "Bordurie"] and world.region_of("Syldavie")["name"] == "Europe"
    assert world.bounds().width() == 200
    assert (
        parse_map({"territories": {"factions": [{"name": "X", "polygons": [[[1, "a"]]], "color": "red"}]}})
        .factions[0]
        .color
        == "#8892a6"
    )


def test_research_map_shows_countries_members_and_events(make_launcher, server, tmp_path):
    seed_iris(server, [("meteor", "Météorite : pluie", 160, 320)])
    shell = sign_in(make_launcher(user_dir=tmp_path / "joueur"), "joueur", "player")
    window = shell.window
    window.show_page("intel")
    tool = shell.registry.get("intel")
    page = tool.page
    assert not tool.world.empty and page.count.text() == "2 pays"
    assert page.events_banner.isVisible() and "Météorite : pluie (160, 320)" in page.events_banner.text()

    assert page.find("Tintin")
    assert page.map.selected == "Syldavie" and page.panel.title == "Syldavie" and page.panel.isVisible()
    page.search.setText("milou")
    assert page.count.text() == "1 / 2 pays"
    hits = tool.search("syl", 5)
    assert [h.title for h in hits] == ["Syldavie"]

    page.map.resize(800, 600)
    page.map.fit()
    point = page.map.to_screen(2, 1)
    assert page.map.pick_country(point) == "Syldavie"
    assert page.map.pick_event(page.map.to_screen(10, 20)).title == "Météorite : pluie"
    page.map.set_layer("markers", True)
    marker = page.map.pick_marker(page.map.to_screen(50, 50))
    page.show_marker(marker)
    assert page.panel.title == "Plaines" and page.panel_kind == "marker"
    page.show_world()
    assert page.panel.title == "Terre" and tool.world.game_time() == "12:00 · pluie"
    window.open_in_tool("intel", "at:160:320")
    assert page.panel_kind == "event" and page.map.center == QPointF(10, 20)
    page.map.grab()

    tool.refresh()
    assert page.world is tool.world, "rien n'a changé : la carte n'est pas retéléchargée (ETag)"


def test_alerts_warn_once_for_chosen_kinds(make_launcher, server, tmp_path):
    seed_iris(server, [("meteor", "Météorite", 160, 320), ("volcano", "Volcan", -48, 16)])
    shell = sign_in(make_launcher(user_dir=tmp_path / "joueur"), "joueur", "player")
    window = shell.window
    received = []
    shell.host.notifications.alerted.connect(lambda *args: received.append(args))
    QApplication.processEvents()
    alerts = shell.registry.get("alerts")
    assert sorted(a[0] for a in received) == ["Météorite", "Volcan"]
    assert ("Météorite", "Position : x 160 · z 320", "intel", "at:160:320") in received
    assert "Volcan" in window.toast.message() or "Météorite" in window.toast.message()
    assert alerts.status().badge == "2" and window.sidebar.badge_text("alerts") == "2"

    alerts.poll()
    assert len(received) == 2, "un événement n'alerte qu'une fois"
    window.show_page("alerts")
    page = alerts.page
    assert len(page.cards) == 2 and page.recent.rowCount() == 2
    page.boxes["volcano"].setChecked(False)
    assert alerts.status().badge == "1" and alerts.kinds["volcano"] is False

    asyncio.run(
        server._sql(
            "insert into iris_events (key, kind, title, x, z, payload, first_seen, last_seen) "
            "values ('k9', 'volcano', 'Volcan 2', 0, 0, '{}', now(), now())",
            server.db_name,
        )
    )
    alerts.poll()
    assert len(received) == 2, "les volcans ne sont plus suivis"
    page.cards[0].showRequested.emit(160, 320)
    assert window.current_page == "intel"

    again = sign_in(make_launcher(user_dir=tmp_path / "joueur"), "joueur", "player")
    replay = []
    again.host.notifications.alerted.connect(lambda *args: replay.append(args))
    QApplication.processEvents()
    assert replay == [] and again.registry.get("alerts").kinds["volcano"] is False


def test_team_sees_iris_collection_status(make_launcher, server, tmp_path):
    seed_iris(server)
    chef = sign_in(make_launcher(user_dir=tmp_path / "chef"), "chef", "admin")
    view = admin_section(chef, "admin.iris")
    assert view.status["enabled"] and view.table.rowCount() == 7
    assert view.state_chip.text() == "Active"
