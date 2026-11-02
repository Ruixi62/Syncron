"""Profils, annuaire des membres, et préparation de l'API NationsGlory (API simulée)."""

from __future__ import annotations

import json

import httpx
from pydantic import SecretStr

from syncron_server.app import create_app

from .conftest import login


async def test_profile_is_edited_and_shown_in_the_directory(client, player, admin):
    empty = (await client.get("/api/v1/profile", headers=player)).json()
    assert empty["nickname"] == "" and empty["color"] == "teal" and empty["discord_username"] == "joueur"
    profile = {
        "nickname": "Joueur_42",
        "title": "  Ministre   de la Guerre ",
        "bio": "Spécialiste des sièges.",
        "specialties": ["Mineur", "mineur", "Ingénieur", "  Diplomate  "],
        "availability": "Soirs et week-ends",
        "color": "violet",
        "show_discord": False,
    }
    saved = await client.put("/api/v1/profile", json=profile, headers=player)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["title"] == "Ministre de la Guerre" and body["specialties"] == ["Mineur", "Ingénieur", "Diplomate"]

    other = await login(client, "voisin", "player")
    members = (await client.get("/api/v1/members", headers=other)).json()
    me = next(m for m in members if m["nickname"] == "Joueur_42")
    assert me["discord_username"] is None and me["bio"] == "Spécialiste des sièges."
    assert (await client.get(f"/api/v1/members/{me['id']}", headers=admin)).json()["discord_username"] == "joueur"

    for bad in ({"nickname": "a b"}, {"nickname": "ab"}, {"color": "noir"}, {"bio": "x" * 601}):
        assert (await client.put("/api/v1/profile", json=bad, headers=player)).status_code == 422
    assert (await client.put("/api/v1/profile", json={"specialties": ["x"] * 9}, headers=player)).status_code == 422
    assert (await client.get("/api/v1/members")).status_code == 401

    users = (await client.get("/api/v1/admin/users", params={"q": "joueur"}, headers=admin)).json()
    await client.patch(f"/api/v1/admin/users/{users[0]['id']}", json={"is_banned": True}, headers=admin)
    assert not any(m["nickname"] == "Joueur_42" for m in (await client.get("/api/v1/members", headers=other)).json())
    assert (await client.get(f"/api/v1/members/{me['id']}", headers=other)).status_code == 404


class FakeNationsGlory:
    """Répond comme l'API publique ; garde les requêtes reçues."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "x"})
        if request.url.path == "/playercount":
            return httpx.Response(200, json={"count": 1234})
        if request.url.path.startswith("/country/list/"):
            return httpx.Response(200, json=[{"name": "levant"}])
        if request.url.path.startswith("/country/"):
            return httpx.Response(200, json={"name": "Empire du Levant", "claims": 42})
        if request.url.path == "/huge":
            return httpx.Response(200, content=b"[" + b"1," * 2_000_000 + b"1]")
        return httpx.Response(404, json={})


async def _ng_client(settings, database, discord, fake: FakeNationsGlory, key: str = "cle-secrete"):
    settings.ng_api_key = SecretStr(key)
    settings.ng_server = "blue"
    settings.ng_country = "levant"
    app = create_app(settings, database, discord, nationsglory_transport=httpx.MockTransport(fake.handler))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://api.syncron.test")


async def test_nationsglory_calls_are_checked_cached_and_stored(settings, database, discord):
    fake = FakeNationsGlory()
    async with await _ng_client(settings, database, discord, fake) as client:
        admin = await login(client, "patron", "admin")
        player = await login(client, "joueur", "player")
        assert (await client.get("/api/v1/nationsglory/country", headers=player)).status_code == 404

        state = (await client.get("/api/v1/admin/nationsglory", headers=admin)).json()
        assert state["configured"] and state["key_set"] and state["country"] == "levant"
        assert "cle-secrete" not in json.dumps(state)
        assert (await client.get("/api/v1/admin/nationsglory", headers=player)).status_code == 403

        country = await client.post("/api/v1/admin/nationsglory/fetch", json={"kind": "country"}, headers=admin)
        assert country.status_code == 200, country.text
        assert country.json()["payload"]["claims"] == 42 and country.json()["target"] == "country/blue/levant"
        sent = fake.requests[-1]
        assert sent.headers["authorization"] == "Bearer cle-secrete" and sent.url.path == "/country/blue/levant"

        again = await client.post("/api/v1/admin/nationsglory/fetch", json={"kind": "country"}, headers=admin)
        assert again.json()["from_cache"] and len(fake.requests) == 1
        fresh = {"kind": "country", "refresh": True}
        assert not (await client.post("/api/v1/admin/nationsglory/fetch", json=fresh, headers=admin)).json()[
            "from_cache"
        ]

        shared = (await client.get("/api/v1/nationsglory/country", headers=player)).json()
        assert shared["payload"]["name"] == "Empire du Levant"

        for bad in (
            {"kind": "country", "country": "../admin"},
            {"kind": "user", "username": "a/b"},
            {"kind": "inconnu"},
            {"kind": "planning"},
        ):
            assert (await client.post("/api/v1/admin/nationsglory/fetch", json=bad, headers=admin)).status_code == 422

        fake.status = 403
        refused = await client.post("/api/v1/admin/nationsglory/fetch", json={"kind": "playercount"}, headers=admin)
        assert refused.status_code == 403 and "refusée" in refused.json()["detail"]
        history = (await client.get("/api/v1/admin/nationsglory/snapshots", headers=admin)).json()
        assert [h["status"] for h in history][:1] == [403] and history[0]["payload"] is None
        detail = (await client.get(f"/api/v1/admin/nationsglory/snapshots/{history[1]['id']}", headers=admin)).json()
        assert detail["payload"]["claims"] == 42
        board = (await client.get("/api/v1/admin/overview", headers=admin)).json()
        assert next(s for s in board["systems"] if s["id"] == "nationsglory")["stats"][1]["value"] == "1"


async def test_nationsglory_without_key_and_oversized_responses(settings, database, discord):
    from syncron_server.nationsglory import NationsGloryClient, NationsGloryError, Request

    fake = FakeNationsGlory()
    async with await _ng_client(settings, database, discord, fake, key="") as client:
        admin = await login(client, "patron", "admin")
        assert not (await client.get("/api/v1/admin/nationsglory", headers=admin)).json()["configured"]
        missing = await client.post("/api/v1/admin/nationsglory/fetch", json={"kind": "playercount"}, headers=admin)
        assert missing.status_code == 503 and "SYNCRON_NG_API_KEY" in missing.json()["detail"]
        assert fake.requests == []

    ng = NationsGloryClient("https://publicapi.test", "k", transport=httpx.MockTransport(fake.handler))
    try:
        await ng.fetch(Request("huge", "/huge"))
    except NationsGloryError as error:
        assert "volumineuse" in str(error)
    else:
        raise AssertionError("réponse trop grosse acceptée")
