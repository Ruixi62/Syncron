"""Comptes (administrateurs) : rôle, systèmes confiés aux éditeurs, suspension."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QMenu, QToolButton, QVBoxLayout, QWidget

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.session import Role
from syncron_client.ui.format import format_datetime
from syncron_client.ui.tables import fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Banner, Card, SearchField, button, label

ROLE_CHOICES = tuple((role.value, role.label) for role in (Role.PLAYER, Role.EDITOR, Role.ADMIN))


class UsersView(QWidget):
    def __init__(self, host: ToolHost, systems: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._systems = systems
        self._users: list[dict[str, Any]] = []
        self._search = SearchField("Rechercher un pseudo ou un ID Discord…")
        self._search.returnPressed.connect(self.refresh)
        self.banner = Banner("danger")
        self.banner.hide()
        self.table = make_table(["Compte", "ID Discord", "Rôle", "Systèmes gérés", "Suspendu", "Dernière connexion"], 0)
        header = self.table.horizontalHeader()
        for column, width in ((2, 170), (3, 220), (4, 90)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        hint = label(
            "Membre : consulte les outils. Éditeur : gère les systèmes qui lui sont confiés (Craft, R&D, Calendrier, "
            "Messagerie). Administrateur : gère tout, y compris les comptes. Suspendre un compte coupe "
            "immédiatement ses sessions. Chaque changement est signalé à la personne dans sa messagerie.",
            "faint",
            wrap=True,
        )
        card = Card(padding=16, spacing=10)
        top = QHBoxLayout()
        top.addWidget(self._search, 1)
        refresh = button("Actualiser", "refresh")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        card.body.addLayout(top)
        card.body.addWidget(hint)
        card.body.addWidget(self.banner)
        card.body.addWidget(self.table, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)

    def refresh(self) -> None:
        query = self._search.text().strip()
        call_api(self._host, lambda: self._host.api.users(query), self._show, banner=self.banner)

    def users(self) -> list[dict[str, Any]]:
        return self._users

    def patch(self, user: dict[str, Any], **changes: Any) -> None:
        name = user.get("display_name") or user["username"]
        call_api(
            self._host,
            lambda: self._host.api.patch_user(user["id"], **changes),
            lambda _result: self.refresh(),
            banner=self.banner,
            success=f"Compte « {name} » mis à jour.",
        )

    def _show(self, users: list[dict[str, Any]]) -> None:
        self._users = users
        me = self._host.session.user_id
        fill_rows(
            self.table,
            [
                [
                    text_cell(user.get("display_name") or user["username"]),
                    muted_cell(user["discord_id"]),
                    text_cell(""),
                    text_cell(""),
                    text_cell(""),
                    muted_cell(format_datetime(user.get("last_login_at"))),
                ]
                for user in users
            ],
        )
        for row, user in enumerate(users):
            editable = user["id"] != me
            role = QComboBox()
            for value, text in ROLE_CHOICES:
                role.addItem(text, value)
            role.setCurrentIndex(max(role.findData(user["role"]), 0))
            role.setEnabled(editable)
            if not editable:
                role.setToolTip("Tu ne peux pas modifier ton propre compte.")
            role.currentIndexChanged.connect(lambda _i, u=user, c=role: self.patch(u, role=c.currentData()))
            self.table.setCellWidget(row, 2, role)
            self.table.setCellWidget(row, 3, self._systems_button(user, editable))
            banned = QCheckBox()
            banned.setChecked(bool(user["is_banned"]))
            banned.setEnabled(editable)
            banned.toggled.connect(lambda checked, u=user: self.patch(u, is_banned=checked))
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(8, 0, 8, 0)
            holder_layout.addWidget(banned)
            self.table.setCellWidget(row, 4, holder)
            if user["is_banned"]:
                self.table.item(row, 0).setForeground(QColor(COLORS.danger))

    def _systems_button(self, user: dict[str, Any], editable: bool) -> QToolButton:
        widget = QToolButton()
        widget.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        role = Role(user["role"])
        granted = [system for system in self._systems if system in (user.get("permissions") or [])]
        if role is Role.ADMIN:
            widget.setText("Tous")
            widget.setEnabled(False)
            return widget
        if role is Role.PLAYER:
            widget.setText("—")
            widget.setToolTip("Passe ce compte en éditeur pour lui confier des systèmes.")
            widget.setEnabled(False)
            return widget
        widget.setText(", ".join(self._systems[s] for s in granted) or "Aucun : à choisir")
        menu = QMenu(widget)
        for system, name in self._systems.items():
            action = QAction(name, menu)
            action.setCheckable(True)
            action.setChecked(system in granted)
            action.toggled.connect(lambda checked, u=user, s=system: self._toggle_system(u, s, checked))
            menu.addAction(action)
        widget.setMenu(menu)
        widget.setEnabled(editable)
        return widget

    def _toggle_system(self, user: dict[str, Any], system: str, checked: bool) -> None:
        current = set(user.get("permissions") or [])
        current = current | {system} if checked else current - {system}
        self.patch(user, permissions=sorted(current))
