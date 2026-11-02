"""Profils et annuaire des membres.

Chaque compte modifie son propre profil (pseudo en jeu, grade, description, spécialités,
disponibilités, couleur). Tout compte connecté voit l'annuaire des membres non suspendus ;
le pseudo Discord n'y apparaît que si son propriétaire l'a accepté.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server.deps import SessionDep, UserDep
from syncron_server.models import User, UserProfile, utcnow
from syncron_server.schemas import MemberOut, ProfileIn, UserOut

router = APIRouter(prefix="/api/v1", tags=["Profils"])


def member_out(user: User, profile: UserProfile | None, viewer: User) -> MemberOut:
    own = viewer.id == user.id
    show_discord = profile.show_discord if profile else True
    return MemberOut(
        id=user.id,
        name=user.display_name or user.username,
        discord_username=user.username if (show_discord or own or viewer.is_staff) else None,
        avatar_url=UserOut.of(user).avatar_url,
        role=user.role_enum,
        nickname=profile.nickname if profile else "",
        title=profile.title if profile else "",
        bio=profile.bio if profile else "",
        specialties=list(profile.specialties or []) if profile else [],
        availability=profile.availability if profile else "",
        color=profile.color if profile else "teal",
        show_discord=show_discord,
        joined_at=user.created_at,
        last_seen_at=user.last_login_at,
        updated_at=profile.updated_at if profile else None,
    )


async def _profile(session: AsyncSession, user_id: uuid.UUID) -> UserProfile | None:
    return await session.get(UserProfile, user_id)


@router.get("/profile", response_model=MemberOut)
async def my_profile(session: SessionDep, user: UserDep) -> MemberOut:
    profile = await _profile(session, user.id)
    await session.commit()
    return member_out(user, profile, user)


@router.put("/profile", response_model=MemberOut)
async def save_profile(payload: ProfileIn, session: SessionDep, user: UserDep) -> MemberOut:
    profile = await session.get(UserProfile, user.id, with_for_update=True)
    if profile is None:
        profile = UserProfile(user_id=user.id)
        session.add(profile)
    profile.nickname = payload.nickname
    profile.title = payload.title
    profile.bio = payload.bio
    profile.specialties = payload.specialties
    profile.availability = payload.availability
    profile.color = payload.color
    profile.show_discord = payload.show_discord
    profile.updated_at = utcnow()
    await session.commit()
    return member_out(user, profile, user)


@router.get("/members", response_model=list[MemberOut])
async def members(session: SessionDep, viewer: UserDep) -> list[MemberOut]:
    rows = (
        await session.execute(
            select(User, UserProfile)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where(User.is_banned.is_(False))
            .order_by(User.display_name, User.username)
        )
    ).all()
    await session.commit()
    result = [member_out(user, profile, viewer) for user, profile in rows]
    return sorted(result, key=lambda member: member.name.casefold())


@router.get("/members/{member_id}", response_model=MemberOut)
async def member(member_id: uuid.UUID, session: SessionDep, viewer: UserDep) -> MemberOut:
    user = await session.get(User, member_id)
    if user is None or user.is_banned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membre introuvable.")
    profile = await _profile(session, member_id)
    await session.commit()
    return member_out(user, profile, viewer)
