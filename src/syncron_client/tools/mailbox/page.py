"""Page de la messagerie : liste des messages (tous / non lus) et lecture."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.ui import icons
from syncron_client.ui.format import format_datetime, relative_time
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, Chip, EmptyState, SegmentedControl, button, label

PAGE_SIZE = 50
ITEM_HEIGHT = 50
ID_ROLE = Qt.ItemDataRole.UserRole + 1
SYSTEM_ICONS = {
    "craft": "hammer",
    "research": "flask",
    "calendar": "calendar",
    "messages": "megaphone",
    "accounts": "user",
}
SYSTEM_TONES = {
    "research": "violet",
    "calendar": "info",
    "messages": "accent",
    "accounts": "neutral",
    "craft": "success",
}


def system_label(host: ToolHost, system: str) -> str:
    return (
        "Compte" if system == "accounts" else ("Annonce" if system == "messages" else host.session.system_name(system))
    )


class MessageView(QWidget):
    """Lecture d'un message."""

    def __init__(self, host: ToolHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._message: dict[str, Any] | None = None
        self.chip = Chip("", "neutral")
        self.title = label("", "title", wrap=True)
        self.meta = label("", "faint")
        self.body = label("", wrap=True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.open_button = button("Ouvrir", "arrow-right", "primary")
        self.open_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.open_button.clicked.connect(self._open_link)
        self.delete_button = button("Supprimer", "trash", "ghost")

        text = QWidget()
        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.addWidget(self.body)
        text_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(text)

        actions = QHBoxLayout()
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        actions.addWidget(self.open_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.title)
        layout.addWidget(self.meta)
        layout.addSpacing(6)
        layout.addWidget(scroll, 1)
        layout.addLayout(actions)

    @property
    def message(self) -> dict[str, Any] | None:
        return self._message

    def clear(self) -> None:
        self._message = None

    def show_message(self, message: dict[str, Any]) -> None:
        self._message = message
        system = message["system"]
        self.chip.set_content(
            system_label(self._host, system), SYSTEM_TONES.get(system, "neutral"), SYSTEM_ICONS.get(system, "mail")
        )
        self.title.setText(message["title"])
        author = message.get("author") or "Syncron"
        self.meta.setText(f"De {author} · {format_datetime(message['created_at'])}")
        self.body.setText(message.get("body") or "Ce message n'a pas de texte.")
        tool_id = message.get("link_tool")
        target = next((tool for tool in self._host.tools() if tool.info.id == tool_id), None)
        self.open_button.setVisible(target is not None)
        if target is not None:
            self.open_button.setText(f"Voir dans {target.info.name}".replace("&", "&&"))

    def _open_link(self) -> None:
        if self._message and self._message.get("link_tool"):
            self._host.open_tool(self._message["link_tool"], self._message.get("link_key") or None)


class MailboxPage(QWidget):
    def __init__(self, host: ToolHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._messages: list[dict[str, Any]] = []
        self._exhausted = False

        self.filter = SegmentedControl([("Tous", "inbox"), ("Non lus", "mail")])
        self.filter.currentChanged.connect(lambda _index: self.reload())
        self.mark_all_button = button("Tout marquer comme lu", "check", "ghost")
        self.mark_all_button.clicked.connect(self.mark_all_read)
        self.list = QListWidget()
        self.list.setIconSize(QSize(20, 20))
        self.list.setSpacing(2)
        self.list.currentItemChanged.connect(self._on_current)
        self.more_button = button("Charger plus", "history", "ghost")
        self.more_button.clicked.connect(self._load_more)
        self.count = label("", "faint")

        list_card = Card(padding=14, spacing=10)
        top = QHBoxLayout()
        top.addWidget(self.filter)
        top.addStretch(1)
        top.addWidget(self.mark_all_button)
        list_card.body.addLayout(top)
        list_card.body.addWidget(self.count)
        list_card.body.addWidget(self.list, 1)
        list_card.body.addWidget(self.more_button, 0, Qt.AlignmentFlag.AlignHCenter)

        self.view = MessageView(host)
        self.view.delete_button.clicked.connect(self.delete_current)
        self._empty = EmptyState(
            "inbox", "Aucun message sélectionné", "Les annonces de l'équipe et les nouvelles du pays arrivent ici."
        )
        self._detail_stack = QStackedWidget()
        self._detail_stack.addWidget(self._empty)
        self._detail_stack.addWidget(self.view)
        detail_card = Card(padding=22, spacing=0)
        detail_card.body.addWidget(self._detail_stack)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        splitter.addWidget(list_card)
        splitter.addWidget(detail_card)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 760])
        list_card.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.addWidget(splitter)

    # -- données ----------------------------------------------------------------------------

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self._messages

    @property
    def unread_only(self) -> bool:
        return self.filter.current_index() == 1

    def reload(self) -> None:
        if not self._host.session.online:
            self._show([], keep=None)
            self.count.setText("Hors ligne : la messagerie n'est pas disponible.")
            return
        keep = self.view.message["id"] if self.view.message else None
        unread_only = self.unread_only
        call_api(
            self._host,
            lambda: self._host.api.inbox(PAGE_SIZE, unread_only=unread_only),
            lambda messages: self._show(messages, keep),
        )

    def _load_more(self) -> None:
        if not self._messages:
            return
        before = self._messages[-1]["id"]
        unread_only = self.unread_only
        call_api(
            self._host,
            lambda: self._host.api.inbox(PAGE_SIZE, before=before, unread_only=unread_only),
            lambda messages: self._show(self._messages + messages, None, len(messages) < PAGE_SIZE),
        )

    def _show(self, messages: list[dict[str, Any]], keep: int | None, exhausted: bool | None = None) -> None:
        self._messages = messages
        self._exhausted = len(messages) < PAGE_SIZE if exhausted is None else exhausted
        self.list.blockSignals(True)
        self.list.clear()
        for message in messages:
            self.list.addItem(self._item(message))
        self.list.blockSignals(False)
        self._update_count()
        self.more_button.setVisible(bool(messages) and not self._exhausted)
        self.mark_all_button.setEnabled(any(not m["read"] for m in messages) or self._host.notifications.unread > 0)
        if keep is not None and self.select(keep):
            return
        self.list.setCurrentItem(None)
        self._detail_stack.setCurrentWidget(self._empty)

    def _item(self, message: dict[str, Any]) -> QListWidgetItem:
        system = message["system"]
        meta = f"{system_label(self._host, system)} · {relative_time(message['created_at'])}"
        item = QListWidgetItem(f"{message['title']}\n{meta}")
        item.setData(ID_ROLE, message["id"])
        item.setSizeHint(QSize(0, ITEM_HEIGHT))
        color = COLORS.accent if not message["read"] else COLORS.text_faint
        item.setIcon(icons.icon(SYSTEM_ICONS.get(system, "mail"), color, 20))
        font = QFont(self.list.font())
        font.setWeight(QFont.Weight.DemiBold if not message["read"] else QFont.Weight.Normal)
        item.setFont(font)
        item.setForeground(QColor(COLORS.text if not message["read"] else COLORS.text_muted))
        return item

    def _update_count(self) -> None:
        unread = sum(1 for m in self._messages if not m["read"])
        text = f"{len(self._messages)} message(s) · {unread} non lu(s)" if self._messages else "Aucun message."
        self.count.setText(text)

    def select(self, message_id: int) -> bool:
        for row in range(self.list.count()):
            if self.list.item(row).data(ID_ROLE) == message_id:
                self.list.setCurrentRow(row)
                return True
        return False

    # -- actions -----------------------------------------------------------------------------

    def _on_current(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self._detail_stack.setCurrentWidget(self._empty)
            return
        message = next(m for m in self._messages if m["id"] == current.data(ID_ROLE))
        self.view.show_message(message)
        self._detail_stack.setCurrentWidget(self.view)
        if not message["read"]:
            message["read"] = True
            row = self.list.row(current)
            self.list.blockSignals(True)
            self.list.takeItem(row)
            self.list.insertItem(row, self._item(message))
            self.list.setCurrentRow(row)
            self.list.blockSignals(False)
            self._update_count()
            self._host.notifications.mark_read([message["id"]])

    def mark_all_read(self) -> None:
        self._host.notifications.mark_read(None, self.reload)

    def delete_current(self) -> None:
        message = self.view.message
        if message is None:
            return
        answer = QMessageBox.question(self, "Supprimer", f"Supprimer « {message['title']} » de ta messagerie ?")
        if answer == QMessageBox.StandardButton.Yes:
            self.delete(message["id"])

    def delete(self, message_id: int) -> None:
        def done() -> None:
            self.view.clear()
            self.reload()

        self._host.notifications.delete(message_id, done)
