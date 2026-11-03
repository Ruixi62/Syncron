"""Design system : jetons de couleur (sombre et clair), typographie, feuille de style globale.

Tous les écrans (plateforme et outils) n'utilisent que ces jetons : changer l'identité
visuelle = modifier ce fichier. `COLORS` est un seul objet dont les valeurs changent avec
le thème (`use_palette`) ; les écrans le relisent quand la fenêtre est reconstruite.

Style « épuré » : fonds unis, cartes sans contour (léger liseré en clair), boutons et
champs sans bordure tant qu'on ne les survole pas, un seul accent turquoise.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
CHECK_IMAGE = (ASSETS_DIR / "check.svg").as_posix()
FONT_FAMILY = "Inter"
FALLBACK_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Ubuntu", "Cantarell", "Helvetica Neue", "Arial"]
THEME_KEY = "theme"


class ThemeMode(StrEnum):
    SYSTEM = "system"
    DARK = "dark"
    LIGHT = "light"
    FOREST = "forest"
    CHERRY = "cherry"
    CHRISTMAS = "christmas"

    @property
    def label(self) -> str:
        return {
            "system": "Système",
            "dark": "Sombre",
            "light": "Clair",
            "forest": "Forêt",
            "cherry": "Cerisier",
            "christmas": "Noël",
        }[self.value]

    @property
    def caption(self) -> str:
        return {
            "system": "Suit le mode sombre ou clair de ton ordinateur",
            "dark": "Nuit bleutée, accent turquoise",
            "light": "Gris doux, sans blanc éclatant",
            "forest": "Sombre aux reflets verts",
            "cherry": "Rose pâle de fleur de cerisier",
            "christmas": "Rouge, vert sapin et or, avec de la neige sur l'accueil",
        }[self.value]


@dataclass(slots=True)
class Palette:
    dark: bool = True
    festive: bool = False
    bg: str = "#0b0e14"
    sidebar: str = "#0d1118"
    surface: str = "#131823"
    surface_alt: str = "#1a2130"
    surface_hover: str = "#212a3c"
    border: str = "#1f2736"
    border_strong: str = "#2e384c"
    card_border: str = "transparent"
    text: str = "#e8ebf2"
    text_muted: str = "#8d96aa"
    text_faint: str = "#5d6679"
    accent: str = "#3fcfb8"
    accent_hover: str = "#62dcc8"
    accent_pressed: str = "#2bb19c"
    accent_text: str = "#03211c"
    accent_soft: str = "rgba(63, 207, 184, 0.13)"
    info: str = "#6ea8ff"
    info_soft: str = "rgba(110, 168, 255, 0.13)"
    success: str = "#93d46c"
    success_soft: str = "rgba(147, 212, 108, 0.13)"
    warning: str = "#f5a524"
    warning_soft: str = "rgba(245, 165, 36, 0.12)"
    danger: str = "#f2555a"
    danger_soft: str = "rgba(242, 85, 90, 0.12)"
    violet: str = "#a78bfa"
    violet_soft: str = "rgba(167, 139, 250, 0.12)"
    hero_start: str = "#0f2621"
    hero_end: str = "#0f1b29"
    brand_start: str = "#0f2a25"
    brand_mid: str = "#0d1520"
    brand_end: str = "#0b1a2a"
    shadow: str = "rgba(0, 0, 0, 0.35)"


DARK = Palette()
LIGHT = Palette(
    dark=False,
    bg="#e4e8ee",
    sidebar="#dbe0e7",
    surface="#f4f6f9",
    surface_alt="#eaedf2",
    surface_hover="#e0e4eb",
    border="#d4dae3",
    border_strong="#c0c8d3",
    card_border="#d6dce4",
    text="#1a202c",
    text_muted="#4e586a",
    text_faint="#7d8698",
    accent="#0f9883",
    accent_hover="#12ab93",
    accent_pressed="#0b8170",
    accent_text="#ffffff",
    accent_soft="rgba(15, 152, 131, 0.12)",
    info="#2d68d6",
    info_soft="rgba(45, 104, 214, 0.11)",
    success="#3a8a1e",
    success_soft="rgba(58, 138, 30, 0.12)",
    warning="#b06900",
    warning_soft="rgba(214, 135, 0, 0.13)",
    danger="#cf3a40",
    danger_soft="rgba(207, 58, 64, 0.11)",
    violet="#7050d0",
    violet_soft="rgba(112, 80, 208, 0.11)",
    hero_start="#d5ece7",
    hero_end="#dce4f1",
    brand_start="#d3ebe5",
    brand_mid="#e6ebf1",
    brand_end="#d9e3f0",
    shadow="rgba(16, 24, 40, 0.08)",
)
FOREST = Palette(
    dark=True,
    bg="#0b130f",
    sidebar="#0e1712",
    surface="#132019",
    surface_alt="#192920",
    surface_hover="#203327",
    border="#1d2d24",
    border_strong="#2b4134",
    card_border="transparent",
    text="#e3eee6",
    text_muted="#91a898",
    text_faint="#5d7365",
    accent="#5cd08a",
    accent_hover="#7ddca2",
    accent_pressed="#43b672",
    accent_text="#04200e",
    accent_soft="rgba(92, 208, 138, 0.14)",
    info="#6cb1e6",
    info_soft="rgba(108, 177, 230, 0.13)",
    success="#a7d878",
    success_soft="rgba(167, 216, 120, 0.13)",
    warning="#e8b04a",
    warning_soft="rgba(232, 176, 74, 0.12)",
    danger="#ee6461",
    danger_soft="rgba(238, 100, 97, 0.12)",
    violet="#b29ad9",
    violet_soft="rgba(178, 154, 217, 0.12)",
    hero_start="#14301f",
    hero_end="#10211a",
    brand_start="#14301f",
    brand_mid="#0f1a14",
    brand_end="#0f2219",
    shadow="rgba(0, 0, 0, 0.35)",
)
CHERRY = Palette(
    dark=False,
    bg="#f3e4ea",
    sidebar="#ecd8e0",
    surface="#fcf5f7",
    surface_alt="#f6e9ee",
    surface_hover="#efdce4",
    border="#e7d0da",
    border_strong="#d9b9c7",
    card_border="#e9d3dc",
    text="#2b1a21",
    text_muted="#6b525d",
    text_faint="#9c8490",
    accent="#cc4a7a",
    accent_hover="#da6690",
    accent_pressed="#b23b67",
    accent_text="#ffffff",
    accent_soft="rgba(204, 74, 122, 0.12)",
    info="#4b7bd1",
    info_soft="rgba(75, 123, 209, 0.11)",
    success="#45925a",
    success_soft="rgba(69, 146, 90, 0.12)",
    warning="#bb7718",
    warning_soft="rgba(187, 119, 24, 0.12)",
    danger="#c93847",
    danger_soft="rgba(201, 56, 71, 0.11)",
    violet="#8d63d1",
    violet_soft="rgba(141, 99, 209, 0.11)",
    hero_start="#f8d9e4",
    hero_end="#efe1f5",
    brand_start="#f6d5e1",
    brand_mid="#f9ecf1",
    brand_end="#eedff4",
    shadow="rgba(80, 20, 40, 0.08)",
)
CHRISTMAS = Palette(
    dark=True,
    festive=True,
    bg="#0d1411",
    sidebar="#101a15",
    surface="#15211b",
    surface_alt="#1b2a22",
    surface_hover="#23362b",
    border="#1f3027",
    border_strong="#2e4637",
    card_border="transparent",
    text="#f4efe4",
    text_muted="#b3ab9b",
    text_faint="#7c7566",
    accent="#e0464a",
    accent_hover="#ea6266",
    accent_pressed="#c53337",
    accent_text="#ffffff",
    accent_soft="rgba(224, 70, 74, 0.16)",
    info="#7db4e6",
    info_soft="rgba(125, 180, 230, 0.13)",
    success="#5cc27c",
    success_soft="rgba(92, 194, 124, 0.14)",
    warning="#e8c25a",
    warning_soft="rgba(232, 194, 90, 0.14)",
    danger="#ff6b6b",
    danger_soft="rgba(255, 107, 107, 0.13)",
    violet="#e8c25a",
    violet_soft="rgba(232, 194, 90, 0.13)",
    hero_start="#3b1517",
    hero_end="#123222",
    brand_start="#3b1517",
    brand_mid="#101a15",
    brand_end="#123222",
    shadow="rgba(0, 0, 0, 0.35)",
)
PALETTES: dict[ThemeMode, Palette] = {
    ThemeMode.DARK: DARK,
    ThemeMode.LIGHT: LIGHT,
    ThemeMode.FOREST: FOREST,
    ThemeMode.CHERRY: CHERRY,
    ThemeMode.CHRISTMAS: CHRISTMAS,
}

COLORS = replace(DARK)

# Variantes de pastilles (Chip) : (texte, fond) ; recalculées à chaque changement de thème.
TONES: dict[str, tuple[str, str]] = {}


def _refresh_tones() -> None:
    c = COLORS
    TONES.update(
        neutral=(c.text_muted, c.surface_alt),
        accent=(c.accent, c.accent_soft),
        info=(c.info, c.info_soft),
        success=(c.success, c.success_soft),
        warning=(c.warning, c.warning_soft),
        danger=(c.danger, c.danger_soft),
        violet=(c.violet, c.violet_soft),
    )


_refresh_tones()


def system_prefers_dark() -> bool:
    app = QGuiApplication.instance()
    if app is None:
        return True
    return app.styleHints().colorScheme() != Qt.ColorScheme.Light


def resolve_mode(mode: str | ThemeMode | None) -> ThemeMode:
    """Thème effectif : « Système » devient Sombre ou Clair selon le réglage de Windows / macOS / du bureau."""
    try:
        chosen = ThemeMode(mode or ThemeMode.SYSTEM)
    except ValueError:
        chosen = ThemeMode.SYSTEM
    if chosen is ThemeMode.SYSTEM:
        return ThemeMode.DARK if system_prefers_dark() else ThemeMode.LIGHT
    return chosen


def use_palette(mode: str | ThemeMode | None) -> ThemeMode:
    """Remplace les valeurs de COLORS (même objet partout) par celles du thème choisi."""
    resolved = resolve_mode(mode)
    source = PALETTES[resolved]
    for field in fields(Palette):
        setattr(COLORS, field.name, getattr(source, field.name))
    _refresh_tones()
    return resolved


def load_fonts() -> str:
    """Charge Inter embarquée ; retourne la famille effectivement utilisée."""
    loaded = False
    for font_file in sorted(FONTS_DIR.glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(font_file)) >= 0:
            loaded = True
    if loaded and FONT_FAMILY in QFontDatabase.families():
        return FONT_FAMILY
    available = set(QFontDatabase.families())
    return next((family for family in FALLBACK_FAMILIES if family in available), QFont().family())


_applied: dict[int, ThemeMode] = {}
_families: list[str] = []


def apply_theme(app: QApplication, mode: str | ThemeMode | None = ThemeMode.DARK) -> ThemeMode:
    """Applique le thème à toute l'application ; renvoie le thème effectif (sombre ou clair).
    Rien n'est refait si ce thème est déjà en place (la feuille de style se recalcule sur tous les widgets)."""
    resolved = use_palette(mode)
    if _applied.get(id(app)) is resolved:
        return resolved
    _applied[id(app)] = resolved
    if not _families:
        _families.append(load_fonts())
    family = _families[0]
    font = QFont(family)
    font.setPixelSize(13)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(stylesheet(family))
    return resolved


