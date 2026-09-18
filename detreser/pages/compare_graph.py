"""Page 8 · Comparison graph (shared by TRES and anisotropy): series styling, editable axes, exports."""
from __future__ import annotations

import copy
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QFrame, QGridLayout, QScrollArea, QWidget

from tres_suite.config import SeriesConfig

from ..model import Node, Session
from ..theme import PANEL, ComboBox, Header, button, hbox, panel, section_label, vbox
from ..widgets.plot_canvas import AxesEditor, PlotCanvas
from .graph_view import OverlaySample, SampleStyleDialog
from .results_page import CompareSpec, SeriesStyle, build_plot_config, default_style


class CompareGraphPage(QWidget):
    back_requested = Signal()
    advanced_requested = Signal()
    export_full_requested = Signal()

    def __init__(self, session: Session, on_readme):
        super().__init__()
        self.session = session
        self.spec: Optional[CompareSpec] = None
        self.pc = None
        lay = vbox(self)
        self.header = Header("TRES Results · Comparison", on_readme)
        lay.addWidget(self.header)
        body = QWidget()
        bl = hbox(body, (24, 24, 24, 24), 24)
        # left controls scroll as one unit so a long series list never compresses the axes panel
        left = panel()
        left.setMinimumWidth(420)
        left.setMinimumHeight(720)
        ll = vbox(left, (20, 20, 20, 20), 14)
        ll.addWidget(button("← Back to setup", "link", self.back_requested.emit), 0, Qt.AlignLeft)
        ll.addWidget(section_label("Series"))
        self.series_box = QWidget()
        self.series_lay = vbox(self.series_box, spacing=8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.series_box)
        scroll.setMaximumHeight(230)
        scroll.setMinimumHeight(60)
        self.series_scroll = scroll
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background: {PANEL}; }} QScrollArea > QWidget > QWidget {{ background: {PANEL}; }}")
        ll.addWidget(scroll)
        self.add_combo = ComboBox()
        self.add_combo.setStyleSheet("QComboBox { border: 1px dashed #8e9bb0; }")
        self.add_combo.activated.connect(self._add_series)
        ll.addWidget(self.add_combo)
        opts = QWidget()
        oh = hbox(opts, spacing=14)
        self.legend_check = QCheckBox("Show legend")
        self.connect_check = QCheckBox("Connect points")
        self.error_check = QCheckBox("Error bars (SD)")
        for check in (self.legend_check, self.connect_check, self.error_check):
            check.toggled.connect(self._plot_options_changed)
            oh.addWidget(check)
        oh.addStretch(1)
        ll.addWidget(opts)
        ll.addSpacing(4)
        self.axes = AxesEditor(compact=True)
        self.axes.changed.connect(self._axes_changed)
        ll.addWidget(self.axes)
        ll.addStretch(1)
        ex = QWidget()
        eg = QGridLayout(ex)
        eg.setContentsMargins(0, 0, 0, 0)
        eg.setHorizontalSpacing(10)
        eg.addWidget(button("Export graph as…", "", self._export_graph), 0, 0)
        eg.addWidget(button("Export data as…", "", self._export_data), 0, 1)
        ll.addWidget(ex)
        left_scroll = QScrollArea()
        left_scroll.setObjectName("comparisonControlsScroll")
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setFixedWidth(450)
        left_scroll.setStyleSheet(
            f"QScrollArea#comparisonControlsScroll {{ background: {PANEL}; }} "
            f"QScrollArea#comparisonControlsScroll > QWidget > QWidget {{ background: {PANEL}; }}"
        )
        left_scroll.setWidget(left)
        bl.addWidget(left_scroll)
        # right: canvas + footer
        right = QWidget()
        rl = vbox(right, spacing=16)
        card = panel()
        cl = vbox(card, (20, 20, 20, 20))
        self.canvas = PlotCanvas()
        cl.addWidget(self.canvas)
        rl.addWidget(card, 1)
        foot = QWidget()
        fl = hbox(foot)
        fl.addWidget(button("Advanced…", "", self.advanced_requested.emit))
        fl.addStretch(1)
        fl.addWidget(button("Export full data…", "outline", self.export_full_requested.emit))
        rl.addWidget(foot)
        bl.addWidget(right, 1)
        lay.addWidget(body, 1)

    # ---- public --------------------------------------------------------------------
    def show_spec(self, spec: CompareSpec) -> None:
        self.spec = spec
        for check, value in ((self.legend_check, spec.show_legend), (self.connect_check, spec.connect_points), (self.error_check, spec.error_bars)):
            check.blockSignals(True)
            check.setChecked(value)
            check.blockSignals(False)
        self.header.set_title(("Anisotropy" if spec.kind == "anisotropy" else "TRES") + " Results · Comparison")
        self._rebuild_series()
        self._draw(reset_axes=True)

    # ---- series list ------------------------------------------------------------------
    def _rebuild_series(self) -> None:
        while self.series_lay.count():
            it = self.series_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for st in self.spec.series:
            self.series_lay.addWidget(self._series_row(st))
        self.series_lay.addStretch(1)
        self.series_scroll.setMinimumHeight(min(260, 44 * max(len(self.spec.series), 1) + 8))
        # add-series options: folders of the same level not yet used
        self.add_combo.blockSignals(True)
        self.add_combo.clear()
        self.add_combo.addItem("+ Add series…", None)
        used = {st.node.path for st in self.spec.series}
        level = self.spec.series[0].node.level if self.spec.series else max(self.session.n_levels - 1, 1)
        for r in self.session.roots:
            for n in r.folders_at(level):
                if n.path not in used:
                    self.add_combo.addItem(" › ".join(n.labels), n.path)
        self.add_combo.blockSignals(False)
        self.add_combo.setVisible(self.add_combo.count() > 1)

    def _series_row(self, st: SeriesStyle) -> QWidget:
        w = QFrame()
        w.setProperty("subpanel", True)
        row = hbox(w, (7, 6, 7, 6), 7)
        swatch = button("", "tiny", lambda _=False, s=st: self._style_series(s))
        swatch.setFixedSize(22, 22)
        swatch.setStyleSheet(f"QPushButton {{ background: {st.color}; border-radius: 4px; }}")
        swatch.setToolTip("Edit series style")
        row.addWidget(swatch)
        name = button(st.label or st.node.name, "link", lambda _=False, s=st: self._style_series(s))
        name.setToolTip("Edit series style · " + " › ".join(st.node.labels))
        row.addWidget(name, 1)
        row.addWidget(button("×", "tiny", lambda _=False, s=st: self._remove_series(s)))
        return w

    def _style_series(self, st: SeriesStyle) -> None:
        default_label = " › ".join(st.node.labels) if st.node.level > 1 else st.node.name
        sample = OverlaySample(st.node, SeriesConfig(label=st.label or default_label, color=st.color, marker=st.marker,
                                                     line_style=st.line_style, line_width=st.line_width))
        dlg = SampleStyleDialog(sample, self, "Series style")
        if dlg.exec() != QDialog.Accepted:
            return
        dlg.apply()
        st.color = sample.series.color
        st.marker = sample.series.marker
        st.line_style = sample.series.line_style
        st.line_width = sample.series.line_width
        st.label = sample.series.label
        self._rebuild_series()
        self._draw()

    def _remove_series(self, st: SeriesStyle) -> None:
        self.spec.series = [s for s in self.spec.series if s is not st]
        self._rebuild_series()
        self._draw()

    def _add_series(self, i: int) -> None:
        path = self.add_combo.itemData(i)
        if not path:
            return
        from ..widgets.folder_tree import find_node
        node = find_node(self.session, path)
        if node is None:
            return
        color, marker = default_style(len(self.spec.series))
        self.spec.series.append(SeriesStyle(node, color, marker))
        self._rebuild_series()
        self._draw()

    def _plot_options_changed(self) -> None:
        if self.spec is None:
            return
        self.spec.show_legend = self.legend_check.isChecked()
        self.spec.connect_points = self.connect_check.isChecked()
        self.spec.error_bars = self.error_check.isChecked()
        self._draw()

    # ---- drawing --------------------------------------------------------------------
    def _draw(self, reset_axes: bool = False) -> None:
        if self.spec is None:
            return
        try:
            self.pc = build_plot_config(self.session, self.spec, name=self._plot_name())
        except ValueError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Cannot plot", str(exc))
            return
        self.canvas.draw(self.session.result, self.pc)
        if reset_axes:
            xl, yl = self.canvas.current_labels()
            self.axes.set_titles(xl, yl)
            self.axes.set_limits(self.spec.x_limits, self.spec.y_limits)
            self.axes.set_figure_size(self.spec.figsize)
        s = self.session
        s.plots_made = [p for p in s.plots_made if p.name != self.pc.name] + [copy.deepcopy(self.pc)]

    def _plot_name(self) -> str:
        sp = self.spec
        if sp.plot_type() == "metric_vs_metric":
            return f"{sp.metric_y}_vs_{sp.metric_x}"
        metric = sp.metric_y if sp.group_axis == "x" else sp.metric_x
        return f"{metric}_vs_{self.session.level_name(sp.values_level or self.session.n_levels)}"

    def _axes_changed(self) -> None:
        sp = self.spec
        # titles: write into the spec so the plot config keeps them
        xt, yt = self.axes.x_title.text().strip(), self.axes.y_title.text().strip()
        if sp.plot_type() == "metric_vs_metric":
            sp.value_title_x, sp.value_title_y = xt, yt
        elif sp.group_axis == "x":
            sp.group_title, sp.value_title_y = xt, yt
        else:
            sp.value_title_x, sp.group_title = xt, yt
        tmp = copy.deepcopy(self.pc)
        self.axes.apply_to(tmp)
        sp.x_limits, sp.y_limits = tmp.x_limits, tmp.y_limits
        sp.figsize = tmp.extra.get("figsize")
        self._draw()

    def _export_graph(self) -> None:
        if self.pc is not None:
            self.canvas.export_image(self, self.pc.name, dpi=int(self.session.advanced["output"]["dpi"]))

    def _export_data(self) -> None:
        if self.pc is not None:
            self.canvas.export_data(self, self.pc.name + "_data")
