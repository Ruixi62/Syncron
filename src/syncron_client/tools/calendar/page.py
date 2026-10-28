"""Page du calendrier : vue du mois, détail du jour choisi, événements à venir."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from syncron_client.tools.calendar.model import CATEGORIES, Event, events_on, month_grid
from syncron_client.ui import icons
from syncron_client.ui.format import WEEKDAYS_SHORT, long_date, month_title
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, Chip, button, icon_button, label

MAX_LINES = 3


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class DayCell(QFrame):
    clicked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.day: date | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(96, 92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._number = QLabel()
        self._lines = QLabel()
        self._lines.setTextFormat(Qt.TextFormat.RichText)
        self._lines.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._lines.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        layout.addWidget(self._number)
        layout.addWidget(self._lines, 1)

    def show_day(self, day: date, events: list[Event], current_month: bool, today: bool, selected: bool) -> None:
        self.day = day
        number_color = COLORS.accent if today else (COLORS.text if current_month else COLORS.text_faint)
        weight = 700 if today else 600
        self._number.setText(str(day.day))
        self._number.setStyleSheet(f"color: {number_color}; font-weight: {weight}; background: transparent;")
        lines = []
        for event in events[:MAX_LINES]:
            prefix = "" if event.all_day else f"{event.starts_at:%H:%M} "
            lines.append(
                f"<span style='color:{event.category.color}'>●</span> "
                f"<span style='color:{COLORS.text if current_month else COLORS.text_faint}'>"
                f"{prefix}{_escape(event.title)}</span>"
            )
        if len(events) > MAX_LINES:
            lines.append(f"<span style='color:{COLORS.text_faint}'>+{len(events) - MAX_LINES} autre(s)</span>")
        self._lines.setText("<br>".join(lines))
        self._lines.setStyleSheet("font-size: 11px; background: transparent;")
        self.setToolTip("\n".join(f"{e.time_text(day)} · {e.title}" for e in events))
        background = COLORS.surface_hover if selected else (COLORS.surface if current_month else COLORS.bg)
        border = COLORS.accent if selected or today else COLORS.border
        self.setStyleSheet(f"DayCell {{ background: {background}; border: 1px solid {border}; border-radius: 10px; }}")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.day is not None:
            self.clicked.emit(self.day)
        super().mousePressEvent(event)


class EventCard(Card):
    editRequested = Signal(str)

    def __init__(self, event: Event, editable: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent, flat=True, padding=14, spacing=6)
        self.calendar_event = event
        head = QHBoxLayout()
        head.addWidget(Chip(event.category.label, event.category.tone), 0, Qt.AlignmentFlag.AlignTop)
        head.addStretch(1)
        if editable:
            edit = icon_button("edit", "Modifier dans l'administration", 15)
            edit.clicked.connect(lambda: self.editRequested.emit(event.id))
            head.addWidget(edit)
        self.body.addLayout(head)
        self.body.addWidget(label(event.title, "heading", wrap=True))
        self.body.addLayout(_info_row("clock", event.time_text()))
        if event.location:
            self.body.addLayout(_info_row("map-pin", event.location))
        if event.description:
            description = label(event.description, "muted", wrap=True)
            description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.body.addWidget(description)
        if event.author:
            self.body.addWidget(label(f"Ajouté par {event.author}", "faint"))


class UpcomingRow(QWidget):
    """Ligne « à venir » : un clic affiche le jour de l'événement."""

    clicked = Signal(object, str)

    def __init__(self, event: Event, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.calendar_event = event
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        dot = QLabel(f"<span style='color:{event.category.color}'>●</span>")
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(label(event.title, wrap=True))
        when = long_date(event.first_day).capitalize()
        texts.addWidget(label(when if event.all_day else f"{when} · {event.starts_at:%H:%M}", "faint"))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(texts, 1)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.calendar_event.first_day, self.calendar_event.id)
        super().mousePressEvent(event)


def _info_row(icon_name: str, text: str) -> QHBoxLayout:
    glyph = QLabel()
    glyph.setPixmap(icons.pixmap(icon_name, COLORS.text_faint, 14))
    row = QHBoxLayout()
    row.setSpacing(6)
    row.addWidget(glyph)
    row.addWidget(label(text, "muted", wrap=True), 1)
    return row


