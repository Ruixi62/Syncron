"""Carte Iris : collecte (site simulé), événements météo, routes de lecture et de gestion."""

from __future__ import annotations

import json

import httpx
import pytest

from syncron_server.app import create_app
from syncron_server.iris import IrisClient, IrisError, normalize_events

from .conftest import login

TERRITORIES = {
    "factions": [
        {
            "id": "c1",
            "name": "Syldavie",
            "color": "#ff0000",
            "chunks": 12,
            "polygons": [[[0, 0, 4, 0, 4, 3, 0, 3]]],
            "label": [2, 1],
            "homes": [{"name": "capitale", "x": 32, "z": 16}],
            "members": 3,
        },
        {"id": "c2", "name": "Bordurie", "color": "#0000ff", "chunks": 4, "polygons": [], "members": 0},
    ]
}
ATLAS = {"countries": [], "biomes": [], "regions": [], "markers": [], "bounds": [-100, -100, 100, 100]}


class FakeIris:
    def __init__(self) -> None:
        self.weather: dict = {"events": []}
        self.calls: list[str] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        if self.down:
            return httpx.Response(503)
        routes = {
            "/api/territories/earth": TERRITORIES,
            "/api/atlas/earth": ATLAS,
            "/api/frontiers/earth": {"countries": []},
            "/api/regions/earth": {"regions": []},
            "/api/weather/earth": self.weather,
            "/api/state": {"worlds": [{"dayTime": 6000, "raining": False, "thundering": False}]},
            "/api/countries/c1/members": {
                "total": 1,
                "complete": True,
                "members": [{"name": "Tintin", "rank": "Chef", "leader": True}],
            },
        }
        if path not in routes:
            return httpx.Response(404)
        return httpx.Response(200, content=json.dumps(routes[path]).encode())


@pytest.fixture
def iris() -> FakeIris:
    return FakeIris()


@pytest.fixture
async def app(settings, database, discord, iris):
    settings.iris_pause_seconds = 0.05
    return create_app(settings, database, discord, iris_transport=httpx.MockTransport(iris.handler))


