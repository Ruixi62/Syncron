"""Schéma initial : comptes, sessions, catalogue normalisé, journal.

Revision ID: 0001
Revises:
Create Date: 2026-10-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_state")),
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("max_level", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind in ('job', 'research', 'other')", name=op.f("ck_skills_kind")),
        sa.CheckConstraint("max_level is null or max_level >= 1", name=op.f("ck_skills_max_level")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
    )
    op.create_table(
        "stations",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stations")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("discord_id", sa.String(length=32), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=True),
        sa.Column("avatar", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_banned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role in ('player', 'editor', 'admin')", name=op.f("ck_users_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_discord_id"), "users", ["discord_id"], unique=True)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_audit_log_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_created_at"), "audit_log", ["created_at"], unique=False)
    op.create_index(op.f("ix_audit_log_user_id"), "audit_log", ["user_id"], unique=False)
    op.create_table(
        "items",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=255), nullable=True),
        sa.Column("output", sa.Integer(), nullable=True),
        sa.Column("station_id", sa.String(length=80), nullable=True),
        sa.Column("time_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(type = 'raw' and output is null and station_id is null and time_seconds = 0) or (type = 'crafted' and output >= 1)",
            name=op.f("ck_items_recipe_fields"),
        ),
        sa.CheckConstraint("type in ('raw', 'crafted')", name=op.f("ck_items_type")),
        sa.CheckConstraint("time_seconds >= 0", name=op.f("ck_items_time")),
        sa.ForeignKeyConstraint(
            ["station_id"], ["stations.id"], name=op.f("fk_items_station_id_stations"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_items_updated_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_items")),
    )
    op.create_index(op.f("ix_items_station_id"), "items", ["station_id"], unique=False)
    op.create_table(
        "login_codes",
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_login_codes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("code_hash", name=op.f("pk_login_codes")),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_table(
        "item_requirements",
        sa.Column("item_id", sa.String(length=80), nullable=False),
        sa.Column("skill_id", sa.String(length=80), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("level >= 1", name=op.f("ck_item_requirements_level")),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_item_requirements_item_id_items"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_item_requirements_skill_id_skills"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("item_id", "skill_id", name=op.f("pk_item_requirements")),
    )
    op.create_index(op.f("ix_item_requirements_skill_id"), "item_requirements", ["skill_id"], unique=False)
    op.create_table(
        "recipe_ingredients",
        sa.Column("item_id", sa.String(length=80), nullable=False),
        sa.Column("ingredient_id", sa.String(length=80), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("item_id <> ingredient_id", name=op.f("ck_recipe_ingredients_not_self")),
        sa.CheckConstraint("quantity >= 1", name=op.f("ck_recipe_ingredients_quantity")),
        sa.ForeignKeyConstraint(
            ["ingredient_id"], ["items.id"], name=op.f("fk_recipe_ingredients_ingredient_id_items"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_recipe_ingredients_item_id_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("item_id", "ingredient_id", name=op.f("pk_recipe_ingredients")),
    )
    op.create_index(op.f("ix_recipe_ingredients_ingredient_id"), "recipe_ingredients", ["ingredient_id"], unique=False)
    op.execute("insert into catalog_state (id, revision, updated_at) values (1, 0, now())")


def downgrade() -> None:
    op.drop_index(op.f("ix_recipe_ingredients_ingredient_id"), table_name="recipe_ingredients")
    op.drop_table("recipe_ingredients")
    op.drop_index(op.f("ix_item_requirements_skill_id"), table_name="item_requirements")
    op.drop_table("item_requirements")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("login_codes")
    op.drop_index(op.f("ix_items_station_id"), table_name="items")
    op.drop_table("items")
    op.drop_index(op.f("ix_audit_log_user_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_created_at"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_users_discord_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("stations")
    op.drop_table("skills")
    op.drop_table("catalog_state")
