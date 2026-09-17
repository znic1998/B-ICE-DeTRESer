"""Pages 4, 6, 7, 9, 10 · Results: single-sample plot selection and comparison setup (TRES and anisotropy)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QRadioButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from tres_suite.config import PlotConfig, SeriesConfig

from ..model import ANISO_METRICS, DEFAULT_AXIS_TITLES, SINGLE_DEFAULTS, SINGLE_PLOTS, TRES_METRICS, Node, Session
from ..theme import (ComboBox, SERIES_COLORS, SERIES_MARKERS, Badge, Header, Segmented, button, hbox, hline, label, level_colors, panel, section_label, vbox)
from ..widgets.drop_zone import LevelDropZone
from ..widgets.folder_tree import FolderTree


@dataclass
class SeriesStyle:
    node: Node
    color: str
    marker: str


@dataclass
class CompareSpec:
    x_mode: str = "group"  # group | value
    y_mode: str = "value"
    series: List[SeriesStyle] = field(default_factory=list)  # dropped folders (one line each)
    values_level: int = 0  # folder level whose names give the group-axis positions (0 = deepest)
    group_title: str = ""
    metric_x: str = "gp"
    metric_y: str = "gp"
    value_title_x: str = ""
    value_title_y: str = ""
    error_bars: bool = True
    fit: bool = False
    kind: str = "tres"
    x_limits: Optional[list] = None
    y_limits: Optional[list] = None
    figsize: Optional[list] = None

    @property
    def group_axis(self) -> Optional[str]:
        if self.x_mode == "group" and self.y_mode == "value":
            return "x"
        if self.y_mode == "group" and self.x_mode == "value":
            return "y"
        return None

    def plot_type(self) -> Optional[str]:
        if self.x_mode == "value" and self.y_mode == "value":
            return "metric_vs_metric"
        if self.group_axis:
            return "metric_vs_label"
        return None


def default_style(i: int) -> tuple:
    return SERIES_COLORS[i % len(SERIES_COLORS)][1], SERIES_MARKERS[i % 3][1]


def build_plot_config(session: Session, spec: CompareSpec, name: str = "comparison") -> PlotConfig:
    """Translate the comparison setup into the backend's metric_vs_label / metric_vs_metric plot."""
    names = session.all_level_names()
    ptype = spec.plot_type()
    if ptype is None:
        raise ValueError("Choose Value for at least one axis.")
    series = []
    for i, st in enumerate(spec.series):
        series.append(SeriesConfig(label=" › ".join(st.node.labels) if st.node.level > 1 else st.node.name,
                                   select=session.select_for_node(st.node), color=st.color, marker=st.marker))
    extra = {"kind": spec.kind}
    if ptype == "metric_vs_metric":
        pc = PlotConfig(type=ptype, name=name, series=series, x=spec.metric_x, y=spec.metric_y,
                        x_label=spec.value_title_x or DEFAULT_AXIS_TITLES.get(spec.metric_x), y_label=spec.value_title_y or DEFAULT_AXIS_TITLES.get(spec.metric_y),
                        error_bars=spec.error_bars, fit=spec.fit, extra=extra)
    else:
        lvl = spec.values_level or session.n_levels
        level_name = names[lvl - 1]
        metric = spec.metric_y if spec.group_axis == "x" else spec.metric_x
        if spec.group_axis == "y":
            extra["label_axis"] = "y"
            x_label = spec.value_title_x or DEFAULT_AXIS_TITLES.get(metric, metric)
            y_label = spec.group_title or level_name
        else:
            x_label = spec.group_title or level_name
            y_label = spec.value_title_y or DEFAULT_AXIS_TITLES.get(metric, metric)
        pc = PlotConfig(type="metric_vs_label", name=name, series=series, x=level_name, y=metric, x_label=x_label, y_label=y_label,
                        error_bars=spec.error_bars, fit=spec.fit, extra=extra)
    pc.x_limits = spec.x_limits
    pc.y_limits = spec.y_limits
    if spec.figsize:
        pc.extra["figsize"] = list(spec.figsize)
    return pc


