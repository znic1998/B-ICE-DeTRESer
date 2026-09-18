"""Graph viewer for single-sample plots, including compatible multi-sample overlays."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QFrame, QGridLayout, QHeaderView, QLabel, QLineEdit, QScrollArea, QStackedWidget,
                               QTreeWidget, QTreeWidgetItem, QWidget)

from tres_suite.config import SeriesConfig

from ..model import Node, Session
from ..theme import (PANEL, SERIES_COLORS, Badge, ComboBox, Header, Segmented, button, hbox, label,
                     panel, section_label, vbox)
from ..widgets.folder_tree import find_node
from ..widgets.plot_canvas import AxesEditor, PlotCanvas, SampleTables
from .results_page import default_style


LINE_STYLES = [("Solid", "-"), ("Dashed", "--"), ("Dotted", ":"), ("Dash-dot", "-.")]
MARKERS = [("None", ""), ("Circle", "o"), ("Square", "s"), ("Triangle", "^"), ("Diamond", "D")]


@dataclass
class OverlaySample:
    node: Node
    series: SeriesConfig


class SamplePickerDialog(QDialog):
    """Choose additional analysed condition groups for the active plot."""

    def __init__(self, session: Session, already: set[str], parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Add samples")
        self.resize(620, 520)
        lay = vbox(self, (20, 18, 20, 18), 12)
        lay.addWidget(label("Add samples", h2=True))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search samples…")
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Sample", "Status"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().resizeSection(1, 230)
        for root in session.roots:
            for node in root.folders_at(session.group_level()):
                group = session.group_for_node(node)
                n = group.n_replicates if group is not None else 0
                item = QTreeWidgetItem([" › ".join(node.labels), f"n={n}"])
                item.setData(0, Qt.UserRole, node.path)
                item.setCheckState(0, Qt.Unchecked)
                if node.path in already:
                    item.setText(1, f"n={n} · already added")
                    item.setDisabled(True)
                elif group is None or group.status != "ok":
                    item.setText(1, f"blocked · {node.block_reason or 'not analysed'}")
                    item.setDisabled(True)
                self.tree.addTopLevelItem(item)
        lay.addWidget(self.tree, 1)
        note = QLabel("Only analysed samples from this run are available. They are added to the currently selected plot type.")
        note.setWordWrap(True)
        note.setProperty("muted13", True)
        lay.addWidget(note)
        box = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        box.button(QDialogButtonBox.Ok).setText("Add selected")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.search.textChanged.connect(self._filter)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setHidden(bool(text) and text not in (item.text(0) + " " + item.text(1)).lower())

    def selected_nodes(self) -> List[Node]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked and not item.isDisabled():
                node = find_node(self.session, item.data(0, Qt.UserRole))
                if node is not None:
                    out.append(node)
        return out


class SampleStyleDialog(QDialog):
    """Edit the visual identity and legend name of one overlaid sample."""

    def __init__(self, sample: OverlaySample, parent=None, title: str = "Sample style"):
        super().__init__(parent)
        self.sample = sample
        self.color = str(sample.series.color or SERIES_COLORS[0][1])
        self.setWindowTitle(title)
        self.resize(420, 360)
        lay = vbox(self, (20, 18, 20, 18), 14)
        lay.addWidget(label(title, h2=True))
        lay.addWidget(label(" › ".join(sample.node.labels), bold=True))
        form = QFormLayout()
        self.color_btn = button(self.color, "", self._choose_color)
        self._paint_color()
        form.addRow("Color", self.color_btn)
        self.line = ComboBox()
        for name, value in LINE_STYLES:
            self.line.addItem(name, value)
        self.line.setCurrentIndex(max(self.line.findData(sample.series.line_style or "-"), 0))
        form.addRow("Line style", self.line)
        self.width = QDoubleSpinBox()
        self.width.setRange(0.5, 8.0)
        self.width.setSingleStep(0.25)
        self.width.setValue(float(sample.series.line_width or 1.8))
        form.addRow("Line width", self.width)
        self.marker = ComboBox()
        for name, value in MARKERS:
            self.marker.addItem(name, value)
        self.marker.setCurrentIndex(max(self.marker.findData(sample.series.marker or ""), 0))
        form.addRow("Marker", self.marker)
        self.legend_name = QLineEdit(sample.series.label)
        form.addRow("Legend name", self.legend_name)
        lay.addLayout(form)
        self.preview = QLabel("Preview   ━━━━━━━━━")
        self.preview.setStyleSheet(f"color: {self.color}; font-size: 16px; padding: 12px; border: 1px solid #d9e0ea; border-radius: 8px;")
        lay.addWidget(self.preview)
        box = QDialogButtonBox(QDialogButtonBox.Reset | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        box.clicked.connect(self._clicked)
        lay.addWidget(box)

    def _paint_color(self) -> None:
        self.color_btn.setText(self.color)
        self.color_btn.setStyleSheet(f"QPushButton {{ color: white; background: {self.color}; }}")
        if hasattr(self, "preview"):
            self.preview.setStyleSheet(f"color: {self.color}; font-size: 16px; padding: 12px; border: 1px solid #d9e0ea; border-radius: 8px;")

    def _choose_color(self) -> None:
        chosen = QColorDialog.getColor(parent=self, title="Sample colour")
        if chosen.isValid():
            self.color = chosen.name()
            self._paint_color()

    def _clicked(self, btn) -> None:
        role = self.sender().buttonRole(btn)
        if role == QDialogButtonBox.ResetRole:
            self.color = SERIES_COLORS[0][1]
            self.line.setCurrentIndex(0)
            self.width.setValue(1.8)
            self.marker.setCurrentIndex(0)
            self.legend_name.setText(" / ".join(self.sample.node.labels[-2:]))
            self._paint_color()
        elif role == QDialogButtonBox.RejectRole:
            self.reject()
        else:
            self.accept()

    def apply(self) -> None:
        s = self.sample.series
        s.color = self.color
        s.line_style = self.line.currentData()
        s.line_width = self.width.value()
        s.marker = self.marker.currentData()
        s.label = self.legend_name.text().strip() or " / ".join(self.sample.node.labels[-2:])


class GraphViewPage(QWidget):
    back_requested = Signal()
    export_full_requested = Signal()

    def __init__(self, session: Session, on_readme):
        super().__init__()
        self.session = session
        self.node = None
        self.plots = []
        self.samples_by_plot: List[List[OverlaySample]] = []
        self.current = 0
        lay = vbox(self)
        self.header = Header("Graph viewer", on_readme)
        lay.addWidget(self.header)
        body = QWidget()
        bl = vbox(body, (24, 24, 24, 24), 16)
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
        mid = QWidget()
        ml = hbox(mid, spacing=20)
        card = panel()
        cl = vbox(card, (24, 24, 24, 24), 8)
        self.plot_title = label("", h3=True)
        cl.addWidget(self.plot_title)
        self.stack = QStackedWidget()
        self.table = SampleTables()
        self.canvas = PlotCanvas()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.canvas)
        self.stack.setCurrentIndex(1)
        cl.addWidget(self.stack, 1)
        ml.addWidget(card, 1)
        side_scroll = QScrollArea()
        side_scroll.setObjectName("graphControlsScroll")
        side_scroll.setStyleSheet(
            f"QScrollArea#graphControlsScroll {{ background: {PANEL}; }} "
            f"QScrollArea#graphControlsScroll > QWidget > QWidget {{ background: {PANEL}; }}"
        )
        side_scroll.setWidgetResizable(True)
        side_scroll.setFixedWidth(360)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side = QWidget()
        side.setObjectName("graphControlsHost")
        side.setStyleSheet(f"QWidget#graphControlsHost {{ background: {PANEL}; }}")
        sl = vbox(side, spacing=12)
        sample_panel = QFrame()
        sample_panel.setProperty("panel", True)
        spl = vbox(sample_panel, (14, 14, 14, 14), 8)
        spl.addWidget(section_label("Samples"))
        self.samples_box = QWidget()
        self.samples_lay = vbox(self.samples_box, spacing=7)
        spl.addWidget(self.samples_box)
        spl.addWidget(button("+ Add sample…", "outline", self._add_samples))
        self.legend_check = QCheckBox("Show legend")
        self.legend_check.setChecked(True)
        self.legend_check.toggled.connect(self._options_changed)
        spl.addWidget(self.legend_check)
        self.sd_check = QCheckBox("Shaded SD band / error bars")
        self.sd_check.setChecked(True)
        self.sd_check.toggled.connect(self._options_changed)
        spl.addWidget(self.sd_check)
        sl.addWidget(sample_panel)
        self.axes = AxesEditor(compact=True)
        self.axes.changed.connect(self._axes_changed)
        sl.addWidget(self.axes)
        exports = QWidget()
        export_grid = QGridLayout(exports)
        export_grid.setContentsMargins(0, 0, 0, 0)
        export_grid.setHorizontalSpacing(8)
        export_grid.addWidget(button("Export graph as…", "", self._export_graph), 0, 0)
        export_grid.addWidget(button("Export data as…", "", self._export_data), 0, 1)
        sl.addWidget(exports)
        sl.addStretch(1)
        side_scroll.setWidget(side)
        ml.addWidget(side_scroll)
        bl.addWidget(mid, 1)
        bottom = QWidget()
        btl = hbox(bottom)
        self.switcher = Segmented([""], self._switch)
        btl.addWidget(self.switcher)
        btl.addStretch(1)
        btl.addWidget(button("Export full data…", "outline", self.export_full_requested.emit))
        bl.addWidget(bottom)
        lay.addWidget(body, 1)

    def _default_sample(self, node: Node, index: int = 0) -> OverlaySample:
        color, _ = default_style(index)
        group = self.session.group_for_node(node)
        n = group.n_replicates if group is not None else 0
        legend = f"{' / '.join(node.labels[-2:])} (n={n})"
        return OverlaySample(node, SeriesConfig(label=legend, select=self.session.select_for_node(node), color=color,
                                                marker="", line_style="-", line_width=1.8))

    def show_plots(self, node: Node, plots: List) -> None:
        self.node = node
        self.plots = plots
        self.samples_by_plot = [[self._default_sample(node)] for _ in plots]
        self.switcher.set_items([p.extra.get("display_name", p.type) for p in plots])
        for b in self.switcher._buttons:
            b.setProperty("compact", True)
            b.style().unpolish(b)
            b.style().polish(b)
        self.current = 0
        self._draw(reset_controls=True)

    def _switch(self, i: int) -> None:
        self.current = i
        self._draw(reset_controls=True)

    def _sync_plot(self, pc) -> None:
        samples = self.samples_by_plot[self.current]
        pc.series = [copy.deepcopy(s.series) for s in samples]
        pc.group = copy.deepcopy(samples[0].series.select) if samples else None
        pc.extra["legend_labels_exact"] = True
        pc.extra["show_legend"] = self.legend_check.isChecked()
        pc.error_bars = self.sd_check.isChecked()

    def _draw(self, reset_controls: bool = False) -> None:
        if not self.plots:
            return
        pc = self.plots[self.current]
        if reset_controls:
            self.legend_check.blockSignals(True)
            self.sd_check.blockSignals(True)
            self.legend_check.setChecked(bool(pc.extra.get("show_legend", True)))
            self.sd_check.setChecked(bool(pc.error_bars))
            self.legend_check.blockSignals(False)
            self.sd_check.blockSignals(False)
        self._sync_plot(pc)
        samples = self.samples_by_plot[self.current]
        base_title = pc.extra.get("card_title") or pc.title or pc.extra.get("display_name", "")
        if len(samples) > 1:
            base_title = f"{pc.extra.get('display_name', base_title)} — {len(samples)} samples"
        self.plot_title.setText(base_title)
        self._rebuild_crumbs()
        self._rebuild_samples()
        self.canvas.draw(self.session.result, pc)
        xl, yl = self.canvas.current_labels()
        self.axes.set_titles(pc.x_label or xl, pc.y_label or yl)
        self.axes.set_limits(pc.x_limits, pc.y_limits)
        self.axes.set_figure_size(pc.extra.get("figsize"))
        if self.canvas.draw_result is not None:
            self.table.set_df(self.canvas.draw_result.data)
        self._remember(pc)

    def _rebuild_crumbs(self) -> None:
        while self.crumbs_lay.count():
            item = self.crumbs_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        samples = self.samples_by_plot[self.current]
        if samples:
            for i, name in enumerate(samples[0].node.labels, start=1):
                if i > 1:
                    self.crumbs_lay.addWidget(QLabel("›"))
                self.crumbs_lay.addWidget(Badge(name, level=i))
        if len(samples) > 1:
            self.crumbs_lay.addWidget(label(f"+ {len(samples) - 1} more", bold=True))

    def _rebuild_samples(self) -> None:
        while self.samples_lay.count():
            item = self.samples_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        samples = self.samples_by_plot[self.current]
        for sample in samples:
            row = QFrame()
            row.setProperty("subpanel", True)
            rl = hbox(row, (7, 6, 7, 6), 6)
            swatch = button("", "tiny", lambda _=False, s=sample: self._style_sample(s))
            swatch.setFixedSize(22, 22)
            swatch.setStyleSheet(f"QPushButton {{ background: {sample.series.color}; border-radius: 4px; }}")
            swatch.setToolTip("Edit sample style")
            rl.addWidget(swatch)
            name = button(sample.series.label, "link", lambda _=False, s=sample: self._style_sample(s))
            name.setToolTip("Edit sample style")
            rl.addWidget(name, 1)
            remove = button("×", "tiny", lambda _=False, s=sample: self._remove_sample(s))
            remove.setEnabled(len(samples) > 1)
            rl.addWidget(remove)
            self.samples_lay.addWidget(row)

    def _add_samples(self) -> None:
        current = self.samples_by_plot[self.current]
        dlg = SamplePickerDialog(self.session, {s.node.path for s in current}, self)
        if dlg.exec() != QDialog.Accepted:
            return
        selected = dlg.selected_nodes()
        for node in selected:
            current.append(self._default_sample(node, len(current)))
        if selected:
            self._draw()

    def _remove_sample(self, sample: OverlaySample) -> None:
        samples = self.samples_by_plot[self.current]
        if len(samples) <= 1:
            return
        samples.remove(sample)
        self._draw()

    def _style_sample(self, sample: OverlaySample) -> None:
        dlg = SampleStyleDialog(sample, self)
        if dlg.exec() == QDialog.Accepted:
            dlg.apply()
            self._draw()

    def _remember(self, pc) -> None:
        s = self.session
        s.plots_made = [p for p in s.plots_made if p.name != pc.name] + [copy.deepcopy(pc)]

    def _axes_changed(self) -> None:
        pc = self.plots[self.current]
        self.axes.apply_to(pc)
        self._draw()

    def _options_changed(self) -> None:
        if self.plots:
            self._draw()

    def _toggle_view(self, i: int) -> None:
        self.stack.setCurrentIndex(i)

    def _export_graph(self) -> None:
        pc = self.plots[self.current]
        self.canvas.export_image(self, pc.name, dpi=int(self.session.advanced["output"]["dpi"]))

    def _export_data(self) -> None:
        pc = self.plots[self.current]
        self.canvas.export_data(self, pc.name + "_data")
