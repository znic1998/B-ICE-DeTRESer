"""Embedded matplotlib canvas that draws backend PlotConfigs, plus the axes editor and export helpers."""
from __future__ import annotations

import copy
import math
import os
from typing import Callable, Optional

import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QLabel, QLineEdit, QMessageBox, QScrollArea, QSizePolicy, QTableView, QVBoxLayout, QWidget)
from PySide6.QtCore import QAbstractTableModel, QModelIndex

from ..theme import MONO, PANEL, button, hbox, label, section_label, vbox

def _register_fonts() -> None:
    """Make the bundled IBM Plex fonts available to matplotlib as well (falls back silently)."""
    try:
        from matplotlib import font_manager
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
        for fn in os.listdir(here) if os.path.isdir(here) else []:
            if fn.lower().endswith((".ttf", ".otf")):
                font_manager.fontManager.addfont(os.path.join(here, fn))
        names = {f.name for f in font_manager.fontManager.ttflist}
        family = ["IBM Plex Sans"] if "IBM Plex Sans" in names else []
        matplotlib.rcParams.update({"font.family": family + ["DejaVu Sans", "sans-serif"], "font.size": 10, "axes.titlesize": 11,
                                    "svg.fonttype": "none", "figure.autolayout": False})
    except Exception:
        matplotlib.rcParams.update({"font.size": 10, "axes.titlesize": 11, "svg.fonttype": "none"})


_register_fonts()


class PlotCanvas(QWidget):
    """Draws one backend PlotConfig on a Qt canvas via ``tres_suite.plotting.draw_plot``."""

    drawn = Signal(object)  # DrawResult

    def __init__(self):
        super().__init__()
        self.fig = Figure(figsize=(6, 4.2), dpi=100, facecolor="white")
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = vbox(self)
        lay.addWidget(self.canvas, 0, Qt.AlignCenter)
        self._fixed = None
        self.set_figure_size(None)
        self.result = None
        self.pc = None
        self.draw_result = None
        self.error: Optional[str] = None

    def set_figure_size(self, fs) -> None:
        """``fs`` = (width, height) in inches for a fixed-size figure, or None to fill the widget."""
        self._fixed = tuple(fs) if fs else None
        if self._fixed:
            w, h = int(self._fixed[0] * 100), int(self._fixed[1] * 100)
            self.canvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.canvas.setFixedSize(w, h)
            self.fig.set_size_inches(self._fixed[0], self._fixed[1], forward=True)
        else:
            self.canvas.setMinimumSize(0, 0)
            self.canvas.setMaximumSize(16777215, 16777215)
            self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout().setAlignment(self.canvas, Qt.AlignCenter if self._fixed else Qt.Alignment())

    def draw(self, result, pc) -> None:
        """Redraw with the given RunResult and PlotConfig (a copy is drawn so the backend may fill in default labels)."""
        from tres_suite.plotting import draw_plot
        self.result = result
        self.pc = pc
        self.set_figure_size(pc.extra.get("figsize"))
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        self.error = None
        try:
            self.draw_result = draw_plot(result, copy.deepcopy(pc), ax)
        except Exception as exc:
            self.draw_result = None
            self.error = f"{exc.__class__.__name__}: {exc}"
            ax.clear()
            ax.text(0.5, 0.5, f"This plot is not available\n{self.error}", ha="center", va="center", fontsize=9, color="#b42318", wrap=True, transform=ax.transAxes)
            ax.set_axis_off()
        try:
            self.fig.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()
        self.drawn.emit(self.draw_result)

    def current_labels(self):
        ax = self.fig.axes[0] if self.fig.axes else None
        if ax is None:
            return "", ""
        return ax.get_xlabel(), ax.get_ylabel()

    # ---- exports -------------------------------------------------------------------
    def export_image(self, parent, default_name: str, dpi: int = 300) -> Optional[str]:
        path, _ = QFileDialog.getSaveFileName(parent, "Export graph as", os.path.join(os.path.expanduser("~"), default_name + ".png"),
                                              "PNG image (*.png);;SVG vector image (*.svg);;PDF (*.pdf)")
        if not path:
            return None
        try:
            if self._fixed:
                self.fig.savefig(path, dpi=dpi, facecolor="white")
            else:  # exported at the backend's default figure size, not the on-screen size
                w, h = self.fig.get_size_inches()
                self.fig.set_size_inches(5.5, 4.2, forward=False)
                try:
                    self.fig.tight_layout()
                    self.fig.savefig(path, dpi=dpi, facecolor="white")
                finally:
                    self.fig.set_size_inches(w, h, forward=True)
                    self.fig.tight_layout()
                    self.canvas.draw_idle()
        except Exception as exc:
            QMessageBox.critical(parent, "Export failed", str(exc))
            return None
        return path

    def export_data(self, parent, default_name: str) -> Optional[str]:
        if self.draw_result is None or self.draw_result.data is None:
            QMessageBox.information(parent, "Nothing to export", "There is no plotted data for this graph.")
            return None
        path, _ = QFileDialog.getSaveFileName(parent, "Export data as", os.path.join(os.path.expanduser("~"), default_name + ".csv"), "CSV (*.csv)")
        if not path:
            return None
        try:
            self.draw_result.data.to_csv(path, index=False, float_format="%.17g")
        except Exception as exc:
            QMessageBox.critical(parent, "Export failed", str(exc))
            return None
        return path