# ------------------------------------------------------------------------------
class _AxisModePanel(QFrame):
    """The grey panel with "X axis: Value / Group" and "Y axis: Value / Group"."""

    changed = Signal()

    def __init__(self, x_mode: str, y_mode: str):
        super().__init__()
        self.setProperty("subpanel", True)
        lay = vbox(self, (20, 4, 20, 4))
        self.groups: Dict[str, QButtonGroup] = {}
        for i, (axis, mode) in enumerate((("X axis", x_mode), ("Y axis", y_mode))):
            row = QWidget()
            g = QGridLayout(row)
            g.setContentsMargins(0, 10, 0, 10)
            g.setHorizontalSpacing(16)
            t = label(axis, bold=True)
            t.setFixedWidth(120)
            g.addWidget(t, 0, 0)
            inner = QWidget()
            h = hbox(inner, spacing=24)
            bg = QButtonGroup(inner)
            for j, txt in enumerate(("Value", "Group")):
                r = QRadioButton(txt)
                bg.addButton(r, j)
                h.addWidget(r)
                if (j == 0) == (mode == "value"):
                    r.setChecked(True)
            h.addStretch(1)
            g.addWidget(inner, 0, 1)
            g.setColumnStretch(1, 1)
            self.groups["x" if i == 0 else "y"] = bg
            bg.idClicked.connect(lambda _i: self.changed.emit())
            lay.addWidget(row)
            if i == 0:
                lay.addWidget(hline())

    def mode(self, axis: str) -> str:
        return "value" if self.groups[axis].checkedId() == 0 else "group"


class _ValueOptions(QWidget):
    """Value-axis tab: metric choice (dropdown for TRES, radios for anisotropy), axis title, show options."""

    changed = Signal()

    def __init__(self, session: Session, radios: bool):
        super().__init__()
        self.session = session
        self.radios = radios
        lay = vbox(self, (0, 4, 0, 0), 16)
        # value to plot
        row = QWidget()
        g = QGridLayout(row)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(16)
        t = label("Value to plot", bold=True)
        t.setFixedWidth(140)
        g.addWidget(t, 0, 0, Qt.AlignTop if radios else Qt.AlignVCenter)
        if radios:
            box = QWidget()
            bl = vbox(box, spacing=12)
            self.radio_group = QButtonGroup(box)
            self.radio_keys = []
            for i, (lab_text, key) in enumerate(ANISO_METRICS):
                r = QRadioButton(lab_text)
                if key == "wobble_eta_Pa_s":
                    w = QWidget()
                    h = hbox(w, spacing=8)
                    h.addWidget(r)
                    n = QLabel("— only if Microviscosity is set to Calculate")
                    n.setProperty("muted13", True)
                    h.addWidget(n)
                    h.addStretch(1)
                    bl.addWidget(w)
                else:
                    bl.addWidget(r)
                self.radio_group.addButton(r, i)
                self.radio_keys.append(key)
            self.radio_group.button(0).setChecked(True)
            self.radio_group.idClicked.connect(self._metric_changed)
            g.addWidget(box, 0, 1)
        else:
            self.combo = ComboBox()
            self.combo.setFixedWidth(320)
            self.combo.currentIndexChanged.connect(self._metric_changed)
            g.addWidget(self.combo, 0, 1, Qt.AlignLeft)
        g.setColumnStretch(1, 1)
        lay.addWidget(row)
        # axis title
        row2 = QWidget()
        g2 = QGridLayout(row2)
        g2.setContentsMargins(0, 0, 0, 0)
        g2.setHorizontalSpacing(16)
        t2 = label("Axis title", bold=True)
        t2.setFixedWidth(140)
        g2.addWidget(t2, 0, 0)
        self.title = QLineEdit()
        self.title.setFixedWidth(320)
        g2.addWidget(self.title, 0, 1, Qt.AlignLeft)
        g2.setColumnStretch(1, 1)
        lay.addWidget(row2)
        # show
        row3 = QWidget()
        g3 = QGridLayout(row3)
        g3.setContentsMargins(0, 0, 0, 0)
        g3.setHorizontalSpacing(16)
        t3 = label("Show", bold=True)
        t3.setFixedWidth(140)
        g3.addWidget(t3, 0, 0)
        sw = QWidget()
        sh = hbox(sw, spacing=24)
        self.err = QCheckBox("Error bars (SD of replicates)")
        self.err.setChecked(True)
        self.fit = QCheckBox("Linear fit + R²")
        sh.addWidget(self.err)
        sh.addWidget(self.fit)
        sh.addStretch(1)
        g3.addWidget(sw, 0, 1)
        g3.setColumnStretch(1, 1)
        lay.addWidget(row3)
        lay.addStretch(1)
        self._title_auto = True
        self.title.textEdited.connect(lambda _t: setattr(self, "_title_auto", False))
        self.refresh_metrics()

    def refresh_metrics(self) -> None:
        if self.radios:
            self._metric_changed(0)
            return
        cur = self.metric_key()
        self.combo.blockSignals(True)
        self.combo.clear()
        for lab_text, key in self.session.metrics():
            self.combo.addItem(lab_text, key)
        idx = self.combo.findData(cur) if cur else -1
        self.combo.setCurrentIndex(idx if idx >= 0 else (1 if self.combo.count() > 1 else 0))
        self.combo.blockSignals(False)
        self._metric_changed(self.combo.currentIndex())

    def metric_key(self) -> str:
        if self.radios:
            i = self.radio_group.checkedId()
            return self.radio_keys[i] if i >= 0 else self.radio_keys[0]
        return self.combo.currentData() or ""

    def _metric_changed(self, _i) -> None:
        if self._title_auto:
            self.title.setText(DEFAULT_AXIS_TITLES.get(self.metric_key(), self.metric_key()))
        self.changed.emit()

    def set_metric(self, key: str) -> None:
        if self.radios:
            if key in self.radio_keys:
                self.radio_group.button(self.radio_keys.index(key)).setChecked(True)
                self._metric_changed(self.radio_keys.index(key))
        else:
            i = self.combo.findData(key)
            if i >= 0:
                self.combo.setCurrentIndex(i)


