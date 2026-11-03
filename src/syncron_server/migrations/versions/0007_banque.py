"""Banque du pays : opérations (entrées, sorties) avec motif, catégorie, membre et date.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=True),
        sa.Column("member_name", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "amount <> 0 and amount between -1000000000000 and 1000000000000", name=op.f("ck_bank_transactions_amount")
        ),
        sa.CheckConstraint(
            "category in ('contribution', 'sale', 'purchase', 'tax', 'war', 'salary', 'other')",
            name=op.f("ck_bank_transactions_category"),
        ),
        sa.CheckConstraint("label <> ''", name=op.f("ck_bank_transactions_label")),
        sa.ForeignKeyConstraint(
            ["member_id"], ["users.id"], name=op.f("fk_bank_transactions_member_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_bank_transactions_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_transactions")),
    )
    op.create_index(op.f("ix_bank_transactions_member_id"), "bank_transactions", ["member_id"], unique=False)
    op.create_index(op.f("ix_bank_transactions_occurred_at"), "bank_transactions", ["occurred_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bank_transactions_occurred_at"), table_name="bank_transactions")
    op.drop_index(op.f("ix_bank_transactions_member_id"), table_name="bank_transactions")
    op.drop_table("bank_transactions")
