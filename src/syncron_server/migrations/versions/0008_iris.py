"""Carte NationsGlory (iris.nationsglory.fr) : dernières données et événements météo.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iris_snapshots",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=False),
        sa.CheckConstraint(
            "kind in ('territories', 'atlas', 'frontiers', 'regions', 'weather', 'state', 'members')",
            name=op.f("ck_iris_snapshots_kind"),
        ),
        sa.PrimaryKeyConstraint("kind", name=op.f("pk_iris_snapshots")),
    )
    op.create_table(
        "iris_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("x", sa.Integer(), nullable=True),
        sa.Column("z", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind in ('meteor', 'rift', 'volcano', 'other')", name=op.f("ck_iris_events_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_iris_events")),
        sa.UniqueConstraint("key", name=op.f("uq_iris_events_key")),
    )
    op.create_index(op.f("ix_iris_events_first_seen"), "iris_events", ["first_seen"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_iris_events_first_seen"), table_name="iris_events")
    op.drop_table("iris_events")
    op.drop_table("iris_snapshots")
