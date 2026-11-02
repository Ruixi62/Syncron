"""Hébergement d'images : chaque membre envoie des images et obtient un lien public à partager.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosted_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "content_type in ('image/png', 'image/jpeg', 'image/gif')", name=op.f("ck_hosted_images_content_type")
        ),
        sa.CheckConstraint("width >= 1 and height >= 1 and size_bytes >= 1", name=op.f("ck_hosted_images_dimensions")),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f("fk_hosted_images_uploaded_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hosted_images")),
        sa.UniqueConstraint("path", name=op.f("uq_hosted_images_path")),
    )
    op.create_index(op.f("ix_hosted_images_uploaded_by"), "hosted_images", ["uploaded_by"], unique=False)
    op.create_index(op.f("ix_hosted_images_created_at"), "hosted_images", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_hosted_images_created_at"), table_name="hosted_images")
    op.drop_index(op.f("ix_hosted_images_uploaded_by"), table_name="hosted_images")
    op.drop_table("hosted_images")
