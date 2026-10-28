"""Dépendances FastAPI : configuration, session, utilisateur courant, rôles."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server.config import Settings
from syncron_server.discord import DiscordProvider
from syncron_server.models import Role, User
from syncron_server.security import TokenError, decode_access_token
from syncron_server.systems import CALENDAR, CRAFT, MESSAGES, RESEARCH, SYSTEMS

bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_discord(request: Request) -> DiscordProvider:
    return request.app.state.discord


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.sessions() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_user(
    settings: SettingsDep,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Connexion requise.", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(settings.jwt_secret.get_secret_value(), credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError):
        raise unauthorized from None
    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized
    if user.is_banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte suspendu.")
    return user


UserDep = Annotated[User, Depends(current_user)]


def require(role: Role) -> Callable[[User], Coroutine[Any, Any, User]]:
    async def checker(user: UserDep) -> User:
        if user.role_enum.rank < role.rank:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Rôle « {role.label} » requis.")
        return user

    return checker


EditorDep = Annotated[User, Depends(require(Role.EDITOR))]
AdminDep = Annotated[User, Depends(require(Role.ADMIN))]


def manager(system: str) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Gestion d'un système : administrateur, ou éditeur à qui ce système a été confié."""

    async def checker(user: UserDep) -> User:
        if not user.can_manage(system):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"La gestion « {SYSTEMS[system]} » ne t'a pas été confiée.")
        return user

    return checker


CraftManager = Annotated[User, Depends(manager(CRAFT))]
ResearchManager = Annotated[User, Depends(manager(RESEARCH))]
CalendarManager = Annotated[User, Depends(manager(CALENDAR))]
MessagesManager = Annotated[User, Depends(manager(MESSAGES))]
