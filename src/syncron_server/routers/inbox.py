"""Messagerie : boîte de réception de chaque compte, et annonces de l'équipe.

Le client interroge `/inbox/summary` régulièrement (quelques octets) et
n'affiche une notification que pour les messages plus récents que le dernier vu.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server import audit, messaging
from syncron_server.deps import MessagesManager, SessionDep, UserDep
from syncron_server.models import Message, MessageReceipt, Role, User, utcnow
from syncron_server.schemas import (
    AnnouncementIn,
    InboxReadIn,
    InboxSummaryOut,
    MessageOut,
    OverviewStat,
    RecipientOut,
    SentMessageOut,
    SystemOverviewOut,
)
from syncron_server.systems import MESSAGES, SYSTEMS, overview_provider

router = APIRouter(prefix="/api/v1/inbox", tags=["messagerie"])
admin_router = APIRouter(prefix="/api/v1/admin/messages", tags=["messagerie (gestion)"])
AUDIENCE_LABELS = {"all": "tout le pays", "staff": "l'équipe", "direct": "des membres choisis"}


async def _summary(session: AsyncSession, user: User) -> InboxSummaryOut:
    unread, latest = await messaging.summary(session, user)
    return InboxSummaryOut(unread=unread, latest_id=latest)


@router.get("", response_model=list[MessageOut])
async def inbox(
    session: SessionDep,
    user: UserDep,
    limit: int = Query(50, ge=1, le=200),
    before: int | None = Query(None),
    unread_only: bool = Query(False),
) -> list[MessageOut]:
    query = (
        messaging.visible(user)
        .add_columns(User.username)
        .outerjoin(User, User.id == Message.author_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    if before is not None:
        query = query.where(Message.id < before)
    if unread_only:
        query = query.where(MessageReceipt.read_at.is_(None))
    rows = (await session.execute(query)).all()
    return [
        MessageOut(
            id=message.id,
            system=message.system,
            title=message.title,
            body=message.body,
            author=author,
            link_tool=message.link_tool,
            link_key=message.link_key,
            created_at=message.created_at,
            read=read_at is not None,
        )
        for message, read_at, author in rows
    ]


@router.get("/summary", response_model=InboxSummaryOut)
async def summary(session: SessionDep, user: UserDep) -> InboxSummaryOut:
    result = await _summary(session, user)
    await session.commit()
    return result


@router.post("/read", response_model=InboxSummaryOut)
async def mark_read(payload: InboxReadIn, session: SessionDep, user: UserDep) -> InboxSummaryOut:
    ids = await messaging.visible_ids(session, user, None if payload.all else payload.ids, unread_only=True)
    await messaging.mark(session, user, ids)
    await session.commit()
    return await _summary(session, user)


@router.delete("/{message_id}", response_model=InboxSummaryOut)
async def delete_message(message_id: int, session: SessionDep, user: UserDep) -> InboxSummaryOut:
    ids = await messaging.visible_ids(session, user, [message_id], unread_only=False)
    if not ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message introuvable.")
    await messaging.mark(session, user, ids, deleted=True)
    await session.commit()
    return await _summary(session, user)


# -- annonces (gestion) ----------------------------------------------------------------------


@overview_provider(MESSAGES)
async def overview(session: AsyncSession) -> SystemOverviewOut:
    since = utcnow() - timedelta(days=30)
    sent, last = (
        await session.execute(
            select(func.count(), func.max(Message.created_at)).where(
                Message.system == MESSAGES, Message.created_at >= since
            )
        )
    ).one()
    total = (await session.execute(select(func.count()).select_from(Message))).scalar_one()
    return SystemOverviewOut(
        id=MESSAGES,
        name=SYSTEMS[MESSAGES],
        stats=[
            OverviewStat(label="Annonces (30 jours)", value=str(sent)),
            OverviewStat(label="Messages envoyés", value=str(total), detail="tous systèmes confondus"),
        ],
        updated_at=last,
    )


async def _audience_size(session: AsyncSession, message: Message) -> int:
    if message.audience == "direct":
        query = select(func.count()).select_from(MessageReceipt).where(MessageReceipt.message_id == message.id)
    else:
        query = select(func.count()).select_from(User).where(~User.is_banned)
        if message.audience == "staff":
            query = query.where(User.role.in_([Role.EDITOR.value, Role.ADMIN.value]))
    return (await session.execute(query)).scalar_one()


async def _sent_out(session: AsyncSession, message: Message, author: str | None) -> SentMessageOut:
    read = (
        await session.execute(
            select(func.count())
            .select_from(MessageReceipt)
            .where(MessageReceipt.message_id == message.id, MessageReceipt.read_at.is_not(None))
        )
    ).scalar_one()
    return SentMessageOut(
        id=message.id,
        system=message.system,
        title=message.title,
        body=message.body,
        audience=message.audience,
        author=author,
        created_at=message.created_at,
        recipients=await _audience_size(session, message),
        read=read,
    )


@admin_router.post("", response_model=SentMessageOut, status_code=status.HTTP_201_CREATED)
async def announce(payload: AnnouncementIn, session: SessionDep, user: MessagesManager) -> SentMessageOut:
    recipients = []
    if payload.audience == "users":
        recipients = list(
            (await session.execute(select(User.id).where(User.id.in_(payload.user_ids), ~User.is_banned))).scalars()
        )
        if not recipients:
            raise HTTPException(422, "Aucun destinataire valide.")
    audience = "direct" if payload.audience == "users" else payload.audience
    message = await messaging.post_message(
        session,
        system=MESSAGES,
        title=payload.title,
        body=payload.body,
        audience=audience,
        recipients=recipients,
        link_tool=payload.link_tool,
        link_key=payload.link_key,
        author_id=user.id,
    )
    audit.record(
        session,
        user.id,
        MESSAGES,
        "message.send",
        "message",
        str(message.id),
        f"Annonce à {AUDIENCE_LABELS[audience]} : {payload.title}",
    )
    await session.commit()
    return await _sent_out(session, message, user.username)


@admin_router.get("/recipients", response_model=list[RecipientOut])
async def recipients(session: SessionDep, _user: MessagesManager) -> list[RecipientOut]:
    """Comptes actifs, pour choisir les destinataires d'une annonce."""
    query = select(User).where(~User.is_banned).order_by(func.lower(func.coalesce(User.display_name, User.username)))
    return [
        RecipientOut(id=user.id, name=user.display_name or user.username, username=user.username, role=user.role_enum)
        for user in (await session.execute(query)).scalars()
    ]


@admin_router.get("", response_model=list[SentMessageOut])
async def sent(
    session: SessionDep, _user: MessagesManager, limit: int = Query(50, ge=1, le=200)
) -> list[SentMessageOut]:
    query = (
        select(Message, User.username)
        .outerjoin(User, User.id == Message.author_id)
        .where(Message.system == MESSAGES)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(query)).all()
    result = [await _sent_out(session, message, author) for message, author in rows]
    await session.commit()
    return result


@admin_router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retract(message_id: int, session: SessionDep, user: MessagesManager) -> None:
    message = await session.get(Message, message_id)
    if message is None or message.system != MESSAGES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Annonce introuvable.")
    audit.record(
        session, user.id, MESSAGES, "message.delete", "message", str(message.id), f"Annonce retirée : {message.title}"
    )
    await session.delete(message)
    await session.commit()
