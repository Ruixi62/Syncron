"""Gestion du calendrier : liste des fiches et formulaire (horaire, journée, plusieurs jours, répétition)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from PySide6.QtCore import QDate, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
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
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Banner, Card, SegmentedControl, ask, button, choose, compact_combo, label
from syncron_core.recurrence import DAILY, MONTHLY, NONE, WEEKLY, Rule, days_mask, mask_days

TIMED, DAY, SPAN = 0, 1, 2
KINDS = (("Horaire", None), ("Journée", None), ("Plusieurs jours", None))
REPEATS = ((NONE, "Ne se répète pas"), (DAILY, "Chaque jour"), (WEEKLY, "Chaque semaine"), (MONTHLY, "Chaque mois"))
INTERVAL_UNITS = {DAILY: "jour(s)", WEEKLY: "semaine(s)", MONTHLY: "mois"}
DAY_LETTERS = ("L", "M", "M", "J", "V", "S", "D")


def _date_edit() -> QDateEdit:
    field = QDateEdit()
    field.setCalendarPopup(True)
    field.setDisplayFormat("dd/MM/yyyy")
    field.setMinimumWidth(120)
    return field


def _time_edit() -> QTimeEdit:
    field = QTimeEdit()
    field.setDisplayFormat("HH:mm")
    field.setMinimumWidth(76)
    return field


def _to_date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _local(day: date, moment: time) -> datetime:
    return datetime.combine(day, moment).astimezone()


class WeekdayPicker(QWidget):
    """Sept boutons L M M J V S D pour la répétition hebdomadaire."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for weekday, letter in enumerate(DAY_LETTERS):
            day_button = QPushButton(letter)
            day_button.setCheckable(True)
            day_button.setFixedSize(34, 32)
            day_button.setToolTip(WEEKDAYS_SHORT[weekday])
            day_button.setStyleSheet(
                "QPushButton { padding: 0; border-radius: 8px; }"
                f"QPushButton:checked {{ background: {COLORS.accent}; color: {COLORS.accent_text};"
                f" border-color: {COLORS.accent}; }}"
            )
            self._group.addButton(day_button, weekday)
            layout.addWidget(day_button)
        layout.addStretch(1)
        self._group.idToggled.connect(lambda *_args: self.changed.emit())

    def days(self) -> list[int]:
        return [weekday for weekday in range(7) if self._group.button(weekday).isChecked()]

    def set_days(self, days: list[int]) -> None:
        for weekday in range(7):
            self._group.button(weekday).setChecked(weekday in days)


