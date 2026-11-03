"""Paramètres, en rubriques : Profil · Apparence · Notifications · Compte · Serveur · Stockage · Outils · À propos.

Le profil (pseudo en jeu, grade, description, spécialités, disponibilités, couleur) est
enregistré sur le serveur et visible des autres membres dans l'annuaire ; un aperçu montre
la carte telle qu'ils la verront. Le reste est propre à ce PC.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QRectF, QRegularExpression, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QEnterEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPixmap,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from syncron_client.config import SERVER_URL_KEY, is_safe_server_url
from syncron_client.platform.admin import call_api
from syncron_client.platform.registry import ToolRegistry
from syncron_client.platform.tool import NotifyLevel, Placement, ToolHost, ToolStage
from syncron_client.settings import JsonSettingsStore
from syncron_client.ui import icons
from syncron_client.ui.format import format_datetime
from syncron_client.ui.profile import (
    BIO_MAX,
    NICKNAME_PATTERN,
    PROFILE_COLORS,
    SPECIALTIES_MAX,
    Member,
    MemberCard,
)
from syncron_client.ui.theme import COLORS, PALETTES, THEME_KEY, ThemeMode, resolve_mode
from syncron_client.ui.widgets import Banner, Card, Chip, FlowWidget, button, divider, label
from syncron_core import APP_DISPLAY_NAME, __version__

DESKTOP_NOTIFICATIONS_KEY = "desktop_notifications"
TASKBAR_BADGE_KEY = "taskbar_badge"
THEME_CHOICES = (
    ThemeMode.SYSTEM,
    ThemeMode.DARK,
    ThemeMode.LIGHT,
    ThemeMode.FOREST,
    ThemeMode.CHERRY,
    ThemeMode.CHRISTMAS,
)
HEART_COLOR = "#ff4d6d"
SECTIONS = (
    ("profile", "Profil", "user"),
    ("appearance", "Apparence", "sparkles"),
    ("notifications", "Notifications", "bell"),
    ("account", "Compte", "shield"),
    ("server", "Serveur", "globe"),
    ("storage", "Stockage", "database"),
    ("tools", "Outils", "grid"),
    ("about", "À propos", "info"),
)


# -- petits composants ------------------------------------------------------------------------


class HiddenHeart(QLabel):
    """Tout petit cœur de la couleur des bordures : il ne rosit qu'au survol."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show(COLORS.border_strong)

    def _show(self, color: str) -> None:
        self.setPixmap(icons.pixmap("heart", color, 11, stroke=2.2))

    def enterEvent(self, event: QEnterEvent) -> None:
        self._show(HEART_COLOR)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._show(COLORS.border_strong)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ThemePreview(QWidget):
    """Miniature d'un thème : fond, barre latérale, carte, accent."""

    def __init__(self, mode: ThemeMode, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.setFixedSize(132, 78)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        halves = (
            [PALETTES[ThemeMode.LIGHT], PALETTES[ThemeMode.DARK]]
            if self.mode is ThemeMode.SYSTEM
            else [PALETTES[self.mode]]
        )
        width = self.width() / len(halves)
        for index, palette in enumerate(halves):
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)
            painter.setClipPath(clip)
            painter.setClipRect(QRectF(index * width, 0, width, self.height()), Qt.ClipOperation.IntersectClip)
            painter.fillRect(QRectF(0, 0, self.width(), self.height()), QColor(palette.bg))
            painter.fillRect(QRectF(0, 0, 30, self.height()), QColor(palette.sidebar))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette.accent))
            painter.drawRoundedRect(QRectF(7, 12, 16, 5), 2, 2)
            painter.setBrush(QColor(palette.text_faint))
            for row in range(3):
                painter.drawRoundedRect(QRectF(7, 24 + row * 9, 14, 3), 1.5, 1.5)
            painter.setBrush(QColor(palette.surface))
            painter.drawRoundedRect(QRectF(38, 12, self.width() - 46, 54), 7, 7)
            painter.setBrush(QColor(palette.text))
            painter.drawRoundedRect(QRectF(46, 21, 46, 5), 2, 2)
            painter.setBrush(QColor(palette.text_muted))
            painter.drawRoundedRect(QRectF(46, 32, 66, 3), 1.5, 1.5)
            painter.drawRoundedRect(QRectF(46, 39, 56, 3), 1.5, 1.5)
            painter.setBrush(QColor(palette.accent))
            painter.drawRoundedRect(QRectF(46, 50, 30, 9), 4, 4)
            painter.restore()
        painter.end()


