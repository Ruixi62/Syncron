"""Administration générale : vue d'ensemble par système, journal, comptes.

La gestion de chaque système est dans son propre routeur (`/api/v1/admin/<système>/…`).
Éditeur : vue d'ensemble et journal des systèmes qui lui sont confiés.
Administrateur : tous les systèmes, plus les comptes (rôles, systèmes confiés, suspension).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from syncron_server import audit
from syncron_server.deps import AdminDep, EditorDep, SessionDep, SettingsDep
from syncron_server.messaging import post_message
from syncron_server.models import Role, User
from syncron_server.routers.auth import revoke_all
from syncron_server.schemas import AccountsOverviewOut, AuditOut, OverviewOut, UserOut, UserPatch
from syncron_server.systems import ACCOUNTS, LABELS, SYSTEMS, clean_permissions, overview_providers

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])


def managed_systems(user: User) -> list[str]:
    return [system for system in SYSTEMS if user.can_manage(system)]


def journal_systems(user: User) -> list[str]:
    systems = managed_systems(user)
    return [*systems, ACCOUNTS] if user.role_enum is Role.ADMIN else systems


@router.get("/overview", response_model=OverviewOut)
async def overview(session: SessionDep, user: EditorDep) -> OverviewOut:
    systems = []
    for system, provider in overview_providers().items():
        if user.can_manage(system):
            systems.append(await provider(session))
    accounts = None
    if user.role_enum is Role.ADMIN:
        roles = dict((await session.execute(select(User.role, func.count()).group_by(User.role))).all())
        banned = (await session.execute(select(func.count()).select_from(User).where(User.is_banned))).scalar_one()
        accounts = AccountsOverviewOut(
            total=sum(roles.values()), by_role={role.value: roles.get(role.value, 0) for role in Role}, banned=banned
        )
    recent = await audit.entries(session, 12, systems=journal_systems(user))
    await session.commit()
    return OverviewOut(systems=systems, accounts=accounts, recent=recent)


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(
    session: SessionDep,
    user: EditorDep,
    limit: int = Query(50, ge=1, le=200),
    before: int | None = Query(None),
    system: str | None = Query(None, max_length=16),
) -> list[AuditOut]:
    allowed = journal_systems(user)
    if system is not None:
        if system not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Ce journal ne t'est pas accessible.")
        allowed = [system]
    return await audit.entries(session, limit, before, allowed)


# -- comptes --------------------------------------------------------------------------------


@router.get("/users", response_model=list[UserOut])
async def list_users(session: SessionDep, _admin: AdminDep, q: str = Query("", max_length=64)) -> list[UserOut]:
    query = select(User).order_by(User.last_login_at.desc().nulls_last(), User.username).limit(500)
    if q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(
            User.username.ilike(pattern) | User.display_name.ilike(pattern) | (User.discord_id == q.strip())
        )
    return [UserOut.of(user) for user in (await session.execute(query)).scalars()]


@router.patch("/users/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: uuid.UUID, payload: UserPatch, session: SessionDep, settings: SettingsDep, admin: AdminDep
) -> UserOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")
    if target.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu ne peux pas modifier ton propre compte.")
    if target.discord_id in settings.admin_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ce compte est administrateur par configuration du serveur.")
    changes: list[str] = []
    news: list[str] = []
    if payload.role is not None and payload.role.value != target.role:
        changes.append(f"rôle {Role(target.role).label} → {payload.role.label}")
        news.append(f"Ton rôle est maintenant : {payload.role.label}.")
        target.role = payload.role.value
    if payload.permissions is not None:
        try:
            permissions = clean_permissions(payload.permissions)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if permissions != sorted(target.permissions or []):
            granted = [SYSTEMS[s] for s in permissions if s not in (target.permissions or [])]
            changes.append("systèmes : " + (", ".join(LABELS[s] for s in permissions) or "aucun"))
            if granted:
                news.append("Tu peux maintenant gérer : " + ", ".join(granted) + ".")
            target.permissions = permissions
    if payload.is_banned is not None and payload.is_banned != target.is_banned:
        target.is_banned = payload.is_banned
        changes.append("suspendu" if payload.is_banned else "réactivé")
        if payload.is_banned:
            await revoke_all(session, target.id)
    if changes:
        audit.record(
            session,
            admin.id,
            ACCOUNTS,
            "user.update",
            "user",
            target.discord_id,
            f"Utilisateur {target.username} : " + ", ".join(changes),
        )
    if news and not target.is_banned:
        await post_message(
            session,
            system=ACCOUNTS,
            title="Ton compte a été mis à jour",
            body="\n".join(news),
            audience="direct",
            recipients=[target.id],
            author_id=admin.id,
        )
    await session.commit()
    return UserOut.of(target)
