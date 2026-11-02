"""Profils des membres : données, couleurs, carte de profil (annuaire et aperçu dans les Paramètres)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from syncron_client.shell.sidebar import initials_avatar, round_avatar
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Chip, ElidedLabel, FlowWidget, label, plain_tooltip

PROFILE_COLORS: dict[str, tuple[str, str]] = {
    "teal": ("#2fbfa8", "Turquoise"),
    "blue": ("#4f8ff0", "Bleu"),
    "violet": ("#8f6ff0", "Violet"),
    "pink": ("#e0609a", "Rose"),
    "red": ("#e0484e", "Rouge"),
    "orange": ("#ec8a3a", "Orange"),
    "yellow": ("#d9ad1f", "Jaune"),
    "green": ("#3fb36b", "Vert"),
}
ROLE_LABELS = {"admin": ("Administrateur", "accent"), "editor": ("Éditeur", "info"), "player": ("Membre", "neutral")}
NICKNAME_PATTERN = r"^([A-Za-z0-9_]{3,16})?$"
BIO_MAX = 600
SPECIALTIES_MAX = 8
COMPACT_BIO = 110


def profile_color(name: str) -> str:
    return PROFILE_COLORS.get(name, PROFILE_COLORS["teal"])[0]


@dataclass(frozen=True, slots=True)
class Member:
    id: str
    name: str
    discord_username: str | None = None
    avatar_url: str | None = None
    role: str = "player"
    nickname: str = ""
    title: str = ""
    bio: str = ""
    specialties: tuple[str, ...] = field(default_factory=tuple)
    availability: str = ""
    color: str = "teal"
    show_discord: bool = True
    joined_at: datetime | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Member:
        joined = raw.get("joined_at")
        return cls(
            id=str(raw["id"]),
            name=raw.get("name") or "?",
            discord_username=raw.get("discord_username"),
            avatar_url=raw.get("avatar_url"),
            role=raw.get("role") or "player",
            nickname=raw.get("nickname") or "",
            title=raw.get("title") or "",
            bio=raw.get("bio") or "",
            specialties=tuple(raw.get("specialties") or ()),
            availability=raw.get("availability") or "",
            color=raw.get("color") or "teal",
            show_discord=raw.get("show_discord", True) is not False,
            joined_at=datetime.fromisoformat(joined) if joined else None,
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "nickname": self.nickname,
            "title": self.title,
            "bio": self.bio,
            "specialties": list(self.specialties),
            "availability": self.availability,
            "color": self.color,
            "show_discord": self.show_discord,
        }

    @property
    def subtitle(self) -> str:
        parts = []
        if self.nickname:
            parts.append(f"En jeu : {self.nickname}")
        if self.discord_username:
            parts.append(f"@{self.discord_username}")
        return " · ".join(parts)

    def matches(self, query: str) -> bool:
        haystack = " ".join(
            [self.name, self.nickname, self.title, self.bio, self.availability, *self.specialties]
        ).casefold()
        return all(word in haystack for word in query.casefold().split())


class MemberCard(QFrame):
    """Carte de profil : liseré de couleur, avatar, nom, pseudo, grade, spécialités, disponibilités, description.
    `compact` : description sur trois lignes au plus (annuaire)."""

    clicked = Signal(str)

    def __init__(self, member: Member, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.member = member
        self._compact = compact
        self.setObjectName("MemberCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor if compact else Qt.CursorShape.ArrowCursor)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 16)
        self._layout.setSpacing(10)
        self._avatar = QLabel()
        self._avatar.setFixedSize(52, 52)
        self._pixmap: QPixmap | None = None
        self.show_member(member)

    def show_member(self, member: Member) -> None:
        self.member = member
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._avatar:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                _empty(item.layout(), keep=self._avatar)
        color = profile_color(member.color)
        self.setStyleSheet(
            f"QFrame#MemberCard {{ background: {COLORS.surface}; border: 1px solid {COLORS.card_border};"
            f" border-top: 4px solid {color}; border-radius: 16px; }}"
        )
        self._paint_avatar()
        names = QVBoxLayout()
        names.setSpacing(1)
        title = ElidedLabel(member.name, "heading")
        names.addWidget(title)
        if member.subtitle:
            names.addWidget(ElidedLabel(member.subtitle, "faint"))
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(names, 1)
        role_label, tone = ROLE_LABELS.get(member.role, ROLE_LABELS["player"])
        if member.role != "player":
            head.addWidget(Chip(role_label, tone, "shield"), 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addLayout(head)
        if member.title:
            grade = label(member.title, wrap=True)
            grade.setStyleSheet(f"color: {color}; font-weight: 600;")
            self._layout.addWidget(grade)
        if member.specialties:
            tags = FlowWidget(spacing=6)
            for tag in member.specialties:
                tags.add(Chip(tag, "neutral"))
            self._layout.addWidget(tags)
        if member.availability:
            row = QHBoxLayout()
            row.setSpacing(6)
            clock = QLabel()
            clock.setPixmap(icons.pixmap("clock", COLORS.text_faint, 14))
            row.addWidget(clock)
            row.addWidget(label(member.availability, "muted"), 1)
            self._layout.addLayout(row)
        if member.bio:
            text = member.bio
            if self._compact and len(text) > COMPACT_BIO:
                text = text[:COMPACT_BIO].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"
            bio = label(text, "muted", wrap=True)
            bio.setToolTip(plain_tooltip(member.bio) if text != member.bio else "")
            self._layout.addWidget(bio)
        elif not self._compact:
            self._layout.addWidget(label("Pas encore de description.", "faint"))
        self._layout.addStretch(1)

    def set_avatar(self, pixmap: QPixmap) -> None:
        if not pixmap.isNull():
            self._pixmap = pixmap
            self._paint_avatar()

    def _paint_avatar(self) -> None:
        if self._pixmap is not None:
            self._avatar.setPixmap(round_avatar(self._pixmap, 52))
        else:
            self._avatar.setPixmap(initials_avatar(self.member.name, 52, profile_color(self.member.color)))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._compact:
            self.clicked.emit(self.member.id)
        super().mousePressEvent(event)


def _empty(layout, keep: QWidget) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is keep:
            continue
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _empty(item.layout(), keep)
