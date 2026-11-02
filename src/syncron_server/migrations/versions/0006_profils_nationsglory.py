"""Profils des membres et réponses de l'API NationsGlory.

- user_profiles : pseudo en jeu, grade, description, spécialités, disponibilités, couleur.
- ng_snapshots : chaque appel à l'API publique NationsGlory, gardé pour l'historique.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("nickname", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("specialties", sa.JSON(), nullable=False),
        sa.Column("availability", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=12), nullable=False),
        sa.Column("show_discord", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "nickname = '' or nickname ~ '^[A-Za-z0-9_]{3,16}$'", name=op.f("ck_user_profiles_nickname")
        ),
        sa.CheckConstraint("char_length(bio) <= 600", name=op.f("ck_user_profiles_bio")),
        sa.CheckConstraint(
            "color in ('teal', 'blue', 'violet', 'pink', 'red', 'orange', 'yellow', 'green')",
            name=op.f("ck_user_profiles_color"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_profiles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
    )
    op.create_table(
        "ng_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("target", sa.String(length=160), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("fetched_by", sa.Uuid(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["fetched_by"], ["users.id"], name=op.f("fk_ng_snapshots_fetched_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ng_snapshots")),
    )
    op.create_index(
        "ix_ng_snapshots_kind_target_fetched", "ng_snapshots", ["kind", "target", "fetched_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_ng_snapshots_kind_target_fetched", table_name="ng_snapshots")
    op.drop_table("ng_snapshots")
    op.drop_table("user_profiles")