class AxesEditor(QFrame):
    """X/Y title + min/max fields (blank = automatic).  Emits ``changed`` when any field is edited."""

    changed = Signal()

    def __init__(self, compact: bool = False):
        super().__init__()
        self.setProperty("panel", True)
        self._building = False
        lay = vbox(self, (14, 14, 14, 14), 8)
        lay.addWidget(section_label("Axes"))
        g = QGridLayout()
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)
        self.x_title, self.x_min, self.x_max = QLineEdit(), QLineEdit(), QLineEdit()
        self.y_title, self.y_min, self.y_max = QLineEdit(), QLineEdit(), QLineEdit()
        for w in (self.x_min, self.x_max, self.y_min, self.y_max):
            w.setPlaceholderText("auto")
            w.setProperty("mono", True)
        if compact:
            g.addWidget(QLabel(""), 0, 0)
            for c, t in enumerate(("Title", "Min", "Max"), start=1):
                lab = QLabel(t)
                lab.setProperty("muted13", True)
                g.addWidget(lab, 0, c)
            g.addWidget(label("X", bold=True), 1, 0)
            g.addWidget(self.x_title, 1, 1)
            g.addWidget(self.x_min, 1, 2)
            g.addWidget(self.x_max, 1, 3)
            g.addWidget(label("Y", bold=True), 2, 0)
            g.addWidget(self.y_title, 2, 1)
            g.addWidget(self.y_min, 2, 2)
            g.addWidget(self.y_max, 2, 3)
            for w in (self.x_min, self.x_max, self.y_min, self.y_max):
                w.setFixedWidth(72)
            for w in (self.x_title, self.y_title):
                w.setMinimumWidth(60)
            g.setColumnStretch(1, 1)
        else:
            r = 0
            for axis, title, mn, mx in (("X", self.x_title, self.x_min, self.x_max), ("Y", self.y_title, self.y_min, self.y_max)):
                lab = QLabel(f"{axis} title")
                lab.setProperty("muted13", True)
                g.addWidget(lab, r, 0, 1, 2)
                g.addWidget(title, r + 1, 0, 1, 2)
                l1, l2 = QLabel(f"{axis} min"), QLabel(f"{axis} max")
                l1.setProperty("muted13", True)
                l2.setProperty("muted13", True)
                g.addWidget(l1, r + 2, 0)
                g.addWidget(l2, r + 2, 1)
                g.addWidget(mn, r + 3, 0)
                g.addWidget(mx, r + 3, 1)
                r += 4
        lay.addLayout(g)
        note = QLabel("Leave Min / Max blank for automatic range.")
        note.setStyleSheet("font-size: 12px; color: #4a5566;")
        lay.addWidget(note)
        # figure size (inches): blank = fill the available space
        sz = QWidget()
        sh = QGridLayout(sz)
        sh.setContentsMargins(0, 6, 0, 0)
        sh.setHorizontalSpacing(8)
        l1 = QLabel("Plot width (in)"); l1.setProperty("muted13", True)
        l2 = QLabel("Plot height (in)"); l2.setProperty("muted13", True)
        self.fig_w, self.fig_h = QLineEdit(), QLineEdit()
        for w in (self.fig_w, self.fig_h):
            w.setPlaceholderText("fill")
            w.setProperty("mono", True)
            w.setFixedWidth(72)
        sh.addWidget(l1, 0, 0); sh.addWidget(l2, 0, 1)
        sh.addWidget(self.fig_w, 1, 0); sh.addWidget(self.fig_h, 1, 1)
        sh.setColumnStretch(2, 1)
        lay.addWidget(sz)
        note2 = QLabel("Set both for a fixed plot size (e.g. 5 × 4 for a square-ish figure); this is also the exported image size.")
        note2.setWordWrap(True)
        note2.setStyleSheet("font-size: 12px; color: #4a5566;")
        lay.addWidget(note2)
        for w in (self.x_title, self.y_title, self.x_min, self.x_max, self.y_min, self.y_max, self.fig_w, self.fig_h):
            w.editingFinished.connect(self._emit)

    def _emit(self) -> None:
        if not self._building:
            self.changed.emit()

    def set_titles(self, x: str, y: str) -> None:
        self._building = True
        self.x_title.setText(x)
        self.y_title.setText(y)
        self.x_title.setCursorPosition(0)
        self.y_title.setCursorPosition(0)
        self._building = False

    def set_limits(self, xlim, ylim) -> None:
        self._building = True
        self.x_min.setText("" if not xlim else _fmt(xlim[0]))
        self.x_max.setText("" if not xlim else _fmt(xlim[1]))
        self.y_min.setText("" if not ylim else _fmt(ylim[0]))
        self.y_max.setText("" if not ylim else _fmt(ylim[1]))
        self._building = False

    def apply_to(self, pc) -> None:
        """Write the fields into a PlotConfig (titles only when non-blank, limits only when both given)."""
        pc.x_label = self.x_title.text().strip() or None
        pc.y_label = self.y_title.text().strip() or None
        pc.x_limits = _limits(self.x_min.text(), self.x_max.text())
        pc.y_limits = _limits(self.y_min.text(), self.y_max.text())
        fs = self.figure_size()
        if fs:
            pc.extra["figsize"] = list(fs)
        else:
            pc.extra.pop("figsize", None)

    def figure_size(self):
        try:
            w, h = float(self.fig_w.text()), float(self.fig_h.text())
        except ValueError:
            return None
        return (w, h) if 1 <= w <= 30 and 1 <= h <= 30 else None

    def set_figure_size(self, fs) -> None:
        self._building = True
        self.fig_w.setText("" if not fs else _fmt(fs[0]))
        self.fig_h.setText("" if not fs else _fmt(fs[1]))
        self._building = False