def _clear(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


class CalendarPage(QWidget):
    monthChanged = Signal(int, int)
    newRequested = Signal(object)  # date
    editRequested = Signal(str)  # id de l'événement

    def __init__(self, editable: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editable = editable
        today = date.today()
        self._year, self._month = today.year, today.month
        self._selected = today
        self._events: list[Event] = []
        self._highlight: str | None = None

        previous = icon_button("chevron-left", "Mois précédent", 18)
        previous.clicked.connect(lambda: self.monthChanged.emit(*self._shifted(-1)))
        following = icon_button("chevron-right", "Mois suivant", 18)
        following.clicked.connect(lambda: self.monthChanged.emit(*self._shifted(1)))
        self.today_button = button("Aujourd'hui", "today")
        self.today_button.clicked.connect(self.go_today)
        self.title = label("", "title")
        self.new_button = button("Nouvel événement", "plus", "primary")
        self.new_button.clicked.connect(lambda: self.newRequested.emit(self._selected))
        self.new_button.setVisible(editable)
        legend = QHBoxLayout()
        legend.setSpacing(6)
        for category in CATEGORIES.values():
            legend.addWidget(Chip(category.label, category.tone))
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(previous)
        header.addWidget(following)
        header.addWidget(self.title)
        header.addSpacing(8)
        header.addWidget(self.today_button)
        header.addStretch(1)
        header.addLayout(legend)
        header.addSpacing(8)
        header.addWidget(self.new_button)

        grid = QGridLayout()
        grid.setSpacing(6)
        for column, name in enumerate(WEEKDAYS_SHORT):
            heading = label(name.upper(), "overline")
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(heading, 0, column)
        self.cells: list[DayCell] = []
        for index in range(42):
            cell = DayCell()
            cell.clicked.connect(self.select_day)
            self.cells.append(cell)
            grid.addWidget(cell, 1 + index // 7, index % 7)
        for column in range(7):
            grid.setColumnStretch(column, 1)
        for row in range(1, 7):
            grid.setRowStretch(row, 1)
        month_card = Card(padding=14, spacing=12)
        month_card.body.addLayout(grid, 1)

        self.day_title = label("", "heading")
        self._day_events = QVBoxLayout()
        self._day_events.setSpacing(10)
        self.day_empty = label("Rien de prévu ce jour-là.", "faint")
        day_content = QWidget()
        day_layout = QVBoxLayout(day_content)
        day_layout.setContentsMargins(0, 0, 0, 0)
        day_layout.setSpacing(10)
        day_layout.addWidget(self.day_title)
        day_layout.addWidget(self.day_empty)
        day_layout.addLayout(self._day_events)
        day_layout.addSpacing(10)
        day_layout.addWidget(label("À VENIR", "overline"))
        self._upcoming = QVBoxLayout()
        self._upcoming.setSpacing(6)
        day_layout.addLayout(self._upcoming)
        day_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(day_content)
        side = Card(padding=16, spacing=0)
        side.setFixedWidth(340)
        side.body.addWidget(scroll)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(month_card, 1)
        body.addWidget(side)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addLayout(body, 1)
        self._render()

    # -- état -------------------------------------------------------------------------------

    @property
    def month(self) -> tuple[int, int]:
        return self._year, self._month

    @property
    def selected_day(self) -> date:
        return self._selected

    @property
    def events(self) -> list[Event]:
        return self._events

    def day_event_titles(self) -> list[str]:
        return [card.calendar_event.title for card in self._cards()]

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self.new_button.setVisible(editable)
        self._render_day()

    def set_month(self, year: int, month: int, events: list[Event]) -> None:
        self._year, self._month = year, month
        self._events = events
        if (self._selected.year, self._selected.month) != (year, month):
            today = date.today()
            self._selected = today if (today.year, today.month) == (year, month) else date(year, month, 1)
        self._render()

    def set_upcoming(self, events: list[Event]) -> None:
        _clear(self._upcoming)
        if not events:
            self._upcoming.addWidget(label("Aucun événement prévu.", "faint"))
            return
        for event in events:
            row = UpcomingRow(event)
            row.clicked.connect(self._jump)
            self._upcoming.addWidget(row)

    def select_day(self, day: date) -> None:
        self._selected = day
        self._highlight = None
        if (day.year, day.month) != (self._year, self._month):
            self.monthChanged.emit(day.year, day.month)
            return
        self._render()

    def focus_event(self, event: Event) -> None:
        """Après set_month : sélectionne le jour de l'événement et le met en avant."""
        self._selected = event.first_day
        self._highlight = event.id
        self._render()

    def go_today(self) -> None:
        today = date.today()
        self._selected = today
        if (today.year, today.month) != (self._year, self._month):
            self.monthChanged.emit(today.year, today.month)
        else:
            self._render()

    # -- rendu ------------------------------------------------------------------------------

    def _shifted(self, delta: int) -> tuple[int, int]:
        index = self._year * 12 + self._month - 1 + delta
        return index // 12, index % 12 + 1

    def _render(self) -> None:
        self.title.setText(month_title(self._year, self._month))
        today = date.today()
        for cell, day in zip(self.cells, month_grid(self._year, self._month), strict=True):
            cell.show_day(
                day, events_on(self._events, day), day.month == self._month, day == today, day == self._selected
            )
        self._render_day()

    def _render_day(self) -> None:
        _clear(self._day_events)
        self.day_title.setText(long_date(self._selected).capitalize())
        events = events_on(self._events, self._selected)
        self.day_empty.setVisible(not events)
        for event in events:
            card = EventCard(event, self._editable)
            card.editRequested.connect(self.editRequested)
            if event.id == self._highlight:
                card.setStyleSheet(f"QFrame[card='flat'] {{ border: 1px solid {COLORS.accent}; }}")
            self._day_events.addWidget(card)

    def _cards(self) -> list[EventCard]:
        cards = []
        for index in range(self._day_events.count()):
            widget = self._day_events.itemAt(index).widget()
            if isinstance(widget, EventCard):
                cards.append(widget)
        return cards

    def _jump(self, day: date, event_id: str) -> None:
        self._selected = day
        self._highlight = event_id
        if (day.year, day.month) != (self._year, self._month):
            self.monthChanged.emit(day.year, day.month)
        else:
            self._render()
