"""Systèmes : droits par système, journal par système, R&D, calendrier, messagerie.

- users.permissions : systèmes confiés à un éditeur. Les éditeurs existants
  gardent ce qu'ils avaient (le Craft).
- audit_log.system : système concerné par chaque entrée (craft, accounts…).
- R&D : les cinq domaines du jeu, avec leur nombre de paliers.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

RESEARCH_SEED = (
    ("global", "Global", "globe", 16, "Bonus pour les membres et le pays."),
    ("militaire", "Militaire", "sword", 16, "Lancer et mener des conquêtes militaires."),
    ("ressources", "Ressources", "pickaxe", 15, "Construction et agriculture."),
    ("industrie", "Industrie", "station", 12, "Développement technologique."),
    ("technologie", "Technologie", "cpu", 7, "Accès à Edora. Demande d'avoir terminé l'Industrie."),
)

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_categories",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tier_count", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("skill_id", sa.String(length=80), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("completed between 0 and tier_count", name=op.f("ck_research_categories_completed")),
        sa.CheckConstraint("not active or completed < tier_count", name=op.f("ck_research_categories_active")),
        sa.CheckConstraint("tier_count between 0 and 100", name=op.f("ck_research_categories_tier_count")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_categories")),
    )
    op.create_index(
        "uq_research_categories_active", "research_categories", ["active"], unique=True, postgresql_where="active"
    )
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category in ('meeting', 'war', 'event', 'economy', 'other')", name=op.f("ck_calendar_events_category")
        ),
        sa.CheckConstraint("ends_at is null or ends_at >= starts_at", name=op.f("ck_calendar_events_period")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_calendar_events_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_events")),
    )
    op.create_index(op.f("ix_calendar_events_starts_at"), "calendar_events", ["starts_at"], unique=False)
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("system", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(length=8), nullable=False),
        sa.Column("link_tool", sa.String(length=32), nullable=True),
        sa.Column("link_key", sa.String(length=160), nullable=True),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("audience in ('all', 'staff', 'direct')", name=op.f("ck_messages_audience")),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_messages_author_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(op.f("ix_messages_created_at"), "messages", ["created_at"], unique=False)
    op.create_table(
        "research_tiers",
        sa.Column("category_id", sa.String(length=32), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("level >= 1", name=op.f("ck_research_tiers_level")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["research_categories.id"],
            name=op.f("fk_research_tiers_category_id_research_categories"),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("category_id", "level", name=op.f("pk_research_tiers")),
    )
    op.create_table(
        "message_receipts",
        sa.Column("message_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name=op.f("fk_message_receipts_message_id_messages"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_message_receipts_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("message_id", "user_id", name=op.f("pk_message_receipts")),
    )
    op.create_index(op.f("ix_message_receipts_user_id"), "message_receipts", ["user_id"], unique=False)
    op.create_table(
        "research_lines",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.String(length=32), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=True),
        sa.Column("item_id", sa.String(length=80), nullable=True),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.CheckConstraint("kind in ('condition', 'reward')", name=op.f("ck_research_lines_kind")),
        sa.CheckConstraint("text <> '' or item_id is not null", name=op.f("ck_research_lines_content")),
        sa.CheckConstraint("quantity is null or quantity >= 1", name=op.f("ck_research_lines_quantity")),
        sa.ForeignKeyConstraint(
            ["category_id", "level"],
            ["research_tiers.category_id", "research_tiers.level"],
            name="fk_research_lines_tier",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_lines")),
    )
    op.create_index("ix_research_lines_tier", "research_lines", ["category_id", "level"], unique=False)
    op.add_column("audit_log", sa.Column("system", sa.String(length=16), nullable=False, server_default="craft"))
    op.execute("update audit_log set system = 'accounts' where entity_type = 'user'")
    op.alter_column("audit_log", "system", server_default=None)
    op.create_index(op.f("ix_audit_log_system"), "audit_log", ["system"], unique=False)
    op.add_column("users", sa.Column("permissions", sa.JSON(), nullable=False, server_default="[]"))
    op.execute("""update users set permissions = '["craft"]' where role = 'editor'""")
    op.alter_column("users", "permissions", server_default=None)

    categories = sa.table(
        "research_categories",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("icon", sa.String),
        sa.column("position", sa.Integer),
        sa.column("tier_count", sa.Integer),
        sa.column("completed", sa.Integer),
        sa.column("active", sa.Boolean),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        categories,
        [
            {
                "id": key,
                "name": name,
                "description": description,
                "icon": icon,
                "position": position,
                "tier_count": tiers,
                "completed": 0,
                "active": False,
                "updated_at": now,
            }
            for position, (key, name, icon, tiers, description) in enumerate(RESEARCH_SEED)
        ],
    )


def downgrade() -> None:
    op.drop_column("users", "permissions")
    op.drop_index(op.f("ix_audit_log_system"), table_name="audit_log")
    op.drop_column("audit_log", "system")
    op.drop_index("ix_research_lines_tier", table_name="research_lines")
    op.drop_table("research_lines")
    op.drop_index(op.f("ix_message_receipts_user_id"), table_name="message_receipts")
    op.drop_table("message_receipts")
    op.drop_table("research_tiers")
    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_calendar_events_starts_at"), table_name="calendar_events")
    op.drop_table("calendar_events")
    op.drop_index("uq_research_categories_active", table_name="research_categories", postgresql_where="active")
    op.drop_table("research_categories")
