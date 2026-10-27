from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from syncron_server.discord import DiscordUser
from syncron_server.security import new_secret_token, pkce_challenge

from .conftest import ADMIN_DISCORD_ID

REDIRECT = "http://127.0.0.1:53682/callback"


def _query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


async def discord_login(client, discord, discord_id: str, code: str = "abc", verifier: str | None = None):
    """Rejoue le parcours complet du client de bureau ; retourne (réponse /token, paramètres du retour loopback)."""
    discord.users.setdefault(code, DiscordUser(discord_id, f"user{discord_id[-3:]}", "Pseudo", "hash"))
    verifier = verifier or new_secret_token() + new_secret_token()
    start = await client.get(
        "/api/v1/auth/discord/start",
        params={"redirect_uri": REDIRECT, "state": "client-state-1", "code_challenge": pkce_challenge(verifier)},
    )
    assert start.status_code == 307
    flow_state = _query(start.headers["location"])["state"]
    callback = await client.get("/api/v1/auth/discord/callback", params={"state": flow_state, "code": code})
    assert callback.status_code == 307
    back = callback.headers["location"]
    assert back.startswith(REDIRECT)
    params = _query(back)
    assert params["state"] == "client-state-1"
    if "code" not in params:
        return None, params
    token = await client.post("/api/v1/auth/token", json={"code": params["code"], "code_verifier": verifier})
    return token, params


async def test_meta(client):
    meta = (await client.get("/api/v1/meta")).json()
    assert meta["name"] == "Syncron" and meta["api_version"] == 1 and meta["discord_login"] and meta["dev_login"]


async def test_discord_flow_issues_tokens_and_bootstraps_admin(client, discord):
    token, _ = await discord_login(client, discord, ADMIN_DISCORD_ID)
    assert token.status_code == 200
    body = token.json()
    assert body["user"]["role"] == "admin" and body["user"]["avatar_url"].startswith("https://cdn.discordapp.com/")
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["discord_id"] == ADMIN_DISCORD_ID


async def test_new_user_is_player(client, discord):
    token, _ = await discord_login(client, discord, "200000000000000002")
    assert token.json()["user"]["role"] == "player"


async def test_login_code_needs_matching_verifier_and_is_single_use(client, discord):
    verifier = "v" * 64
    discord.users["code-x"] = DiscordUser("300", "x", None, None)
    start = await client.get(
        "/api/v1/auth/discord/start",
        params={"redirect_uri": REDIRECT, "state": "client-state-1", "code_challenge": pkce_challenge(verifier)},
    )
    state = _query(start.headers["location"])["state"]
    back = (await client.get("/api/v1/auth/discord/callback", params={"state": state, "code": "code-x"})).headers[
        "location"
    ]
    code = _query(back)["code"]
    wrong = await client.post("/api/v1/auth/token", json={"code": code, "code_verifier": "w" * 64})
    assert wrong.status_code == 400
    ok = await client.post("/api/v1/auth/token", json={"code": code, "code_verifier": verifier})
    assert ok.status_code == 200
    again = await client.post("/api/v1/auth/token", json={"code": code, "code_verifier": verifier})
    assert again.status_code == 400


@pytest.mark.parametrize(
    "redirect", ["https://evil.example/callback", "http://evil.example:80/cb", "http://127.0.0.1/cb"]
)
async def test_start_rejects_non_loopback_redirects(client, redirect):
    response = await client.get(
        "/api/v1/auth/discord/start",
        params={"redirect_uri": redirect, "state": "statestate", "code_challenge": "c" * 43},
    )
    assert response.status_code == 400


async def test_tampered_flow_state_is_rejected(client):
    response = await client.get("/api/v1/auth/discord/callback", params={"state": "forged", "code": "x"})
    assert response.status_code == 400


async def test_guild_requirement(client, discord, settings):
    settings.discord_required_guild_id = "999"
    discord.users["outsider"] = DiscordUser("400", "dehors", None, None)
    token, params = await discord_login(client, discord, "400", code="outsider")
    assert token is None and params["error"] == "not_in_guild"
    discord.users["member"] = DiscordUser("401", "membre", None, None)
    discord.guilds["member"] = {"999"}
    token, _ = await discord_login(client, discord, "401", code="member")
    assert token.status_code == 200


async def test_discord_failure_and_denial_are_reported_to_client(client, discord):
    discord.fail = True
    token, params = await discord_login(client, discord, "500")
    assert token is None and params["error"] == "discord_unavailable"
    start = await client.get(
        "/api/v1/auth/discord/start",
        params={"redirect_uri": REDIRECT, "state": "client-state-1", "code_challenge": "c" * 43},
    )
    state = _query(start.headers["location"])["state"]
    denied = await client.get("/api/v1/auth/discord/callback", params={"state": state, "error": "access_denied"})
    assert _query(denied.headers["location"])["error"] == "access_denied"


async def test_refresh_rotation_and_reuse_detection(client):
    first = (await client.post("/api/v1/auth/dev-login", json={"username": "rota"})).json()
    second = await client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reused.status_code == 401
    # La réutilisation d'un jeton révoqué coupe aussi le jeton le plus récent.
    latest = await client.post("/api/v1/auth/refresh", json={"refresh_token": second.json()["refresh_token"]})
    assert latest.status_code == 401


async def test_logout_revokes(client):
    tokens = (await client.post("/api/v1/auth/dev-login", json={"username": "partant"})).json()
    assert (
        await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 204
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401


async def test_protected_routes_require_token(client):
    assert (await client.get("/api/v1/catalog")).status_code == 401
    assert (await client.get("/api/v1/catalog", headers={"Authorization": "Bearer nope"})).status_code == 401


async def test_dev_login_disabled_returns_404(client, settings):
    settings.dev_login = False
    assert (await client.post("/api/v1/auth/dev-login", json={"username": "x1"})).status_code == 404


def test_settings_refuse_dev_login_in_production():
    from pydantic import ValidationError

    from syncron_server.config import Settings

    with pytest.raises(ValidationError):
        Settings(jwt_secret="x" * 40, dev_login=True, discord_client_id="a", discord_client_secret="b")
    with pytest.raises(ValidationError):
        Settings(jwt_secret="x" * 40)
