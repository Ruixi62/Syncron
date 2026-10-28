"""Gestion de la messagerie : rédiger une annonce, suivre les annonces envoyées."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.session import Role
from syncron_client.ui.format import relative_time
from syncron_client.ui.tables import fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.widgets import Banner, Card, SearchField, SegmentedControl, button, label
from syncron_core.text import normalize

AUDIENCES = (("all", "Tout le pays", "globe"), ("staff", "L'équipe", "shield"), ("users", "Membres choisis", "users"))
AUDIENCE_LABELS = {"all": "Tout le pays", "staff": "L'équipe", "direct": "Membres choisis"}
USER_ROLE = Qt.ItemDataRole.UserRole + 1


class AnnouncementsView(QWidget):
    def __init__(self, host: ToolHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._sent: list[dict[str, Any]] = []

        compose = Card(padding=20, spacing=12)
        compose.body.addWidget(label("NOUVELLE ANNONCE", "overline"))
        self.banner = Banner("danger")
        self.banner.hide()
        self.title_field = QLineEdit()
        self.title_field.setMaxLength(160)
        self.title_field.setPlaceholderText("Mobilisation générale samedi 21 h")
        self.body_field = QPlainTextEdit()
        self.body_field.setPlaceholderText("Détails, consignes, liens…")
        self.body_field.setMinimumHeight(140)
        self.audience = SegmentedControl([(text, icon) for _value, text, icon in AUDIENCES])
        self.audience.currentChanged.connect(self._audience_changed)
        self.recipient_search = SearchField("Filtrer les membres…")
        self.recipient_search.textChanged.connect(self._filter_recipients)
        self.recipients = QListWidget()
        self.recipients.setMinimumHeight(160)
        self._recipients_box = QWidget()
        box = QVBoxLayout(self._recipients_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.recipient_search)
        box.addWidget(self.recipients)
        self._recipients_box.hide()
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.addRow("Titre", self.title_field)
        form.addRow("Message", self.body_field)
        form.addRow("Destinataires", self.audience)
        form.addRow("", self._recipients_box)
        self.send_button = button("Envoyer", "megaphone", "primary")
        self.send_button.clicked.connect(self.send)
        hint = label("Chaque destinataire est prévenu dans Syncron et retrouve l'annonce dans sa messagerie.", "faint")
        hint.setWordWrap(True)
        actions = QHBoxLayout()
        actions.addWidget(hint, 1)
        actions.addWidget(self.send_button)
        compose.body.addWidget(self.banner)
        compose.body.addLayout(form)
        compose.body.addStretch(1)
        compose.body.addLayout(actions)

        history = Card(padding=20, spacing=10)
        head = QHBoxLayout()
        head.addWidget(label("ANNONCES ENVOYÉES", "overline"), 1)
        self.retract_button = button("Retirer", "trash", "ghost")
        self.retract_button.clicked.connect(self._retract_selected)
        head.addWidget(self.retract_button)
        self.table = make_table(["Date", "Titre", "Pour", "Lu par"], 1)
        history.body.addLayout(head)
        history.body.addWidget(self.table, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        splitter.addWidget(compose)
        splitter.addWidget(history)
        splitter.setSizes([520, 680])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    @property
    def sent(self) -> list[dict[str, Any]]:
        return self._sent

    def refresh(self) -> None:
        call_api(self._host, self._host.api.sent_messages, self._show_sent)
        if not self.recipients.count():
            call_api(self._host, self._host.api.recipients, self._show_recipients)

    def is_dirty(self) -> bool:
        return bool(self.title_field.text().strip() or self.body_field.toPlainText().strip())

    def set_audience(self, value: str) -> None:
        self.audience.set_current_index([a[0] for a in AUDIENCES].index(value))

    def choose(self, usernames: set[str]) -> None:
        for row in range(self.recipients.count()):
            item = self.recipients.item(row)
            checked = item.data(USER_ROLE)["username"] in usernames
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def send(self) -> None:
        audience = AUDIENCES[self.audience.current_index()][0]
        payload: dict[str, Any] = {
            "title": self.title_field.text().strip(),
            "body": self.body_field.toPlainText().strip(),
            "audience": audience,
        }
        if not payload["title"]:
            self.banner.set_text("Le titre est obligatoire.")
            self.banner.show()
            return
        if audience == "users":
            payload["user_ids"] = [
                self.recipients.item(row).data(USER_ROLE)["id"]
                for row in range(self.recipients.count())
                if self.recipients.item(row).checkState() == Qt.CheckState.Checked
            ]

        def sent(result: dict[str, Any]) -> None:
            self.title_field.clear()
            self.body_field.clear()
            self.choose(set())
            self._host.notifications.poll()
            self.refresh()

        call_api(
            self._host,
            lambda: self._host.api.announce(payload),
            sent,
            banner=self.banner,
            success="Annonce envoyée.",
        )

    def retract(self, message_id: int) -> None:
        call_api(
            self._host,
            lambda: self._host.api.retract_message(message_id),
            lambda _result: self.refresh(),
            success="Annonce retirée des messageries.",
        )

    def _retract_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            return
        message = self._sent[rows[0]]
        answer = QMessageBox.question(
            self, "Retirer", f"Retirer « {message['title']} » de toutes les messageries ? C'est définitif."
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.retract(message["id"])

    def _show_sent(self, messages: list[dict[str, Any]]) -> None:
        self._sent = messages
        fill_rows(
            self.table,
            [
                [
                    muted_cell(relative_time(m["created_at"])),
                    text_cell(m["title"]),
                    muted_cell(AUDIENCE_LABELS.get(m["audience"], m["audience"])),
                    muted_cell(f"{m['read']} / {m['recipients']}"),
                ]
                for m in messages
            ],
        )
        self.retract_button.setEnabled(bool(messages))

    def _show_recipients(self, users: list[dict[str, Any]]) -> None:
        self.recipients.clear()
        for user in users:
            role = Role(user["role"])
            suffix = "" if role is Role.PLAYER else f"  ·  {role.label}"
            item = QListWidgetItem(f"{user['name']}  (@{user['username']}){suffix}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(USER_ROLE, user)
            self.recipients.addItem(item)
        self._filter_recipients(self.recipient_search.text())

    def _filter_recipients(self, text: str) -> None:
        tokens = normalize(text).split()
        for row in range(self.recipients.count()):
            item = self.recipients.item(row)
            haystack = normalize(item.text())
            item.setHidden(not all(token in haystack for token in tokens))

    def _audience_changed(self, index: int) -> None:
        self._recipients_box.setVisible(AUDIENCES[index][0] == "users")
