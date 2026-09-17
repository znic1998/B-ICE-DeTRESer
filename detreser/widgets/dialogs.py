"""Popups: Run-Loading, Run-Errors, Advanced settings, Read Me, overwrite confirmation."""
from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
                               QRadioButton, QScrollArea, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget, QButtonGroup, QFileDialog)

from ..model import Session, default_advanced
from ..theme import (ComboBox, ACCENT, BORDER_SOFT, ERROR, ERROR_BG, ERROR_BORDER, MONO, TEXT_SOFT, Header, Segmented, button, hbox, hline, label,
                     section_label, vbox)


class _Overlay(QDialog):
    """Frameless modal dialog drawn over the main window with the dimmed navy header of the mockups."""

    def __init__(self, parent, width: int):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        outer = vbox(self)
        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setStyleSheet("#card { background: white; border-radius: 14px; }")
        self.card.setFixedWidth(width)
        outer.addStretch(1)
        outer.addWidget(self.card, 0, Qt.AlignHCenter)
        outer.addStretch(1)
        self.body = vbox(self.card, (32, 32, 32, 32), 16)

    def showEvent(self, ev):
        super().showEvent(ev)
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.frameGeometry() if p.isWindow() else p.geometry())
            self.move(p.mapToGlobal(p.rect().topLeft()))
            self.resize(p.size())

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 21, 41, 150))
        p.fillRect(0, 0, self.width(), 56, QColor(10, 21, 41, 220))
        p.setPen(QColor("#b7c0cf"))
        f = p.font()
        f.setPointSize(16)
        f.setItalic(True)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(24, 0, 400, 56), Qt.AlignVCenter | Qt.AlignLeft, "B-ICE DeTRESer")


class Spinner(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(96, 96)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(30)

    def _tick(self):
        self.angle = (self.angle + 12) % 360
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(5, 5, 86, 86)
        p.setPen(QPen(QColor(BORDER_SOFT), 10))
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(ACCENT), 10, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, -self.angle * 16, 90 * 16)


class RunLoadingDialog(_Overlay):
    """Spinner + progress bar + "k of n files" + Cancel."""

    cancel_requested = Signal()

    def __init__(self, parent):
        super().__init__(parent, 440)
        self.body.setAlignment(Qt.AlignHCenter)
        self.spinner = Spinner()
        self.body.addWidget(self.spinner, 0, Qt.AlignHCenter)
        self.title = label("Analyzing…", h2=True)
        self.title.setAlignment(Qt.AlignCenter)
        self.body.addWidget(self.title)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 0)
        self.bar.setFixedHeight(8)
        self.body.addWidget(self.bar)
        self.status = label("Loading workbooks…", muted=True)
        self.status.setAlignment(Qt.AlignCenter)
        self.body.addWidget(self.status)
        self.cancel_btn = button("Cancel", "small", self._cancel)
        self.cancel_btn.setFixedHeight(40)
        self.body.addWidget(self.cancel_btn, 0, Qt.AlignHCenter)

    def set_progress(self, done: int, total: int, stage: str) -> None:
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(done)
        else:
            self.bar.setRange(0, 0)
        verb = "Loading" if stage == "loading" else "Analysing"
        self.status.setText(f"{verb}: {done} of {total} files")

    def set_message(self, text: str) -> None:
        self.status.setText(text)

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.status.setText("Cancelling…")
        self.cancel_requested.emit()

    def keyPressEvent(self, ev):  # block Esc
        ev.ignore()