class _GroupOptions(QWidget):
    """Group-axis tab: drop zone for folders (one series each), values-from level, axis title."""

    changed = Signal()

    def __init__(self, session: Session, title_default: str = "Drag {level} folders here",
                 hint: str = "Each folder becomes one line. The names of its {level} folders (e.g. 15, 25, 35) become the x values."):
        super().__init__()
        self.session = session
        lay = vbox(self, (0, 4, 0, 0), 16)
        self.zone = LevelDropZone(session, self.series_level, title_default, hint, multi=True)
        self.zone.changed.connect(self.changed.emit)
        lay.addWidget(self.zone, 1)
        row = QWidget()
        h = hbox(row, spacing=12)
        h.addWidget(label("Values from", bold=True))
        self.values_from = ComboBox()
        self.values_from.setFixedWidth(220)
        self.values_from.currentIndexChanged.connect(self._level_changed)
        h.addWidget(self.values_from)
        h.addSpacing(16)
        h.addWidget(label("Axis title", bold=True))
        self.title = QLineEdit()
        self.title.setFixedWidth(220)
        h.addWidget(self.title)
        h.addStretch(1)
        lay.addWidget(row)
        self._title_auto = True
        self.title.textEdited.connect(lambda _t: setattr(self, "_title_auto", False))
        self.refresh()

    def series_level(self) -> int:
        return max(self.session.n_levels - 1, 1)

    def refresh(self) -> None:
        s = self.session
        self.values_from.blockSignals(True)
        cur = self.values_from.currentData()
        self.values_from.clear()
        lo = self.series_level() + 1 if s.n_levels > 1 else 1
        for k in range(lo, s.n_levels + 1):
            self.values_from.addItem(f"{s.level_name(k)} folder names", k)
        idx = self.values_from.findData(cur) if cur else -1
        self.values_from.setCurrentIndex(idx if idx >= 0 else self.values_from.count() - 1)
        self.values_from.blockSignals(False)
        self.zone.refresh_text()
        self._level_changed(0)

    def _level_changed(self, _i) -> None:
        if self._title_auto:
            k = self.values_from.currentData() or self.session.n_levels
            self.title.setText(self.session.level_name(k))
        self.changed.emit()

    def level(self) -> int:
        return self.values_from.currentData() or self.session.n_levels


