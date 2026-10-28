"""Journal des modifications, commun à tous les systèmes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server.models import ID_LENGTH, AuditEntry, User, utcnow
from syncron_server.schemas import AuditOut


def record(
    session: AsyncSession,
    user_id: uuid.UUID | None,
    system: str,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Ajoute une entrée à la transaction en cours."""
    session.add(
        AuditEntry(
            user_id=user_id,
            system=system,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id[:ID_LENGTH],
            summary=summary,
            details=details,
            created_at=utcnow(),
        )
    )


async def entries(
    session: AsyncSession, limit: int, before: int | None = None, systems: list[str] | None = None
) -> list[AuditOut]:
    """Entrées les plus récentes d'abord ; `systems` restreint aux systèmes visibles par le lecteur."""
    query = (
        select(AuditEntry, User.username)
        .outerjoin(User, User.id == AuditEntry.user_id)
        .order_by(AuditEntry.id.desc())
        .limit(limit)
    )
    if before is not None:
        query = query.where(AuditEntry.id < before)
    if systems is not None:
        query = query.where(AuditEntry.system.in_(systems))
    rows = (await session.execute(query)).all()
    return [
        AuditOut(
            id=entry.id,
            created_at=entry.created_at,
            username=username,
            system=entry.system,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            summary=entry.summary,
        )
        for entry, username in rows
    ]
