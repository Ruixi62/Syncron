"""Administration › NationsGlory : état de la connexion à l'API publique, appels, historique des réponses.

Prépare l'exploitation des données du serveur (alertes, pays, notations…) : l'équipe vérifie
que la clé fonctionne, appelle une route et lit la réponse brute avant qu'un outil ne s'en serve.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.ui.format import format_datetime
from syncron_client.ui.tables import KEY_ROLE, fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.widgets import Banner, Card, Chip, button, compact_combo, label

KINDS = {
    "playercount": ("Nombre de joueurs", ()),
    "country": ("Pays", ("server", "country")),
    "countries": ("Liste des pays", ("server",)),
    "notations": ("Notations", ("server", "country", "week")),
    "mmr": ("MMR", ("server",)),
    "hdv": ("HDV (hôtel des ventes)", ("server",)),
    "planning": ("Planning", ("server", "month", "year")),
    "user": ("Joueur", ("username",)),
}
MAX_SHOWN = 200_000


def pretty(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(text) > MAX_SHOWN:
        return text[:MAX_SHOWN] + f"\n… (réponse tronquée : {len(text) // 1024} Ko au total)"
    return text


class NationsGloryView(QWidget):
    def __init__(self, host: ToolHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._status: dict[str, Any] | None = None
        self.last_result: dict[str, Any] | None = None

        self.state_chip = Chip("", "neutral")
        self.state_text = label("", "muted", wrap=True)
        self.setup_hint = label(
            "À régler sur le serveur, dans .env : SYNCRON_NG_API_KEY (clé de l'API), SYNCRON_NG_SERVER (blue…), "
            "SYNCRON_NG_COUNTRY (identifiant du pays), puis docker compose up -d. La clé ne quitte jamais le "
            "serveur.",
            "faint",
            wrap=True,
        )
        state = Card(padding=18, spacing=8)
        head = QHBoxLayout()
        head.addWidget(label("CONNEXION", "overline"), 1)
        head.addWidget(self.state_chip)
        state.body.addLayout(head)
        state.body.addWidget(self.state_text)
        state.body.addWidget(self.setup_hint)

        self.banner = Banner("danger")
        self.banner.hide()
        self.kind = compact_combo(min_chars=14)
        for kind, (title, _fields) in KINDS.items():
            self.kind.addItem(title, kind)
        self.kind.currentIndexChanged.connect(self._update_fields)
        self.server = QLineEdit()
        self.server.setPlaceholderText("serveur du pays")
        self.country = QLineEdit()
        self.country.setPlaceholderText("pays du serveur")
        self.username = QLineEdit()
        self.username.setPlaceholderText("pseudo")
        self.username.setMaxLength(16)
        self.week = QSpinBox()
        self.week.setRange(0, 999_999)
        self.week.setSpecialValueText("semaine en cours")
        self.month = QSpinBox()
        self.month.setRange(1, 12)
        self.month.setValue(date.today().month)
        self.month.setPrefix("mois ")
        self.year = QSpinBox()
        self.year.setRange(2010, 2100)
        self.year.setValue(date.today().year)
        self.refresh_box = QCheckBox("Ignorer le cache")
        self.call_button = button("Appeler", "play", "primary")
        self.call_button.clicked.connect(self.call)
        self._fields = {
            "server": self.server,
            "country": self.country,
            "username": self.username,
            "week": self.week,
            "month": self.month,
            "year": self.year,
        }
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.addWidget(self.kind, 0, 0, 1, 2)
        form.addWidget(self.server, 1, 0)
        form.addWidget(self.country, 1, 1)
        form.addWidget(self.username, 2, 0)
        form.addWidget(self.week, 2, 1)
        form.addWidget(self.month, 3, 0)
        form.addWidget(self.year, 3, 1)
        call_row = QHBoxLayout()
        call_row.addWidget(self.refresh_box)
        call_row.addStretch(1)
        call_row.addWidget(self.call_button)
        request = Card(padding=18, spacing=10)
        request.body.addWidget(label("APPEL", "overline"))
        request.body.addWidget(self.banner)
        request.body.addLayout(form)
        request.body.addLayout(call_row)

        self.history = make_table(["Quand", "Route", "Statut", "Taille", "Durée"], 1)
        self.history.itemSelectionChanged.connect(self._history_selected)
        history = Card(padding=18, spacing=8)
        history.body.addWidget(label("HISTORIQUE", "overline"))
        history.body.addWidget(self.history, 1)

        self.result_title = label("Aucune réponse affichée.", "faint")
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPixelSize(12)
        self.result.setFont(mono)
        result = Card(padding=18, spacing=8)
        result.body.addWidget(label("RÉPONSE", "overline"))
        result.body.addWidget(self.result_title)
        result.body.addWidget(self.result, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        left_layout.addWidget(state)
        left_layout.addWidget(request)
        left_layout.addWidget(history, 1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        splitter.addWidget(result)
        splitter.setSizes([460, 560])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self._update_fields()

    @property
    def status(self) -> dict[str, Any] | None:
        return self._status

    def refresh(self) -> None:
        call_api(self._host, self._host.api.nationsglory_status, self._show_status)
        call_api(self._host, lambda: self._host.api.nationsglory_snapshots(limit=50), self._show_history)

    def payload(self) -> dict[str, Any]:
        kind = self.kind.currentData()
        fields = KINDS[kind][1]
        data: dict[str, Any] = {"kind": kind, "refresh": self.refresh_box.isChecked()}
        if "server" in fields:
            data["server"] = self.server.text().strip().lower()
        if "country" in fields:
            data["country"] = self.country.text().strip().lower()
        if "username" in fields:
            data["username"] = self.username.text().strip()
        if "week" in fields and self.week.value():
            data["week"] = self.week.value()
        if "month" in fields:
            data["month"] = self.month.value()
            data["year"] = self.year.value()
        return data

    def call(self) -> None:
        payload = self.payload()

        def done(result: dict[str, Any]) -> None:
            self._show_result(result)
            call_api(self._host, lambda: self._host.api.nationsglory_snapshots(limit=50), self._show_history)

        def failed(_error: Exception) -> None:
            call_api(self._host, lambda: self._host.api.nationsglory_snapshots(limit=50), self._show_history)

        call_api(self._host, lambda: self._host.api.nationsglory_fetch(payload), done, self.banner, on_failed=failed)

    def _show_status(self, status: dict[str, Any]) -> None:
        self._status = status
        configured = status["configured"]
        self.state_chip.set_content(
            "Configurée" if configured else "Non configurée",
            "success" if configured else "warning",
            "check" if configured else "info",
        )
        target = f"{status['server'] or '—'} / {status['country'] or '—'}"
        self.state_text.setText(
            f"{status['api_url']} · pays : {target} · cache : {status['cache_seconds']} s · "
            f"en-tête : {status['auth_header']}"
        )
        self.setup_hint.setVisible(not configured or not (status["server"] and status["country"]))
        self.server.setPlaceholderText(status["server"] or "serveur du pays")
        self.country.setPlaceholderText(status["country"] or "pays du serveur")
        self.call_button.setEnabled(configured)

    def _show_history(self, rows: list[dict[str, Any]]) -> None:
        cells = []
        for row in rows:
            route = text_cell(row["target"] or row["kind"], key=str(row["id"]))
            ok = row["status"] == 200
            cells.append(
                [
                    muted_cell(format_datetime(row["fetched_at"])),
                    route,
                    text_cell("OK" if ok else f"{row['status']} · {row['error']}"),
                    muted_cell(f"{max(row['size_bytes'] // 1024, 0)} Ko" if ok else "—"),
                    muted_cell(f"{row['duration_ms']} ms" if ok else "—"),
                ]
            )
        fill_rows(self.history, cells)

    def _history_selected(self) -> None:
        items = self.history.selectedItems()
        key = next((item.data(KEY_ROLE) for item in items if item.data(KEY_ROLE)), None)
        if key is None:
            return
        call_api(self._host, lambda: self._host.api.nationsglory_snapshot(int(key)), self._show_result)

    def _show_result(self, result: dict[str, Any]) -> None:
        self.last_result = result
        origin = " (cache)" if result.get("from_cache") else ""
        if result["status"] == 200:
            self.result_title.setText(f"{result['target']}{origin} · {format_datetime(result['fetched_at'])}")
            self.result.setPlainText(pretty(result.get("payload")))
        else:
            self.result_title.setText(f"{result['target']} · erreur {result['status']}")
            self.result.setPlainText(result.get("error") or "")

    def _update_fields(self, *_args) -> None:
        fields = KINDS[self.kind.currentData()][1]
        for name, widget in self._fields.items():
            widget.setVisible(name in fields)