class ResultsPage(QWidget):
    """TRES results (Single sample | Comparison) or anisotropy results (comparison only)."""

    advanced_requested = Signal()
    export_full_requested = Signal()
    single_requested = Signal(object, list)  # node, [PlotConfig]
    compare_requested = Signal(object)  # CompareSpec
    options_requested = Signal()

    def __init__(self, session: Session, kind: str, on_readme):
        super().__init__()
        self.session = session
        self.kind = kind
        aniso = kind == "anisotropy"
        lay = vbox(self)
        self.header = Header("Anisotropy Results" if aniso else "TRES Results", on_readme)
        lay.addWidget(self.header)
        body = QWidget()
        bl = hbox(body, (24, 24, 24, 24), 24)
        self.tree = FolderTree(session, allow_add=False)
        back = button("← Options / new run", "small", self.options_requested.emit)
        back.setFixedHeight(40)
        self.tree.layout().addWidget(back)
        bl.addWidget(self.tree)
        card = panel()
        cl = vbox(card, (28, 24, 28, 24), 16)
        self.stack = QStackedWidget()
        if not aniso:
            self.mode = Segmented(["Single sample", "Comparison"], self.stack.setCurrentIndex)
            cl.addWidget(self.mode, 0, Qt.AlignLeft)
        cl.addWidget(self.stack, 1)
        # ---- single sample view
        if not aniso:
            self.stack.addWidget(self._build_single())
        # ---- comparison view
        self.stack.addWidget(self._build_compare(aniso))
        # footer
        foot = QWidget()
        fl = hbox(foot, spacing=12)
        fl.addWidget(button("Advanced…", "", self.advanced_requested.emit))
        fl.addStretch(1)
        fl.addWidget(button("Export full data…", "outline", self.export_full_requested.emit))
        self.plot_btn = button("Plot →", "primary", self._plot)
        fl.addWidget(self.plot_btn)
        cl.addWidget(foot)
        bl.addWidget(card, 1)
        lay.addWidget(body, 1)
        self.stack.currentChanged.connect(self._view_changed)
        self._view_changed(self.stack.currentIndex())

    # ---- single --------------------------------------------------------------------
    def _build_single(self) -> QWidget:
        w = QWidget()
        lay = vbox(w, spacing=20)
        grid_panel = QFrame()
        grid_panel.setProperty("subpanel", True)
        g = QGridLayout(grid_panel)
        g.setContentsMargins(20, 16, 20, 16)
        g.setHorizontalSpacing(24)
        g.setVerticalSpacing(10)
        self.single_checks: Dict[str, QCheckBox] = {}
        sections = []
        for sec, lab_text, ptype, extra in SINGLE_PLOTS:
            if sec not in sections:
                sections.append(sec)
                g.addWidget(section_label(sec), 0, sections.index(sec))
            cb = QCheckBox(lab_text)
            cb.setChecked(lab_text in SINGLE_DEFAULTS)
            self.single_checks[lab_text] = cb
            col = sections.index(sec)
            row = 1 + sum(1 for s2, _, _, _ in SINGLE_PLOTS[:SINGLE_PLOTS.index((sec, lab_text, ptype, extra))] if s2 == sec)
            g.addWidget(cb, row, col)
        for c in range(len(sections)):
            g.setColumnStretch(c, 1)
        lay.addWidget(grid_panel)
        self.single_zone = LevelDropZone(self.session, lambda: self.session.group_level(), "Drag a {level} folder here",
                                         "Plots use the averaged replicates (Excel files) in that folder", multi=False)
        self.single_zone.changed.connect(self._single_dropped)
        lay.addWidget(self.single_zone, 1)
        return w

    def _single_dropped(self) -> None:
        nodes = self.single_zone.nodes
        if not nodes:
            return
        node = nodes[0]
        g = self.session.group_for_node(node)
        from PySide6.QtWidgets import QMessageBox
        if g is None:
            QMessageBox.information(self, "Not analysed", f"{node.name} was not part of this run.")
            self.single_zone.clear()
            return
        if g.status == "blocked":
            QMessageBox.warning(self, "Group blocked", f"{' › '.join(node.labels)} was blocked: {node.block_reason}.\nFix the files and run the analysis again.")
            self.single_zone.clear()
            return
        plots = self.single_plot_configs(node)
        if not plots:
            QMessageBox.information(self, "No plot selected", "Tick at least one plot above.")
            self.single_zone.clear()
            return
        self.single_requested.emit(node, plots)
        self.single_zone.clear()

    def single_plot_configs(self, node: Node) -> List[PlotConfig]:
        out = []
        sel = self.session.select_for_node(node)
        for sec, lab_text, ptype, extra in SINGLE_PLOTS:
            if not self.single_checks[lab_text].isChecked():
                continue
            kw = copy.deepcopy(extra)
            pc = PlotConfig(type=ptype, name=f"{'_'.join(node.labels)}_{lab_text}", group=sel, **kw)
            pc.extra["display_name"] = lab_text
            pc.extra["card_title"] = f"{lab_text} — {' › '.join(node.labels)}"
            out.append(pc)
        return out

    # ---- comparison ------------------------------------------------------------------
    def _build_compare(self, aniso: bool) -> QWidget:
        w = QWidget()
        lay = vbox(w, spacing=16)
        self.axis_modes = _AxisModePanel("value" if aniso else "group", "group" if aniso else "value")
        self.axis_modes.changed.connect(self._modes_changed)
        lay.addWidget(self.axis_modes)
        self.axis_tabs = Segmented(["X axis options", "Y axis options"], self._tab_changed, tabs=True)
        lay.addWidget(self.axis_tabs)
        self.tab_stack = QStackedWidget()
        # x tab / y tab each has a stacked (group | value) widget
        self.x_group = _GroupOptions(self.session)
        self.x_value = _ValueOptions(self.session, radios=aniso)
        self.y_group = _GroupOptions(self.session, "Drag {level} folders to plot against",
                                     "Each folder becomes one series. The names of its {level} folders (e.g. 15, 25, 35) become the positions on this axis.")
        self.y_value = _ValueOptions(self.session, radios=aniso)
        self.x_stack = QStackedWidget()
        self.x_stack.addWidget(self.x_group)
        self.x_stack.addWidget(self.x_value)
        self.y_stack = QStackedWidget()
        self.y_stack.addWidget(self.y_group)
        self.y_stack.addWidget(self.y_value)
        self.tab_stack.addWidget(self.x_stack)
        self.tab_stack.addWidget(self.y_stack)
        lay.addWidget(self.tab_stack, 1)
        # series zone for value-vs-value (any level)
        self.vv_zone = LevelDropZone(self.session, lambda: 1, "Drag folders here to make series (optional)",
                                     "Without folders every analysed group is one series. Each dropped folder becomes one series.", multi=True)
        self.vv_zone.dragEnterEvent = self._vv_enter  # accept any folder level
        self.vv_zone.dropEvent = self._vv_drop
        lay.addWidget(self.vv_zone)
        self.vv_zone.hide()
        self._modes_changed()
        return w

    def _vv_enter(self, ev):
        from ..widgets.folder_tree import mime_node
        node = mime_node(ev.mimeData(), self.session)
        if node is not None and not node.is_file:
            self.vv_zone.set_active(True)
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def _vv_drop(self, ev):
        from ..widgets.folder_tree import mime_node
        self.vv_zone.set_active(False)
        node = mime_node(ev.mimeData(), self.session)
        if node is None or node.is_file:
            ev.ignore()
            return
        ev.acceptProposedAction()
        if all(n is not node for n in self.vv_zone.nodes):
            self.vv_zone.nodes.append(node)
        self.vv_zone._refresh_chips()

    def _tab_changed(self, i: int) -> None:
        self.tab_stack.setCurrentIndex(i)

    def _modes_changed(self) -> None:
        xm, ym = self.axis_modes.mode("x"), self.axis_modes.mode("y")
        self.x_stack.setCurrentIndex(0 if xm == "group" else 1)
        self.y_stack.setCurrentIndex(0 if ym == "group" else 1)
        both_value = xm == "value" and ym == "value"
        both_group = xm == "group" and ym == "group"
        self.vv_zone.setVisible(both_value)
        if hasattr(self, "plot_btn"):
            self.plot_btn.setEnabled(not both_group)
            self.plot_btn.setToolTip("Choose Value for at least one axis." if both_group else "")

    def _view_changed(self, i: int) -> None:
        comparison = self.kind == "anisotropy" or i == 1
        self.plot_btn.setVisible(comparison)
        if comparison:
            self._modes_changed()

    def refresh(self) -> None:
        """After a run: update tree marks, level names, metric lists."""
        self.session.mark_groups()
        self.tree.refresh()
        self.x_group.refresh()
        self.y_group.refresh()
        self.x_value.refresh_metrics()
        self.y_value.refresh_metrics()
        if hasattr(self, "single_zone"):
            self.single_zone.refresh_text()
            self.single_zone.clear()
        self.x_group.zone.clear()
        self.y_group.zone.clear()
        self.vv_zone.clear()

    def spec(self) -> CompareSpec:
        xm, ym = self.axis_modes.mode("x"), self.axis_modes.mode("y")
        spec = CompareSpec(x_mode=xm, y_mode=ym, kind=self.kind)
        if xm == "group" and ym == "value":
            nodes, spec.values_level, spec.group_title = self.x_group.zone.nodes, self.x_group.level(), self.x_group.title.text().strip()
            spec.metric_y, spec.value_title_y = self.y_value.metric_key(), self.y_value.title.text().strip()
            spec.error_bars, spec.fit = self.y_value.err.isChecked(), self.y_value.fit.isChecked()
        elif ym == "group" and xm == "value":
            nodes, spec.values_level, spec.group_title = self.y_group.zone.nodes, self.y_group.level(), self.y_group.title.text().strip()
            spec.metric_x, spec.value_title_x = self.x_value.metric_key(), self.x_value.title.text().strip()
            spec.error_bars, spec.fit = self.x_value.err.isChecked(), self.x_value.fit.isChecked()
        else:
            nodes = self.vv_zone.nodes
            spec.metric_x, spec.value_title_x = self.x_value.metric_key(), self.x_value.title.text().strip()
            spec.metric_y, spec.value_title_y = self.y_value.metric_key(), self.y_value.title.text().strip()
            spec.error_bars = self.x_value.err.isChecked() or self.y_value.err.isChecked()
            spec.fit = self.x_value.fit.isChecked() or self.y_value.fit.isChecked()
        if not nodes and self.session.n_levels == 1 and spec.group_axis:
            nodes = list(self.session.roots)  # single level: every root folder is a group; one series each
        spec.series = [SeriesStyle(n, *default_style(i)) for i, n in enumerate(nodes)]
        return spec

    def _plot(self) -> None:
        spec = self.spec()
        from PySide6.QtWidgets import QMessageBox
        if spec.group_axis and not spec.series:
            lvl = self.session.level_name(max(self.session.n_levels - 1, 1))
            QMessageBox.information(self, "No folders", f"Drag at least one {lvl} folder onto the drop zone first.")
            return
        self.compare_requested.emit(spec)