def _fmt(v) -> str:
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return ""


def _limits(a: str, b: str):
    a, b = a.strip(), b.strip()
    if not a and not b:
        return None
    try:
        lo = float(a) if a else None
        hi = float(b) if b else None
    except ValueError:
        return None
    if (lo is not None and not math.isfinite(lo)) or (hi is not None and not math.isfinite(hi)):
        return None
    if lo is not None and hi is not None:
        if lo == hi:
            return None
        lo, hi = min(lo, hi), max(lo, hi)
    return [lo, hi]


class DataFrameModel(QAbstractTableModel):
    def __init__(self, df):
        super().__init__()
        self.df = df

    def rowCount(self, parent=QModelIndex()):
        return 0 if self.df is None else len(self.df)

    def columnCount(self, parent=QModelIndex()):
        return 0 if self.df is None else len(self.df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        v = self.df.iat[index.row(), index.column()]
        try:
            import numpy as np
            if isinstance(v, (float, np.floating)):
                return "" if np.isnan(v) else f"{float(v):.6g}"
        except Exception:
            pass
        return "" if v is None else str(v)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self.df.columns[section])
        return str(section + 1)


class DataTable(QTableView):
    def __init__(self):
        super().__init__()
        self.setAlternatingRowColors(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setDefaultSectionSize(24)

    def set_df(self, df) -> None:
        self.setModel(DataFrameModel(df))
        self.resizeColumnsToContents()


class SampleTables(QScrollArea):
    """Horizontal, side-by-side tables for every sample in an overlay plot."""

    def __init__(self):
        super().__init__()
        self.setObjectName("sampleTablesScroll")
        self.setStyleSheet(
            f"QScrollArea#sampleTablesScroll {{ background: {PANEL}; }} "
            f"QScrollArea#sampleTablesScroll > QWidget > QWidget {{ background: {PANEL}; }}"
        )
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.host.setObjectName("sampleTablesHost")
        self.host.setStyleSheet(f"QWidget#sampleTablesHost {{ background: {PANEL}; }}")
        self.rows = hbox(self.host, spacing=14)
        self.rows.addStretch(1)
        self.setWidget(self.host)

    def set_df(self, df) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if df is None:
            self.rows.addStretch(1)
            return
        if "sample" in df.columns:
            groups = []
            for name, part in df.groupby("sample", sort=False):
                part = part.drop(columns=["sample"]).reset_index(drop=True)
                # The card title already identifies the sample. Keep these columns only
                # when they distinguish multiple curves/components inside that sample.
                for column in ("series", "group"):
                    if column in part.columns and part[column].nunique(dropna=False) <= 1:
                        part = part.drop(columns=[column])
                groups.append((str(name), part))
        else:
            groups = [("Plotted data", df.reset_index(drop=True))]
        for title, part in groups:
            card = QFrame()
            card.setProperty("subpanel", True)
            card.setMinimumWidth(420)
            card.setMaximumWidth(560)
            lay = vbox(card, (12, 10, 12, 12), 8)
            heading = label(title, bold=True)
            heading.setWordWrap(True)
            lay.addWidget(heading)
            table = DataTable()
            table.horizontalHeader().setStretchLastSection(False)
            table.set_df(part)
            lay.addWidget(table, 1)
            self.rows.addWidget(card)
        self.rows.addStretch(1)
