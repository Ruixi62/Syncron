"""Vues du mode admin : tableau de bord, utilisateurs, journal, import / export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from syncron_client.tools.admin.common import AdminContext, format_datetime
from syncron_client.ui import icons
from syncron_client.ui.tables import fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Banner, Card, Chip, SearchField, SegmentedControl, StatTile, button, label

ROLE_CHOICES = (("player", "Joueur"), ("editor", "Éditeur"), ("admin", "Administrateur"))
ACTION_ICONS = {
    "item": "box",
    "station": "station",
    "skill": "award",
    "catalog": "database",
    "user": "users",
}


def _scroll(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


# -- tableau de bord ---------------------------------------------------------------------


class DashboardView(QWidget):
    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self._tiles = {
            "items": StatTile("box", "Objets", "accent"),
            "crafted": StatTile("hammer", "Recettes", "success"),
            "stations": StatTile("station", "Ateliers", "info"),
            "skills": StatTile("award", "Compétences", "violet"),
            "users": StatTile("users", "Comptes", "warning"),
        }
        grid = QGridLayout()
        grid.setSpacing(12)
        for column, tile in enumerate(self._tiles.values()):
            grid.addWidget(tile, 0, column)
            grid.setColumnStretch(column, 1)

        self._todo = Card(padding=18, spacing=10)
        self._todo.body.addWidget(label("À COMPLÉTER", "overline"))
        self._todo_rows = QVBoxLayout()
        self._todo_rows.setSpacing(8)
        self._todo.body.addLayout(self._todo_rows)
        self._todo.body.addStretch(1)

        self._activity = Card(padding=18, spacing=10)
        self._activity.body.addWidget(label("ACTIVITÉ RÉCENTE", "overline"))
        self._activity_table = make_table(["Quand", "Qui", "Modification"], 2)
        self._activity.body.addWidget(self._activity_table, 1)

        self._revision = label("", "faint")
        lower = QHBoxLayout()
        lower.setSpacing(16)
        lower.addWidget(self._todo, 2)
        lower.addWidget(self._activity, 5)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addLayout(grid)
        layout.addLayout(lower, 1)
        layout.addWidget(self._revision)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(content))

    def refresh(self) -> None:
        self.ctx.call(self.ctx.api.dashboard, self._show)

    def _show(self, data: dict[str, Any]) -> None:
        self._tiles["items"].set_value(str(data["items_total"]), f"{data['items_raw']} ressource(s) primaire(s)")
        self._tiles["crafted"].set_value(str(data["items_crafted"]), "objets craftables")
        self._tiles["stations"].set_value(str(data["stations"]))
        self._tiles["skills"].set_value(str(data["skills"]))
        roles = data["users_by_role"]
        self._tiles["users"].set_value(
            str(data["users_total"]), f"{roles.get('editor', 0)} éditeur(s) · {roles.get('admin', 0)} admin(s)"
        )
        while self._todo_rows.count():
            widget = self._todo_rows.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        todo = (
            ("Objets sans image", data["items_without_image"], "image"),
            ("Recettes sans temps de fabrication", data["crafted_without_time"], "clock"),
            ("Objets sans catégorie", data["items_without_category"], "layers"),
        )
        for text, count, icon_name in todo:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            glyph = QLabel()
            glyph.setPixmap(icons.pixmap(icon_name, COLORS.text_faint, 16))
            row_layout.addWidget(glyph)
            row_layout.addWidget(label(text, "muted"), 1)
            row_layout.addWidget(Chip(str(count), "warning" if count else "success"))
            self._todo_rows.addWidget(row)
        rows = []
        for entry in data["recent"]:
            what = text_cell(entry["summary"] or entry["action"])
            what.setIcon(icons.icon(ACTION_ICONS.get(entry["entity_type"], "edit"), COLORS.text_faint, 16))
            rows.append([muted_cell(format_datetime(entry["created_at"])), text_cell(entry["username"] or "—"), what])
        fill_rows(self._activity_table, rows)
        self._revision.setText(
            f"Catalogue : révision {data['revision']} · dernière modification {format_datetime(data['updated_at'])}"
        )


# -- utilisateurs --------------------------------------------------------------------------


class UsersView(QWidget):
    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self._users: list[dict[str, Any]] = []
        self._search = SearchField("Rechercher un pseudo ou un ID Discord…")
        self._search.returnPressed.connect(self.refresh)
        self._banner = Banner("danger")
        self._banner.hide()
        self._table = make_table(["Compte", "ID Discord", "Rôle", "Suspendu", "Dernière connexion"], 0)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(2, 190)
        hint = label(
            "Les éditeurs gèrent le catalogue ; les administrateurs gèrent aussi les comptes et peuvent "
            "remplacer tout le catalogue. Suspendre un compte coupe immédiatement ses sessions.",
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
        card.body.addWidget(self._banner)
        card.body.addWidget(self._table, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)

    def refresh(self) -> None:
        query = self._search.text().strip()
        self.ctx.call(lambda: self.ctx.api.users(query), self._show, banner=self._banner)

    def users(self) -> list[dict[str, Any]]:
        return self._users

    def _show(self, users: list[dict[str, Any]]) -> None:
        self._users = users
        me = (self.ctx.host.session.user or {}).get("id")
        fill_rows(
            self._table,
            [
                [
                    text_cell(user.get("display_name") or user["username"]),
                    muted_cell(user["discord_id"]),
                    text_cell(""),
                    text_cell(""),
                    muted_cell(format_datetime(user.get("last_login_at"))),
                ]
                for user in users
            ],
        )
        for row, user in enumerate(users):
            role = QComboBox()
            for value, text in ROLE_CHOICES:
                role.addItem(text, value)
            role.setCurrentIndex(max(role.findData(user["role"]), 0))
            banned = QCheckBox()
            banned.setChecked(bool(user["is_banned"]))
            editable = user["id"] != me
            role.setEnabled(editable)
            banned.setEnabled(editable)
            if not editable:
                role.setToolTip("Tu ne peux pas modifier ton propre compte.")
            role.currentIndexChanged.connect(lambda _i, u=user, c=role: self._patch(u, role=c.currentData()))
            banned.toggled.connect(lambda checked, u=user: self._patch(u, is_banned=checked))
            self._table.setCellWidget(row, 2, role)
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(8, 0, 8, 0)
            holder_layout.addWidget(banned)
            self._table.setCellWidget(row, 3, holder)
            if user["is_banned"]:
                self._table.item(row, 0).setForeground(QColor(COLORS.danger))

    def _patch(self, user: dict[str, Any], **changes: Any) -> None:
        name = user.get("display_name") or user["username"]
        self.ctx.call(
            lambda: self.ctx.api.patch_user(user["id"], **changes),
            lambda _result: self.refresh(),
            banner=self._banner,
            success=f"Compte « {name} » mis à jour.",
        )


# -- journal --------------------------------------------------------------------------------


class AuditView(QWidget):
    PAGE = 50

    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self._entries: list[dict[str, Any]] = []
        self._table = make_table(["Quand", "Qui", "Modification", "Élément"], 2)
        self._more = button("Charger plus", "history")
        self._more.clicked.connect(self._load_more)
        card = Card(padding=16, spacing=10)
        card.body.addWidget(self._table, 1)
        card.body.addWidget(self._more, 0, Qt.AlignmentFlag.AlignHCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)

    def refresh(self) -> None:
        self._entries = []
        self.ctx.call(lambda: self.ctx.api.audit(self.PAGE), self._append)

    def entries(self) -> list[dict[str, Any]]:
        return self._entries

    def _load_more(self) -> None:
        before = self._entries[-1]["id"] if self._entries else None
        self.ctx.call(lambda: self.ctx.api.audit(self.PAGE, before), self._append)

    def _append(self, entries: list[dict[str, Any]]) -> None:
        self._entries += entries
        self._more.setEnabled(len(entries) == self.PAGE)
        rows = []
        for entry in self._entries:
            what = text_cell(entry["summary"] or entry["action"])
            what.setIcon(icons.icon(ACTION_ICONS.get(entry["entity_type"], "edit"), COLORS.text_faint, 16))
            rows.append(
                [
                    muted_cell(format_datetime(entry["created_at"])),
                    text_cell(entry["username"] or "—"),
                    what,
                    muted_cell(f"{entry['entity_type']} · {entry['entity_id']}"),
                ]
            )
        fill_rows(self._table, rows)


# -- import / export ----------------------------------------------------------------------------


class ImportExportView(QWidget):
    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self._document: dict[str, Any] | None = None
        self._analysed_mode: str | None = None

        export = Card(padding=20, spacing=10)
        export.body.addWidget(label("EXPORTER", "overline"))
        export.body.addWidget(
            label(
                "Télécharge tout le catalogue au format JSON (sauvegarde, modifications en masse, partage).",
                "muted",
                wrap=True,
            )
        )
        export_button = button("Exporter le catalogue…", "download", "primary")
        export_button.clicked.connect(self._export)
        export.body.addWidget(export_button, 0, Qt.AlignmentFlag.AlignLeft)

        importer = Card(padding=20, spacing=12)
        importer.body.addWidget(label("IMPORTER", "overline"))
        importer.body.addWidget(
            label(
                "Fusion : ajoute et met à jour, ne supprime rien. Remplacement (administrateurs) : le catalogue "
                "devient exactement le fichier. Le fichier est d'abord analysé : rien n'est écrit avant "
                "« Appliquer ».",
                "muted",
                wrap=True,
            )
        )
        self._file_label = label("Aucun fichier choisi.", "faint")
        choose = button("Choisir un fichier…", "folder")
        choose.clicked.connect(self._choose)
        self._mode = SegmentedControl([("Fusion", "layers"), ("Remplacement", "refresh")])
        self._mode.currentChanged.connect(self._mode_changed)
        if not context.is_admin:
            self._mode.setEnabled(False)
            self._mode.setToolTip("Le remplacement total est réservé aux administrateurs.")
        self._analyse = button("Analyser", "search")
        self._analyse.clicked.connect(lambda: self._run(dry_run=True))
        self._apply = button("Appliquer", "check", "primary")
        self._apply.clicked.connect(lambda: self._run(dry_run=False))
        self._analyse.setEnabled(False)
        self._apply.setEnabled(False)
        self._banner = Banner("danger")
        self._banner.hide()
        self._report = label("", wrap=True)
        self._report.setTextFormat(Qt.TextFormat.RichText)
        row = QHBoxLayout()
        row.addWidget(choose)
        row.addWidget(self._file_label, 1)
        actions = QHBoxLayout()
        actions.addWidget(self._mode)
        actions.addStretch(1)
        actions.addWidget(self._analyse)
        actions.addWidget(self._apply)
        importer.body.addLayout(row)
        importer.body.addLayout(actions)
        importer.body.addWidget(self._banner)
        importer.body.addWidget(self._report)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(export)
        layout.addWidget(importer)
        layout.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(content))

    @property
    def report_text(self) -> str:
        return self._report.text()

    def _export(self) -> None:
        directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le catalogue", str(Path(directory) / "syncron-catalogue.json"), "JSON (*.json)"
        )
        if path:
            self.export_to(Path(path))

    def export_to(self, path: Path) -> None:
        def save(content: bytes) -> None:
            path.write_bytes(content)
            self.ctx.host.notify(f"Catalogue exporté : {path.name}")

        self.ctx.call(self.ctx.api.export_catalog, save, banner=self._banner)

    def _choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importer un catalogue", "", "JSON (*.json)")
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> None:
        self._banner.hide()
        self._report.clear()
        self._apply.setEnabled(False)
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            self._document = None
            self._analyse.setEnabled(False)
            self._banner.set_text(f"Fichier illisible : {exc}")
            self._banner.show()
            return
        self._document = document if isinstance(document, dict) else None
        self._file_label.setText(path.name)
        self._analyse.setEnabled(self._document is not None)

    def set_mode(self, mode: str) -> None:
        self._mode.set_current_index(1 if mode == "replace" else 0)

    def _mode_changed(self, _index: int) -> None:
        self._apply.setEnabled(False)

    def _current_mode(self) -> str:
        return "replace" if self._mode.current_index() == 1 else "merge"

    def _run(self, dry_run: bool) -> None:
        if self._document is None:
            return
        document, mode = self._document, self._current_mode()

        def done(result: dict[str, Any]) -> None:
            self._report.setText(_import_report(result))
            if dry_run:
                self._analysed_mode = mode
                self._apply.setEnabled(any(_changed(result[s]) for s in ("items", "stations", "skills")))
            else:
                self._apply.setEnabled(False)

        self.ctx.call(
            lambda: self.ctx.api.import_catalog(document, mode, dry_run),
            done,
            banner=self._banner,
            success=None if dry_run else "Import appliqué.",
            sync=not dry_run,
        )


def _changed(section: dict[str, Any]) -> bool:
    return bool(section["added"] or section["updated"] or section["removed"])


def _import_report(result: dict[str, Any]) -> str:
    title = "Analyse (rien n'a été écrit)" if result["dry_run"] else "Import appliqué"
    lines = [f"<b>{title}</b> — révision {result['revision']}"]
    for key, name in (("items", "Objets"), ("stations", "Ateliers"), ("skills", "Compétences")):
        section = result[key]
        parts = [
            f"<span style='color:{COLORS.success}'>+{len(section['added'])}</span>",
            f"<span style='color:{COLORS.info}'>~{len(section['updated'])}</span>",
            f"<span style='color:{COLORS.danger}'>−{len(section['removed'])}</span>",
            f"<span style='color:{COLORS.text_faint}'>{section['unchanged']} inchangé(s)</span>",
        ]
        lines.append(f"{name} : " + " · ".join(parts))
        if section["removed"]:
            lines.append(f"<span style='color:{COLORS.danger}'>Supprimés : {', '.join(section['removed'][:20])}</span>")
    for warning in result.get("warnings", []):
        lines.append(f"<span style='color:{COLORS.warning}'>⚠ {warning['message']}</span>")
    return "<br>".join(lines)