class ThemeTile(QPushButton):
    def __init__(self, mode: ThemeMode, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(156, 142)
        self.setStyleSheet(
            f"QPushButton {{ background: {COLORS.surface_alt}; border: 2px solid transparent; border-radius: 14px;"
            " padding: 0; }"
            f"QPushButton:hover {{ border-color: {COLORS.border_strong}; }}"
            f"QPushButton:checked {{ border-color: {COLORS.accent}; background: {COLORS.accent_soft}; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(6)
        layout.addWidget(ThemePreview(mode), 0, Qt.AlignmentFlag.AlignHCenter)
        name = label(mode.label)
        name.setStyleSheet("font-weight: 600; background: transparent;")
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(name)
        self.setToolTip(mode.caption)


class ThemePicker(QWidget):
    """Vignettes des thèmes. Indices : Système, Sombre, Clair, Forêt, Cerisier, Noël."""

    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.tiles: list[ThemeTile] = []
        flow = FlowWidget(spacing=12)
        for index, mode in enumerate(THEME_CHOICES):
            tile = ThemeTile(mode)
            self._group.addButton(tile, index)
            self.tiles.append(tile)
            flow.add(tile)
        self._group.idClicked.connect(self.currentChanged)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(flow)

    def current_index(self) -> int:
        return self._group.checkedId()

    def set_current_index(self, index: int, emit: bool = True) -> None:
        if 0 <= index < len(self.tiles):
            self.tiles[index].setChecked(True)
            if emit:
                self.currentChanged.emit(index)


class TagEditor(QWidget):
    """Spécialités : on tape puis Entrée ; chaque étiquette a sa croix."""

    changed = Signal()

    def __init__(self, maximum: int = SPECIALTIES_MAX, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._maximum = maximum
        self._tags: list[str] = []
        self.field = QLineEdit()
        self.field.setMaxLength(24)
        self.field.setPlaceholderText("Mineur, ingénieur, diplomate… puis Entrée")
        self.field.returnPressed.connect(self._add_from_field)
        self.flow = FlowWidget(spacing=6)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.field)
        layout.addWidget(self.flow)

    def tags(self) -> list[str]:
        return list(self._tags)

    def set_tags(self, tags: list[str] | tuple[str, ...]) -> None:
        self._tags = list(tags)[: self._maximum]
        self._render()

    def add(self, text: str) -> bool:
        tag = " ".join(text.split())[:24]
        if not tag or len(self._tags) >= self._maximum or tag.casefold() in {t.casefold() for t in self._tags}:
            return False
        self._tags.append(tag)
        self._render()
        self.changed.emit()
        return True

    def remove(self, tag: str) -> None:
        self._tags = [t for t in self._tags if t != tag]
        self._render()
        self.changed.emit()

    def _add_from_field(self) -> None:
        if self.add(self.field.text()):
            self.field.clear()

    def _render(self) -> None:
        self.flow.clear()
        for tag in self._tags:
            chip = QToolButton()
            chip.setText(f"{tag}  ✕")
            chip.setToolTip(f"Retirer « {tag} »")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                f"QToolButton {{ background: {COLORS.accent_soft}; color: {COLORS.accent}; border: none;"
                " border-radius: 10px; padding: 4px 10px; font-weight: 600; }"
            )
            chip.clicked.connect(lambda _checked=False, value=tag: self.remove(value))
            self.flow.add(chip)
        full = len(self._tags) >= self._maximum
        self.field.setEnabled(not full)
        self.field.setPlaceholderText(
            f"{self._maximum} spécialités au plus" if full else "Mineur, ingénieur, diplomate… puis Entrée"
        )


class ColorPicker(QWidget):
    changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._names = list(PROFILE_COLORS)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for index, (name, (color, title)) in enumerate(PROFILE_COLORS.items()):
            swatch = QPushButton()
            swatch.setCheckable(True)
            swatch.setFixedSize(28, 28)
            swatch.setToolTip(title)
            swatch.setCursor(Qt.CursorShape.PointingHandCursor)
            swatch.setStyleSheet(
                f"QPushButton {{ background: {color}; border: 2px solid transparent; border-radius: 14px;"
                " padding: 0; }"
                f"QPushButton:checked {{ border: 3px solid {COLORS.text}; }}"
            )
            self._group.addButton(swatch, index)
            layout.addWidget(swatch)
            if name == "teal":
                swatch.setChecked(True)
        layout.addStretch(1)
        self._group.idClicked.connect(lambda index: self.changed.emit(self._names[index]))

    def color(self) -> str:
        index = self._group.checkedId()
        return self._names[index] if index >= 0 else "teal"

    def set_color(self, name: str) -> None:
        index = self._names.index(name) if name in self._names else 0
        self._group.button(index).setChecked(True)


def _section(title: str, intro: str = "") -> tuple[QScrollArea, QVBoxLayout]:
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(4, 0, 12, 24)
    layout.setSpacing(16)
    layout.addWidget(label(title, "title"))
    if intro:
        layout.addWidget(label(intro, "muted", wrap=True))
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    return scroll, layout


def _field(title: str, widget: QWidget, hint: str = "") -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(5)
    box.addWidget(label(title, "faint"))
    box.addWidget(widget)
    if hint:
        box.addWidget(label(hint, "faint", wrap=True))
    return box


# -- profil -----------------------------------------------------------------------------------


class ProfileSection(QWidget):
    """Formulaire du profil et aperçu de la carte vue par les autres membres."""

    saved = Signal(object)

    def __init__(self, host: ToolHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._member: Member | None = None
        self._loading = False
        self._dirty = False

        self.banner = Banner("danger")
        self.banner.hide()
        self.offline_note = label("Hors ligne : le profil se modifie une fois reconnecté.", "faint")
        self.offline_note.hide()
        self.nickname = QLineEdit()
        self.nickname.setMaxLength(16)
        self.nickname.setPlaceholderText("Ton pseudo Minecraft")
        self.nickname.setValidator(QRegularExpressionValidator(QRegularExpression(NICKNAME_PATTERN), self))
        self.title_field = QLineEdit()
        self.title_field.setMaxLength(60)
        self.title_field.setPlaceholderText("Ministre de la Guerre, mineur en chef…")
        self.availability = QLineEdit()
        self.availability.setMaxLength(80)
        self.availability.setPlaceholderText("Soirs et week-ends")
        self.bio = QPlainTextEdit()
        self.bio.setPlaceholderText("Présente-toi en quelques lignes : ce que tu fais dans le pays, ce que tu aimes…")
        self.bio.setFixedHeight(110)
        self.bio_count = label("", "faint")
        self.specialties = TagEditor()
        self.color = ColorPicker()
        self.show_discord = QCheckBox("Montrer mon pseudo Discord aux autres membres")
        self.save_button = button("Enregistrer le profil", "save", "primary")
        self.save_button.clicked.connect(self.save)
        self.reset_button = button("Annuler les modifications", None, "ghost")
        self.reset_button.clicked.connect(lambda: self._member and self.load(self._member))

        form = Card(padding=20, spacing=14)
        form.body.addWidget(self.banner)
        form.body.addWidget(self.offline_note)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        top = Qt.AlignmentFlag.AlignTop
        grid.addLayout(_field("Pseudo en jeu", self.nickname, "3 à 16 lettres, chiffres ou _"), 0, 0, top)
        grid.addLayout(_field("Grade ou fonction", self.title_field), 0, 1, top)
        grid.addLayout(_field("Disponibilités", self.availability), 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        form.body.addLayout(grid)
        bio_box = _field("Description", self.bio)
        bio_box.addWidget(self.bio_count, 0, Qt.AlignmentFlag.AlignRight)
        form.body.addLayout(bio_box)
        form.body.addLayout(_field("Spécialités", self.specialties))
        form.body.addLayout(_field("Couleur du profil", self.color))
        form.body.addWidget(self.show_discord)
        actions = QHBoxLayout()
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        form.body.addLayout(actions)

        self.preview = MemberCard(Member(id="", name=host.session.display_name))
        self.preview.setMinimumWidth(260)
        self.preview.setMaximumWidth(320)
        preview_box = QVBoxLayout()
        preview_box.setSpacing(8)
        preview_box.addWidget(label("APERÇU", "overline"))
        preview_box.addWidget(label("Ce que voient les autres membres dans l'annuaire.", "faint", wrap=True))
        preview_box.addWidget(self.preview)
        preview_box.addStretch(1)

        self._layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(18)
        self._layout.addWidget(form, 3)
        self._layout.addLayout(preview_box, 2)

        for signal in (self.nickname.textChanged, self.title_field.textChanged, self.availability.textChanged):
            signal.connect(self._changed)
        self.bio.textChanged.connect(self._bio_changed)
        self.specialties.changed.connect(self._changed)
        self.color.changed.connect(self._changed)
        self.show_discord.toggled.connect(self._changed)
        self._bio_changed()
        self._dirty = False

    @property
    def member(self) -> Member | None:
        return self._member

    def resizeEvent(self, event) -> None:
        """Fenêtre étroite : l'aperçu passe sous le formulaire au lieu de déborder."""
        super().resizeEvent(event)
        direction = QBoxLayout.Direction.LeftToRight if self.width() >= 860 else QBoxLayout.Direction.TopToBottom
        if self._layout.direction() != direction:
            self._layout.setDirection(direction)

    def is_dirty(self) -> bool:
        return self._dirty

    def refresh(self) -> None:
        online = self._host.session.online
        self.offline_note.setVisible(not online)
        for widget in (self.save_button, self.reset_button):
            widget.setEnabled(online)
        if online:
            call_api(self._host, self._host.api.profile, lambda raw: self.load(Member.from_api(raw)))

    def load(self, member: Member) -> None:
        self._member = member
        self._loading = True
        self.nickname.setText(member.nickname)
        self.title_field.setText(member.title)
        self.availability.setText(member.availability)
        self.bio.setPlainText(member.bio)
        self.specialties.set_tags(member.specialties)
        self.color.set_color(member.color)
        self.show_discord.setChecked(member.show_discord)
        self._loading = False
        self._dirty = False
        self.banner.hide()
        self._update_preview()
        self._load_avatar(member)

    def edited(self) -> Member:
        base = self._member or Member(id="", name=self._host.session.display_name)
        return Member(
            id=base.id,
            name=base.name,
            discord_username=base.discord_username if self.show_discord.isChecked() else None,
            avatar_url=base.avatar_url,
            role=base.role,
            nickname=self.nickname.text().strip(),
            title=self.title_field.text().strip(),
            bio=self.bio.toPlainText().strip()[:BIO_MAX],
            specialties=tuple(self.specialties.tags()),
            availability=self.availability.text().strip(),
            color=self.color.color(),
            show_discord=self.show_discord.isChecked(),
            joined_at=base.joined_at,
        )

    def save(self) -> None:
        member = self.edited()
        if member.nickname and not 3 <= len(member.nickname) <= 16:
            self.banner.set_text("Pseudo en jeu : 3 à 16 caractères.")
            self.banner.show()
            return

        def done(raw: dict[str, Any]) -> None:
            saved = Member.from_api(raw)
            self.load(saved)
            self.saved.emit(saved)

        call_api(
            self._host,
            lambda: self._host.api.save_profile(member.to_api()),
            done,
            banner=self.banner,
            success="Profil enregistré.",
        )

    def _changed(self, *_args) -> None:
        if not self._loading:
            self._dirty = True
            self._update_preview()

    def _bio_changed(self) -> None:
        text = self.bio.toPlainText()
        if len(text) > BIO_MAX:
            cursor = self.bio.textCursor()
            self.bio.setPlainText(text[:BIO_MAX])
            cursor.setPosition(BIO_MAX)
            self.bio.setTextCursor(cursor)
        count = len(self.bio.toPlainText())
        self.bio_count.setText(f"{count} / {BIO_MAX}")
        self._changed()

    def _update_preview(self) -> None:
        self.preview.show_member(self.edited())

    def _load_avatar(self, member: Member) -> None:
        if not member.avatar_url:
            return

        def show(content: bytes) -> None:
            pixmap = QPixmap()
            if pixmap.loadFromData(content):
                self.preview.set_avatar(pixmap)

        self._host.runner.run(lambda: self._host.api.download(member.avatar_url), show, lambda _error: None)


# -- page -------------------------------------------------------------------------------------


class SettingsPage(QWidget):
    logoutRequested = Signal()
    themeRequested = Signal(str)
    loveRequested = Signal()

    def __init__(self, host: ToolHost, registry: ToolRegistry, settings: JsonSettingsStore, parent=None) -> None:
        super().__init__(parent)
        self._host = host
        self._settings = settings
        self._registry = registry

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}
        nav = Card(padding=10, spacing=2)
        nav.setFixedWidth(196)
        for key, title, icon_name in SECTIONS:
            entry = QPushButton(title)
            entry.setObjectName("NavButton")
            entry.setCheckable(True)
            entry.setCursor(Qt.CursorShape.PointingHandCursor)
            entry.setIcon(icons.icon(icon_name, COLORS.text_muted, 17, COLORS.accent))
            entry.setIconSize(QSize(17, 17))
            entry.clicked.connect(lambda _checked=False, k=key: self.show_section(k))
            self.nav_group.addButton(entry)
            self._nav_buttons[key] = entry
            nav.body.addWidget(entry)
        nav.body.addStretch(1)

        self.stack = QStackedWidget()
        self._sections: dict[str, QWidget] = {}
        self._build_profile()
        self._build_appearance()
        self._build_notifications()
        self._build_account()
        self._build_server()
        self._build_storage()
        self._build_tools()
        self._build_about()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 18, 20, 20)
        layout.setSpacing(20)
        layout.addWidget(nav, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.stack, 1)
        self._select("profile")

    # -- navigation -------------------------------------------------------------------------

    @property
    def current_section(self) -> str:
        current = self.stack.currentWidget()
        return next((key for key, widget in self._sections.items() if widget is current), "profile")

    def show_section(self, key: str) -> None:
        if self._select(key):
            self.refresh()

    def _select(self, key: str) -> bool:
        if key not in self._sections:
            return False
        self._nav_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(self._sections[key])
        return True

    def _add(self, key: str, widget: QWidget) -> None:
        self._sections[key] = widget
        self.stack.addWidget(widget)

    # -- rubriques ----------------------------------------------------------------------------

    def _build_profile(self) -> None:
        scroll, layout = _section(
            "Profil",
            "Ta carte dans l'annuaire des membres : pseudo en jeu, rôle dans le pays, description, spécialités.",
        )
        self.profile = ProfileSection(self._host)
        layout.addWidget(self.profile)
        layout.addStretch(1)
        self._add("profile", scroll)

    def _build_appearance(self) -> None:
        scroll, layout = _section("Apparence", "Le thème s'applique tout de suite, à toute l'application.")
        card = Card(padding=20, spacing=14)
        card.body.addWidget(label("THÈME", "overline"))
        self.theme_choice = ThemePicker()
        current = self._settings.get(THEME_KEY, ThemeMode.SYSTEM)
        index = next((i for i, mode in enumerate(THEME_CHOICES) if mode == current), 0)
        self.theme_choice.set_current_index(index, emit=False)
        self.theme_choice.currentChanged.connect(lambda i: self.themeRequested.emit(THEME_CHOICES[i].value))
        card.body.addWidget(self.theme_choice)
        effective = resolve_mode(current)
        self.theme_note = label(
            f"« Système » utilise en ce moment le thème {effective.label.lower()}."
            if current == ThemeMode.SYSTEM
            else THEME_CHOICES[index].caption + ".",
            "faint",
            wrap=True,
        )
        card.body.addWidget(self.theme_note)
        layout.addWidget(card)
        layout.addStretch(1)
        self._add("appearance", scroll)

    def _build_notifications(self) -> None:
        scroll, layout = _section(
            "Notifications",
            "Annonces de l'équipe, événements du calendrier, changements de ton compte : chaque nouveau message "
            "s'affiche dans Syncron et rejoint ta messagerie.",
        )
        card = Card(padding=20, spacing=12)
        self.desktop_notifications = QCheckBox("Prévenir aussi sur le bureau quand Syncron est en arrière-plan")
        self.desktop_notifications.setChecked(self._settings.get(DESKTOP_NOTIFICATIONS_KEY, True) is not False)
        self.desktop_notifications.toggled.connect(lambda on: self._save_setting(DESKTOP_NOTIFICATIONS_KEY, on))
        self.taskbar_badge = QCheckBox("Afficher le nombre de messages non lus sur l'icône de la barre des tâches")
        self.taskbar_badge.setChecked(self._settings.get(TASKBAR_BADGE_KEY, True) is not False)
        self.taskbar_badge.toggled.connect(lambda on: self._save_setting(TASKBAR_BADGE_KEY, on))
        card.body.addWidget(self.desktop_notifications)
        card.body.addWidget(self.taskbar_badge)
        layout.addWidget(card)
        layout.addStretch(1)
        self._add("notifications", scroll)

    def _build_account(self) -> None:
        scroll, layout = _section("Compte", "Ton compte Syncron est lié à ton compte Discord.")
        card = Card(padding=20, spacing=12)
        self._account_name = label("", "heading")
        self._account_details = label("", "faint")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self._account_name)
        texts.addWidget(self._account_details)
        self._role_chip = Chip("", "accent", "shield")
        row = QHBoxLayout()
        row.addLayout(texts, 1)
        row.addWidget(self._role_chip)
        card.body.addLayout(row)
        card.body.addWidget(divider())
        card.body.addWidget(label("SYSTÈMES QUE TU GÈRES", "overline"))
        self._systems = FlowWidget(spacing=6)
        card.body.addWidget(self._systems)
        self._systems_empty = label("Aucun : tu consultes les outils du pays.", "faint")
        card.body.addWidget(self._systems_empty)
        session_card = Card(padding=20, spacing=12)
        session_card.body.addWidget(label("SESSION", "overline"))
        session_card.body.addWidget(
            label(
                "Ta connexion est gardée de façon chiffrée sur ce PC. Se déconnecter l'efface et ferme la session "
                "sur le serveur.",
                "muted",
                wrap=True,
            )
        )
        logout = button("Se déconnecter", "logout")
        logout.clicked.connect(self.logoutRequested)
        session_card.body.addWidget(logout, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(card)
        layout.addWidget(session_card)
        layout.addStretch(1)
        self._add("account", scroll)

    def _build_server(self) -> None:
        scroll, layout = _section(
            "Serveur", "Adresse de l'API Syncron. Ne la change que si l'équipe t'a communiqué une nouvelle adresse."
        )
        card = Card(padding=20, spacing=12)
        self._server_url = QLineEdit(self._host.api.base_url)
        self._server_url.setPlaceholderText("https://api.exemple.fr")
        apply_server = button("Appliquer", "check")
        apply_server.clicked.connect(self._apply_server)
        server_row = QHBoxLayout()
        server_row.addWidget(self._server_url, 1)
        server_row.addWidget(apply_server)
        card.body.addLayout(server_row)
        self._server_status = Chip("", "neutral")
        card.body.addWidget(self._server_status, 0, Qt.AlignmentFlag.AlignLeft)
        self._server_version = label("", "faint")
        card.body.addWidget(self._server_version)
        layout.addWidget(card)
        layout.addStretch(1)
        self._add("server", scroll)

    def _build_storage(self) -> None:
        scroll, layout = _section(
            "Stockage",
            "Tes préférences et une copie des dernières données reçues (pour démarrer vite et consulter hors ligne) "
            "sont gardées sur ce PC. Les données du pays, elles, sont sur le serveur.",
        )
        card = Card(padding=20, spacing=12)
        card.body.addLayout(self._path_row("Dossier Syncron", self._host.app_paths.user_dir))
        card.body.addWidget(divider())
        self._cache_info = label("", "faint")
        clear = button("Vider le cache", "trash")
        clear.clicked.connect(self._clear_cache)
        cache_row = QHBoxLayout()
        cache_texts = QVBoxLayout()
        cache_texts.setSpacing(2)
        cache_texts.addWidget(label("Cache des données et des images", "heading"))
        cache_texts.addWidget(self._cache_info)
        cache_row.addLayout(cache_texts, 1)
        cache_row.addWidget(clear)
        card.body.addLayout(cache_row)
        layout.addWidget(card)
        layout.addStretch(1)
        self._add("storage", scroll)

    def _build_tools(self) -> None:
        scroll, layout = _section("Outils", "Les outils installés dans ce Syncron et leur version.")
        card = Card(padding=20, spacing=12)
        for tool in (t for t in self._registry if t.info.placement is Placement.TOOLS):
            row = QHBoxLayout()
            badge = QLabel()
            badge.setPixmap(icons.pixmap(tool.info.icon, COLORS.accent, 18))
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
            texts = QVBoxLayout()
            texts.setSpacing(2)
            texts.addWidget(label(tool.info.name, "heading"))
            texts.addWidget(label(tool.info.description, "faint", wrap=True))
            row.addLayout(texts, 1)
            if tool.info.stage is ToolStage.PLANNED:
                row.addWidget(Chip("En développement", "violet", "clock"))
            else:
                row.addWidget(Chip(f"v{tool.info.version}", "neutral"))
            card.body.addLayout(row)
        layout.addWidget(card)
        layout.addStretch(1)
        self._add("tools", scroll)

    def _build_about(self) -> None:
        scroll, layout = _section("À propos")
        card = Card(padding=20, spacing=8)
        card.body.addWidget(label(f"{APP_DISPLAY_NAME} {__version__}", "heading"))
        nation = self._host.session.nation_name
        card.body.addWidget(
            label(
                f"Logiciel interne de {nation or 'notre pays'}, réservé à ses membres. Connexion avec Discord : "
                "Syncron ne reçoit que ton identifiant, ton pseudo et ton avatar. Ton profil n'est visible que "
                "des membres connectés.",
                "muted",
                wrap=True,
            )
        )
        self.heart = HiddenHeart()
        self.heart.clicked.connect(self.loveRequested)
        card.body.addWidget(self.heart, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(card)
        layout.addStretch(1)
        self._add("about", scroll)

    # -- état ---------------------------------------------------------------------------------

    def refresh(self) -> None:
        """Rubrique affichée à jour ; le profil n'est rechargé que s'il n'a pas de modification en cours."""
        if self.current_section == "profile" and not self.profile.is_dirty():
            self.profile.refresh()
        session = self._host.session
        user = session.user or {}
        self._account_name.setText(session.display_name)
        details = [f"@{user['username']}"] if user.get("username") else ["Non connecté"]
        if user.get("created_at"):
            details.append(f"inscrit le {format_datetime(user['created_at'])[:10]}")
        self._account_details.setText(" · ".join(details))
        self._role_chip.set_content(session.role.label, "accent" if session.role.rank else "neutral", "shield")
        self._systems.clear()
        managed = [name for system, name in session.systems.items() if session.can_manage(system)]
        for name in managed:
            self._systems.add(Chip(name, "accent"))
        self._systems_empty.setVisible(not managed)
        online = "en ligne" if session.online else "hors ligne"
        revision = self._host.catalog.revision
        self._server_status.set_content(
            f"{online} · catalogue Craft révision {revision if revision >= 0 else '—'}",
            "success" if session.online else "warning",
            "check" if session.online else "wifi-off",
        )
        version = session.server_version
        self._server_version.setText(f"Serveur Syncron {version}" if version else "")
        self._cache_info.setText(f"{_folder_size(self._host.app_paths.cache_dir) // 1024} Ko")

    def _save_setting(self, key: str, value: Any) -> None:
        self._settings.set(key, value)
        try:
            self._settings.save()
        except OSError:
            self._host.notify("Préférence non enregistrée.", NotifyLevel.ERROR)

    def _apply_server(self) -> None:
        url = self._server_url.text().strip().rstrip("/")
        if not is_safe_server_url(url):
            self._host.notify(
                "Adresse refusée : elle doit commencer par https:// (connexion chiffrée).", NotifyLevel.ERROR
            )
            return
        if url == self._host.api.base_url:
            return
        self._settings.set(SERVER_URL_KEY, url)
        self._settings.save()
        self._host.notify("Nouvelle adresse enregistrée : reconnexion…", NotifyLevel.INFO)
        self.logoutRequested.emit()

    def _clear_cache(self) -> None:
        self._host.catalog.clear_cache()
        self.refresh()
        self._host.notify("Cache vidé : il sera reconstruit à la prochaine synchronisation.", NotifyLevel.SUCCESS)

    @staticmethod
    def _path_row(title: str, path: Path) -> QHBoxLayout:
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(title, "heading"))
        location = label(str(path), "faint")
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        texts.addWidget(location)
        open_button = button("Ouvrir", "folder")

        def open_folder() -> None:
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

        open_button.clicked.connect(open_folder)
        row = QHBoxLayout()
        row.addLayout(texts, 1)
        row.addWidget(open_button)
        return row


def _folder_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
