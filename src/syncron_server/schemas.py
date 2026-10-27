"""Contrats JSON de l'API (entrées validées, sorties typées)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class TokenRequest(BaseModel):
    code: str = Field(min_length=10, max_length=200)
    code_verifier: str = Field(min_length=43, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=200)


class DevLoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_.\-]+$")
    role: Role = Role.PLAYER


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
    action: str
    entity_type: str
    entity_id: str
    summary: str


class DashboardOut(BaseModel):
    revision: int
    updated_at: datetime
    items_total: int
    items_raw: int
    items_crafted: int
    stations: int
    skills: int
    users_total: int
    users_by_role: dict[str, int]
    users_banned: int
    items_without_image: int
    crafted_without_time: int
    items_without_category: int
    recent: list[AuditOut]


class UserPatch(BaseModel):
    role: Role | None = None
    is_banned: bool | None = None
