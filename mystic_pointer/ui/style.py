"""Adwaita-inspired visual system for Mystic Pointer.

The overlay is a dark GNOME popover so it reads clearly over a dimmed desktop,
while the preferences window follows the system light/dark preference.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

ACCENT = "#3584e4"
ACCENT_HOVER = "#1c71d8"
ACCENT_PRESSED = "#1a5fb4"

LIGHT_THEME = {
    "window_bg": "#fafafa",
    "card_bg": "#ffffff",
    "card_border": "#deddda",
    "text": "#2e3436",
    "secondary": "#77767b",
    "border": "#c0bfbc",
    "input_bg": "#ffffff",
    "hover_bg": "#f6f5f4",
    "pressed_bg": "#ebebeb",
    "accent": ACCENT,
    "accent_hover": ACCENT_HOVER,
    "accent_pressed": ACCENT_PRESSED,
    "accent_text": "#ffffff",
    "destructive": "#c01c28",
    "warning": "#c64600",
    "separator": "#f0efed",
    "disabled_text": "#9a9996",
    "scrollbar": "#c0bfbc",
    "scrollbar_hover": "#9a9996",
    "sidebar_bg": "#ebebeb",
    "sidebar_hover": "rgba(255, 255, 255, 0.55)",
    "sidebar_selected_bg": "#ffffff",
    "sidebar_selected_text": "#1a5fb4",
    "flat_hover": "rgba(53, 132, 228, 0.10)",
    "tooltip_bg": "#242424",
    "tooltip_text": "#ffffff",
}

DARK_THEME = {
    "window_bg": "#242424",
    "card_bg": "#303030",
    "card_border": "#3d3d3d",
    "text": "#ffffff",
    "secondary": "#b5b3b0",
    "border": "#5e5c64",
    "input_bg": "#1e1e1e",
    "hover_bg": "#3d3d3d",
    "pressed_bg": "#2a2a2a",
    "accent": ACCENT,
    "accent_hover": ACCENT_HOVER,
    "accent_pressed": ACCENT_PRESSED,
    "accent_text": "#ffffff",
    "destructive": "#ff7b72",
    "warning": "#ffbe6f",
    "separator": "#3d3d3d",
    "disabled_text": "#77767b",
    "scrollbar": "#5e5c64",
    "scrollbar_hover": "#77767b",
    "sidebar_bg": "#1e1e1e",
    "sidebar_hover": "rgba(255, 255, 255, 0.06)",
    "sidebar_selected_bg": "#3d3d3d",
    "sidebar_selected_text": "#ffffff",
    "flat_hover": "rgba(53, 132, 228, 0.16)",
    "tooltip_bg": "#1e1e1e",
    "tooltip_text": "#ffffff",
}


FLOATING_PANEL_STYLE = """
QFrame#MysticFloatingPanel {
    background-color: rgba(36, 36, 36, 0.98);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
}

QLabel {
    color: #ffffff;
    font-family: 'Cantarell', 'Inter', 'Noto Sans', 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 13px;
    background: transparent;
}

QLineEdit#PromptInput {
    background-color: #303030;
    border: 1px solid #5e5c64;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 22px;
    color: #ffffff;
    selection-background-color: #3584e4;
    selection-color: #ffffff;
}

QLineEdit#PromptInput:focus {
    border: 2px solid #3584e4;
    padding: 7px 11px;
}

QPushButton {
    background-color: #303030;
    color: #ffffff;
    border: 1px solid #5e5c64;
    border-radius: 8px;
    padding: 6px 12px;
    font-family: 'Cantarell', 'Inter', 'Noto Sans', 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 12px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #3d3d3d;
}

QPushButton:pressed {
    background-color: #2a2a2a;
}

QPushButton:disabled {
    color: #77767b;
    border-color: #3d3d3d;
    background-color: #2a2a2a;
}

