"""Design system : jetons de couleur, typographie, feuille de style globale.

Tous les écrans (plateforme et outils) n'utilisent que ces jetons :
changer l'identité visuelle = modifier ce fichier.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
CHECK_IMAGE = (ASSETS_DIR / "check.svg").as_posix()
FONT_FAMILY = "Inter"
FALLBACK_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Ubuntu", "Cantarell", "Helvetica Neue", "Arial"]


@dataclass(frozen=True, slots=True)
class Palette:
    bg: str = "#0b0e14"
    sidebar: str = "#0e1219"
    surface: str = "#131823"
    surface_alt: str = "#181f2d"
    surface_hover: str = "#1d2536"
    border: str = "#222a3a"
    border_strong: str = "#2e384c"
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


COLORS = Palette()

# Variantes de pastilles (Chip) : (texte, fond)
TONES: dict[str, tuple[str, str]] = {
    "neutral": (COLORS.text_muted, COLORS.surface_alt),
    "accent": (COLORS.accent, COLORS.accent_soft),
    "info": (COLORS.info, COLORS.info_soft),
    "success": (COLORS.success, COLORS.success_soft),
    "warning": (COLORS.warning, COLORS.warning_soft),
    "danger": (COLORS.danger, COLORS.danger_soft),
    "violet": (COLORS.violet, COLORS.violet_soft),
}


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


def apply_theme(app: QApplication) -> None:
    family = load_fonts()
    font = QFont(family)
    font.setPixelSize(13)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(stylesheet(family))


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
QLabel[role="display"] {{ font-size: 26px; font-weight: 700; }}
QLabel[role="title"] {{ font-size: 20px; font-weight: 600; }}
QLabel[role="heading"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="overline"] {{ color: {c.text_faint}; font-size: 11px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {c.text_muted}; }}
QLabel[role="faint"] {{ color: {c.text_faint}; font-size: 12px; }}
QLabel[role="stat"] {{ font-size: 22px; font-weight: 700; }}

/* ---------- Surfaces ---------- */
QFrame#Sidebar {{ background: {c.sidebar}; border-right: 1px solid {c.border}; }}
QFrame#TopBar {{ background: {c.bg}; border-bottom: 1px solid {c.border}; }}
QFrame[card="true"] {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 14px; }}
QFrame[card="flat"] {{ background: {c.surface_alt}; border: 1px solid {c.border}; border-radius: 12px; }}
QFrame#IconTile {{ background: {c.surface_alt}; border: 1px solid {c.border_strong}; border-radius: 14px; }}
QFrame#Banner[tone="danger"] {{ background: {c.danger_soft}; border: 1px solid {c.danger}; border-radius: 10px; }}
QFrame#Banner[tone="warning"] {{ background: {c.warning_soft}; border: 1px solid {c.warning}; border-radius: 10px; }}
QFrame#Divider {{ background: {c.border}; max-height: 1px; min-height: 1px; border: none; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

/* ---------- Navigation latérale ---------- */
QPushButton#NavButton {{
    text-align: left; padding: 9px 12px; border: none; border-radius: 9px;
    color: {c.text_muted}; font-weight: 500; background: transparent;
}}
QPushButton#NavButton:hover {{ background: {c.surface}; color: {c.text}; }}
QPushButton#NavButton:checked {{ background: {c.accent_soft}; color: {c.accent}; font-weight: 600; }}
QLabel#NavBadge {{ background: {c.danger}; color: white; border-radius: 8px; padding: 0 6px;
                   font-size: 11px; font-weight: 700; min-height: 16px; }}

/* ---------- Boutons ---------- */
QPushButton, QToolButton {{
    background: {c.surface_alt}; border: 1px solid {c.border_strong}; border-radius: 9px;
    padding: 7px 14px; font-weight: 500; color: {c.text};
}}
QPushButton:hover, QToolButton:hover {{ background: {c.surface_hover}; border-color: {c.text_faint}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {c.surface}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {c.text_faint}; border-color: {c.border};
                                              background: {c.surface}; }}
QPushButton[variant="primary"] {{ background: {c.accent}; color: {c.accent_text}; border: 1px solid {c.accent};
                                  font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {c.accent_hover}; border-color: {c.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {c.accent_pressed}; }}
QPushButton[variant="ghost"], QToolButton[variant="ghost"] {{ background: transparent; border-color: transparent; }}
QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover {{ background: {c.surface_alt};
                                                                          border-color: {c.border}; }}
QToolButton[variant="compact"] {{ background: transparent; border: 1px solid transparent; padding: 6px 9px;
                                  color: {c.text_muted}; }}
QToolButton[variant="compact"]:hover {{ background: {c.surface_alt}; border-color: {c.border}; color: {c.text}; }}
QToolButton[variant="icon"] {{ padding: 6px; border-radius: 8px; background: transparent; border-color: transparent; }}
QToolButton[variant="icon"]:hover {{ background: {c.surface_alt}; border-color: {c.border}; }}
QPushButton#SearchLauncher {{
    text-align: left; color: {c.text_faint}; background: {c.surface}; border: 1px solid {c.border};
    border-radius: 10px; padding: 7px 12px; min-width: 230px;
}}
QPushButton#SearchLauncher:hover {{ border-color: {c.border_strong}; color: {c.text_muted}; }}

/* ---------- Contrôle segmenté ---------- */
QFrame#Segmented {{ background: {c.surface_alt}; border: 1px solid {c.border}; border-radius: 10px; }}
QPushButton#Segment {{ background: transparent; border: none; border-radius: 7px; padding: 6px 12px;
                       color: {c.text_muted}; font-weight: 500; }}
QPushButton#Segment:hover {{ color: {c.text}; }}
QPushButton#Segment:checked {{ background: {c.surface_hover}; color: {c.text}; font-weight: 600; }}

/* ---------- Champs ---------- */
QLineEdit, QSpinBox, QComboBox, QDateEdit, QTimeEdit, QPlainTextEdit, QTextEdit {{
    background: {c.surface_alt}; border: 1px solid {c.border}; border-radius: 9px;
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
QCheckBox::indicator:disabled {{ background: {c.surface}; border-color: {c.border}; }}
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
    background: transparent; color: {c.text_faint}; border: none; border-bottom: 1px solid {c.border_strong};
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
