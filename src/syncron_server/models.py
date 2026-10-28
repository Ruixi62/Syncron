"""Tables PostgreSQL, regroupées par système.

- Comptes : users, refresh_tokens, login_codes ; journal commun (audit_log).
- Craft : catalogue normalisé (stations, skills, items, recipe_ingredients,
  item_requirements) avec clés étrangères : la base refuse à elle seule une
  recette qui pointerait vers un objet, un atelier ou une compétence inexistant.
- R&D : research_categories → research_tiers → research_lines.
- Calendrier : calendar_events.
- Messagerie : messages, message_receipts (lu / supprimé, par compte).
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
    ForeignKeyConstraint,
    Index,
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
        return {"player": "Membre", "editor": "Éditeur", "admin": "Administrateur"}[self.value]


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    discord_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(64))
    avatar: Mapped[str | None] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default=Role.PLAYER.value)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("role in ('player', 'editor', 'admin')", name="role"),)

    @property
    def role_enum(self) -> Role:
        return Role(self.role)

    @property
    def is_staff(self) -> bool:
        return self.role_enum.rank >= Role.EDITOR.rank

    def can_manage(self, system: str) -> bool:
        """Administrateur : tous les systèmes. Éditeur : ceux que l'administration lui a confiés."""
        if self.role_enum is Role.ADMIN:
            return True
        return self.role_enum is Role.EDITOR and system in (self.permissions or [])


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
    system: Mapped[str] = mapped_column(String(16), default="craft", index=True)
    action: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[str] = mapped_column(String(ID_LENGTH))
    summary: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# -- R&D ---------------------------------------------------------------------------------


class ResearchCategory(Base):
    """Domaine de recherche (global, militaire…) : nombre de paliers, progression du pays."""

    __tablename__ = "research_categories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(32), default="flask")
    position: Mapped[int] = mapped_column(Integer, default=0)
    tier_count: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    skill_id: Mapped[str | None] = mapped_column(String(ID_LENGTH))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    tiers: Mapped[list[ResearchTier]] = relationship(
        order_by="ResearchTier.level", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("tier_count between 0 and 100", name="tier_count"),
        CheckConstraint("completed between 0 and tier_count", name="completed"),
        CheckConstraint("not active or completed < tier_count", name="active"),
        Index("uq_research_categories_active", "active", unique=True, postgresql_where="active"),
    )


class ResearchTier(Base):
    __tablename__ = "research_tiers"

    category_id: Mapped[str] = mapped_column(
        ForeignKey("research_categories.id", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True
    )
    level: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    lines: Mapped[list[ResearchLine]] = relationship(
        order_by="ResearchLine.position", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (CheckConstraint("level >= 1", name="level"),)


class ResearchLine(Base):
    """Condition ou récompense d'un palier : un texte, et éventuellement une quantité d'un objet du catalogue."""

    __tablename__ = "research_lines"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    category_id: Mapped[str] = mapped_column(String(32))
    level: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(String(300), default="")
    quantity: Mapped[int | None] = mapped_column(BigInteger)
    item_id: Mapped[str | None] = mapped_column(String(ID_LENGTH))
    done: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["category_id", "level"],
            ["research_tiers.category_id", "research_tiers.level"],
            ondelete="CASCADE",
            onupdate="CASCADE",
            name="fk_research_lines_tier",
        ),
        Index("ix_research_lines_tier", "category_id", "level"),
        CheckConstraint("kind in ('condition', 'reward')", name="kind"),
        CheckConstraint("quantity is null or quantity >= 1", name="quantity"),
        CheckConstraint("text <> '' or item_id is not null", name="content"),
    )


# -- Calendrier -----------------------------------------------------------------------------


EVENT_CATEGORIES = ("meeting", "war", "event", "economy", "other")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(16), default="event")
    location: Mapped[str] = mapped_column(String(120), default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint(f"category in {EVENT_CATEGORIES}", name="category"),
        CheckConstraint("ends_at is null or ends_at >= starts_at", name="period"),
    )


# -- Messagerie -------------------------------------------------------------------------------


AUDIENCES = ("all", "staff", "direct")


class Message(Base):
    """Message de la messagerie. `audience` : tout le pays, l'équipe (éditeurs et admins) ou des comptes précis
    (une ligne message_receipts par destinataire, créée à l'envoi)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    system: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(String(8))
    link_tool: Mapped[str | None] = mapped_column(String(32))
    link_key: Mapped[str | None] = mapped_column(String(160))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    __table_args__ = (CheckConstraint(f"audience in {AUDIENCES}", name="audience"),)


class MessageReceipt(Base):
    __tablename__ = "message_receipts"

    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
