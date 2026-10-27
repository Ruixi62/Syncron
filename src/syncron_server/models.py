"""Tables PostgreSQL.

Le catalogue (stations, skills, items, recipe_ingredients, item_requirements)
est normalisé avec des clés étrangères : la base refuse à elle seule une
recette qui pointerait vers un objet, un atelier ou une compétence inexistant.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syncron_server.db import Base

ID_LENGTH = 80


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    PLAYER = "player"
    EDITOR = "editor"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return {"player": 0, "editor": 1, "admin": 2}[self.value]

    @property
    def label(self) -> str:
        return {"player": "Joueur", "editor": "Éditeur", "admin": "Administrateur"}[self.value]


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    discord_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(64))
    avatar: Mapped[str | None] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default=Role.PLAYER.value)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("role in ('player', 'editor', 'admin')", name="role"),)

    @property
    def role_enum(self) -> Role:
        return Role(self.role)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginCode(Base):
    """Code à usage unique remis au client après la connexion Discord (échangé contre des jetons, avec PKCE)."""

    __tablename__ = "login_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code_challenge: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default="other")
    max_level: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("kind in ('job', 'research', 'other')", name="kind"),
        CheckConstraint("max_level is null or max_level >= 1", name="max_level"),
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(String(255))
    output: Mapped[int | None] = mapped_column(Integer)
    station_id: Mapped[str | None] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), index=True)
    time_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        foreign_keys="RecipeIngredient.item_id",
        order_by="RecipeIngredient.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    requirements: Mapped[list[ItemRequirement]] = relationship(
        order_by="ItemRequirement.position", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("type in ('raw', 'crafted')", name="type"),
        CheckConstraint("time_seconds >= 0", name="time"),
        CheckConstraint(
            "(type = 'raw' and output is null and station_id is null and time_seconds = 0) "
            "or (type = 'crafted' and output >= 1)",
            name="recipe_fields",
        ),
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    ingredient_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("quantity >= 1", name="quantity"),
        CheckConstraint("item_id <> ingredient_id", name="not_self"),
    )


class ItemRequirement(Base):
    __tablename__ = "item_requirements"

    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True, index=True)
    level: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (CheckConstraint("level >= 1", name="level"),)


class CatalogState(Base):
    """Ligne unique : révision du catalogue (ETag du client) et verrou d'écriture."""

    __tablename__ = "catalog_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[str] = mapped_column(String(ID_LENGTH))
    summary: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
