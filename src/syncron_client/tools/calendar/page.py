"""Page du calendrier : vue du mois (ou liste), détail du jour choisi, événements à venir.

La grille du mois est dessinée d'un bloc (MonthView) : chaque case reçoit
exactement sa part de la surface, et n'affiche que les lignes qui y tiennent
(titres raccourcis avec « … », « +2 autres » au besoin). Rien ne peut se
chevaucher, quelle que soit la taille de la fenêtre ; le titre complet est
dans l'info-bulle et dans le détail du jour.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QHelpEvent, QMouseEvent, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from syncron_client.tools.calendar.model import CATEGORIES, Event, events_on, month_grid
from syncron_client.ui import icons
from syncron_client.ui.format import WEEKDAYS_SHORT, long_date, month_title
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Card, Chip, FlowWidget, SegmentedControl, button, icon_button, label

HEADER_HEIGHT = 24
CELL_GAP = 4
LINE_HEIGHT = 17
CELL_PADDING = 6
TIME_PREFIX_MIN_WIDTH = 110  # case étroite : le titre d'abord, l'heure est dans le détail du jour


class MonthView(QWidget):
    """Grille de 6 semaines dessinée : aucune case ne peut déborder sur sa voisine."""

    daySelected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._days: list[date] = []
        self._month = 1
        self._events: list[Event] = []
        self._selected: date | None = None
        self._hover: int | None = None

    def minimumSizeHint(self) -> QSize:
        return QSize(7 * 52, HEADER_HEIGHT + 6 * 46)

    def sizeHint(self) -> QSize:
        return QSize(7 * 120, HEADER_HEIGHT + 6 * 104)

    def set_month(self, year: int, month: int, events: list[Event], selected: date) -> None:
        self._days = month_grid(year, month)
        self._month = month
        self._events = events
        self._selected = selected
        self.update()

    def cell_rect(self, index: int) -> QRect:
        width = (self.width() - CELL_GAP * 6) / 7
        height = (self.height() - HEADER_HEIGHT - CELL_GAP * 5) / 6
        column, row = index % 7, index // 7
        x = round(column * (width + CELL_GAP))
        y = round(HEADER_HEIGHT + row * (height + CELL_GAP))
        return QRect(x, y, round(width), round(height))

    def index_at(self, point: QPoint) -> int | None:
        for index in range(len(self._days)):
            if self.cell_rect(index).contains(point):
                return index
        return None

    def visible_lines(self, index: int) -> int:
        """Lignes d'événements qui tiennent dans la case (sous le numéro du jour)."""
        available = self.cell_rect(index).height() - CELL_PADDING * 2 - 18
        return max(available // LINE_HEIGHT, 0)

    # -- dessin ---------------------------------------------------------------------------

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QFont(self.font())
        small = QFont(base)
        small.setPixelSize(11)
        bold = QFont(base)
        bold.setWeight(QFont.Weight.DemiBold)
        width = (self.width() - CELL_GAP * 6) / 7
        painter.setFont(small)
        painter.setPen(QColor(COLORS.text_faint))
        for column, name in enumerate(WEEKDAYS_SHORT):
            rect = QRectF(column * (width + CELL_GAP), 0, width, HEADER_HEIGHT - 4)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, name.upper())
        today = date.today()
        metrics = QFontMetrics(small)
        for index, day in enumerate(self._days):
            rect = self.cell_rect(index)
            current = day.month == self._month
            selected = day == self._selected
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)
            background = COLORS.surface_hover if selected else (COLORS.surface if current else COLORS.bg)
            if index == self._hover and not selected:
                background = COLORS.surface_alt
            painter.fillPath(path, QColor(background))
            border = COLORS.accent if (selected or day == today) else COLORS.border
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(border))
            painter.drawPath(path)

            painter.setFont(bold)
            painter.setPen(QColor(COLORS.accent if day == today else (COLORS.text if current else COLORS.text_faint)))
            number = rect.adjusted(CELL_PADDING + 2, CELL_PADDING - 2, -CELL_PADDING, 0)
            painter.drawText(number, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(day.day))

            events = events_on(self._events, day)
            capacity = self.visible_lines(index)
            shown = events if len(events) <= capacity else events[: max(capacity - 1, 0)]
            painter.setFont(small)
            y = rect.top() + CELL_PADDING + 18
            text_width = rect.width() - CELL_PADDING * 2 - 10
            for event in shown:
                painter.setBrush(QColor(event.category.color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(rect.left() + CELL_PADDING, y + 4, 4, LINE_HEIGHT - 8), 2, 2)
                roomy = text_width >= TIME_PREFIX_MIN_WIDTH
                prefix = f"{event.starts_at:%H:%M} " if roomy and not event.all_day else ""
                text = metrics.elidedText(prefix + event.title, Qt.TextElideMode.ElideRight, text_width)
                painter.setPen(QColor(COLORS.text if current else COLORS.text_faint))
                painter.drawText(
                    QRect(rect.left() + CELL_PADDING + 9, y, text_width, LINE_HEIGHT),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    text,
                )
                y += LINE_HEIGHT
            hidden = len(events) - len(shown)
            if hidden > 0 and capacity > 0:
                painter.setPen(QColor(COLORS.text_faint))
                painter.drawText(
                    QRect(rect.left() + CELL_PADDING + 9, y, text_width, LINE_HEIGHT),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    f"+{hidden} autre{'s' if hidden > 1 else ''}",
                )
            elif hidden > 0:
                painter.setBrush(QColor(COLORS.accent))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QRectF(rect.right() - 12, rect.top() + 8, 6, 6))
        painter.end()

    # -- interaction ------------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        index = self.index_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and index is not None:
            self.daySelected.emit(self._days[index])
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self.index_at(event.position().toPoint())
        if index != self._hover:
            self._hover = index
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            index = self.index_at(event.pos())
            events = events_on(self._events, self._days[index]) if index is not None else []
            if events:
                text = "\n".join(f"{e.time_text()} · {e.title}" for e in events)
                QToolTip.showText(event.globalPos(), f"{long_date(self._days[index]).capitalize()}\n{text}", self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)