class RunErrorsDialog(_Overlay):
    """Shown only when at least one group was blocked."""

    def __init__(self, parent, blocked: List[Dict[str, Any]], n_warnings: int):
        super().__init__(parent, 620)
        self.body.setContentsMargins(32, 28, 32, 28)
        head = QWidget()
        h = hbox(head, spacing=12)
        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setStyleSheet(f"border: 2px solid {ERROR}; border-radius: 14px; color: {ERROR}; font-weight: 700; font-size: 16px;")
        icon.setAlignment(Qt.AlignCenter)
        icon.setText("!")
        h.addWidget(icon)
        n = len(blocked)
        h.addWidget(label(f"{n} group{'s' if n != 1 else ''} couldn’t be analyzed", h2=True))
        h.addStretch(1)
        self.body.addWidget(head)
        self.body.addWidget(label("Everything else finished. These groups are skipped until the files are fixed.", muted=True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = vbox(inner, spacing=10)
        for b in blocked:
            card = QFrame()
            card.setStyleSheet(f"QFrame {{ background: {ERROR_BG}; border: 1px solid {ERROR_BORDER}; border-radius: 8px; }} QLabel {{ background: transparent; border: none; }}")
            cl = vbox(card, (14, 12, 14, 12), 4)
            cl.addWidget(label(b["name"], h3=True))
            for r in b["reasons"]:
                cl.addWidget(QLabel(r))
            for d in b["details"]:
                dl = QLabel(d)
                dl.setWordWrap(True)
                dl.setStyleSheet(f"font-family: '{MONO}', monospace; font-size: 12px; color: {TEXT_SOFT};")
                cl.addWidget(dl)
            il.addWidget(card)
        il.addStretch(1)
        scroll.setWidget(inner)
        scroll.setMaximumHeight(360)
        self.body.addWidget(scroll)
        if n_warnings:
            self.body.addWidget(label(f"{n_warnings} warning{'s' if n_warnings != 1 else ''} (not blocking) are listed in diagnostics.csv.", muted13=True))
        row = QWidget()
        rl = hbox(row, spacing=12)
        rl.addStretch(1)
        rl.addWidget(button("Go back", "", self.reject))
        rl.addWidget(button("Continue to results", "primary", self.accept))
        self.body.addWidget(row)


class ReadMeDialog(QDialog):
    def __init__(self, parent, markdown_text: str):
        super().__init__(parent)
        self.setWindowTitle("B-ICE DeTRESer — Read Me")
        self.resize(820, 640)
        lay = vbox(self, (24, 24, 24, 24), 12)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setMarkdown(markdown_text)
        lay.addWidget(tb)
        lay.addWidget(button("Close", "", self.accept), 0, Qt.AlignRight)


def ask_overwrite(parent, folder: str, policy: str) -> bool:
    """Backend refuses a non-empty folder; ask (or always overwrite) according to the Output setting."""
    if not (os.path.isdir(folder) and os.listdir(folder)):
        return True
    if policy == "always":
        return True
    r = QMessageBox.question(parent, "Folder is not empty", f"{folder}\n\nThis folder already contains files. Write the export into it anyway? "
                             "Files with the same names will be replaced.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return r == QMessageBox.Yes


# ------------------------------------------------------------------------------
# advanced settings
# ------------------------------------------------------------------------------
def _num(value, width: int = 110) -> QLineEdit:
    e = QLineEdit("" if value is None else f"{value:g}" if isinstance(value, float) else str(value))
    e.setProperty("mono", True)
    e.setFixedWidth(width)
    return e


def _field(text: str, widget) -> QWidget:
    w = QWidget()
    h = hbox(w, spacing=10)
    lab = QLabel(text)
    h.addWidget(lab)
    h.addStretch(1)
    h.addWidget(widget)
    return w


def _float(e: QLineEdit, default):
    t = e.text().strip()
    if t == "":
        return None
    try:
        return float(t)
    except ValueError:
        return default


def _int(e: QLineEdit, default):
    v = _float(e, default)
    return default if v is None else int(v)


class AdvancedDialog(QDialog):
    """Four tabs mapped to the backend config sections.  ``session.advanced`` is updated on Save."""

    open_fit_review = Signal()

    def __init__(self, parent, session: Session):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Advanced settings")
        self.setModal(True)
        self.resize(900, 640)
        self.values = copy.deepcopy(session.advanced)
        lay = vbox(self, (24, 24, 24, 24), 16)
        head = QWidget()
        h = hbox(head)
        h.addWidget(label("Advanced settings", h2=True))
        h.addStretch(1)
        x = button("×", "tiny", self.reject)
        h.addWidget(x)
        lay.addWidget(head)
        self.tabs = Segmented(["Analysis", "Validation", "Output", "Extras"], self._switch, tabs=True)
        lay.addWidget(self.tabs)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self._build_analysis()
        self._build_validation()
        self._build_output()
        self._build_extras()
        foot = QWidget()
        fl = hbox(foot, spacing=12)
        fl.addWidget(button("Reset tab to defaults", "", self._reset_tab))
        fl.addStretch(1)
        fl.addWidget(button("Cancel", "", self.reject))
        fl.addWidget(button("Save", "primary", lambda: self._save(True)))
        lay.addWidget(foot)
        self._load(self.values)

    def _switch(self, i: int) -> None:
        self.stack.setCurrentIndex(i)

    def _column(self, title: str) -> tuple:
        w = QFrame()
        w.setProperty("subpanel", True)
        l = vbox(w, (16, 14, 16, 14), 10)
        l.addWidget(section_label(title))
        return w, l

    # ---- Analysis --------------------------------------------------------------
    def _build_analysis(self) -> None:
        page = QWidget()
        row = hbox(page, spacing=16)
        c1, l1 = self._column("TDFS")
        self.a_dt = _num(0.01); l1.addWidget(_field("Time step (ns)", self.a_dt))
        self.a_tmin = _num(0.1); l1.addWidget(_field("Metrics start at (ns)", self.a_tmin))
        self.a_tail = _num(5); l1.addWidget(_field("Tail points", self.a_tail))
        self.a_floor = _num(0.01); l1.addWidget(_field("Intensity floor", self.a_floor))
        self.a_fwhm = _num(0.25); l1.addWidget(_field("FWHM smoothing (ns)", self.a_fwhm))
        self.a_clip = QCheckBox("Clip negative C"); l1.addWidget(self.a_clip)
        self.a_com = QCheckBox("Also compute center of mass"); l1.addWidget(self.a_com)
        l1.addStretch(1)
        c2, l2 = self._column("DAS")
        self.a_amp = ComboBox(); self.a_amp.addItems(["Full precision (Results sheet)", "2-decimal (Summary, legacy)"])
        l2.addWidget(QLabel("Amplitude source")); l2.addWidget(self.a_amp)
        self.a_bubble = ComboBox(); self.a_bubble.addItems(["Quadratic peak", "Log-normal fit"])
        l2.addWidget(QLabel("Bubble method")); l2.addWidget(self.a_bubble)
        self.a_blue = _num(440); l2.addWidget(_field("GP blue (nm)", self.a_blue))
        self.a_red = _num(490); l2.addWidget(_field("GP red (nm)", self.a_red))
        l2.addStretch(1)
        c3, l3 = self._column("Anisotropy")
        self.a_phi = ComboBox(); self.a_phi.addItems(["Amplitude-weighted mean", "Longest", "Shortest", "Specific component…"])
        l3.addWidget(QLabel("φ used for viscosity")); l3.addWidget(self.a_phi)
        self.a_phi_k = _num(1, 70)
        self.a_phi_k_row = _field("Component number", self.a_phi_k)
        l3.addWidget(self.a_phi_k_row)
        self.a_phi.currentIndexChanged.connect(lambda i: self.a_phi_k_row.setVisible(i == 3))
        self.a_r0 = _num(0.39); l3.addWidget(_field("Literature r₀", self.a_r0))
        l3.addStretch(1)
        for c in (c1, c2, c3):
            row.addWidget(c, 1)
        self.stack.addWidget(page)

    # ---- Validation -----------------------------------------------------------
    def _build_validation(self) -> None:
        page = QWidget()
        row = hbox(page, spacing=16)
        c1, l1 = self._column("Warnings (never block)")
        self.v_chi = _num(1.5); l1.addWidget(_field("Warn if χ² is above", self.v_chi))
        self.v_reduced = QCheckBox("EzTime χ² is a reduced χ²"); l1.addWidget(self.v_reduced)
        self.v_var = _num(20); l1.addWidget(_field("Warn if replicates vary by more than (%)", self.v_var))
        l1.addWidget(QLabel("Check variation of:"))
        self.v_metrics = {}
        grid = QGridLayout(); grid.setHorizontalSpacing(16)
        for i, (t, k) in enumerate([("GP", "gp"), ("Mean lifetime ⟨τ⟩", "tmean_ns"), ("Δν, peak", "peak_delta_nu_cm-1"), ("τr, peak", "peak_tau_r_ns")]):
            cb = QCheckBox(t); self.v_metrics[k] = cb; grid.addWidget(cb, i // 2, i % 2)
        l1.addLayout(grid)
        self.v_phi = _num(20); l1.addWidget(_field("Warn if anisotropy φ spread exceeds (%)", self.v_phi))
        n = QLabel("Leave a box empty to report the values without warning."); n.setProperty("muted13", True); n.setWordWrap(True); l1.addWidget(n)
        l1.addStretch(1)
        c2, l2 = self._column("Errors (block the group)")
        self.v_wtol = _num(1e-6); l2.addWidget(_field("Wavelength match tolerance (nm)", self.v_wtol))
        self.v_minpts = _num(3); l2.addWidget(_field("Minimum wavelength points", self.v_minpts))
        self.v_nonuni = QCheckBox("Allow uneven wavelength spacing"); l2.addWidget(self.v_nonuni)
        n2 = QLabel("Mismatched component counts, wavelength ranges or spacing, and mixed TRES / anisotropy files always block the group.")
        n2.setProperty("muted13", True); n2.setWordWrap(True); l2.addWidget(n2)
        l2.addStretch(1)
        row.addWidget(c1, 1); row.addWidget(c2, 1)
        self.stack.addWidget(page)

    # ---- Output ---------------------------------------------------------------
    def _build_output(self) -> None:
        page = QWidget()
        row = hbox(page, spacing=16)
        c1, l1 = self._column("Images")
        fr = QWidget(); fl = hbox(fr, spacing=24)
        self.o_png = QCheckBox("PNG"); self.o_svg = QCheckBox("SVG"); fl.addWidget(self.o_png); fl.addWidget(self.o_svg); fl.addStretch(1)
        l1.addWidget(fr)
        self.o_dpi = _num(300); l1.addWidget(_field("Resolution (DPI)", self.o_dpi))
        l1.addWidget(label("When the export folder isn’t empty", bold=True))
        self.o_ask = QRadioButton("Ask me each time"); self.o_always = QRadioButton("Always overwrite")
        l1.addWidget(self.o_ask); l1.addWidget(self.o_always)
        l1.addStretch(1)
        c2, l2 = self._column("Files in Export full data")
        self.o_legacy = QCheckBox("Legacy-style tables (old tres1 / tdfs layouts)"); l2.addWidget(self.o_legacy)
        self.o_recon = QCheckBox("Reconstructed TRES / TRANES spectra"); l2.addWidget(self.o_recon)
        self.o_traj = QCheckBox("TDFS trajectories"); l2.addWidget(self.o_traj)
        n = QLabel("Summary tables, per-metric tables, diagnostics and the run settings are always included so every export can be reproduced.")
        n.setProperty("muted13", True); n.setWordWrap(True); l2.addWidget(n)
        l2.addStretch(1)
        row.addWidget(c1, 1); row.addWidget(c2, 1)
        self.stack.addWidget(page)

    # ---- Extras ---------------------------------------------------------------
    def _build_extras(self) -> None:
        page = QWidget()
        col = vbox(page, spacing=16)
        c1, l1 = self._column("Time-gated spectra")
        self.e_tg = QCheckBox("Time-gated spectra"); l1.addWidget(self.e_tg)
        n = QLabel("Spectra averaged over time windows, taken from the raw Data sheet."); n.setProperty("muted13", True); l1.addWidget(n)
        gr = QWidget(); self.gates_lay = hbox(gr, spacing=8)
        self.gates_lay.addWidget(QLabel("Gates (ns):"))
        self.gate_widgets = []
        self.gates_lay.addStretch(1)
        self.gates_lay.addWidget(button("+ Add gate", "small", self._add_gate))
        self.e_mode = ComboBox(); self.e_mode.addItems(["Integral", "Mean"]); self.e_mode.setFixedWidth(120)
        self.gates_lay.addWidget(QLabel("Mode")); self.gates_lay.addWidget(self.e_mode)
        l1.addWidget(gr)
        c2, l2 = self._column("Parallel loading")
        n2 = QLabel("Reads and analyses workbooks at the same time. Faster; results are identical."); n2.setProperty("muted13", True); l2.addWidget(n2)
        self.e_workers = _num(4, 70); l2.addWidget(_field("Workers", self.e_workers))
        c3, l3 = self._column("Log-normal deconvolution")
        n3 = QLabel("Split each DAS component into 1–3 log-normal peaks and review every fit. Accepted fits are saved so the run can be repeated exactly.")
        n3.setProperty("muted13", True); n3.setWordWrap(True); l3.addWidget(n3)
        self.e_review = button("Open fit review…", "outline", self._fit_review)
        l3.addWidget(self.e_review, 0, Qt.AlignLeft)
        col.addWidget(c1); col.addWidget(c2); col.addWidget(c3); col.addStretch(1)
        self.stack.addWidget(page)

    def _add_gate(self, lo=None, hi=None) -> None:
        w = QWidget()
        h = hbox(w, spacing=4)
        a = _num(0.0 if lo is None else lo, 60); b = _num(0.5 if hi is None else hi, 60)
        h.addWidget(a); h.addWidget(QLabel("–")); h.addWidget(b)
        x = button("×", "tiny")
        h.addWidget(x)
        self.gate_widgets.append((w, a, b))
        x.clicked.connect(lambda: self._remove_gate(w))
        self.gates_lay.insertWidget(1 + len(self.gate_widgets) - 1, w)

    def _remove_gate(self, w) -> None:
        self.gate_widgets = [g for g in self.gate_widgets if g[0] is not w]
        w.setParent(None); w.deleteLater()

    def _fit_review(self) -> None:
        self._save(close=True)
        self.open_fit_review.emit()

    # ---- load / save --------------------------------------------------------------
    def _load(self, v: Dict[str, Any], only_tab: Optional[int] = None) -> None:
        if only_tab in (None, 0):
            t = v["tdfs"]; d = v["das"]; w = v["wobble"]
            self.a_dt.setText(f"{t['recon_dt_ns']:g}"); self.a_tmin.setText(f"{t['metric_tmin_ns']:g}"); self.a_tail.setText(str(int(t['tail_points'])))
            self.a_floor.setText(f"{t['intensity_floor']:g}"); self.a_fwhm.setText(f"{t['fwhm_smooth_window_ns']:g}")
            self.a_clip.setChecked(bool(t["clip_negative_c"])); self.a_com.setChecked(bool(t["compute_com"]))
            self.a_amp.setCurrentIndex(0 if d["amplitude_source"] == "results" else 1)
            self.a_bubble.setCurrentIndex(0 if d["bubble_method"] == "quadratic_peak" else 1)
            self.a_blue.setText(f"{d['gp_blue_nm']:g}"); self.a_red.setText(f"{d['gp_red_nm']:g}")
            sel = w["phi_selection"]
            idx = {"mean": 0, "longest": 1, "shortest": 2}.get(sel, 3)
            self.a_phi.setCurrentIndex(idx); self.a_phi_k_row.setVisible(idx == 3)
            if sel.startswith("component:"):
                self.a_phi_k.setText(sel.split(":")[1])
            self.a_r0.setText(f"{w['r0_literature']:g}")
        if only_tab in (None, 1):
            va = v["validation"]
            self.v_chi.setText("" if va["chi_sq_warning_threshold"] is None else f"{va['chi_sq_warning_threshold']:g}")
            self.v_reduced.setChecked(bool(va["chi_sq_is_reduced"]))
            self.v_var.setText("" if va["replicate_variation_warning_percent"] is None else f"{va['replicate_variation_warning_percent']:g}")
            for k, cb in self.v_metrics.items():
                cb.setChecked(k in (va.get("replicate_variation_metrics") or []))
            self.v_phi.setText("" if va["anisotropy_correlation_time_tolerance_percent"] is None else f"{va['anisotropy_correlation_time_tolerance_percent']:g}")
            self.v_wtol.setText(f"{va['wavelength_tolerance_nm']:g}"); self.v_minpts.setText(str(int(va["min_wavelength_points"])))
            self.v_nonuni.setChecked(bool(va["allow_nonuniform_grid"]))
        if only_tab in (None, 2):
            o = v["output"]
            self.o_png.setChecked(bool(o["png"])); self.o_svg.setChecked(bool(o["svg"])); self.o_dpi.setText(str(int(o["dpi"])))
            (self.o_always if o["overwrite_policy"] == "always" else self.o_ask).setChecked(True)
            self.o_legacy.setChecked(bool(o["legacy_compatible"])); self.o_recon.setChecked(bool(o["write_reconstructed_spectra"])); self.o_traj.setChecked(bool(o["write_trajectories"]))
        if only_tab in (None, 3):
            tg = v["time_gated"]
            self.e_tg.setChecked(bool(tg["enabled"]))
            for w, _, _ in list(self.gate_widgets):
                self._remove_gate(w)
            for lo, hi in tg["gates_ns"]:
                self._add_gate(lo, hi)
            self.e_mode.setCurrentIndex(0 if tg["gate_mode"] == "integral" else 1)
            self.e_workers.setText(str(int(v["project"]["workers"])))

    def _collect(self) -> Dict[str, Any]:
        v = copy.deepcopy(self.values)
        v["tdfs"].update({"recon_dt_ns": _float(self.a_dt, 0.01) or 0.01, "metric_tmin_ns": _float(self.a_tmin, 0.1) or 0.1, "tail_points": _int(self.a_tail, 5),
                          "intensity_floor": _float(self.a_floor, 0.01) or 0.01, "fwhm_smooth_window_ns": _float(self.a_fwhm, 0.25) or 0.25,
                          "clip_negative_c": self.a_clip.isChecked(), "compute_com": self.a_com.isChecked()})
        phi = ["mean", "longest", "shortest"][self.a_phi.currentIndex()] if self.a_phi.currentIndex() < 3 else f"component:{_int(self.a_phi_k, 1)}"
        v["das"].update({"amplitude_source": "results" if self.a_amp.currentIndex() == 0 else "summary",
                         "bubble_method": "quadratic_peak" if self.a_bubble.currentIndex() == 0 else "lognormal_fit",
                         "gp_blue_nm": _float(self.a_blue, 440.0) or 440.0, "gp_red_nm": _float(self.a_red, 490.0) or 490.0})
        v["wobble"].update({"phi_selection": phi, "r0_literature": _float(self.a_r0, 0.39) or 0.39})
        v["validation"].update({"chi_sq_warning_threshold": _float(self.v_chi, None), "chi_sq_is_reduced": self.v_reduced.isChecked(),
                                "replicate_variation_warning_percent": _float(self.v_var, None),
                                "replicate_variation_metrics": [k for k, cb in self.v_metrics.items() if cb.isChecked()],
                                "anisotropy_correlation_time_tolerance_percent": _float(self.v_phi, None),
                                "wavelength_tolerance_nm": _float(self.v_wtol, 1e-6) or 1e-6, "min_wavelength_points": _int(self.v_minpts, 3),
                                "allow_nonuniform_grid": self.v_nonuni.isChecked()})
        v["output"].update({"png": self.o_png.isChecked(), "svg": self.o_svg.isChecked(), "dpi": _int(self.o_dpi, 300),
                            "overwrite_policy": "always" if self.o_always.isChecked() else "ask", "legacy_compatible": self.o_legacy.isChecked(),
                            "write_reconstructed_spectra": self.o_recon.isChecked(), "write_trajectories": self.o_traj.isChecked()})
        gates = []
        for _, a, b in self.gate_widgets:
            lo, hi = _float(a, None), _float(b, None)
            if lo is not None and hi is not None and hi > lo:
                gates.append([lo, hi])
        v["time_gated"].update({"enabled": self.e_tg.isChecked(), "gates_ns": gates or [[0.0, 0.5], [0.5, 2.0], [2.0, 7.0]],
                                "gate_mode": "integral" if self.e_mode.currentIndex() == 0 else "mean"})
        v["project"]["workers"] = max(1, _int(self.e_workers, 4))
        return v

    def _reset_tab(self) -> None:
        d = default_advanced()
        tab = self.tabs.current()
        cur = self._collect()
        keys = {0: ["tdfs", "das", "wobble"], 1: ["validation"], 2: ["output"], 3: ["time_gated", "project"]}[tab]
        for k in keys:
            cur[k] = d[k]
        self.values = cur
        self._load(cur, only_tab=tab)

    def _save(self, close: bool = True) -> None:
        self.session.advanced = self._collect()
        if close:
            self.accept()
