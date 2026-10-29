"""Messagerie : boîte de réception de chaque membre ; annonces de l'équipe (gestion).

Les autres systèmes y déposent leurs nouvelles côté serveur (événement créé,
palier de R&D terminé…) ; le centre de notifications de la plateforme
prévient l'utilisateur à leur arrivée.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget

from syncron_client.platform.admin import AdminSection
from syncron_client.platform.tool import Placement, StatusLevel, Tool, ToolHost, ToolInfo, ToolStatus
from syncron_client.tools.mailbox.admin import AnnouncementsView
from syncron_client.tools.mailbox.page import MailboxPage
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS

ANNOUNCEMENTS = "messages.announcements"


class MailboxTool(Tool):
    _INFO = ToolInfo(
        id="mailbox",
        name="Messagerie",
        description="Annonces de l'équipe et nouvelles du pays.",
        icon="mail",
        version="4.3.0",
        placement=Placement.MAIN,
        system="messages",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._page: MailboxPage | None = None
        self._announcements: AnnouncementsView | None = None
        self._actions: list[QAction] = []

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> MailboxPage | None:
        return self._page

    @property
    def announcements(self) -> AnnouncementsView | None:
        return self._announcements

    def setup(self, host: ToolHost) -> None:
        self._host = host
        host.notifications.unreadChanged.connect(self._on_unread)
        host.notifications.received.connect(self._on_received)

    def create_page(self) -> QWidget:
        self._page = MailboxPage(self._host)
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Relever la messagerie")
        refresh.triggered.connect(self._refresh)
        self._actions = [refresh]
        return self._page

    def activated(self) -> None:
        self._refresh()

    def open(self, key: str) -> None:
        if self._page is not None and key.isdigit():
            self._page.select(int(key))

    def status(self) -> ToolStatus:
        unread = self._host.notifications.unread if self._host else 0
        if unread:
            return ToolStatus(StatusLevel.INFO, f"{unread} message(s) non lu(s)", "99+" if unread > 99 else str(unread))
        return ToolStatus()

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    def admin_sections(self) -> Sequence[AdminSection]:
        return [AdminSection(ANNOUNCEMENTS, "Annonces", "megaphone", self._create_announcements)]

    def shutdown(self) -> None:
        for signal, slot in (
            (self._host.notifications.unreadChanged, self._on_unread),
            (self._host.notifications.received, self._on_received),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                continue

    def _create_announcements(self) -> AnnouncementsView:
        self._announcements = AnnouncementsView(self._host)
        return self._announcements

    def _refresh(self) -> None:
        self._host.notifications.poll()
        if self._page is not None:
            self._page.reload()

    def _on_unread(self, _count: int) -> None:
        self._host.status_changed(self.info.id)

    def _on_received(self, _messages: list) -> None:
        if self._page is not None and self._page.isVisible():
            self._page.reload()
