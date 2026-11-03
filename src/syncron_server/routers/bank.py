"""Banque du pays : solde, opérations, contributeurs.

Lecture : tout compte connecté. Saisie, correction et suppression des opérations : comptes
qui gèrent le système « bank ». Chaque écriture est journalisée.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from syncron_core.text import format_quantity
from syncron_server import audit
from syncron_server.deps import SessionDep, UserDep, manager
from syncron_server.models import BankTransaction, User, utcnow
from syncron_server.schemas import (
    BankContributorOut,
    BankOut,
    BankTransactionIn,
    BankTransactionOut,
    OverviewStat,
    SystemOverviewOut,
)
from syncron_server.systems import BANK, SYSTEMS, overview_provider

router = APIRouter(prefix="/api/v1/bank", tags=["Banque"])
admin_router = APIRouter(prefix="/api/v1/admin/bank", tags=["Banque (gestion)"])
BankManager = Annotated[User, Depends(manager(BANK))]
TOP_CONTRIBUTORS = 10


def _name(user: User | None) -> str | None:
    return (user.display_name or user.username) if user else None


def _out(row: BankTransaction, member: User | None, author: User | None) -> BankTransactionOut:
    return BankTransactionOut(
        id=row.id,
        amount=row.amount,
        label=row.label,
        category=row.category,
        member_id=row.member_id,
        member=_name(member) or row.member_name,
        occurred_at=row.occurred_at,
        author=_name(author),
        created_at=row.created_at,
    )


def money(amount: int) -> str:
    return f"{format_quantity(amount)} $"


async def _totals(session: AsyncSession) -> tuple[int, int, int, int]:
    since = utcnow() - timedelta(days=30)
    totals = select(func.coalesce(func.sum(BankTransaction.amount), 0), func.count(BankTransaction.id))
    balance, count = (await session.execute(totals)).one()
    income, expenses = (
        await session.execute(
            select(
                func.coalesce(func.sum(BankTransaction.amount).filter(BankTransaction.amount > 0), 0),
                func.coalesce(func.sum(BankTransaction.amount).filter(BankTransaction.amount < 0), 0),
            ).where(BankTransaction.occurred_at >= since)
        )
    ).one()
    return int(balance), int(income), int(-expenses), int(count)


@router.get("", response_model=BankOut)
async def bank(session: SessionDep, _user: UserDep, limit: Annotated[int, Query(ge=1, le=1000)] = 300) -> BankOut:
    member, author = aliased(User), aliased(User)
    rows = (
        await session.execute(
            select(BankTransaction, member, author)
            .outerjoin(member, member.id == BankTransaction.member_id)
            .outerjoin(author, author.id == BankTransaction.created_by)
            .order_by(BankTransaction.occurred_at.desc(), BankTransaction.id.desc())
            .limit(limit)
        )
    ).all()
    contributor = func.coalesce(member.display_name, member.username, BankTransaction.member_name)
    top = (
        await session.execute(
            select(contributor, BankTransaction.member_id, func.sum(BankTransaction.amount), func.count())
            .outerjoin(member, member.id == BankTransaction.member_id)
            .where(BankTransaction.amount > 0, contributor != "")
            .group_by(contributor, BankTransaction.member_id)
            .order_by(func.sum(BankTransaction.amount).desc())
            .limit(TOP_CONTRIBUTORS)
        )
    ).all()
    balance, income, expenses, count = await _totals(session)
    await session.commit()
    return BankOut(
        balance=balance,
        income_30_days=income,
        expenses_30_days=expenses,
        count=count,
        transactions=[_out(row, m, a) for row, m, a in rows],
        contributors=[
            BankContributorOut(member=name, member_id=member_id, total=int(total), count=int(n))
            for name, member_id, total, n in top
        ],
    )


async def _check_member(session: AsyncSession, member_id: uuid.UUID | None) -> User | None:
    if member_id is None:
        return None
    user = await session.get(User, member_id)
    if user is None:
        raise HTTPException(422, "Membre introuvable.")
    return user


def _fill(row: BankTransaction, payload: BankTransactionIn, member: User | None) -> None:
    row.amount = payload.amount
    row.label = payload.label
    row.category = payload.category
    row.member_id = member.id if member else None
    row.member_name = "" if member else payload.member_name
    row.occurred_at = payload.occurred_at or utcnow()
    row.updated_at = utcnow()


def _summary(verb: str, row: BankTransaction) -> str:
    sign = "+" if row.amount > 0 else "−"
    return f"Banque : {verb} {sign}{money(abs(row.amount))} · {row.label}"


@admin_router.post("/transactions", response_model=BankTransactionOut, status_code=status.HTTP_201_CREATED)
async def add_transaction(payload: BankTransactionIn, session: SessionDep, user: BankManager) -> BankTransactionOut:
    member = await _check_member(session, payload.member_id)
    row = BankTransaction(created_by=user.id, created_at=utcnow())
    _fill(row, payload, member)
    session.add(row)
    await session.flush()
    audit.record(session, user.id, BANK, "bank.add", "bank", str(row.id), _summary("ajout", row))
    await session.commit()
    return _out(row, member, user)


@admin_router.put("/transactions/{transaction_id}", response_model=BankTransactionOut)
async def edit_transaction(
    transaction_id: int, payload: BankTransactionIn, session: SessionDep, user: BankManager
) -> BankTransactionOut:
    row = await session.get(BankTransaction, transaction_id, with_for_update=True)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable.")
    member = await _check_member(session, payload.member_id)
    _fill(row, payload, member)
    audit.record(session, user.id, BANK, "bank.edit", "bank", str(row.id), _summary("correction", row))
    await session.commit()
    author = await session.get(User, row.created_by) if row.created_by else None
    return _out(row, member, author)


@admin_router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(transaction_id: int, session: SessionDep, user: BankManager) -> None:
    row = await session.get(BankTransaction, transaction_id, with_for_update=True)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable.")
    summary = _summary("suppression", row)
    await session.delete(row)
    audit.record(session, user.id, BANK, "bank.delete", "bank", str(transaction_id), summary)
    await session.commit()


@overview_provider(BANK)
async def overview(session: AsyncSession) -> SystemOverviewOut:
    balance, income, expenses, count = await _totals(session)
    last = (await session.execute(select(func.max(BankTransaction.updated_at)))).scalar_one()
    return SystemOverviewOut(
        id=BANK,
        name=SYSTEMS[BANK],
        stats=[
            OverviewStat(label="Solde", value=money(balance), detail=f"{count} opération(s)"),
            OverviewStat(label="30 derniers jours", value=f"+{money(income)}", detail=f"sorties : −{money(expenses)}"),
        ],
        updated_at=last,
    )