class EventCard(Card):
    editRequested = Signal(str)
    skipRequested = Signal(str, object)  # id de la série, date

    def __init__(self, event: Event, editable: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent, flat=True, padding=14, spacing=6)
        self.calendar_event = event
        head = QHBoxLayout()
        head.addWidget(Chip(event.category.label, event.category.tone), 0, Qt.AlignmentFlag.AlignTop)
        if event.recurring:
            head.addWidget(Chip("Récurrent", "neutral", "refresh"), 0, Qt.AlignmentFlag.AlignTop)
        head.addStretch(1)
        if editable:
            if event.recurring and event.occurrence:
                skip = icon_button("close", "Annuler seulement cette date", 15)
                skip.clicked.connect(lambda: self.skipRequested.emit(event.id, event.occurrence))
                head.addWidget(skip)
            edit = icon_button("edit", "Modifier dans l'administration", 15)
            edit.clicked.connect(lambda: self.editRequested.emit(event.id))
            head.addWidget(edit)
        self.body.addLayout(head)
        self.body.addWidget(label(event.title, "heading", wrap=True))
        self.body.addLayout(_info_row("clock", event.time_text()))
        if event.recurring:
            self.body.addLayout(_info_row("refresh", event.recurrence_text))
        if event.location:
            self.body.addLayout(_info_row("map-pin", event.location))
        if event.description:
            description = label(event.description, "muted", wrap=True)
            description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.body.addWidget(description)
        if event.author:
            self.body.addWidget(label(f"Ajouté par {event.author}", "faint"))


class EventRow(QFrame):
    """Ligne cliquable (à venir, vue liste) : pastille de catégorie, titre complet, date."""

    clicked = Signal(object, str)

    def __init__(self, event: Event, with_day: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.calendar_event = event
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {event.category.color}; border-radius: 5px;")
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(label(event.title, wrap=True))
        when = event.time_text()
        if with_day:
            day = long_date(event.first_day).capitalize()
            when = day if event.all_day else f"{day} · {event.starts_at:%H:%M}"
        if event.recurring:
            when += " · récurrent"
        texts.addWidget(label(when, "faint", wrap=True))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(10)
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(texts, 1)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.calendar_event.first_day, self.calendar_event.key)
        super().mousePressEvent(event)


def _info_row(icon_name: str, text: str) -> QHBoxLayout:
    glyph = QLabel()
    glyph.setPixmap(icons.pixmap(icon_name, COLORS.text_faint, 14))
    row = QHBoxLayout()
    row.setSpacing(6)
    row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
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


