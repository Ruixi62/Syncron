"""Messagerie : service commun à tous les systèmes.

Un système publie un message avec `post_message(...)` dans sa transaction ;
le client le reçoit dans sa boîte et sous forme de notification.

Audiences :
    all     tout le pays (comptes non suspendus) ;
    staff   éditeurs et administrateurs ;
    direct  comptes précis (un accusé `message_receipts` par destinataire, créé à l'envoi).

Les accusés des messages `all` / `staff` sont créés à la première lecture ou
suppression. Un nouveau compte voit les annonces des BACKLOG derniers jours.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import timedelta

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server.models import Message, MessageReceipt, User, utcnow

BACKLOG = timedelta(days=30)
TITLE_LENGTH = 160


async def post_message(
    session: AsyncSession,
    *,
    system: str,
    title: str,
    body: str = "",
    audience: str = "all",
    recipients: Iterable[uuid.UUID] = (),
    link_tool: str | None = None,
    link_key: str | None = None,
    author_id: uuid.UUID | None = None,
) -> Message:
    """Ajoute un message à la transaction en cours (l'appelant valide)."""
    message = Message(
        system=system,
        title=title[:TITLE_LENGTH],
        body=body,
        audience=audience,
        link_tool=link_tool,
        link_key=link_key,
        author_id=author_id,
        created_at=utcnow(),
    )
    session.add(message)
    await session.flush()
    now = utcnow()
    targets = set(recipients) if audience == "direct" else set()
    for user_id in targets:
        read_at = now if user_id == author_id else None
        session.add(MessageReceipt(message_id=message.id, user_id=user_id, read_at=read_at))
    if author_id is not None and author_id not in targets and audience != "direct":
        session.add(MessageReceipt(message_id=message.id, user_id=author_id, read_at=now))
    return message


def _receipt_join(user: User):
    return and_(MessageReceipt.message_id == Message.id, MessageReceipt.user_id == user.id)


def visible(user: User) -> Select:
    """Messages de la boîte de `user` (non supprimés), avec leur accusé éventuel."""
    broadcast = ["all", "staff"] if user.is_staff else ["all"]
    return (
        select(Message, MessageReceipt.read_at)
        .outerjoin(MessageReceipt, _receipt_join(user))
        .where(
            or_(
                and_(Message.audience == "direct", MessageReceipt.user_id.is_not(None)),
                and_(Message.audience.in_(broadcast), Message.created_at >= user.created_at - BACKLOG),
            ),
            MessageReceipt.deleted_at.is_(None),
        )
    )


async def summary(session: AsyncSession, user: User) -> tuple[int, int]:
    """(non lus, plus grand identifiant visible)."""
    inner = visible(user).subquery()
    unread, latest = (
        await session.execute(
            select(func.count().filter(inner.c.read_at.is_(None)), func.coalesce(func.max(inner.c.id), 0))
        )
    ).one()
    return unread, latest


async def visible_ids(session: AsyncSession, user: User, ids: Iterable[int] | None, unread_only: bool) -> list[int]:
    query = visible(user).with_only_columns(Message.id)
    if ids is not None:
        query = query.where(Message.id.in_(list(ids)))
    if unread_only:
        query = query.where(MessageReceipt.read_at.is_(None))
    return list((await session.execute(query)).scalars())


async def mark(session: AsyncSession, user: User, ids: list[int], *, deleted: bool = False) -> None:
    """Marque comme lus (et supprimés si `deleted`). `ids` doit venir de visible_ids()."""
    if not ids:
        return
    now = utcnow()
    values = [
        {"message_id": message_id, "user_id": user.id, "read_at": now, "deleted_at": now if deleted else None}
        for message_id in ids
    ]
    statement = insert(MessageReceipt).values(values)
    updates = {"read_at": func.coalesce(MessageReceipt.read_at, statement.excluded.read_at)}
    if deleted:
        updates["deleted_at"] = statement.excluded.deleted_at
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[MessageReceipt.message_id, MessageReceipt.user_id], set_=updates
        )
    )