@pytest.fixture
async def http(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://api.syncron.test") as c:
        yield c


def test_events_are_recognised_whatever_their_shape():
    events = normalize_events(
        {
            "events": [
                {"id": 7, "type": "METEOR_SHOWER", "x": 120.4, "z": -50, "remaining": 30},
                {"type": "faille", "position": {"x": 1, "y": 70, "z": 2}},
                {"name": "Éruption du volcan", "location": [10, 64, 20]},
                {"type": "aurora"},
            ]
        }
    )
    assert [e.kind for e in events] == ["meteor", "rift", "volcano", "other"]
    assert (events[0].x, events[0].z) == (120, -50) and (events[1].x, events[1].z) == (1, 2)
    assert (events[2].x, events[2].z) == (10, 20)
    assert events[0].title.startswith("Météorite") and events[3].title == "Aurora"
    moved = normalize_events({"events": [{"id": 7, "type": "METEOR_SHOWER", "x": 0, "z": 0, "remaining": 5}]})
    assert moved[0].key == events[0].key
    countdown = normalize_events([{"type": "rift", "remainingSeconds": 10}, {"type": "rift", "remainingSeconds": 9}])
    assert countdown[0].key == countdown[1].key
    assert normalize_events({"events": "rien"}) == [] and normalize_events(None) == []


async def test_client_refuses_redirects_and_oversized_answers():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/state":
            return httpx.Response(302, headers={"Location": "https://ailleurs.test/"})
        return httpx.Response(200, content=b"pas du json")

    client = IrisClient("https://iris.test", transport=httpx.MockTransport(handler))
    with pytest.raises(IrisError, match="302"):
        await client.get("/api/state")
    with pytest.raises(IrisError, match="illisible"):
        await client.get("/api/weather/earth")


async def test_weather_events_open_and_close(app, http, iris):
    player = await login(http, "joueur", "player")
    collector = app.state.iris
    iris.weather = {"events": [{"id": "m1", "type": "meteor", "x": 100, "z": 200}]}
    assert await collector.run("weather", force=True)
    body = (await http.get("/api/v1/iris/events", headers=player)).json()
    assert body["enabled"] and body["checked_at"]
    [event] = body["events"]
    assert event["kind"] == "meteor" and event["active"] and (event["x"], event["z"]) == (100, 200)

    iris.weather = {"events": [{"id": "m1", "type": "meteor", "x": 100, "z": 200}, {"type": "volcan", "x": 5, "z": 5}]}
    await collector.run("weather", force=True)
    events = (await http.get("/api/v1/iris/events", headers=player)).json()["events"]
    assert {e["kind"] for e in events if e["active"]} == {"meteor", "volcano"}
    assert next(e for e in events if e["kind"] == "meteor")["id"] == event["id"]

    iris.weather = {"events": []}
    await collector.run("weather", force=True)
    events = (await http.get("/api/v1/iris/events", headers=player)).json()["events"]
    assert len(events) == 2 and not any(e["active"] for e in events)

    live = (await http.get("/api/v1/iris/live", headers=player)).json()
    assert live["state"]["worlds"][0]["dayTime"] == 6000 and live["events"] == []

    iris.down = True
    await collector.run("weather", force=True)
    live = (await http.get("/api/v1/iris/live", headers=player)).json()
    assert live["weather"] == {"events": []}, "l'ancienne réponse reste servie si le site ne répond pas"


async def test_map_and_members_are_served_with_etag(app, http, iris):
    player = await login(http, "joueur", "player")
    assert (await http.get("/api/v1/iris/map")).status_code == 401
    empty = (await http.get("/api/v1/iris/map", headers=player)).json()
    assert empty["territories"] is None

    collector = app.state.iris
    await collector.run("map", force=True)
    await collector.run("members", force=True)
    assert "/api/countries/c2/members" not in iris.calls, "les pays sans membres ne sont pas interrogés"

    response = await http.get("/api/v1/iris/map", headers=player)
    body = response.json()
    assert body["territories"]["factions"][0]["name"] == "Syldavie" and body["atlas"]["bounds"] == ATLAS["bounds"]
    assert body["fetched"]["territories"]
    tag = response.headers["etag"]
    again = await http.get("/api/v1/iris/map", headers={**player, "If-None-Match": tag})
    assert again.status_code == 304 and again.content == b""

    members = (await http.get("/api/v1/iris/members", headers=player)).json()["members"]
    assert members["Syldavie"]["members"][0]["name"] == "Tintin"

    calls = len(iris.calls)
    assert not await collector.run("map") or len(iris.calls) == calls, "rien n'est relancé avant l'heure"


async def test_admin_status_and_refresh(app, http, iris, settings):
    player = await login(http, "joueur", "player")
    admin = await login(http, "patron", "admin")
    assert (await http.get("/api/v1/admin/iris", headers=player)).status_code == 403
    status = (await http.get("/api/v1/admin/iris", headers=admin)).json()
    assert status["enabled"] and status["world"] == "earth" and {k["kind"] for k in status["kinds"]} >= {"weather"}

    iris.weather = {"events": [{"type": "rift", "x": 1, "z": 1}]}
    refreshed = await http.post("/api/v1/admin/iris/refresh", json={"job": "weather"}, headers=admin)
    assert refreshed.status_code == 200 and refreshed.json()["started"]
    status = (await http.get("/api/v1/admin/iris", headers=admin)).json()
    assert status["events_active"] == 1
    assert (await http.post("/api/v1/admin/iris/refresh", json={"job": "x"}, headers=admin)).status_code == 422

    journal = (await http.get("/api/v1/admin/audit", headers=admin)).json()
    entries = journal["entries"] if isinstance(journal, dict) else journal
    assert any(e["action"] == "iris.refresh" for e in entries)

    iris.down = True
    await http.post("/api/v1/admin/iris/refresh", json={"job": "map"}, headers=admin)
    kinds = {k["kind"]: k for k in (await http.get("/api/v1/admin/iris", headers=admin)).json()["kinds"]}
    assert "503" in kinds["territories"]["error"]

    settings.iris_enabled = False
    assert (await http.get("/api/v1/iris/map", headers=player)).status_code == 404
