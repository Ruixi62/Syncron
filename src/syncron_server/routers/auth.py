"""Connexion Discord pour une application de bureau (OAuth2 + PKCE, redirection loopback).

    client                         API                                Discord
      │ ouvre le navigateur  ───▶  /auth/discord/start
      │  (redirect 127.0.0.1,       │ état signé (port, state, challenge)
      │   state, code_challenge)    └──────────────▶ /oauth2/authorize
      │                                             ◀── l'utilisateur accepte
      │                            /auth/discord/callback ◀─────────── code
      │                             │ échange (secret côté serveur), profil,
      │                             │ contrôle d'appartenance au serveur Discord
      │ ◀── 127.0.0.1/callback?code=<code à usage unique>&state
      │ POST /auth/token (code + code_verifier) ──▶ jetons d'accès et de rafraîchissement

Le secret Discord ne quitte jamais le serveur ; le code renvoyé au client est
inutilisable sans le code_verifier, connu du seul client qui a lancé la connexion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_core import APP_NAME
from syncron_server.config import Settings
from syncron_server.deps import SessionDep, SettingsDep, UserDep, get_discord
from syncron_server.discord import DiscordError, DiscordProvider, DiscordUser
from syncron_server.messaging import post_message
from syncron_server.models import LoginCode, RefreshToken, Role, User, utcnow
from syncron_server.schemas import DevLoginRequest, RefreshRequest, TokenPair, TokenRequest, UserOut
from syncron_server.security import (
    TokenError,
    decode_flow,
    encode_access_token,
    encode_flow,
    hash_token,
    new_secret_token,
    verify_pkce,
)
from syncron_server.systems import ACCOUNTS, SYSTEMS, clean_permissions

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
LOGIN_CODE_TTL = timedelta(minutes=2)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _check_loopback(redirect_uri: str) -> None:
    parts = urlsplit(redirect_uri)
    if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS or not parts.port:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "redirect_uri doit être http://127.0.0.1:<port>/…")


def _scopes(settings: Settings) -> tuple[str, ...]:
    return ("identify", "guilds") if settings.discord_required_guild_id else ("identify",)


@router.get("/discord/start", include_in_schema=False)
async def discord_start(
    settings: SettingsDep,
    redirect_uri: str = Query(..., max_length=200),
    state: str = Query(..., min_length=8, max_length=200),
    code_challenge: str = Query(..., min_length=43, max_length=128),
    code_challenge_method: str = Query("S256"),
    discord: DiscordProvider = Depends(get_discord),
) -> RedirectResponse:
    if not settings.discord_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Connexion Discord non configurée sur ce serveur.")
    if code_challenge_method != "S256":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Seul code_challenge_method=S256 est accepté.")
    _check_loopback(redirect_uri)
    flow = encode_flow(
        settings.jwt_secret.get_secret_value(),
        {"redirect_uri": redirect_uri, "client_state": state, "challenge": code_challenge},
    )
    return RedirectResponse(discord.authorize_url(flow, settings.discord_redirect_uri, _scopes(settings)))


@router.get("/discord/callback", include_in_schema=False)
async def discord_callback(
    settings: SettingsDep,
    session: SessionDep,
    state: str = Query(...),
    code: str | None = Query(None),
    error: str | None = Query(None),
    discord: DiscordProvider = Depends(get_discord),
) -> RedirectResponse:
    try:
        flow = decode_flow(settings.jwt_secret.get_secret_value(), state)
    except TokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Connexion expirée ou invalide : recommence.") from None

    def back_to_client(**params: str) -> RedirectResponse:
        query = urlencode({**params, "state": flow["client_state"]})
        return RedirectResponse(f"{flow['redirect_uri']}?{query}")

    if error or not code:
        return back_to_client(error=error or "access_denied")
    try:
        token = await discord.exchange_code(code, settings.discord_redirect_uri)
        profile = await discord.fetch_user(token)
        if settings.discord_required_guild_id and settings.discord_required_guild_id not in (
            await discord.fetch_guild_ids(token)
        ):
            return back_to_client(error="not_in_guild")
    except DiscordError:
        return back_to_client(error="discord_unavailable")

    user = await upsert_user(session, settings, profile)
    if user.is_banned:
        await session.commit()
        return back_to_client(error="banned")
    login_code = new_secret_token()
    session.add(
        LoginCode(
            code_hash=hash_token(login_code),
            user_id=user.id,
            code_challenge=flow["challenge"],
            expires_at=utcnow() + LOGIN_CODE_TTL,
        )
    )
    await session.commit()
    return back_to_client(code=login_code)


@router.post("/token", response_model=TokenPair)
async def exchange_login_code(payload: TokenRequest, settings: SettingsDep, session: SessionDep) -> TokenPair:
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "Code de connexion invalide ou expiré.")
    login = await session.get(LoginCode, hash_token(payload.code), with_for_update=True)
    if login is None or login.used_at is not None or _aware(login.expires_at) < utcnow():
        raise invalid
    if not verify_pkce(payload.code_verifier, login.code_challenge):
        raise invalid
    login.used_at = utcnow()
    user = await session.get(User, login.user_id)
    if user is None or user.is_banned:
        raise invalid
    return await issue_tokens(session, settings, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, settings: SettingsDep, session: SessionDep) -> TokenPair:
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée : reconnecte-toi.")
    stored = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(payload.refresh_token)).with_for_update()
        )
    ).scalar_one_or_none()
    if stored is None:
        raise invalid
    if stored.revoked_at is not None:
        # Jeton déjà utilisé : probable vol. On coupe toutes les sessions de ce compte.
        await revoke_all(session, stored.user_id)
        await session.commit()
        raise invalid
    if _aware(stored.expires_at) < utcnow():
        raise invalid
    user = await session.get(User, stored.user_id)
    if user is None or user.is_banned:
        raise invalid
    stored.revoked_at = utcnow()
    return await issue_tokens(session, settings, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, session: SessionDep) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(payload.refresh_token), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()


@router.post("/dev-login", response_model=TokenPair, include_in_schema=False)
async def dev_login(payload: DevLoginRequest, settings: SettingsDep, session: SessionDep) -> TokenPair:
    """Connexion sans Discord, uniquement si SYNCRON_DEV_LOGIN=true (interdit en production)."""
    if not settings.dev_login:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    profile = DiscordUser(
        id=f"dev-{payload.username.lower()}", username=payload.username, global_name=None, avatar=None
    )
    user = await upsert_user(session, settings, profile)
    user.role = payload.role.value
    if payload.permissions is not None:
        user.permissions = clean_permissions(payload.permissions)
    elif payload.role is Role.EDITOR:
        user.permissions = list(SYSTEMS)
    return await issue_tokens(session, settings, user)


@router.get("/me", response_model=UserOut, tags=["auth"])
async def me(user: UserDep) -> UserOut:
    return UserOut.of(user)


# -- services ----------------------------------------------------------------------


async def upsert_user(session: AsyncSession, settings: Settings, profile: DiscordUser) -> User:
    user = (await session.execute(select(User).where(User.discord_id == profile.id))).scalar_one_or_none()
    created = user is None
    if user is None:
        user = User(
            discord_id=profile.id,
            username=profile.username,
            role=Role.PLAYER.value,
            permissions=[],
            created_at=utcnow(),
        )
        session.add(user)
    user.username = profile.username
    user.display_name = profile.global_name
    user.avatar = profile.avatar
    user.last_login_at = utcnow()
    if profile.id in settings.admin_ids:
        user.role = Role.ADMIN.value
        user.is_banned = False
    await session.flush()
    if created:
        await _welcome(session, settings, user)
    return user


async def _welcome(session: AsyncSession, settings: Settings, user: User) -> None:
    country = settings.nation_name or "notre pays"
    await post_message(
        session,
        system=ACCOUNTS,
        title=f"Bienvenue sur {APP_NAME}",
        body=(
            f"{APP_NAME} rassemble les outils internes de {country} : Craft, R&D, Calendrier et Convertisseur.\n"
            "Les annonces de l'équipe et les nouvelles du pays arrivent ici, dans ta messagerie."
        ),
        audience="direct",
        recipients=[user.id],
    )
    await post_message(
        session,
        system=ACCOUNTS,
        title=f"Nouveau compte : {profile_name(user)}",
        body="Un membre vient de se connecter pour la première fois.",
        audience="staff",
    )


def profile_name(user: User) -> str:
    return user.display_name or user.username


async def issue_tokens(session: AsyncSession, settings: Settings, user: User) -> TokenPair:
    refresh_token = new_secret_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            created_at=utcnow(),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
        )
    )
    access = encode_access_token(
        settings.jwt_secret.get_secret_value(), user.id, user.role, settings.access_token_minutes
    )
    await session.commit()
    return TokenPair(
        access_token=access,
        refresh_token=refresh_token,
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.of(user),
    )


async def revoke_all(session: AsyncSession, user_id) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
