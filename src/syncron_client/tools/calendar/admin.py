"""Gestion du calendrier : liste des événements et fiche (création, modification, suppression)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from PySide6.QtCore import QDate, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import ToolHost
from syncron_client.tools.calendar.model import CATEGORIES, Event
from syncron_client.ui import icons
from syncron_client.ui.entity_list import EntityList
from syncron_client.ui.format import WEEKDAYS_SHORT
from syncron_client.ui.widgets import Banner, Card, button, label

PAST_DAYS = 60
FUTURE_DAYS = 330  # le serveur limite une requête à 400 jours


def _date_edit() -> QDateEdit:
    field = QDateEdit()
    field.setCalendarPopup(True)
    field.setDisplayFormat("dd/MM/yyyy")
    return field


def _time_edit() -> QTimeEdit:
    field = QTimeEdit()
    field.setDisplayFormat("HH:mm")
    return field


def _local(day: QDate, moment: QTime) -> datetime:
    return datetime.combine(date(day.year(), day.month(), day.day()), time(moment.hour(), moment.minute())).astimezone()


class EventsAdmin(QWidget):
    changed = Signal()

    def __init__(self, host: ToolHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._events: dict[str, Event] = {}
        self._current: str | None = None
        self._dirty = False
        self._loading = False

        self.list = EntityList("ÉVÉNEMENTS", "Rechercher un événement…")
        self.list.selected.connect(self._on_selected)
        self.list.setMinimumWidth(280)

        self.banner = Banner("danger")
        self.banner.hide()
        self.heading = label("", "title")
        new_button = button("Nouvel événement", "plus")
        new_button.clicked.connect(lambda: self._confirm_leave() and self.load(None))
        self.title_field = QLineEdit()
        self.title_field.setMaxLength(120)
        self.title_field.setPlaceholderText("Réunion du conseil, assaut, marché…")
        self.category_field = QComboBox()
        for category in CATEGORIES.values():
            self.category_field.addItem(icons.icon("circle", category.color, 12), category.label, category.id)
        self.all_day = QCheckBox("Toute la journée")
        self.start_date = _date_edit()
        self.start_time = _time_edit()
        self.has_end = QCheckBox("Fin")
        self.end_date = _date_edit()
        self.end_time = _time_edit()
        self.location_field = QLineEdit()
        self.location_field.setMaxLength(120)
        self.location_field.setPlaceholderText("Capitale, frontière, Discord vocal…")
        self.description_field = QPlainTextEdit()
        self.description_field.setPlaceholderText("Détails, consignes, équipement…")
        self.description_field.setMinimumHeight(110)
        self.notify_field = QCheckBox("Prévenir tout le pays (message dans la messagerie)")

        start_row = QHBoxLayout()
        start_row.addWidget(self.start_date, 1)
        start_row.addWidget(self.start_time)
        start_row.addWidget(self.all_day)
        end_row = QHBoxLayout()
        end_row.addWidget(self.has_end)
        end_row.addWidget(self.end_date, 1)
        end_row.addWidget(self.end_time)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.addRow("Titre", self.title_field)
        form.addRow("Catégorie", self.category_field)
        form.addRow("Début", start_row)
        form.addRow("", end_row)
        form.addRow("Lieu", self.location_field)
        form.addRow("Description", self.description_field)
        form.addRow("", self.notify_field)

        self.delete_button = button("Supprimer", "trash", "ghost")
        self.delete_button.setStyleSheet("QPushButton { color: #f2555a; }")
        self.delete_button.clicked.connect(self._delete)
        self.save_button = button("Enregistrer", "save", "primary")
        self.save_button.clicked.connect(self.save)
        actions = QHBoxLayout()
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        header = QHBoxLayout()
        header.addWidget(self.heading, 1)
        header.addWidget(new_button)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(14)
        inner_layout.addLayout(header)
        inner_layout.addWidget(self.banner)
        inner_layout.addLayout(form)
        inner_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        form_card = Card(padding=20, spacing=14)
        form_card.body.addWidget(scroll, 1)
        form_card.body.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        splitter.addWidget(self.list)
        splitter.addWidget(form_card)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 860])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self.all_day.toggled.connect(self._update_fields)
        self.has_end.toggled.connect(self._update_fields)
        for signal in (
            self.title_field.textChanged,
            self.category_field.currentIndexChanged,
            self.all_day.toggled,
            self.start_date.dateChanged,
            self.start_time.timeChanged,
            self.has_end.toggled,
            self.end_date.dateChanged,
            self.end_time.timeChanged,
            self.location_field.textChanged,
            self.description_field.textChanged,
        ):
            signal.connect(self._mark_dirty)
        self.load(None)

    # -- cycle ------------------------------------------------------------------------------

    @property
    def current_id(self) -> str | None:
        return self._current

    def is_dirty(self) -> bool:
        return self._dirty

    def refresh(self) -> None:
        now = datetime.now().astimezone()
        start, end = now - timedelta(days=PAST_DAYS), now + timedelta(days=FUTURE_DAYS)
        call_api(self._host, lambda: self._host.api.events(start, end), self._show_list)

    def open_key(self, key: str) -> None:
        """« new:AAAA-MM-JJ » : nouvel événement ce jour-là ; sinon l'identifiant d'un événement."""
        if not self._confirm_leave():
            return
        if key.startswith("new:"):
            self.load(None, date.fromisoformat(key.removeprefix("new:")))
        elif key in self._events:
            self.load(key)
            self.list.select(key, emit=False)
        else:
            call_api(self._host, lambda: self._host.api.event(key), self._load_remote)

    def load(self, event_id: str | None, day: date | None = None) -> None:
        event = self._events.get(event_id) if event_id else None
        self._current = event.id if event else None
        self._loading = True
        self.banner.hide()
        self.heading.setText(event.title if event else "Nouvel événement")
        self.title_field.setText(event.title if event else "")
        self.category_field.setCurrentIndex(
            max(self.category_field.findData(event.category.id if event else "event"), 0)
        )
        self.location_field.setText(event.location if event else "")
        self.description_field.setPlainText(event.description if event else "")
        self.all_day.setChecked(event.all_day if event else False)
        start = event.starts_at if event else datetime.combine(day or date.today(), time(21, 0))
        self.start_date.setDate(QDate(start.year, start.month, start.day))
        self.start_time.setTime(QTime(start.hour, start.minute))
        end = event.ends_at if event else None
        self.has_end.setChecked(end is not None)
        end = end or start + timedelta(hours=2)
        self.end_date.setDate(QDate(end.year, end.month, end.day))
        self.end_time.setTime(QTime(end.hour, end.minute))
        self.notify_field.setChecked(event is None)
        self.delete_button.setVisible(event is not None)
        self._loading = False
        self._dirty = False
        self._update_fields()
        if event is None:
            self.list.clear_selection()
            self.title_field.setFocus()

    def period(self) -> tuple[datetime, datetime | None]:
        all_day = self.all_day.isChecked()
        starts_at = _local(self.start_date.date(), QTime(0, 0) if all_day else self.start_time.time())
        ends_at = None
        if self.has_end.isChecked():
            ends_at = _local(self.end_date.date(), QTime(23, 59) if all_day else self.end_time.time())
        return starts_at, ends_at

    def payload(self) -> dict[str, Any]:
        all_day = self.all_day.isChecked()
        starts_at, ends_at = self.period()
        return {
            "title": self.title_field.text().strip(),
            "category": self.category_field.currentData(),
            "location": self.location_field.text().strip(),
            "description": self.description_field.toPlainText().strip(),
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat() if ends_at else None,
            "all_day": all_day,
            "notify": self.notify_field.isChecked(),
        }

    def save(self) -> None:
        payload = self.payload()
        if not payload["title"]:
            self.banner.set_text("Le titre est obligatoire.")
            self.banner.show()
            return
        starts_at, ends_at = self.period()
        if ends_at is not None and ends_at < starts_at:
            self.banner.set_text("La fin doit être après le début.")
            self.banner.show()
            return
        event_id = self._current
        api = self._host.api
        request = (lambda: api.update_event(event_id, payload)) if event_id else (lambda: api.create_event(payload))

        def saved(raw: dict[str, Any]) -> None:
            event = Event.from_api(raw)
            self._events[event.id] = event
            self._current = event.id
            self._dirty = False
            self.heading.setText(event.title)
            self.delete_button.show()
            self.notify_field.setChecked(False)
            if payload["notify"]:
                self._host.notifications.poll()
            self.changed.emit()
            self.refresh()

        call_api(self._host, request, saved, banner=self.banner, success=f"« {payload['title']} » enregistré.")

    def delete(self, notify: bool) -> None:
        event_id = self._current
        if event_id is None:
            return

        def deleted(_result: Any) -> None:
            self._events.pop(event_id, None)
            self._dirty = False
            self.load(None)
            if notify:
                self._host.notifications.poll()
            self.changed.emit()
            self.refresh()

        call_api(
            self._host,
            lambda: self._host.api.delete_event(event_id, notify),
            deleted,
            banner=self.banner,
            success="Événement supprimé.",
        )

    # -- interne ----------------------------------------------------------------------------

    def _show_list(self, raw_events: list[dict[str, Any]]) -> None:
        events = [Event.from_api(raw) for raw in raw_events]
        self._events = {event.id: event for event in events}
        entries = []
        for event in sorted(events, key=lambda e: e.starts_at, reverse=True):
            when = f"{WEEKDAYS_SHORT[event.starts_at.weekday()]} {event.starts_at:%d/%m/%Y}"
            if not event.all_day:
                when += f" · {event.starts_at:%H:%M}"
            entries.append(
                (
                    event.id,
                    event.title,
                    f"{when} · {event.category.label}",
                    icons.icon("calendar", event.category.color, 28),
                )
            )
        self.list.set_entries(entries, keep=self._current)

    def _load_remote(self, raw: dict[str, Any]) -> None:
        event = Event.from_api(raw)
        self._events[event.id] = event
        self.load(event.id)

    def _on_selected(self, key: str) -> None:
        if key == self._current:
            return
        if self._confirm_leave():
            self.load(key)
        elif self._current:
            self.list.select(self._current, emit=False)
        else:
            self.list.clear_selection()

    def _delete(self) -> None:
        event = self._events.get(self._current or "")
        if event is None:
            return
        box = QMessageBox(QMessageBox.Icon.Question, "Supprimer", f"Supprimer « {event.title} » ?", parent=self)
        notify = box.addButton("Supprimer et prévenir le pays", QMessageBox.ButtonRole.AcceptRole)
        quiet = box.addButton("Supprimer sans prévenir", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() in (notify, quiet):
            self.delete(box.clickedButton() is notify)

    def _confirm_leave(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(self, "Modifications non enregistrées", "Abandonner les modifications en cours ?")
        return answer == QMessageBox.StandardButton.Yes

    def _mark_dirty(self, *_args) -> None:
        if not self._loading:
            self._dirty = True

    def _update_fields(self, *_args) -> None:
        all_day = self.all_day.isChecked()
        self.start_time.setEnabled(not all_day)
        self.end_date.setEnabled(self.has_end.isChecked())
        self.end_time.setEnabled(self.has_end.isChecked() and not all_day)
        self.has_end.setText("Jusqu'au" if all_day else "Fin")
