"""Gestion du Craft : export et import du catalogue (JSON), avec analyse avant application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from syncron_client.tools.craft.admin.context import CraftAdminContext
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Banner, Card, SegmentedControl, button, label


def _scroll(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


class ImportExportView(QWidget):
    def __init__(self, context: CraftAdminContext, parent: QWidget | None = None) -> None:
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