def _scroll(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


class CalendarPage(QWidget):
    monthChanged = Signal(int, int)
    newRequested = Signal(object)  # date
    editRequested = Signal(str)  # id de l'événement
    skipRequested = Signal(str, object)  # id de la série, date

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
        self.title.setMinimumWidth(170)
        self.view_choice = SegmentedControl([("Mois", "grid"), ("Liste", "list")])
        self.view_choice.currentChanged.connect(self._view_changed)
        self.new_button = button("Nouvel événement", "plus", "primary")
        self.new_button.clicked.connect(lambda: self.newRequested.emit(self._selected))
        self.new_button.setVisible(editable)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(previous)
        header.addWidget(following)
        header.addWidget(self.title)
        header.addWidget(self.today_button)
        header.addStretch(1)
        header.addWidget(self.view_choice)
        header.addWidget(self.new_button)

        self.month_view = MonthView()
        self.month_view.daySelected.connect(self.select_day)
        legend = FlowWidget(spacing=6)
        for category in CATEGORIES.values():
            legend.add(Chip(category.label, category.tone))
        self._list_content = QVBoxLayout()
        self._list_content.setSpacing(6)
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(4, 0, 8, 0)
        list_layout.addLayout(self._list_content)
        list_layout.addStretch(1)
        self._views = QStackedWidget()
        self._views.addWidget(self.month_view)
        self._views.addWidget(_scroll(list_widget))
        month_card = Card(padding=12, spacing=10)
        month_card.body.addWidget(self._views, 1)
        month_card.body.addWidget(legend)

        self.day_title = label("", "heading")
        self.day_title.setWordWrap(True)
        self._day_events = QVBoxLayout()
        self._day_events.setSpacing(10)
        self.day_empty = label("Rien de prévu ce jour-là.", "faint")
        day_content = QWidget()
        day_layout = QVBoxLayout(day_content)
        day_layout.setContentsMargins(0, 0, 6, 0)
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
        side = Card(padding=16, spacing=0)
        side.setMinimumWidth(250)
        side.setMaximumWidth(330)
        side.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        side.body.addWidget(_scroll(day_content))

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(month_card, 3)
        body.addWidget(side, 1)
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

    @property
    def list_mode(self) -> bool:
        return self.view_choice.current_index() == 1

    def day_event_titles(self) -> list[str]:
        return [card.calendar_event.title for card in self._cards()]

    def list_titles(self) -> list[str]:
        titles = []
        for index in range(self._list_content.count()):
            widget = self._list_content.itemAt(index).widget()
            if isinstance(widget, EventRow):
                titles.append(widget.calendar_event.title)
        return titles

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
            row = EventRow(event)
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
        self._highlight = event.key
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

    def _view_changed(self, index: int) -> None:
        self._views.setCurrentIndex(index)

    def _render(self) -> None:
        self.title.setText(month_title(self._year, self._month))
        self.month_view.set_month(self._year, self._month, self._events, self._selected)
        self._render_list()
        self._render_day()

    def _render_list(self) -> None:
        _clear(self._list_content)
        days = sorted({day for day in month_grid(self._year, self._month) if day.month == self._month})
        empty = True
        for day in days:
            events = events_on(self._events, day)
            if not events:
                continue
            empty = False
            heading = label(long_date(day).capitalize(), "overline")
            heading.setContentsMargins(0, 8, 0, 0)
            self._list_content.addWidget(heading)
            for event in events:
                row = EventRow(event, with_day=False)
                row.clicked.connect(lambda _day, _key, target=day: self.select_day(target))
                self._list_content.addWidget(row)
        if empty:
            self._list_content.addWidget(label("Aucun événement ce mois-ci.", "faint"))

    def _render_day(self) -> None:
        _clear(self._day_events)
        self.day_title.setText(long_date(self._selected).capitalize())
        events = events_on(self._events, self._selected)
        self.day_empty.setVisible(not events)
        for event in events:
            card = EventCard(event, self._editable)
            card.editRequested.connect(self.editRequested)
            card.skipRequested.connect(self.skipRequested)
            if event.key == self._highlight or event.id == self._highlight:
                card.setStyleSheet(f"QFrame[card='flat'] {{ border: 1px solid {COLORS.accent}; }}")
            self._day_events.addWidget(card)

    def _cards(self) -> list[EventCard]:
        cards = []
        for index in range(self._day_events.count()):
            widget = self._day_events.itemAt(index).widget()
            if isinstance(widget, EventCard):
                cards.append(widget)
        return cards

    def _jump(self, day: date, key: str) -> None:
        self._selected = day
        self._highlight = key
        if (day.year, day.month) != (self._year, self._month):
            self.monthChanged.emit(day.year, day.month)
        else:
            self._render()