QPushButton#SendButton {
    background-color: #3584e4;
    color: #ffffff;
    border: none;
    padding: 0;
    min-height: 34px;
    min-width: 64px;
}

QPushButton#SendButton:hover {
    background-color: #1c71d8;
}

QPushButton#SendButton:pressed {
    background-color: #1a5fb4;
}

QPushButton#SuggestionChip {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 500;
    color: #deddda;
}

QPushButton#SuggestionChip:hover {
    background-color: rgba(53, 132, 228, 0.20);
    border-color: #3584e4;
    color: #ffffff;
}

QPushButton#AddButton {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 8px;
    color: #deddda;
    padding: 4px 9px;
    font-size: 11px;
}

QPushButton#AddButton:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #ffffff;
}

QPushButton#AddButton:checked {
    background: rgba(53, 132, 228, 0.30);
    border-color: #3584e4;
    color: #ffffff;
}

QPushButton#AddButton:checked:hover {
    background: rgba(53, 132, 228, 0.40);
}

QPushButton#AddButton:pressed {
    background: rgba(53, 132, 228, 0.50);
    border-color: #78aeed;
}

QFrame#AddHint {
    background-color: rgba(53, 132, 228, 0.14);
    border: 1px solid rgba(53, 132, 228, 0.55);
    border-radius: 8px;
}

QLabel#AddHintDot {
    color: #78aeed;
    font-size: 9px;
}

QLabel#AddHintLabel {
    color: #deddda;
    font-size: 11px;
}

QPushButton#CloseButton, QPushButton#RemoveButton, QPushButton#CopyButton {
    background: transparent;
    border: none;
    color: #b5b3b0;
    padding: 2px;
    font-size: 12px;
}

QPushButton#CloseButton:hover, QPushButton#RemoveButton:hover {
    background: rgba(255, 255, 255, 0.10);
    color: #ffffff;
}

QPushButton#CloseButton {
    border-radius: 8px;
}

QPushButton#RemoveButton {
    border-radius: 5px;
    font-size: 14px;
}

QPushButton#CopyButton {
    color: #deddda;
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 6px;
}

QPushButton#CopyButton:hover {
    background: rgba(255, 255, 255, 0.10);
    color: #ffffff;
}

QFrame#ThumbnailChip {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
}

QLabel#ThumbnailLabel {
    font-size: 11px;
    font-weight: 600;
    color: #deddda;
}

QLabel#ThumbnailMore {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 700;
    color: #b5b3b0;
}

QFrame#ResponseCard {
    background: transparent;
    border: none;
    border-top: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 0;
}

QLabel#ResponseMeta {
    color: #b5b3b0;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}

QTextEdit#ResponseText {
    background: transparent;
    border: none;
    padding: 0;
    color: #f6f5f4;
    font-family: 'Cantarell', 'Inter', 'Noto Sans', 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 13px;
    selection-background-color: #3584e4;
    selection-color: #ffffff;
}

QTextEdit#ResponseText:focus {
    border: none;
}

QLabel#ErrorLabel {
    color: #ff7b72;
    font-size: 12px;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.20);
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 0.32);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QToolTip {
    background-color: #1e1e1e;
    color: #ffffff;
    border: 1px solid #5e5c64;
    border-radius: 6px;
    padding: 5px 8px;
}
"""


RESPONSE_DOCUMENT_STYLE = """
p {
    margin-top: 0px;
    margin-bottom: 6px;
}

h1, h2, h3, h4, h5, h6 {
    color: #ffffff;
    font-weight: 700;
    margin-top: 6px;
    margin-bottom: 4px;
}

h1 { font-size: 17px; }
h2 { font-size: 16px; }
h3 { font-size: 15px; }
h4, h5, h6 { font-size: 14px; }

ul, ol {
    margin-top: 0px;
    margin-bottom: 6px;
    -qt-list-indent: 1;
}

li {
    margin-top: 0px;
    margin-bottom: 2px;
}

