"""Contrats JSON de l'API (entrées validées, sorties typées)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from syncron_core.models.validation import ValidationIssue
from syncron_server.models import Role, User

Name = Field(min_length=1, max_length=120)
Description = Field("", max_length=4000)


class UserOut(BaseModel):
    id: uuid.UUID
    discord_id: str
    username: str
    display_name: str | None
    avatar_url: str | None
    role: Role
    permissions: list[str]
    is_banned: bool
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def of(cls, user: User) -> UserOut:
        avatar = None
        if user.avatar:
            avatar = f"https://cdn.discordapp.com/avatars/{user.discord_id}/{user.avatar}.png?size=128"
        return cls(
            id=user.id,
            discord_id=user.discord_id,
            username=user.username,
            display_name=user.display_name,
            avatar_url=avatar,
            role=user.role_enum,
            permissions=sorted(user.permissions or []),
            is_banned=user.is_banned,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class MetaOut(BaseModel):
    name: str
    version: str
    api_version: int
    min_client_version: str
    catalog_revision: int
    discord_login: bool
    dev_login: bool
    nation_name: str
    systems: dict[str, str]


class TokenRequest(BaseModel):
    code: str = Field(min_length=10, max_length=200)
    code_verifier: str = Field(min_length=43, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=200)


class DevLoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_.\-]+$")
    role: Role = Role.PLAYER
    permissions: list[str] | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


class IssueOut(BaseModel):
    severity: str
    message: str
    entity_id: str | None
    section: str

    @classmethod
    def of(cls, issue: ValidationIssue) -> IssueOut:
        return cls(severity=issue.severity.value, message=issue.message, entity_id=issue.item_id, section=issue.section)


class StationIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Name
    description: str = Description


class SkillIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Name
    kind: Literal["job", "research", "other"] = "other"
    max_level: int | None = Field(None, ge=1, le=1_000_000)
    description: str = Description


class ItemIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Name
    type: Literal["raw", "crafted"]
    category: str = Field("", max_length=80)
    description: str = Description
    output: int = Field(1, ge=1, le=1_000_000)
    station_id: str | None = None
    time: int | str = 0
    requires: dict[str, int] = Field(default_factory=dict)
    recipe: dict[str, int] = Field(default_factory=dict)


class SectionDiffOut(BaseModel):
    added: list[str]
    updated: list[str]
    removed: list[str]
    unchanged: int


class WriteOut(BaseModel):
    revision: int
    changed: bool


class ImportOut(BaseModel):
    dry_run: bool
    applied: bool
    revision: int
    stations: SectionDiffOut
    skills: SectionDiffOut
    items: SectionDiffOut
    warnings: list[IssueOut]


class CraftPlanRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(1, ge=1, le=1_000_000_000)


class AuditOut(BaseModel):
    id: int
    created_at: datetime
    username: str | None
    system: str
    action: str
    entity_type: str
    entity_id: str
    summary: str


class OverviewStat(BaseModel):
    label: str
    value: str
    detail: str = ""


class OverviewTodo(BaseModel):
    label: str
    count: int


class SystemOverviewOut(BaseModel):
    id: str
    name: str
    stats: list[OverviewStat]
    todo: list[OverviewTodo] = Field(default_factory=list)
    updated_at: datetime | None = None


class AccountsOverviewOut(BaseModel):
    total: int
    by_role: dict[str, int]
    banned: int


class OverviewOut(BaseModel):
    systems: list[SystemOverviewOut]
    accounts: AccountsOverviewOut | None
    recent: list[AuditOut]


class UserPatch(BaseModel):
    role: Role | None = None
    is_banned: bool | None = None
    permissions: list[str] | None = None


# -- R&D ------------------------------------------------------------------------------------


class ResearchLineIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    text: str = Field("", max_length=300)
    quantity: int | None = Field(None, ge=1, le=10_000_000_000)
    item_id: str | None = Field(None, max_length=80)
    done: bool = False

    @model_validator(mode="after")
    def _content(self) -> ResearchLineIn:
        self.item_id = self.item_id or None
        if not self.text and not self.item_id:
            raise ValueError("Une ligne doit avoir un texte ou un objet.")
        return self


class ResearchLineOut(BaseModel):
    id: int
    text: str
    quantity: int | None
    item_id: str | None
    done: bool


class ResearchTierIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field("", max_length=120)
    description: str = Description
    conditions: list[ResearchLineIn] = Field(default_factory=list, max_length=100)
    rewards: list[ResearchLineIn] = Field(default_factory=list, max_length=100)


class ResearchTierOut(BaseModel):
    level: int
    name: str
    description: str
    conditions: list[ResearchLineOut]
    rewards: list[ResearchLineOut]


class ResearchCategoryIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    description: str = Description
    icon: str = Field("flask", max_length=32)
    position: int = Field(0, ge=0, le=1000)
    tier_count: int = Field(0, ge=0, le=100)
    completed: int = Field(0, ge=0, le=100)
    active: bool = False
    skill_id: str | None = Field(None, max_length=80)
    notify: bool = False


class ResearchCategoryOut(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    position: int
    tier_count: int
    completed: int
    active: bool
    skill_id: str | None
    updated_at: datetime
    tiers: list[ResearchTierOut]


class ResearchOut(BaseModel):
    categories: list[ResearchCategoryOut]


# -- Calendrier ------------------------------------------------------------------------------


EventCategory = Literal["meeting", "war", "event", "economy", "other"]


class EventIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Name
    description: str = Description
    category: EventCategory = "event"
    location: str = Field("", max_length=120)
    starts_at: datetime
    ends_at: datetime | None = None
    all_day: bool = False
    notify: bool = False

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("La date doit préciser son fuseau horaire.")
        return value

    @model_validator(mode="after")
    def _period(self) -> EventIn:
        if self.ends_at is not None and self.ends_at < self.starts_at:
            raise ValueError("La fin doit être après le début.")
        return self


class EventOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    category: EventCategory
    location: str
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    author: str | None
    updated_at: datetime


# -- Messagerie --------------------------------------------------------------------------------


class MessageOut(BaseModel):
    id: int
    system: str
    title: str
    body: str
    author: str | None
    link_tool: str | None
    link_key: str | None
    created_at: datetime
    read: bool


class InboxSummaryOut(BaseModel):
    unread: int
    latest_id: int


class InboxReadIn(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=500)
    all: bool = False


class AnnouncementIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field("", max_length=8000)
    audience: Literal["all", "staff", "users"] = "all"
    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    link_tool: str | None = Field(None, max_length=32)
    link_key: str | None = Field(None, max_length=160)

    @model_validator(mode="after")
    def _recipients(self) -> AnnouncementIn:
        if self.audience == "users" and not self.user_ids:
            raise ValueError("Choisis au moins un destinataire.")
        return self


class RecipientOut(BaseModel):
    id: uuid.UUID
    name: str
    username: str
    role: Role


class SentMessageOut(BaseModel):
    id: int
    system: str
    title: str
    body: str
    audience: str
    author: str | None
    created_at: datetime
    recipients: int
    read: int