class EventsAdmin(QWidget):
    changed = Signal()

    def __init__(self, host: ToolHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._events: dict[str, Event] = {}
        self._current: str | None = None
        self._dirty = False
        self._loading = False

        self.list = EntityList("ÉVÉNEMENTS", "Rechercher…")
        self.list.selected.connect(self._on_selected)
        self.list.setMinimumWidth(190)

        self.banner = Banner("danger")
        self.banner.hide()
        self.heading = label("", "title")
        self.heading.setWordWrap(True)
        new_button = button("Nouveau", "plus")
        new_button.setToolTip("Nouvel événement")
        new_button.clicked.connect(lambda: self._confirm_leave() and self.load(None))

        self.title_field = QLineEdit()
        self.title_field.setMaxLength(120)
        self.title_field.setPlaceholderText("Réunion du conseil, assaut, marché…")
        self.category_field = compact_combo()
        for category in CATEGORIES.values():
            self.category_field.addItem(icons.icon("circle", category.color, 12), category.label, category.id)

        self.kind = SegmentedControl(list(KINDS))
        self.start_date = _date_edit()
        self.start_time = _time_edit()
        self.has_end = QCheckBox("Fin à")
        self.end_time = _time_edit()
        self.end_date = _date_edit()
        self._timed_row = QWidget()
        timed = QHBoxLayout(self._timed_row)
        timed.setContentsMargins(0, 0, 0, 0)
        timed.addWidget(label("Début à", "muted"))
        timed.addWidget(self.start_time)
        timed.addSpacing(10)
        timed.addWidget(self.has_end)
        timed.addWidget(self.end_time)
        timed.addStretch(1)
        self._span_row = QWidget()
        span = QHBoxLayout(self._span_row)
        span.setContentsMargins(0, 0, 0, 0)
        span.addWidget(label("Jusqu'au", "muted"))
        span.addWidget(self.end_date)
        span.addStretch(1)
        date_row = QHBoxLayout()
        date_row.addWidget(self.start_date)
        date_row.addStretch(1)
        when = QVBoxLayout()
        when.setSpacing(8)
        when.addWidget(self.kind, 0, Qt.AlignmentFlag.AlignLeft)
        when.addLayout(date_row)
        when.addWidget(self._timed_row)
        when.addWidget(self._span_row)

        self.repeat_field = compact_combo()
        for value, text in REPEATS:
            self.repeat_field.addItem(text, value)
        self.interval_field = QSpinBox()
        self.interval_field.setRange(1, 52)
        self.interval_field.setPrefix("toutes les ")
        self.weekdays = WeekdayPicker()
        self.has_until = QCheckBox("Jusqu'au")
        self.until_field = _date_edit()
        self._repeat_details = QWidget()
        details = QVBoxLayout(self._repeat_details)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(8)
        interval_row = QHBoxLayout()
        interval_row.addWidget(self.interval_field)
        interval_row.addStretch(1)
        until_row = QHBoxLayout()
        until_row.addWidget(self.has_until)
        until_row.addWidget(self.until_field)
        until_row.addStretch(1)
        details.addLayout(interval_row)
        details.addWidget(self.weekdays)
        details.addLayout(until_row)
        self.summary = label("", "faint", wrap=True)
        repeat = QVBoxLayout()
        repeat.setSpacing(8)
        repeat.addWidget(self.repeat_field, 0, Qt.AlignmentFlag.AlignLeft)
        repeat.addWidget(self._repeat_details)
        repeat.addWidget(self.summary)

        self.location_field = QLineEdit()
        self.location_field.setMaxLength(120)
        self.location_field.setPlaceholderText("Capitale, frontière, Discord vocal…")
        self.description_field = QPlainTextEdit()
        self.description_field.setPlaceholderText("Détails, consignes, équipement…")
        self.description_field.setMinimumHeight(90)
        self.notify_field = QCheckBox("Prévenir tout le pays")
        self.notify_field.setToolTip("Un message part dans la messagerie de chaque membre.")

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("Titre", self.title_field)
        form.addRow("Catégorie", self.category_field)
        form.addRow("Quand", when)
        form.addRow("Répétition", repeat)
        form.addRow("Lieu", self.location_field)
        form.addRow("Description", self.description_field)
        form.addRow("", self.notify_field)

        self.delete_button = button("Supprimer", "trash", "ghost")
        self.delete_button.setStyleSheet(f"QPushButton {{ color: {COLORS.danger}; }}")
        self.delete_button.clicked.connect(self._delete)
        self.save_button = button("Enregistrer", "save", "primary")
        self.save_button.clicked.connect(self.save)
        actions = QHBoxLayout()
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        header = QHBoxLayout()
        header.addWidget(self.heading, 1)
        header.addWidget(new_button, 0, Qt.AlignmentFlag.AlignTop)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 8, 0)
        inner_layout.setSpacing(14)
        inner_layout.addLayout(header)
        inner_layout.addWidget(self.banner)
        inner_layout.addLayout(form)
        inner_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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
        splitter.setSizes([240, 900])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        for signal in (
            self.title_field.textChanged,
            self.category_field.currentIndexChanged,
            self.kind.currentChanged,
            self.start_date.dateChanged,
            self.start_time.timeChanged,
            self.has_end.toggled,
            self.end_time.timeChanged,
            self.end_date.dateChanged,
            self.repeat_field.currentIndexChanged,
            self.interval_field.valueChanged,
            self.weekdays.changed,
            self.has_until.toggled,
            self.until_field.dateChanged,
            self.location_field.textChanged,
            self.description_field.textChanged,
        ):
            signal.connect(self._mark_dirty)
        for signal in (
            self.kind.currentChanged,
            self.repeat_field.currentIndexChanged,
            self.has_end.toggled,
            self.has_until.toggled,
            self.weekdays.changed,
            self.start_date.dateChanged,
            self.start_time.timeChanged,
            self.interval_field.valueChanged,
            self.until_field.dateChanged,
        ):
            signal.connect(self._update_fields)
        self.load(None)

    # -- cycle ------------------------------------------------------------------------------

    @property
    def current_id(self) -> str | None:
        return self._current

    def is_dirty(self) -> bool:
        return self._dirty

    def refresh(self) -> None:
        call_api(self._host, self._host.api.admin_events, self._show_list)

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
            call_api(self._host, lambda: self._host.api.admin_event(key), self._load_remote)

    def load(self, event_id: str | None, day: date | None = None) -> None:
        event = self._events.get(event_id) if event_id else None
        self._current = event.id if event else None
        self._loading = True
        self.banner.hide()
        self.heading.setText(event.title if event else "Nouvel événement")
        self.title_field.setText(event.title if event else "")
        category = event.category.id if event else "event"
        self.category_field.setCurrentIndex(max(self.category_field.findData(category), 0))
        self.location_field.setText(event.location if event else "")
        self.description_field.setPlainText(event.description if event else "")
        start = event.starts_at if event else datetime.combine(day or date.today(), time(21, 0))
        end = event.ends_at if event else None
        if event is None or not event.all_day:
            kind = TIMED
        else:
            kind = SPAN if end is not None and end.date() != start.date() else DAY
        self.kind.set_current_index(kind)
        self.start_date.setDate(_qdate(start.date()))
        self.start_time.setTime(QTime(start.hour, start.minute) if kind == TIMED else QTime(21, 0))
        self.has_end.setChecked(kind == TIMED and end is not None)
        later = end or start + timedelta(hours=2)
        self.end_time.setTime(QTime(later.hour, later.minute))
        self.end_date.setDate(_qdate((end or start + timedelta(days=1)).date()))
        rule = event.rule if event else Rule()
        self.repeat_field.setCurrentIndex(max(self.repeat_field.findData(rule.kind), 0))
        self.interval_field.setValue(rule.interval)
        self.weekdays.set_days(mask_days(rule.days) or [start.weekday()])
        self.has_until.setChecked(rule.until is not None)
        self.until_field.setDate(_qdate(rule.until or start.date() + timedelta(days=90)))
        self.notify_field.setChecked(event is None)
        self.delete_button.setVisible(event is not None)
        self._loading = False
        self._dirty = False
        self._update_fields()
        if event is None:
            self.list.clear_selection()
            self.title_field.setFocus()

    def set_kind(self, kind: int) -> None:
        self.kind.set_current_index(kind)

    def period(self) -> tuple[datetime, datetime | None]:
        kind = self.kind.current_index()
        start_day = _to_date(self.start_date.date())
        if kind == DAY:
            return _local(start_day, time(0, 0)), None
        if kind == SPAN:
            return _local(start_day, time(0, 0)), _local(_to_date(self.end_date.date()), time(23, 59))
        start_time = self.start_time.time()
        starts_at = _local(start_day, time(start_time.hour(), start_time.minute()))
        if not self.has_end.isChecked():
            return starts_at, None
        end_time = self.end_time.time()
        ends_at = _local(start_day, time(end_time.hour(), end_time.minute()))
        if ends_at <= starts_at:
            ends_at = _local(start_day + timedelta(days=1), time(end_time.hour(), end_time.minute()))
        return starts_at, ends_at

    def rule(self) -> Rule:
        kind = self.repeat_field.currentData() if self.kind.current_index() != SPAN else NONE
        until = _to_date(self.until_field.date()) if self.has_until.isChecked() else None
        days = days_mask(self.weekdays.days()) if kind == WEEKLY else 0
        return Rule(kind, self.interval_field.value(), days, until)

    def payload(self) -> dict[str, Any]:
        starts_at, ends_at = self.period()
        rule = self.rule()
        return {
            "title": self.title_field.text().strip(),
            "category": self.category_field.currentData(),
            "location": self.location_field.text().strip(),
            "description": self.description_field.toPlainText().strip(),
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat() if ends_at else None,
            "all_day": self.kind.current_index() != TIMED,
            "recurrence": rule.kind,
            "recurrence_interval": rule.interval,
            "recurrence_days": rule.days,
            "recurrence_until": rule.until.isoformat() if rule.until else None,
            "notify": self.notify_field.isChecked(),
        }

    def save(self) -> None:
        payload = self.payload()
        if not payload["title"]:
            self._refuse("Le titre est obligatoire.")
            return
        starts_at, ends_at = self.period()
        if ends_at is not None and ends_at < starts_at:
            self._refuse("La fin doit être après le début.")
            return
        rule = self.rule()
        if rule.until is not None and rule.repeats and rule.until < starts_at.date():
            self._refuse("La répétition doit s'arrêter après la première date.")
            return
        if rule.kind == WEEKLY and not self.weekdays.days():
            self._refuse("Choisis au moins un jour de la semaine.")
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
        for event in events:
            if event.recurring:
                subtitle = event.recurrence_text
            else:
                subtitle = f"{WEEKDAYS_SHORT[event.starts_at.weekday()]} {event.starts_at:%d/%m/%Y}"
                if not event.all_day:
                    subtitle += f" · {event.starts_at:%H:%M}"
            icon_name = "refresh" if event.recurring else "calendar"
            entries.append((event.id, event.title, subtitle, icons.icon(icon_name, event.category.color, 26)))
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
        scope = "toutes les dates de cette série" if event.recurring else f"« {event.title} »"
        choice = choose(
            self, "Supprimer", f"Supprimer {scope} ?", ["Supprimer et prévenir le pays", "Supprimer sans prévenir"]
        )
        if choice is not None:
            self.delete(choice == 0)

    def _confirm_leave(self) -> bool:
        if not self._dirty:
            return True
        return ask(self, "Modifications non enregistrées", "Abandonner les modifications en cours ?")

    def _refuse(self, text: str) -> None:
        self.banner.set_text(text)
        self.banner.show()

    def _mark_dirty(self, *_args) -> None:
        if not self._loading:
            self._dirty = True

    def _update_fields(self, *_args) -> None:
        kind = self.kind.current_index()
        self._timed_row.setVisible(kind == TIMED)
        self._span_row.setVisible(kind == SPAN)
        self.end_time.setEnabled(self.has_end.isChecked())
        self.repeat_field.setEnabled(kind != SPAN)
        rule = self.rule()
        self._repeat_details.setVisible(rule.repeats)
        self.weekdays.setVisible(rule.kind == WEEKLY)
        self.interval_field.setSuffix(f" {INTERVAL_UNITS.get(rule.kind, '')}")
        self.until_field.setEnabled(self.has_until.isChecked())
        start_day = _to_date(self.start_date.date())
        if kind == SPAN:
            self.summary.setText("Un événement sur plusieurs jours ne se répète pas.")
        elif rule.repeats:
            hour = "" if kind == DAY else f" à {self.start_time.time().toString('HH:mm')}"
            self.summary.setText(f"{rule.describe(start_day)}{hour}, à partir du {start_day:%d/%m/%Y}.")
        else:
            self.summary.setText("")
