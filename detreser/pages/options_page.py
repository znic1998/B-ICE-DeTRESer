"""Pages 2/3 · Options: name the folder levels, TRES or anisotropy options, Run analysis.

One widget serves both mockups; the option rows shown depend on the detected measurement type.
"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QRadioButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..model import Session
from ..theme import (ComboBox, REPLICATE_COLORS, TEXT_MUTED, Badge, Header, button, hbox, hline, label, panel, section_label, vbox)
from ..widgets.folder_tree import FolderTree


def _row(title: str, content: QWidget, align_top: bool = False) -> QWidget:
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 10, 0, 10)
    g.setHorizontalSpacing(16)
    t = QLabel(title)
    t.setProperty("bold", True)
    t.setFixedWidth(180)
    g.addWidget(t, 0, 0, Qt.AlignTop if align_top else Qt.AlignVCenter)
    g.addWidget(content, 0, 1)
    g.setColumnStretch(1, 1)
    return w


def _radio_row(items, spacing: int = 24) -> tuple:
    w = QWidget()
    h = hbox(w, spacing=spacing)
    group = QButtonGroup(w)
    radios = []
    for i, text in enumerate(items):
        r = QRadioButton(text)
        group.addButton(r, i)
        h.addWidget(r)
        radios.append(r)
    return w, h, group, radios


def _num_edit(placeholder: str, width: int) -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setProperty("mono", True)
    e.setFixedWidth(width)
    return e


class OptionsPage(QWidget):
    run_requested = Signal()
    advanced_requested = Signal()
    start_over_requested = Signal()

    def __init__(self, session: Session, on_readme):
        super().__init__()
        self.session = session
        lay = vbox(self)
        self.header = Header("Options", on_readme)
        lay.addWidget(self.header)
        body = QWidget()
        bl = hbox(body, (24, 24, 24, 24), 24)
        self.tree = FolderTree(session)
        self.tree.changed.connect(self.refresh)
        bl.addWidget(self.tree)
        self.card = panel()
        cl = vbox(self.card, (28, 24, 28, 24), 20)
        # level names
        self.level_box = QWidget()
        self.level_lay = vbox(self.level_box, spacing=10)
        self.level_lay.addWidget(section_label("Folder level names"))
        self.level_grid = QGridLayout()
        self.level_grid.setHorizontalSpacing(16)
        self.level_lay.addLayout(self.level_grid)
        cl.addWidget(self.level_box)
        # options
        opts = QWidget()
        ol = vbox(opts)
        ol.addWidget(section_label("Options"))
        ol.addSpacing(6)
        ol.addWidget(hline())
        # measurement type
        w, h, self.type_group, self.type_radios = _radio_row(["Time-resolved emission", "Anisotropy"])
        self.type_note = QLabel("Detected from the workbooks")
        self.type_note.setProperty("muted13", True)
        h.addWidget(self.type_note)
        h.addStretch(1)
        for r in self.type_radios:
            r.setEnabled(False)  # display only: detection decides
        ol.addWidget(_row("Measurement type", w))
        ol.addWidget(hline())
        # probe
        self.probe = QLineEdit()
        self.probe.setFixedWidth(320)
        pw = QWidget(); ph = hbox(pw); ph.addWidget(self.probe); ph.addStretch(1)
        ol.addWidget(_row("Probe name", pw))
        ol.addWidget(hline())
        # --- TRES rows
        self.tres_rows: List[QWidget] = []
        w, h, self.ratio_group, self.ratio_radios = _radio_row(["GP (440 / 490 nm)", "Custom"])
        el = QLabel("Expression"); h.addWidget(el)
        self.ratio_expr = _num_edit("I(510) / I(430)", 200)
        h.addWidget(self.ratio_expr); h.addStretch(1)
        r = _row("Ratio measure", w); ol.addWidget(r); self.tres_rows.append(r)
        s = hline(); ol.addWidget(s); self.tres_rows.append(s)
        w, h, self.nu0_group, self.nu0_radios = _radio_row(["Apparent (shows a warning)", "Custom"])
        h.addWidget(QLabel("Wavenumber"))
        self.nu0_value = _num_edit("23800", 110)
        h.addWidget(self.nu0_value); h.addWidget(QLabel("cm⁻¹")); h.addStretch(1)
        r = _row("ν₀ for TDFS", w); ol.addWidget(r); self.tres_rows.append(r)
        s = hline(); ol.addWidget(s); self.tres_rows.append(s)
        # --- anisotropy rows
        self.aniso_rows: List[QWidget] = []
        w, h, self.visc_group, self.visc_radios = _radio_row(["Calculate", "Skip"])
        h.addStretch(1)
        r = _row("Microviscosity", w); ol.addWidget(r); self.aniso_rows.append(r)
        s = hline(); ol.addWidget(s); self.aniso_rows.append(s)
        vw = QWidget(); vh = hbox(vw, spacing=8)
        self.volume = _num_edit("161", 110)
        self.volume_unit = ComboBox(); self.volume_unit.addItems(["Å³", "nm³", "cm³", "m³"]); self.volume_unit.setFixedWidth(90)
        vh.addWidget(self.volume); vh.addWidget(self.volume_unit); vh.addStretch(1)
        r = _row("Effective volume", vw); ol.addWidget(r); self.aniso_rows.append(r)
        s = hline(); ol.addWidget(s); self.aniso_rows.append(s)
        w, h, self.temp_group, self.temp_radios = _radio_row(["From folder level", "Fixed"])
        self.temp_level = ComboBox(); self.temp_level.setFixedWidth(120)
        h.insertWidget(1, self.temp_level)
        self.temp_fixed = _num_edit("293", 90)
        h.addWidget(self.temp_fixed); h.addWidget(QLabel("K")); h.addStretch(1)
        r = _row("Temperature", w); ol.addWidget(r); self.aniso_rows.append(r)
        s = hline(); ol.addWidget(s); self.aniso_rows.append(s)
        w, h, self.r0_group, self.r0_radios = _radio_row(["Literature (0.39)", "Fitted from data", "Custom"])
        self.r0_custom = _num_edit("0.40", 90)
        h.addWidget(self.r0_custom); h.addStretch(1)
        r = _row("r₀ source", w); ol.addWidget(r); self.aniso_rows.append(r)
        s = hline(); ol.addWidget(s); self.aniso_rows.append(s)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(opts)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollArea > QWidget > QWidget { background: transparent; }")
        cl.addWidget(scroll, 1)
        # footer
        foot = QWidget()
        fl = hbox(foot)
        fl.addWidget(button("Advanced…", "", self.advanced_requested.emit))
        fl.addSpacing(12)
        fl.addWidget(button("Start over", "", self.start_over_requested.emit))
        fl.addStretch(1)
        self.run_btn = button("Run analysis", "primary", self._run)
        fl.addWidget(self.run_btn)
        cl.addWidget(foot)
        bl.addWidget(self.card, 1)
        lay.addWidget(body, 1)
        self.level_edits: List[QLineEdit] = []
        # signals
        self.ratio_group.idClicked.connect(lambda i: self.ratio_expr.setEnabled(i == 1))
        self.nu0_group.idClicked.connect(lambda i: self.nu0_value.setEnabled(i == 1))
        self.temp_group.idClicked.connect(self._temp_mode)
        self.r0_group.idClicked.connect(lambda i: self.r0_custom.setEnabled(i == 2))
        self.visc_group.idClicked.connect(self._visc_mode)
        self.refresh()

    # ---- state -------------------------------------------------------------------
    def refresh(self) -> None:
        s = self.session
        self.tree.refresh()
        # level name inputs
        while self.level_grid.count():
            it = self.level_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.level_edits = []
        placeholders = ["e.g. Composition", "e.g. Temperature", "e.g. Concentration"]
        n = s.n_levels
        for k in range(1, n + 1):
            cell = QWidget()
            cl = vbox(cell, spacing=6)
            cl.addWidget(Badge(f"Level {k}", level=k, size=12, weight=600))
            e = QLineEdit()
            e.setPlaceholderText(placeholders[k - 1] if k <= len(placeholders) else f"e.g. Level {k}")
            if k <= len(s.level_names):
                e.setText(s.level_names[k - 1])
            e.editingFinished.connect(self._names_changed)
            cl.addWidget(e)
            self.level_edits.append(e)
            self.level_grid.addWidget(cell, 0, k - 1)
        rep = QWidget()
        rl = vbox(rep, spacing=6)
        rl.addWidget(Badge("Replicate", REPLICATE_COLORS, size=12, weight=600))
        rt = QLabel("Excel files (automatic)")
        rt.setProperty("muted", True)
        rt.setFixedHeight(36)
        rl.addWidget(rt)
        self.level_grid.addWidget(rep, 0, n)
        for c in range(max(n + 1, 4)):
            self.level_grid.setColumnStretch(c, 1)
        # temperature level combo
        self.temp_level.clear()
        for k in range(1, n + 1):
            self.temp_level.addItem(s.level_name(k))
        self.temp_level.setCurrentIndex(min(max(s.temp_level, 1), max(n, 1)) - 1)
        self._apply_kind()
        # values
        self.probe.setText(s.probe)
        self.probe.setPlaceholderText("e.g. TMA-DPH" if s.kind == "anisotropy" else "e.g. Laurdan")
        self.ratio_radios[0 if s.ratio_mode == "gp" else 1].setChecked(True)
        self.ratio_expr.setText(s.ratio_expression)
        self.ratio_expr.setEnabled(s.ratio_mode == "custom")
        self.nu0_radios[0 if s.nu0_mode == "apparent" else 1].setChecked(True)
        self.nu0_value.setText(s.nu0_value)
        self.nu0_value.setEnabled(s.nu0_mode == "custom")
        self.visc_radios[0 if s.visc_calculate else 1].setChecked(True)
        self.volume.setText(s.volume_value)
        self.volume_unit.setCurrentIndex({"A3": 0, "nm3": 1, "cm3": 2, "m3": 3}.get(s.volume_unit, 0))
        self.temp_radios[0 if s.temp_mode == "level" else 1].setChecked(True)
        self.temp_fixed.setText(s.temp_fixed)
        self._temp_mode(0 if s.temp_mode == "level" else 1)
        self.r0_radios[{"literature": 0, "fitted": 1, "user": 2}[s.r0_source]].setChecked(True)
        self.r0_custom.setText(s.r0_custom)
        self.r0_custom.setEnabled(s.r0_source == "user")
        self._visc_mode(0 if s.visc_calculate else 1)

    def _apply_kind(self) -> None:
        s = self.session
        aniso = s.kind == "anisotropy"
        self.type_radios[1 if aniso else 0].setChecked(True)
        for w in self.tres_rows:
            w.setVisible(not aniso)
        for w in self.aniso_rows:
            w.setVisible(aniso)
        self.type_note.setText(s.kind_detail or "Detected from the workbooks")
        self.run_btn.setEnabled(s.kind in ("tres", "anisotropy", "mixed") and bool(s.roots))

    def set_kind(self, kind: str, detail: str) -> None:
        self.session.kind = kind
        self.session.kind_detail = detail
        self._apply_kind()
        self.probe.setPlaceholderText("e.g. TMA-DPH" if kind == "anisotropy" else "e.g. Laurdan")

    def _names_changed(self) -> None:
        self.session.level_names = [e.text() for e in self.level_edits]
        self.tree.refresh()
        cur = self.temp_level.currentIndex()
        self.temp_level.clear()
        for k in range(1, self.session.n_levels + 1):
            self.temp_level.addItem(self.session.level_name(k))
        self.temp_level.setCurrentIndex(max(cur, 0))

    def _temp_mode(self, i: int) -> None:
        self.temp_level.setEnabled(i == 0 and self.visc_radios[0].isChecked())
        self.temp_fixed.setEnabled(i == 1 and self.visc_radios[0].isChecked())

    def _visc_mode(self, i: int) -> None:
        on = i == 0
        for w in (self.volume, self.volume_unit, self.r0_custom):
            w.setEnabled(on)
        for r in self.temp_radios + self.r0_radios:
            r.setEnabled(on)
        self._temp_mode(0 if self.temp_radios[0].isChecked() else 1)
        if on:
            self.r0_custom.setEnabled(self.r0_radios[2].isChecked())

    def collect(self) -> None:
        s = self.session
        s.level_names = [e.text() for e in self.level_edits]
        s.probe = self.probe.text().strip()
        s.ratio_mode = "gp" if self.ratio_radios[0].isChecked() else "custom"
        s.ratio_expression = self.ratio_expr.text().strip() or "I(510) / I(430)"
        s.nu0_mode = "apparent" if self.nu0_radios[0].isChecked() else "custom"
        s.nu0_value = self.nu0_value.text().strip() or "23800"
        s.visc_calculate = self.visc_radios[0].isChecked()
        s.volume_value = self.volume.text().strip() or "161"
        s.volume_unit = ["A3", "nm3", "cm3", "m3"][self.volume_unit.currentIndex()]
        s.temp_mode = "level" if self.temp_radios[0].isChecked() else "fixed"
        s.temp_level = self.temp_level.currentIndex() + 1
        s.temp_fixed = self.temp_fixed.text().strip() or "293"
        s.r0_source = ["literature", "fitted", "user"][self.r0_group.checkedId() if self.r0_group.checkedId() >= 0 else 0]
        s.r0_custom = self.r0_custom.text().strip() or "0.40"

    def _run(self) -> None:
        self.collect()
        self.run_requested.emit()
