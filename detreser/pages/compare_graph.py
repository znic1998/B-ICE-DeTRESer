"""Page 8 · Comparison graph (shared by TRES and anisotropy): series styling, editable axes, exports."""
from __future__ import annotations

import copy
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QColorDialog, QComboBox, QGridLayout, QLabel, QScrollArea, QSizePolicy, QWidget

from ..model import Node, Session
from ..theme import ComboBox, SERIES_COLORS, SERIES_MARKERS, Badge, Header, button, hbox, label, panel, section_label, vbox
from ..widgets.plot_canvas import AxesEditor, PlotCanvas
from .results_page import CompareSpec, SeriesStyle, build_plot_config, default_style


class _Swatch(QLabel):
    def __init__(self, color: str):
        super().__init__()
        self.setFixedSize(14, 14)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"background: {color}; border-radius: 3px;")


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
        # left card
        left = panel()
        left.setFixedWidth(420)
        ll = vbox(left, (20, 20, 20, 20), 14)
        ll.addWidget(button("← Back to setup", "link", self.back_requested.emit), 0, Qt.AlignLeft)
        ll.addWidget(section_label("Series"))
        self.series_box = QWidget()
        self.series_lay = vbox(self.series_box, spacing=8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.series_box)
        scroll.setMaximumHeight(260)
        scroll.setMinimumHeight(60)
        self.series_scroll = scroll
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        ll.addWidget(scroll)
        self.add_combo = ComboBox()
        self.add_combo.setStyleSheet("QComboBox { border: 1px dashed #8e9bb0; }")
        self.add_combo.activated.connect(self._add_series)
        ll.addWidget(self.add_combo)
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
        bl.addWidget(left)
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
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(8)
        g.setColumnStretch(0, 1)
        badge = Badge(st.node.name, level=st.node.level, size=14)
        badge.setToolTip(" › ".join(st.node.labels))
        badge.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        badge.setMinimumWidth(40)
        g.addWidget(badge, 0, 0)
        cw = QWidget()
        ch = hbox(cw, spacing=6)
        sw = _Swatch(st.color)
        ch.addWidget(sw)
        cc = ComboBox()
        cc.setFixedWidth(104)
        for name, hexv in SERIES_COLORS:
            cc.addItem(name, hexv)
        cc.addItem("Custom…", "custom")
        idx = cc.findData(st.color)
        if idx < 0:
            cc.insertItem(cc.count() - 1, st.color, st.color)
            idx = cc.findData(st.color)
        cc.setCurrentIndex(idx)
        cc.activated.connect(lambda i, s=st, combo=cc, swatch=sw: self._color_changed(s, combo, swatch))
        ch.addWidget(cc)
        g.addWidget(cw, 0, 1)
        mc = ComboBox()
        mc.setFixedWidth(124)
        for name, m in SERIES_MARKERS:
            mc.addItem(name, m)
        mi = mc.findData(st.marker)
        mc.setCurrentIndex(mi if mi >= 0 else 0)
        mc.activated.connect(lambda i, s=st, combo=mc: self._marker_changed(s, combo))
        g.addWidget(mc, 0, 2)
        x = button("×", "tiny", lambda _=False, s=st: self._remove_series(s))
        g.addWidget(x, 0, 3)
        return w

    def _color_changed(self, st: SeriesStyle, combo: QComboBox, swatch: _Swatch) -> None:
        v = combo.currentData()
        if v == "custom":
            c = QColorDialog.getColor(parent=self, title="Series colour")
            if not c.isValid():
                combo.setCurrentIndex(max(combo.findData(st.color), 0))
                return
            v = c.name()
            combo.insertItem(combo.count() - 1, v, v)
            combo.setCurrentIndex(combo.findData(v))
        st.color = v
        swatch.set_color(v)
        self._draw()

    def _marker_changed(self, st: SeriesStyle, combo: QComboBox) -> None:
        st.marker = combo.currentData()
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