pre {
    background-color: #2a2a2a;
    color: #f6f5f4;
    font-family: 'DejaVu Sans Mono', 'Noto Sans Mono', monospace;
    font-size: 12px;
    margin-top: 2px;
    margin-bottom: 8px;
}

code {
    background-color: #3a3a3a;
    color: #f6f5f4;
    font-family: 'DejaVu Sans Mono', 'Noto Sans Mono', monospace;
    font-size: 12px;
}

blockquote {
    color: #b5b3b0;
    margin-left: 12px;
    margin-top: 0px;
    margin-bottom: 6px;
    -qt-block-indent: 1;
}

a {
    color: #78aeed;
    text-decoration: none;
}

table {
    border-collapse: collapse;
    margin-top: 2px;
    margin-bottom: 8px;
}

th {
    background-color: #3a3a3a;
    font-weight: 700;
    padding: 4px 8px;
    border: 1px solid #5e5c64;
}

td {
    padding: 4px 8px;
    border: 1px solid #5e5c64;
}
"""


_SETTINGS_TEMPLATE = """
QDialog {
    background-color: %(window_bg)s;
    color: %(text)s;
    font-family: 'Cantarell', 'Inter', 'Noto Sans', 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 14px;
}

QWidget {
    color: %(text)s;
    font-family: 'Cantarell', 'Inter', 'Noto Sans', 'Segoe UI', 'DejaVu Sans', sans-serif;
}

QLabel {
    background: transparent;
    color: %(text)s;
}

QLabel#Title {
    font-size: 24px;
    font-weight: 700;
}

QLabel#Subtitle {
    font-size: 13px;
    color: %(secondary)s;
}

QLabel#SectionTitle {
    font-size: 12px;
    font-weight: 700;
    color: %(secondary)s;
    padding-left: 4px;
}

QLabel#RowTitle {
    font-size: 14px;
    font-weight: 600;
}

QLabel#RowSubtitle {
    font-size: 12px;
    color: %(secondary)s;
}

QLabel#HintLabel {
    font-size: 11px;
    color: %(secondary)s;
}

QLabel#ValueLabel {
    font-size: 13px;
    font-weight: 700;
    color: %(accent)s;
}

QLabel#ValueLabel:disabled {
    color: %(disabled_text)s;
}

QLabel#StatusLabel {
    font-size: 12px;
    color: %(secondary)s;
}

QLabel#StatusLabel[error="true"] {
    color: %(destructive)s;
}

QLabel#WarningLabel {
    font-size: 12px;
    color: %(warning)s;
}

QFrame#Card {
    background-color: %(card_bg)s;
    border: 1px solid %(card_border)s;
    border-radius: 12px;
}

QFrame#Separator {
    background-color: %(separator)s;
    border: none;
    min-height: 1px;
    max-height: 1px;
}

QListWidget#Sidebar {
    background-color: %(sidebar_bg)s;
    border: none;
    border-radius: 12px;
    padding: 6px;
    outline: none;
}

QListWidget#Sidebar::item {
    color: %(text)s;
    border-radius: 8px;
    padding: 9px 12px;
    margin: 1px 0;
}

QListWidget#Sidebar::item:selected {
    background-color: %(sidebar_selected_bg)s;
    color: %(sidebar_selected_text)s;
    font-weight: 700;
}

QListWidget#Sidebar:focus {
    border: 1px solid %(accent)s;
}

QListWidget#Sidebar::item:hover:!selected {
    background-color: %(sidebar_hover)s;
}

QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}

QWidget#PageContent {
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: %(scrollbar)s;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: %(scrollbar_hover)s;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QLineEdit, QComboBox, QSpinBox {
    background-color: %(input_bg)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 7px 10px;
    min-height: 20px;
    color: %(text)s;
    selection-background-color: %(accent)s;
    selection-color: %(accent_text)s;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 2px solid %(accent)s;
    padding: 6px 9px;
}

