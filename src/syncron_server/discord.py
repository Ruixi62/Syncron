"""Client OAuth2 Discord (côté serveur : le secret ne quitte jamais l'API)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

DISCORD_API = "https://discord.com/api/v10"
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"


class DiscordError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class DiscordUser:
    id: str
    username: str
    global_name: str | None
    avatar: str | None


class DiscordProvider(Protocol):
    def authorize_url(self, state: str, redirect_uri: str, scopes: tuple[str, ...]) -> str: ...

    async def exchange_code(self, code: str, redirect_uri: str) -> str: ...

    async def fetch_user(self, access_token: str) -> DiscordUser: ...

    async def fetch_guild_ids(self, access_token: str) -> set[str]: ...


class DiscordOAuth:
    def __init__(self, client_id: str, client_secret: str, timeout: float = 10.0) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout

    def authorize_url(self, state: str, redirect_uri: str, scopes: tuple[str, ...]) -> str:
        query = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "prompt": "none",
        }
        return f"{AUTHORIZE_URL}?{urlencode(query)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> str:
        data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{DISCORD_API}/oauth2/token", data=data, auth=(self._client_id, self._client_secret)
            )
        if response.status_code != 200:
            raise DiscordError(f"Échange du code Discord refusé ({response.status_code}).")
        token = response.json().get("access_token")
        if not isinstance(token, str):
            raise DiscordError("Réponse Discord sans jeton d'accès.")
        return token

    async def fetch_user(self, access_token: str) -> DiscordUser:
        payload = await self._get("/users/@me", access_token)
        return DiscordUser(
            id=str(payload["id"]),
            username=str(payload.get("username", "")),
            global_name=payload.get("global_name"),
            avatar=payload.get("avatar"),
        )

    async def fetch_guild_ids(self, access_token: str) -> set[str]:
        payload = await self._get("/users/@me/guilds", access_token)
        return {str(guild["id"]) for guild in payload}

    async def _get(self, path: str, access_token: str):
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{DISCORD_API}{path}", headers={"Authorization": f"Bearer {access_token}"})
        if response.status_code != 200:
            raise DiscordError(f"Requête Discord {path} refusée ({response.status_code}).")
        return response.json()