def _palette() -> QPalette:
    c = COLORS
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: c.bg,
        QPalette.ColorRole.WindowText: c.text,
        QPalette.ColorRole.Base: c.surface,
        QPalette.ColorRole.AlternateBase: c.surface_alt,
        QPalette.ColorRole.ToolTipBase: c.surface_alt,
        QPalette.ColorRole.ToolTipText: c.text,
        QPalette.ColorRole.Text: c.text,
        QPalette.ColorRole.Button: c.surface_alt,
        QPalette.ColorRole.ButtonText: c.text,
        QPalette.ColorRole.Highlight: c.accent,
        QPalette.ColorRole.HighlightedText: c.accent_text,
        QPalette.ColorRole.Link: c.accent,
        QPalette.ColorRole.PlaceholderText: c.text_faint,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c.text_faint))
    return palette


def stylesheet(family: str) -> str:
    c = COLORS
    return f"""
* {{ font-family: "{family}"; outline: 0; }}
QWidget {{ color: {c.text}; font-size: 13px; }}
QMainWindow, QDialog {{ background: {c.bg}; }}
QToolTip {{ background: {c.surface_alt}; color: {c.text}; border: 1px solid {c.border_strong};
           border-radius: 6px; padding: 6px 8px; }}

/* ---------- Typographie ---------- */
QLabel[role="display"] {{ font-size: 28px; font-weight: 700; }}
QLabel[role="title"] {{ font-size: 21px; font-weight: 650; }}
QLabel[role="heading"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="overline"] {{ color: {c.text_faint}; font-size: 11px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {c.text_muted}; }}
QLabel[role="faint"] {{ color: {c.text_faint}; font-size: 12px; }}
QLabel[role="stat"] {{ font-size: 22px; font-weight: 700; }}

/* ---------- Surfaces ---------- */
QFrame#Sidebar {{ background: {c.sidebar}; border: none; }}
QFrame#TopBar {{ background: {c.bg}; border: none; }}
QFrame[card="true"] {{ background: {c.surface}; border: 1px solid {c.card_border}; border-radius: 16px; }}
QFrame[card="flat"] {{ background: {c.surface_alt}; border: 1px solid {c.card_border}; border-radius: 12px; }}
QFrame#IconTile {{ background: {c.surface_alt}; border: 1px solid {c.border}; border-radius: 14px; }}
QFrame#Banner[tone="danger"] {{ background: {c.danger_soft}; border: 1px solid {c.danger}; border-radius: 10px; }}
QFrame#Banner[tone="warning"] {{ background: {c.warning_soft}; border: 1px solid {c.warning}; border-radius: 10px; }}
QFrame#Divider {{ background: {c.border}; max-height: 1px; min-height: 1px; border: none; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

/* ---------- Navigation latérale ---------- */
QPushButton#NavButton {{
    text-align: left; padding: 9px 12px; border: none; border-radius: 9px;
    color: {c.text_muted}; font-weight: 500; background: transparent;
}}
QPushButton#NavButton:hover {{ background: {c.surface_alt}; color: {c.text}; }}
QPushButton#NavButton:checked {{ background: {c.accent_soft}; color: {c.accent}; font-weight: 600; }}
QLabel#NavBadge {{ background: {c.danger}; color: white; border-radius: 8px; padding: 0 6px;
                   font-size: 11px; font-weight: 700; min-height: 16px; }}

/* ---------- Boutons ---------- */
QPushButton, QToolButton {{
    background: {c.surface_alt}; border: 1px solid transparent; border-radius: 10px;
    padding: 7px 14px; font-weight: 500; color: {c.text};
}}
QPushButton:hover, QToolButton:hover {{ background: {c.surface_hover}; border-color: {c.border}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {c.surface_alt}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {c.text_faint}; border-color: transparent;
                                              background: {c.surface_alt}; }}
QPushButton[variant="primary"] {{ background: {c.accent}; color: {c.accent_text}; border: 1px solid {c.accent};
                                  font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {c.accent_hover}; border-color: {c.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {c.accent_pressed}; }}
QPushButton[variant="primary"]:disabled {{ background: {c.surface_alt}; color: {c.text_faint};
                                           border-color: transparent; }}
QPushButton[variant="ghost"], QToolButton[variant="ghost"] {{ background: transparent; border-color: transparent; }}
QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover {{ background: {c.surface_alt};
                                                                          border-color: {c.border}; }}
QToolButton[variant="compact"] {{ background: transparent; border: 1px solid transparent; padding: 6px 9px;
                                  color: {c.text_muted}; }}
QToolButton[variant="compact"]:hover {{ background: {c.surface_alt}; border-color: {c.border}; color: {c.text}; }}
QToolButton[variant="icon"] {{ padding: 6px; border-radius: 8px; background: transparent; border-color: transparent; }}
QToolButton[variant="icon"]:hover {{ background: {c.surface_alt}; border-color: {c.border}; }}
QPushButton#SearchLauncher {{
    text-align: left; color: {c.text_faint}; background: {c.surface_alt}; border: 1px solid transparent;
    border-radius: 10px; padding: 7px 12px; min-width: 230px;
}}
QPushButton#SearchLauncher:hover {{ border-color: {c.border_strong}; color: {c.text_muted}; }}

/* ---------- Contrôle segmenté ---------- */
QFrame#Segmented {{ background: {c.surface_alt}; border: none; border-radius: 10px; }}
QPushButton#Segment {{ background: transparent; border: none; border-radius: 7px; padding: 6px 12px;
                       color: {c.text_muted}; font-weight: 500; }}
QPushButton#Segment:hover {{ color: {c.text}; }}
QPushButton#Segment:checked {{ background: {c.surface}; color: {c.text}; font-weight: 600; }}

/* ---------- Champs ---------- */
QLineEdit, QSpinBox, QComboBox, QDateEdit, QTimeEdit, QPlainTextEdit, QTextEdit {{
    background: {c.surface_alt}; border: 1px solid transparent; border-radius: 10px;
    padding: 7px 10px; selection-background-color: {c.accent}; selection-color: {c.accent_text};
}}
QPlainTextEdit, QTextEdit {{ padding: 6px 8px; }}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover, QDateEdit:hover, QTimeEdit:hover,
QPlainTextEdit:hover, QTextEdit:hover {{ border-color: {c.border_strong}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {c.accent}; }}
QLineEdit:read-only {{ color: {c.text_muted}; }}
QDateEdit::drop-down {{ border: none; width: 22px; }}
QDateEdit::up-button, QDateEdit::down-button, QTimeEdit::up-button, QTimeEdit::down-button {{ width: 0; border: none; }}
QCalendarWidget QWidget {{ alternate-background-color: {c.surface}; }}
QCalendarWidget QToolButton {{ border: none; background: transparent; padding: 4px 8px; }}
QCalendarWidget QAbstractItemView {{ selection-background-color: {c.accent}; selection-color: {c.accent_text}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {c.border_strong};
                        background: {c.surface_alt}; }}
QCheckBox::indicator:hover {{ border-color: {c.text_faint}; }}
QCheckBox::indicator:checked {{ background: {c.accent}; border-color: {c.accent}; image: url("{CHECK_IMAGE}"); }}
QCheckBox::indicator:disabled {{ background: transparent; border: 1px dashed {c.border_strong}; }}
QCheckBox::indicator:checked:disabled {{ background: {c.accent_soft}; border: 1px solid {c.accent_soft}; }}
QCheckBox:disabled {{ color: {c.text_faint}; }}
QProgressBar {{ background: {c.surface_alt}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px;
                text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {c.accent}; border-radius: 4px; }}
QListWidget::item:hover {{ background: {c.surface_alt}; }}
QListWidget::item:selected {{ background: {c.surface_hover}; color: {c.text}; }}
QLineEdit[size="large"] {{ font-size: 15px; padding: 11px 12px; border-radius: 11px; }}
QSpinBox {{ padding: 4px 8px; }}
QSpinBox#Quantity {{ font-size: 15px; font-weight: 600; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QSpinBox::up-arrow, QSpinBox::down-arrow {{ image: none; width: 0; height: 0; }}
QSpinBox QLineEdit, QComboBox QLineEdit {{ background: transparent; border: none; padding: 0; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {c.surface_alt}; border: 1px solid {c.border_strong};
    border-radius: 8px; padding: 4px; selection-background-color: {c.surface_hover}; selection-color: {c.text}; }}

/* ---------- Listes, tableaux, arbres ---------- */
QListView, QTableView, QTreeView {{
    background: transparent; border: none; alternate-background-color: transparent;
    selection-background-color: {c.surface_hover}; selection-color: {c.text};
}}
QTableView::item, QTreeView::item {{ padding: 0 8px; border-bottom: 1px solid {c.border}; }}
QTableView::item:selected, QTreeView::item:selected {{ background: {c.surface_hover}; color: {c.text}; }}
QTableView::item:hover, QTreeView::item:hover {{ background: {c.surface_alt}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: transparent; color: {c.text_faint}; border: none; border-bottom: 1px solid {c.border};
    padding: 8px; font-size: 11px; font-weight: 600;
}}
QTableCornerButton::section {{ background: transparent; border: none; }}

/* ---------- Barres de défilement ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {c.border_strong}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {c.text_faint}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none; width: 0; height: 0; }}

QSplitter::handle {{ background: transparent; width: 12px; }}
QMenu {{ background: {c.surface_alt}; border: 1px solid {c.border_strong}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c.surface_hover}; }}
QMessageBox QLabel {{ color: {c.text}; }}
"""