QLineEdit:disabled, QComboBox:disabled {
    color: %(disabled_text)s;
    background-color: %(window_bg)s;
}

QComboBox {
    padding-right: 30px;
}

QComboBox:focus {
    padding-right: 29px;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QComboBox::down-arrow {
    image: none;
}

QComboBox QAbstractItemView {
    background-color: %(card_bg)s;
    border: 1px solid %(card_border)s;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: %(accent)s;
    selection-color: %(accent_text)s;
    outline: none;
}

QPushButton {
    background-color: %(card_bg)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 7px 14px;
    min-height: 20px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: %(hover_bg)s;
}

QPushButton:pressed {
    background-color: %(pressed_bg)s;
}

QPushButton:disabled {
    color: %(disabled_text)s;
    border-color: %(card_border)s;
    background-color: %(window_bg)s;
}

QPushButton[suggested="true"] {
    background-color: %(accent)s;
    color: %(accent_text)s;
    border: none;
}

QPushButton[suggested="true"]:hover {
    background-color: %(accent_hover)s;
}

QPushButton[suggested="true"]:pressed {
    background-color: %(accent_pressed)s;
}

QPushButton[flat="true"] {
    background: transparent;
    border: none;
    color: %(accent)s;
    padding: 6px 8px;
}

QPushButton[flat="true"]:hover {
    background-color: %(flat_hover)s;
}

QPushButton[flat="true"]:disabled {
    color: %(disabled_text)s;
    background: transparent;
}

QSlider::groove:horizontal {
    height: 4px;
    background: %(border)s;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: %(accent)s;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: %(card_bg)s;
    border: 1px solid %(border)s;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: %(hover_bg)s;
}

QSlider::handle:horizontal:disabled {
    background: %(window_bg)s;
    border-color: %(card_border)s;
}

QSlider::groove:horizontal:disabled {
    background: %(card_border)s;
}

QSlider::sub-page:horizontal:disabled {
    background: %(border)s;
}

QToolTip {
    background-color: %(tooltip_bg)s;
    color: %(tooltip_text)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 5px 8px;
}

QMessageBox {
    background-color: %(window_bg)s;
}
"""


def settings_stylesheet(dark: bool = False) -> str:
    """Return the Adwaita light or dark stylesheet for the preferences window."""
    return _SETTINGS_TEMPLATE % (DARK_THEME if dark else LIGHT_THEME)


def tray_menu_stylesheet(dark: bool = False) -> str:
    """Adwaita popover styling for the status-area menu."""
    colors = DARK_THEME if dark else LIGHT_THEME
    template = """
QMenu {
    background-color: %(card_bg)s;
    color: %(text)s;
    border: 1px solid %(card_border)s;
    border-radius: 10px;
    padding: 6px;
    font-family: 'Cantarell', 'Inter', 'Noto Sans', 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 13px;
}
QMenu::item {
    padding: 8px 28px 8px 14px;
    border-radius: 6px;
}
QMenu::item:selected {
    background-color: %(accent)s;
    color: %(accent_text)s;
}
QMenu::item:disabled {
    color: %(disabled_text)s;
}
QMenu::separator {
    height: 1px;
    background: %(separator)s;
    margin: 4px 8px;
}
"""
    return template % colors


def settings_palette(dark: bool = False) -> QPalette:
    """Match Qt's native sub-controls (arrows, message boxes) to the theme."""
    colors = DARK_THEME if dark else LIGHT_THEME
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["window_bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["input_bg"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["hover_bg"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["card_bg"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["tooltip_bg"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["tooltip_text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["accent_text"]))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(colors["disabled_text"]),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(colors["disabled_text"]),
    )
    return palette


def system_is_dark() -> bool:
    """Best-effort read of the desktop's light/dark preference."""
    app = QGuiApplication.instance()
    if not isinstance(app, QGuiApplication):
        return False
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
