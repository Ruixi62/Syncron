"""Outil Membres : l'annuaire du pays, construit à partir des profils (Paramètres › Profil).

Recherche par nom, pseudo en jeu, grade, spécialité ou disponibilités ; un clic sur une
carte affiche le profil complet. Dernier état gardé sur le disque pour le hors-ligne.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from syncron_client.api.errors import ApiError
from syncron_client.platform.tool import NotifyLevel, Tool, ToolHost, ToolInfo
from syncron_client.ui import icons
from syncron_client.ui.profile import Member, MemberCard
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import EmptyState, FlowWidget, SearchField, button, label

CACHE_FILE = "members.json"
CARD_WIDTH = 300


class MembersPage(QWidget):
    refreshRequested = Signal()
    profileRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._members: list[Member] = []
        self._avatars: dict[str, QPixmap] = {}
        self.cards: dict[str, MemberCard] = {}
        self.selected: str | None = None

        self.search = SearchField("Rechercher : nom, pseudo, grade, spécialité…")
        self.search.textChanged.connect(self._render)
        self.count = label("", "faint")
        edit = button("Modifier mon profil", "edit")
        edit.clicked.connect(self.profileRequested)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.count)
        toolbar.addWidget(edit)

        self.grid = FlowWidget(spacing=14)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.addWidget(self.grid)
        content_layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(content)

        self.detail_holder = QVBoxLayout()
        self.detail: MemberCard | None = None
        detail_box = QWidget()
        detail_box.setFixedWidth(330)
        detail_layout = QVBoxLayout(detail_box)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(label("PROFIL", "overline"))
        detail_layout.addLayout(self.detail_holder)
        detail_layout.addStretch(1)
        self.detail_box = detail_box
        self.detail_box.hide()

        self.empty = EmptyState("users", "Aucun membre", "")
        self.empty.hide()

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(self.scroll, 1)
        body.addWidget(self.empty, 1)
        body.addWidget(self.detail_box)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(toolbar)
        layout.addLayout(body, 1)

    @property
    def members(self) -> list[Member]:
        return self._members

    def set_members(self, members: list[Member]) -> None:
        self._members = members
        self._render()
        if self.selected and any(m.id == self.selected for m in members):
            self.select(self.selected)

    def set_avatar(self, member_id: str, pixmap: QPixmap) -> None:
        self._avatars[member_id] = pixmap
        if member_id in self.cards:
            self.cards[member_id].set_avatar(pixmap)
        if self.detail is not None and self.detail.member.id == member_id:
            self.detail.set_avatar(pixmap)

    def select(self, member_id: str) -> None:
        member = next((m for m in self._members if m.id == member_id), None)
        if member is None:
            return
        self.selected = member_id
        if self.detail is not None:
            self.detail.hide()
            self.detail.setParent(None)
            self.detail.deleteLater()
        self.detail = MemberCard(member)
        if member_id in self._avatars:
            self.detail.set_avatar(self._avatars[member_id])
        self.detail_holder.addWidget(self.detail)
        self.detail_box.show()

    def _render(self) -> None:
        self.grid.clear()
        self.cards = {}
        query = self.search.text().strip()
        shown = [m for m in self._members if not query or m.matches(query)]
        for member in shown:
            card = MemberCard(member, compact=True)
            card.setFixedWidth(CARD_WIDTH)
            card.clicked.connect(self.select)
            if member.id in self._avatars:
                card.set_avatar(self._avatars[member.id])
            self.cards[member.id] = card
            self.grid.add(card)
        total = len(self._members)
        self.count.setText(f"{len(shown)} / {total} membre(s)" if query else f"{total} membre(s)")
        self.scroll.setVisible(bool(shown))
        self.empty.setVisible(not shown)
        if query and self._members:
            self.empty.body_label.setText("Personne ne correspond à cette recherche.")
        else:
            self.empty.body_label.setText("L'annuaire se remplit à mesure que les membres se connectent.")


class MembersTool(Tool):
    _INFO = ToolInfo(
        id="members",
        name="Membres",
        description="L'annuaire du pays : qui fait quoi, pseudos en jeu, spécialités et disponibilités.",
        icon="users",
        version="5.3.0",
        parent="country",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._page: MembersPage | None = None
        self._members: list[Member] = []
        self._avatars: dict[str, bytes] = {}
        self._actions: list[QAction] = []

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> MembersPage | None:
        return self._page

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._cache_path = host.tool_paths(self.info.id).user_dir / CACHE_FILE
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            self._members = [Member.from_api(entry) for entry in raw]
        except (OSError, ValueError, KeyError, TypeError):
            self._members = []

    def create_page(self) -> QWidget:
        self._page = MembersPage()
        self._page.profileRequested.connect(self._open_profile)
        self._page.set_members(self._members)
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Recharger l'annuaire")
        refresh.triggered.connect(self.refresh)
        self._actions = [refresh]
        return self._page

    def activated(self) -> None:
        self.refresh()

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def refresh(self) -> None:
        if not self._host.session.online:
            return

        def done(raw: list[dict[str, Any]]) -> None:
            self._members = [Member.from_api(entry) for entry in raw]
            try:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                self._cache_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            except OSError:
                self._host.notify("Annuaire non gardé pour le hors-ligne (disque).", NotifyLevel.WARNING)
            if self._page is not None:
                self._page.set_members(self._members)
            self._load_avatars()

        self._host.runner.run(self._host.api.members, done, lambda error: self._host.handle_error(error, "Membres"))

    def _load_avatars(self) -> None:
        missing = [m for m in self._members if m.avatar_url and m.id not in self._avatars]
        for member_id, content in self._avatars.items():
            self._show_avatar(member_id, content)
        if not missing:
            return

        def download() -> dict[str, bytes]:
            fetched = {}
            for member in missing:
                try:
                    fetched[member.id] = self._host.api.download(member.avatar_url)
                except ApiError:
                    continue
            return fetched

        def done(fetched: dict[str, bytes]) -> None:
            self._avatars.update(fetched)
            for member_id, content in fetched.items():
                self._show_avatar(member_id, content)

        self._host.runner.run(download, done, lambda _error: None)

    def _show_avatar(self, member_id: str, content: bytes) -> None:
        pixmap = QPixmap()
        if self._page is not None and pixmap.loadFromData(content):
            self._page.set_avatar(member_id, pixmap)

    def _open_profile(self) -> None:
        self._host.open_tool("settings", "profile")
