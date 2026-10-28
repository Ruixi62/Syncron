"""Barre du haut : titre de la page, actions de l'outil actif, recherche globale, notifications."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import ElidedLabel

TOP_BAR_HEIGHT = 68
COMPACT_WIDTH = 1180


class TopBar(QFrame):
    searchRequested = Signal()
    retryRequested = Signal()
    notificationsRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(TOP_BAR_HEIGHT)

        self._title = ElidedLabel("", "title")
        self._subtitle = ElidedLabel("", "faint")
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addStretch(1)
        titles.addWidget(self._title)
        titles.addWidget(self._subtitle)
        titles.addStretch(1)

        self._actions = QHBoxLayout()
        self._actions.setSpacing(4)

        self._offline = QPushButton("  Hors ligne · Réessayer")
        self._offline.setIcon(icons.icon("wifi-off", COLORS.warning, 15))
        self._offline.setIconSize(QSize(15, 15))
        self._offline.setCursor(Qt.CursorShape.PointingHandCursor)
        self._offline.setToolTip("Le serveur est injoignable : tu consultes la dernière version enregistrée.")
        self._offline.setStyleSheet(
            f"QPushButton {{ color: {COLORS.warning}; background: {COLORS.warning_soft};"
            f" border: 1px solid {COLORS.warning}; border-radius: 10px; padding: 6px 12px; font-weight: 600; }}"
        )
        self._offline.clicked.connect(self.retryRequested)
        self._offline.hide()

        self._search = QPushButton("  Rechercher partout…        Ctrl K")
        self._search.setObjectName("SearchLauncher")
        self._search.setIcon(icons.icon("search", COLORS.text_faint, 15))
        self._search.setIconSize(QSize(15, 15))
        self._search.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search.clicked.connect(self.searchRequested)

        self._bell = QToolButton()
        self._bell.setProperty("variant", "icon")
        self._bell.setIcon(icons.icon("bell", COLORS.text_muted, 19))
        self._bell.setIconSize(QSize(19, 19))
        self._bell.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bell.setToolTip("Messagerie")
        self._bell.clicked.connect(self.notificationsRequested)
        self._bell_badge = QLabel(self._bell)
        self._bell_badge.setObjectName("NavBadge")
        self._bell_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bell_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._bell_badge.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 20, 0)
        layout.setSpacing(12)
        layout.addLayout(titles, 1)
        layout.addLayout(self._actions)
        layout.addSpacing(8)
        layout.addWidget(self._offline)
        layout.addWidget(self._search)
        layout.addWidget(self._bell)

    def set_search_visible(self, visible: bool) -> None:
        self._search.setVisible(visible)

    def search_visible(self) -> bool:
        return not self._search.isHidden()

    def set_unread(self, count: int) -> None:
        self._bell.setToolTip(f"Messagerie · {count} non lu(s)" if count else "Messagerie")
        if count <= 0:
            self._bell_badge.hide()
            return
        self._bell_badge.setText("99+" if count > 99 else str(count))
        self._bell_badge.adjustSize()
        self._bell_badge.setMinimumWidth(self._bell_badge.height())
        self._bell_badge.adjustSize()
        self._bell_badge.move(self._bell.width() - self._bell_badge.width() + 2, -2)
        self._bell_badge.show()
        self._bell_badge.raise_()

    def unread_text(self) -> str:
        return self._bell_badge.text() if not self._bell_badge.isHidden() else ""

    def set_notifications_available(self, available: bool) -> None:
        self._bell.setVisible(available)

    def set_offline(self, offline: bool) -> None:
        self._offline.setVisible(offline)

    def offline_visible(self) -> bool:
        return not self._offline.isHidden()

    def set_page(self, title: str, subtitle: str, actions: Sequence[QAction] = ()) -> None:
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        while self._actions.count():
            item = self._actions.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for action in actions:
            tool_button = QToolButton()
            tool_button.setDefaultAction(action)
            tool_button.setProperty("variant", "compact")
            tool_button.setCursor(Qt.CursorShape.PointingHandCursor)
            tool_button.setIconSize(QSize(16, 16))
            self._actions.addWidget(tool_button)
        self._apply_compact()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_compact()

    def _apply_compact(self) -> None:
        """Fenêtre étroite : actions en icônes seules (libellés en info-bulle)."""
        compact = self.width() < COMPACT_WIDTH
        for index in range(self._actions.count()):
            tool_button = self._actions.itemAt(index).widget()
            if isinstance(tool_button, QToolButton):
                action = tool_button.defaultAction()
                show_text = bool(action and action.text()) and not compact
                style = (
                    Qt.ToolButtonStyle.ToolButtonTextBesideIcon if show_text else Qt.ToolButtonStyle.ToolButtonIconOnly
                )
                tool_button.setToolButtonStyle(style)
