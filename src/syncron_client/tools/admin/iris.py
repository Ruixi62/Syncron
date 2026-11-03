"""Administration › NationsGlory › Carte Iris : état de la collecte d'iris.nationsglory.fr, relances."""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.ui.format import format_datetime
from syncron_client.ui.tables import fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Banner, Card, Chip, StatTile, button, label

KIND_LABELS = {
    "territories": "Territoires (claims)",
    "atlas": "Atlas (pays, biomes, régions)",
    "frontiers": "Frontières",
    "regions": "Régions",
    "weather": "Météo (alertes)",
    "state": "Heure du jeu",
    "members": "Membres des pays",
}
JOBS = (
    ("weather", "Météo", "refresh"),
    ("map", "Carte", "map"),
    ("members", "Membres", "users"),
)


class IrisView(QWidget):
    def __init__(self, host: ToolHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self.status: dict[str, Any] | None = None

        self.state_chip = Chip("", "neutral")
        self.state_text = label("", "muted", wrap=True)
        hint = label(
            "Réglages du serveur (.env) : SYNCRON_IRIS_ENABLED, SYNCRON_IRIS_WEATHER_SECONDS (60), "
            "SYNCRON_IRIS_MAP_MINUTES (30), SYNCRON_IRIS_MEMBERS_HOURS (12). Un seul processus interroge "
            "le site, avec une pause entre deux pays.",
            "faint",
            wrap=True,
        )
        state = Card(padding=18, spacing=8)
        head = QHBoxLayout()
        head.addWidget(label("COLLECTE", "overline"), 1)
        head.addWidget(self.state_chip)
        state.body.addLayout(head)
        state.body.addWidget(self.state_text)
        state.body.addWidget(hint)

        self.tiles = {
            "active": StatTile("bell", "Événements en cours", "warning"),
            "total": StatTile("history", "Événements suivis (total)"),
        }
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        for tile in self.tiles.values():
            tiles.addWidget(tile, 1)

        self.banner = Banner("danger")
        self.banner.hide()
        self.buttons = {}
        actions = QHBoxLayout()
        actions.addWidget(label("Mettre à jour maintenant :", "muted"))
        for job, text, icon_name in JOBS:
            go = button(text, icon_name)
            go.clicked.connect(lambda _checked=False, j=job: self.refresh_job(j))
            self.buttons[job] = go
            actions.addWidget(go)
        actions.addStretch(1)

        self.table = make_table(["Donnée", "Dernière réponse", "Taille", "Dernier essai"], 0)
        data = Card(padding=18, spacing=10)
        data.body.addWidget(label("DONNÉES GARDÉES", "overline"))
        data.body.addWidget(self.banner)
        data.body.addLayout(actions)
        data.body.addWidget(self.table, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(state)
        layout.addLayout(tiles)
        layout.addWidget(data, 1)

    def refresh(self) -> None:
        call_api(self._host, self._host.api.iris_status, self.show_status, self.banner)

    def refresh_job(self, job: str) -> None:
        def done(result: dict[str, Any]) -> None:
            self._host.notify(result["detail"])
            self.refresh()

        call_api(self._host, lambda: self._host.api.iris_refresh(job), done, self.banner)

    def show_status(self, status: dict[str, Any]) -> None:
        self.status = status
        enabled = status["enabled"]
        self.state_chip.set_content("Active" if enabled else "Désactivée", "success" if enabled else "warning")
        self.state_text.setText(
            f"{status['url']} · monde {status['world']} · météo toutes les {status['weather_seconds']} s · "
            f"carte toutes les {status['map_minutes']} min · membres toutes les {status['members_hours']} h"
        )
        for button_ in self.buttons.values():
            button_.setEnabled(enabled)
        self.tiles["active"].set_value(str(status["events_active"]), "météorites, failles, volcans…")
        self.tiles["total"].set_value(str(status["events_total"]), "depuis la mise en route")
        rows = []
        for kind in status["kinds"]:
            error = kind["error"]
            fetched = format_datetime(kind["fetched_at"]) if kind["fetched_at"] else "jamais"
            result = text_cell(fetched if not error else f"{fetched} · erreur : {error}")
            if error:
                result.setForeground(QColor(COLORS.danger))
            rows.append(
                [
                    text_cell(KIND_LABELS.get(kind["kind"], kind["kind"])),
                    result,
                    muted_cell(f"{kind['size_bytes'] // 1024} Ko" if kind["fetched_at"] else "—"),
                    muted_cell(format_datetime(kind["attempted_at"]) if kind["attempted_at"] else "—"),
                ]
            )
        fill_rows(self.table, rows)
