"""Page 5 · Graph viewer for single-sample plots: canvas, editable axes, data table, exports."""
from __future__ import annotations

import copy
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget

from ..model import Node, Session
from ..theme import Badge, Header, Segmented, button, hbox, label, panel, vbox
from ..widgets.plot_canvas import AxesEditor, DataTable, PlotCanvas


class GraphViewPage(QWidget):
    back_requested = Signal()
    export_full_requested = Signal()

    def __init__(self, session: Session, on_readme):
        super().__init__()
        self.session = session
        self.node = None
        self.plots = []
        self.current = 0
        lay = vbox(self)
        self.header = Header("Graph viewer", on_readme)
        lay.addWidget(self.header)
        body = QWidget()
        bl = vbox(body, (24, 24, 24, 24), 16)
        # top row: back, breadcrumb, data/graph toggle
        top = QWidget()
        tl = hbox(top, spacing=16)
        tl.addWidget(button("← Back", "small", self.back_requested.emit))
        self.crumbs = QWidget()
        self.crumbs_lay = hbox(self.crumbs, spacing=8)
        tl.addWidget(self.crumbs)
        tl.addStretch(1)
        self.view_toggle = Segmented(["Data table", "Graph"], self._toggle_view)
        self.view_toggle.set_current(1)
        tl.addWidget(self.view_toggle)
        bl.addWidget(top)
        # middle: canvas card + side controls
        mid = QWidget()
        ml = hbox(mid, spacing=20)
        card = panel()
        cl = vbox(card, (24, 24, 24, 24), 8)
        self.plot_title = label("", h3=True)
        cl.addWidget(self.plot_title)
        self.stack = QStackedWidget()
        self.table = DataTable()
        self.canvas = PlotCanvas()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.canvas)
        self.stack.setCurrentIndex(1)
        cl.addWidget(self.stack, 1)
        ml.addWidget(card, 1)
        side = QWidget()
        side.setFixedWidth(240)
        sl = vbox(side, spacing=12)
        self.axes = AxesEditor()
        self.axes.changed.connect(self._axes_changed)
        sl.addWidget(self.axes)
        sl.addWidget(button("Export graph as…", "", self._export_graph))
        sl.addWidget(button("Export data as…", "", self._export_data))
        sl.addStretch(1)
        ml.addWidget(side)
        bl.addWidget(mid, 1)
        # bottom: plot switcher + export full
        bottom = QWidget()
        btl = hbox(bottom)
        self.switcher = Segmented([""], self._switch)
        btl.addWidget(self.switcher)
        btl.addStretch(1)
        btl.addWidget(button("Export full data…", "outline", self.export_full_requested.emit))
        bl.addWidget(bottom)
        lay.addWidget(body, 1)

    def show_plots(self, node: Node, plots: List) -> None:
        self.node = node
        self.plots = plots
        # breadcrumb
        while self.crumbs_lay.count():
            it = self.crumbs_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for i, name in enumerate(node.labels, start=1):
            if i > 1:
                sep = QLabel("›")
                sep.setProperty("muted", True)
                self.crumbs_lay.addWidget(sep)
            self.crumbs_lay.addWidget(Badge(name, level=i))
        self.switcher.set_items([p.extra.get("display_name", p.type) for p in plots])
        for b in self.switcher._buttons:
            b.setProperty("compact", True)
            b.style().unpolish(b)
            b.style().polish(b)
        self.current = 0
        self._draw()

    def _switch(self, i: int) -> None:
        self.current = i
        self._draw()

    def _draw(self) -> None:
        if not self.plots:
            return
        pc = self.plots[self.current]
        self.plot_title.setText(pc.extra.get("card_title") or pc.title or pc.extra.get("display_name", ""))
        self.canvas.draw(self.session.result, pc)
        xl, yl = self.canvas.current_labels()
        self.axes.set_titles(pc.x_label or xl, pc.y_label or yl)
        self.axes.set_limits(pc.x_limits, pc.y_limits)
        self.axes.set_figure_size(pc.extra.get("figsize"))
        if self.canvas.draw_result is not None:
            self.table.set_df(self.canvas.draw_result.data)
        self._remember(pc)

    def _remember(self, pc) -> None:
        s = self.session
        s.plots_made = [p for p in s.plots_made if p.name != pc.name] + [copy.deepcopy(pc)]

    def _axes_changed(self) -> None:
        pc = self.plots[self.current]
        self.axes.apply_to(pc)
        self._draw()

    def _toggle_view(self, i: int) -> None:
        self.stack.setCurrentIndex(i)

    def _export_graph(self) -> None:
        pc = self.plots[self.current]
        self.canvas.export_image(self, pc.name, dpi=int(self.session.advanced["output"]["dpi"]))

    def _export_data(self) -> None:
        pc = self.plots[self.current]
        self.canvas.export_data(self, pc.name + "_data")
