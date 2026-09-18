"""Colours, fonts and small reusable widgets shared by every page (taken from the design mockups)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

# --- palette ------------------------------------------------------------------
NAVY = "#0e1e3a"
NAVY_DIM = "#0a1529"
ACCENT = "#2c64b0"
ACCENT_DARK = "#1d4a86"
BG = "#eef1f5"
PANEL = "#ffffff"
PANEL_ALT = "#f6f8fb"
BORDER = "#d5dbe3"
BORDER_SOFT = "#e3e7ee"
BORDER_INPUT = "#b9c2cf"
TEXT = "#16202e"
TEXT_MUTED = "#4a5566"
TEXT_SOFT = "#3b4556"
DASH = "#8e9bb0"
ERROR = "#b42318"
ERROR_BG = "#fdf2f1"
ERROR_BORDER = "#f1c4bf"
OK_GREEN = "#1e6b34"

# folder level colours: (background, foreground).  Levels beyond three cycle through the palette.
LEVEL_COLORS = [("#dcefd9", "#235c2a"), ("#f6dcef", "#7a2463"), ("#d6ebf7", "#1c5a86"), ("#fbe8cf", "#7a4a12"), ("#e6dcf6", "#4b2a7a")]
REPLICATE_COLORS = ("#e8ebf0", "#3b4556")
BLOCKED_COLORS = ("#e8ebf0", "#8a93a3")

SERIES_COLORS = [("Blue", "#2c7fd4"), ("Black", "#16202e"), ("Red", "#c8372d"), ("Green", "#1e6b34"), ("Orange", "#e0781c"),
                 ("Purple", "#6f42c1"), ("Teal", "#0f8b8d"), ("Grey", "#8a93a3")]
SERIES_MARKERS = [("● Circle", "o"), ("■ Square", "s"), ("▲ Triangle", "^"), ("◆ Diamond", "D"), ("▼ Triangle down", "v"), ("None", "None")]

SANS = "IBM Plex Sans"
MONO = "IBM Plex Mono"


def level_colors(level: int):
    """1-based folder level -> (background, foreground)."""
    return LEVEL_COLORS[(level - 1) % len(LEVEL_COLORS)]


def load_fonts() -> None:
    """Register the bundled IBM Plex fonts (SIL OFL); silently keeps the system font when they are missing."""
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    if not os.path.isdir(here):
        return
    for fn in sorted(os.listdir(here)):
        if fn.lower().endswith((".ttf", ".otf")):
            QFontDatabase.addApplicationFont(os.path.join(here, fn))


def _asset(name: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name).replace("\\", "/")


def app_stylesheet() -> str:
    check, chevron, radio = _asset("check.svg"), _asset("chevron.svg"), _asset("radio.svg")
    return f"""
    QWidget {{ font-family: "{SANS}", "Segoe UI", system-ui, sans-serif; font-size: 14px; color: {TEXT}; }}
    QMainWindow, QDialog {{ background: {BG}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        min-height: 34px; max-height: 34px; padding: 0 10px; border: 1px solid {BORDER_INPUT}; border-radius: 6px; background: {PANEL}; color: {TEXT};
        selection-background-color: {ACCENT}; selection-color: white;
    }}
    QComboBox {{ padding-right: 24px; }}
    QComboBox:hover {{ border-color: {ACCENT}; }}
    QComboBox:on {{ border-color: {ACCENT}; }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
    QLineEdit[mono="true"] {{ font-family: "{MONO}", monospace; }}
    QLineEdit:disabled, QComboBox:disabled {{ color: {DASH}; background: {PANEL_ALT}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; margin-right: 8px; }}
    QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDER_INPUT}; border-radius: 6px; padding: 4px; outline: 0;
        selection-background-color: {ACCENT}; selection-color: white; }}
    QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 2px 8px; border-radius: 4px; }}
    QComboBox QAbstractItemView::item:hover {{ background: {PANEL_ALT}; }}
    QPushButton {{ min-height: 42px; padding: 0 20px; border-radius: 8px; border: 1px solid {BORDER_INPUT}; background: {PANEL}; color: {TEXT}; font-weight: 500; }}
    QPushButton:hover {{ background: {PANEL_ALT}; }}
    QPushButton:pressed {{ background: {BORDER_SOFT}; }}
    QPushButton:disabled {{ color: {DASH}; border-color: {BORDER_SOFT}; }}
    QPushButton[primary="true"] {{ background: {ACCENT}; color: white; border: none; font-weight: 600; padding: 0 28px; }}
    QPushButton[primary="true"]:hover {{ background: {ACCENT_DARK}; }}
    QPushButton[primary="true"]:disabled {{ background: #9fb6d6; color: white; }}
    QPushButton[outline="true"] {{ background: {PANEL}; color: {ACCENT}; border: 1px solid {ACCENT}; font-weight: 600; padding: 0 24px; }}
    QPushButton[outline="true"]:hover {{ background: #f0f5fb; }}
    QPushButton[small="true"] {{ min-height: 38px; padding: 0 16px; }}
    QPushButton[tiny="true"] {{ height: 22px; min-height: 22px; max-height: 22px; width: 22px; min-width: 22px; max-width: 22px; padding: 0; border: none; background: {BG}; color: {TEXT_SOFT}; font-size: 13px; font-weight: 600; border-radius: 5px; }}
    QPushButton[tiny="true"]:hover {{ background: {BORDER_SOFT}; color: {ERROR}; }}
    QPushButton[segment="true"] {{ min-height: 38px; padding: 0 20px; border: none; border-radius: 0; background: {PANEL}; color: {TEXT}; font-weight: 500; }}
    QPushButton[segment="true"][compact="true"] {{ padding: 0 12px; font-size: 13px; }}
    QPushButton[segment="true"]:checked {{ background: {NAVY}; color: white; font-weight: 600; }}
    QPushButton[tab="true"] {{ min-height: 38px; padding: 0 20px; border: none; border-bottom: 3px solid transparent; border-radius: 0; background: {PANEL}; color: {TEXT_MUTED}; font-weight: 500; }}
    QPushButton[tab="true"]:checked {{ border-bottom: 3px solid {ACCENT}; color: {TEXT}; font-weight: 600; }}
    QPushButton[link="true"] {{ min-height: 34px; padding: 0 14px; }}
    QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER_INPUT}; border-radius: 3px; background: {PANEL}; }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url("{check}"); }}
    QCheckBox::indicator:disabled {{ border-color: {BORDER_SOFT}; background: {PANEL_ALT}; }}
    QRadioButton::indicator {{ width: 16px; height: 16px; border: none; background: transparent; }}
    QRadioButton::indicator:unchecked {{ border: 1px solid {BORDER_INPUT}; border-radius: 8px; background: {PANEL}; width: 14px; height: 14px; }}
    QRadioButton::indicator:checked {{ image: url("{radio}"); }}
    QRadioButton:disabled, QCheckBox:disabled {{ color: {DASH}; }}
    QFrame[panel="true"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
    QFrame[subpanel="true"] {{ background: {PANEL_ALT}; border: 1px solid {BORDER_SOFT}; border-radius: 8px; }}
    QFrame[hline="true"] {{ background: {BORDER_SOFT}; max-height: 1px; min-height: 1px; border: none; }}
    QLabel[section="true"] {{ font-size: 12px; font-weight: 600; letter-spacing: 1px; color: {TEXT_MUTED}; }}
    QLabel[muted="true"] {{ color: {TEXT_MUTED}; }}
    QLabel[muted13="true"] {{ color: {TEXT_MUTED}; font-size: 13px; }}
    QLabel[bold="true"] {{ font-weight: 600; }}
    QLabel[h1="true"] {{ font-size: 26px; font-weight: 600; }}
    QLabel[h2="true"] {{ font-size: 20px; font-weight: 600; }}
    QLabel[h3="true"] {{ font-size: 15px; font-weight: 600; }}
    QLabel[mono="true"] {{ font-family: "{MONO}", monospace; font-size: 12px; color: {TEXT_SOFT}; }}
    QTreeWidget {{ border: none; background: {PANEL}; outline: 0; }}
    QTreeWidget::item {{ height: 26px; }}
    QTreeWidget::item:selected {{ background: transparent; }}
    QTableView {{ border: 1px solid {BORDER}; background: {PANEL}; gridline-color: {BORDER_SOFT}; font-family: "{MONO}", monospace; font-size: 12px; }}
    QHeaderView::section {{ background: {PANEL_ALT}; border: none; border-bottom: 1px solid {BORDER}; border-right: 1px solid {BORDER_SOFT}; padding: 4px 8px; font-weight: 600; font-family: "{SANS}"; font-size: 12px; }}
    QTableCornerButton::section {{ background: {PANEL_ALT}; border: none; border-bottom: 1px solid {BORDER}; border-right: 1px solid {BORDER_SOFT}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: {BORDER_INPUT}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ height: 10px; background: transparent; }}
    QScrollBar::handle:horizontal {{ background: {BORDER_INPUT}; border-radius: 5px; min-width: 30px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QProgressBar {{ border: none; background: {BORDER_SOFT}; border-radius: 4px; height: 8px; max-height: 8px; text-align: center; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
    QToolTip {{ background: {NAVY}; color: white; border: none; padding: 6px; }}
    QTextBrowser {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; padding: 12px; }}
    QTabWidget::pane {{ border: none; }}
    """


# --- small helpers ------------------------------------------------------------
def set_prop(w: QWidget, name: str, value=True) -> QWidget:
    w.setProperty(name, value)
    w.style().unpolish(w)
    w.style().polish(w)
    return w


def label(text: str, **props) -> QLabel:
    lab = QLabel(text)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse) if props.pop("selectable", False) else None
    for k, v in props.items():
        lab.setProperty(k, v)
    return lab


def section_label(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setProperty("section", True)
    return lab


def hline() -> QFrame:
    f = QFrame()
    f.setProperty("hline", True)
    f.setFrameShape(QFrame.NoFrame)
    return f


def button(text: str, kind: str = "", on_click=None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        for k in kind.split():
            b.setProperty(k, True)
    b.setCursor(Qt.PointingHandCursor)
    if on_click is not None:
        b.clicked.connect(lambda _checked=False: on_click())  # never pass Qt's `checked` flag into the handler
    return b


def panel(sub: bool = False) -> QFrame:
    f = QFrame()
    f.setProperty("subpanel" if sub else "panel", True)
    return f


class ComboBox(QComboBox):
    """QComboBox whose popup is a plain list view so the stylesheet applies on every platform."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        from PySide6.QtWidgets import QListView
        self.setView(QListView())
        self.view().setTextElideMode(Qt.ElideRight)
        self.setSizeAdjustPolicy(self.SizeAdjustPolicy.AdjustToContents)
        self.setCursor(Qt.PointingHandCursor)

    def showPopup(self):
        super().showPopup()
        v = self.view()
        v.setMinimumWidth(max(self.width(), v.sizeHintForColumn(0) + 32))


class Badge(QLabel):
    """A coloured rounded label for folder levels (Level 1 … / Replicate / folder names)."""

    def __init__(self, text: str, colors=None, level: int | None = None, size: int = 13, weight: int = 500, blocked: bool = False):
        super().__init__(text)
        if colors is None:
            colors = level_colors(level) if level else REPLICATE_COLORS
        if blocked:
            colors = BLOCKED_COLORS
        bg, fg = colors
        self.setStyleSheet(f"QLabel {{ background: {bg}; color: {fg}; border-radius: 4px; padding: 3px 8px; font-size: {size}px; font-weight: {weight}; }}")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


class Header(QFrame):
    """Navy title bar: app name (italic), optional page title, Read Me link."""

    def __init__(self, page_title: str = "", on_readme=None, dim: bool = False):
        super().__init__()
        self.setFixedHeight(56)
        self.setStyleSheet(f"QFrame {{ background: {NAVY_DIM if dim else NAVY}; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 0, 24, 0)
        title = QLabel("B-ICE DeTRESer")
        f = QFont(SANS, 20, QFont.DemiBold)
        f.setItalic(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {'#b7c0cf' if dim else 'white'}; letter-spacing: 0.4px;")
        lay.addWidget(title)
        lay.addStretch(1)
        self.page_title = QLabel(page_title)
        self.page_title.setStyleSheet("color: white; font-size: 15px; font-weight: 500;")
        lay.addWidget(self.page_title)
        lay.addStretch(1)
        self.readme = QPushButton("Read Me")
        self.readme.setCursor(Qt.PointingHandCursor)
        self.readme.setFlat(True)
        self.readme.setStyleSheet("QPushButton { background: transparent; border: none; color: #c9d6ea; font-size: 14px; padding: 0; height: 24px; min-height: 24px; } QPushButton:hover { color: white; }")
        if on_readme is not None:
            self.readme.clicked.connect(on_readme)
        lay.addWidget(self.readme)
        if dim:
            self.page_title.hide()
            self.readme.hide()

    def set_title(self, text: str) -> None:
        self.page_title.setText(text)


class Segmented(QWidget):
    """A row of mutually exclusive buttons (Single sample | Comparison, Data table | Graph, plot names)."""

    def __init__(self, items, on_change=None, tabs: bool = False):
        super().__init__()
        from PySide6.QtWidgets import QButtonGroup
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._on_change = on_change
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._buttons = []
        self.tabs = tabs
        if not tabs:
            self.setStyleSheet(f"Segmented {{ border: 1px solid {BORDER_INPUT}; border-radius: 8px; }}")
            self.setObjectName("segmented")
        for i, text in enumerate(items):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("tab" if tabs else "segment", True)
            b.setCursor(Qt.PointingHandCursor)
            self._group.addButton(b, i)
            lay.addWidget(b)
            self._buttons.append(b)
        if tabs:
            lay.addStretch(1)
        self._group.idClicked.connect(self._clicked)
        if self._buttons:
            self._buttons[0].setChecked(True)

    def paintEvent(self, ev):  # rounded border around the whole row
        from PySide6.QtGui import QPainter, QPen, QColor
        from PySide6.QtCore import QRectF
        if not self.tabs:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(BORDER_INPUT), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        else:
            p = QPainter(self)
            p.setPen(QPen(QColor(BORDER), 1))
            p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        super().paintEvent(ev)

    def _clicked(self, i: int) -> None:
        if self._on_change:
            self._on_change(i)

    def current(self) -> int:
        return self._group.checkedId()

    def set_current(self, i: int, emit: bool = False) -> None:
        if 0 <= i < len(self._buttons):
            self._buttons[i].setChecked(True)
            if emit:
                self._clicked(i)

    def set_items(self, items) -> None:
        for b in self._buttons:
            self._group.removeButton(b)
            b.setParent(None)
            b.deleteLater()
        self._buttons = []
        lay = self.layout()
        for i, text in enumerate(items):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("tab" if self.tabs else "segment", True)
            b.setCursor(Qt.PointingHandCursor)
            self._group.addButton(b, i)
            lay.insertWidget(i, b)
            self._buttons.append(b)
        if self._buttons:
            self._buttons[0].setChecked(True)

    def set_text(self, i: int, text: str) -> None:
        self._buttons[i].setText(text)

    def count(self) -> int:
        return len(self._buttons)


class DashedDropFrame(QFrame):
    """Dashed rounded rectangle used by every drop zone."""

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self._active = False
        self._update_style()

    def _update_style(self) -> None:
        color = ACCENT if self._active else DASH
        bg = "#f3f7fc" if self._active else PANEL
        self.setStyleSheet(f"DashedDropFrame {{ border: 2px dashed {color}; border-radius: 12px; background: {bg}; }}")

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()


def vbox(parent=None, margins=(0, 0, 0, 0), spacing=0) -> QVBoxLayout:
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return lay


def hbox(parent=None, margins=(0, 0, 0, 0), spacing=0) -> QHBoxLayout:
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return lay
