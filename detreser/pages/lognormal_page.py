"""Page 11 · Log-normal fit review — the GUI version of ``python -m tres_suite deconvolve``.

Per analysed TRES group and per DAS component: choose 1–3 peaks, edit the low/high bounds (nm),
refit, then Accept or Skip.  "Accept all remaining as-is" is the CLI's no-prompt mode.  Decisions
are written to ``deconvolution_decisions.json`` (and the per-group exports) exactly as the CLI does,
by calling the backend's ``deconvolve_group`` with the recorded decisions.
"""
from __future__ import annotations

import copy
import os
import shutil
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QWidget)

from tres_suite.export import safe_name

from ..model import Session
from ..theme import ComboBox, ACCENT, OK_GREEN, Header, button, hbox, label, panel, vbox
from ..widgets.plot_canvas import PlotCanvas


class LogNormalPage(QWidget):
    back_requested = Signal()

    def __init__(self, session: Session, on_readme):
        super().__init__()
        self.session = session
        self.groups: List[Any] = []  # GroupResult list (analysed TRES groups)
        self.spectra: Dict[str, Dict[str, Any]] = {}
        self.decisions: Dict[str, Dict[str, Dict[str, Any]]] = {}  # group folder -> component -> decision
        self.gi = 0
        self.ci = 0
        lay = vbox(self)
        self.header = Header("Log-normal fit review", on_readme)
        lay.addWidget(self.header)
        body = QWidget()
        bl = vbox(body, (24, 24, 24, 24), 16)
        # top bar
        top = QWidget()
        tl = hbox(top, spacing=16)
        tl.addWidget(button("← Back", "small", self.back_requested.emit))
        tl.addWidget(label("Group", bold=True))
        self.group_combo = ComboBox()
        self.group_combo.setFixedWidth(260)
        self.group_combo.currentIndexChanged.connect(self._group_changed)
        tl.addWidget(self.group_combo)
        self.counter = QLabel("")
        self.counter.setProperty("muted", True)
        tl.addWidget(self.counter)
        tl.addStretch(1)
        self.comp_box = QWidget()
        self.comp_lay = hbox(self.comp_box, spacing=8)
        tl.addWidget(self.comp_box)
        bl.addWidget(top)
        # middle
        mid = QWidget()
        ml = hbox(mid, spacing=20)
        card = panel()
        cl = vbox(card, (24, 24, 24, 24), 8)
        head = QWidget()
        hl = hbox(head)
        self.fit_title = label("", h3=True)
        hl.addWidget(self.fit_title)
        hl.addStretch(1)
        self.fit_stats = QLabel("")
        self.fit_stats.setProperty("mono", True)
        hl.addWidget(self.fit_stats)
        cl.addWidget(head)
        self.canvas = PlotCanvas()
        cl.addWidget(self.canvas, 1)
        ml.addWidget(card, 1)
        side = panel()
        side.setFixedWidth(320)
        sl = vbox(side, (20, 20, 20, 20), 12)
        row = QWidget()
        rh = hbox(row, spacing=10)
        rh.addWidget(label("Number of peaks", bold=True))
        self.n_peaks = ComboBox()
        self.n_peaks.addItems(["1", "2", "3"])
        self.n_peaks.setFixedWidth(70)
        self.n_peaks.currentIndexChanged.connect(self._peaks_changed)
        rh.addWidget(self.n_peaks)
        rh.addStretch(1)
        sl.addWidget(row)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)
        for c, t in enumerate(("Peak", "Low (nm)", "High (nm)", "Fitted")):
            l = QLabel(t)
            l.setProperty("muted13", True)
            self.grid.addWidget(l, 0, c)
        self.bound_edits: List[tuple] = []
        gw = QWidget()
        gw.setLayout(self.grid)
        sl.addWidget(gw)
        sl.addWidget(button("Refit with these bounds", "", self._refit))
        sl.addStretch(1)
        q = QLabel("Is this fit satisfactory? Accepted fits (peak count, bounds, results) are saved so the run can be repeated exactly.")
        q.setWordWrap(True)
        q.setProperty("muted13", True)
        sl.addWidget(q)
        br = QWidget()
        bh = hbox(br, spacing=10)
        bh.addWidget(button("Skip component", "", self._skip))
        bh.addWidget(button("Accept →", "primary", self._accept))
        sl.addWidget(br)
        ml.addWidget(side)
        bl.addWidget(mid, 1)
        foot = QWidget()
        fl = hbox(foot, spacing=12)
        fl.addWidget(button("Accept all remaining as-is", "", self._accept_all))
        fl.addStretch(1)
        fl.addWidget(button("Export fits…", "outline", self._export))
        bl.addWidget(foot)
        lay.addWidget(body, 1)
        self.comp_buttons: List[QPushButton] = []

    # ---- setup -----------------------------------------------------------------------
    def start(self) -> bool:
        from tres_suite.advanced.deconvolution import group_spectra_from_result
        res = self.session.result
        self.groups = [g for g in (res.ok_groups("tres") if res else []) if g.das_spectra is not None]
        if not self.groups:
            QMessageBox.information(self, "No DAS spectra", "Run a TRES analysis first; the fit review works on the analysed groups of the current run.")
            return False
        self.spectra = {}
        self.decisions = self.session.deconvolution or {}
        for g in self.groups:
            self.spectra[self._folder(g)] = group_spectra_from_result(g)
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        for g in self.groups:
            self.group_combo.addItem(" › ".join(g.group.key))
        self.group_combo.blockSignals(False)
        self.gi, self.ci = 0, 0
        self.group_combo.setCurrentIndex(0)
        self._group_changed(0)
        return True

    @staticmethod
    def _folder(g) -> str:
        return safe_name(g.group.name)

    def _decision(self, gi: int, ci: int, create: bool = True) -> Optional[Dict[str, Any]]:
        from tres_suite.lognormal import _default_bounds
        g = self.groups[gi]
        f = self._folder(g)
        comps = self.decisions.setdefault(f, {})
        key = str(ci + 1)
        if key not in comps:
            if not create:
                return None
            comps[key] = {"lifetime_ns": float(self.spectra[f]["lifetimes_ns"][ci]), "n_peaks": 2, "bounds_nm": list(_default_bounds(2, ci)),
                          "accepted": False, "decided": False, "fit": {}}
        return comps[key]

    # ---- navigation ------------------------------------------------------------------
    def _group_changed(self, i: int) -> None:
        if i < 0 or not self.groups:
            return
        self.gi = i
        self.counter.setText(f"Group {i + 1} of {len(self.groups)}")
        # component buttons
        for b in self.comp_buttons:
            b.setParent(None)
            b.deleteLater()
        self.comp_buttons = []
        while self.comp_lay.count():
            self.comp_lay.takeAt(0)
        n = self.spectra[self._folder(self.groups[i])]["n_components"]
        for c in range(n):
            b = QPushButton("")
            b.setProperty("segment", True)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QPushButton { border: 1px solid #b9c2cf; border-radius: 8px; } QPushButton:checked { background: #0e1e3a; color: white; }")
            b.clicked.connect(lambda _=False, c=c: self._show_component(c))
            self.comp_lay.addWidget(b)
            self.comp_buttons.append(b)
        self._show_component(0)

    def _refresh_comp_buttons(self) -> None:
        f = self._folder(self.groups[self.gi])
        taus = self.spectra[f]["lifetimes_ns"]
        for c, b in enumerate(self.comp_buttons):
            d = self._decision(self.gi, c, create=False)
            mark = ""
            if d and d.get("decided"):
                mark = " ✓" if d.get("accepted") else " –"
            b.setText(f"τ{c + 1} = {taus[c]:.2f} ns{mark}")
            b.setChecked(c == self.ci)

    def _show_component(self, c: int) -> None:
        self.ci = c
        d = self._decision(self.gi, c)
        self.n_peaks.blockSignals(True)
        self.n_peaks.setCurrentIndex(d["n_peaks"] - 1)
        self.n_peaks.blockSignals(False)
        self._build_bounds(d)
        if not d.get("fit"):
            self._fit(d)
        self._draw(d)
        self._refresh_comp_buttons()

    def _build_bounds(self, d: Dict[str, Any]) -> None:
        for widgets in self.bound_edits:
            for w in widgets:
                w.setParent(None)
                w.deleteLater()
        self.bound_edits = []
        for k in range(d["n_peaks"]):
            num = QLabel(str(k + 1))
            lo = QLineEdit(f"{d['bounds_nm'][2 * k]:g}")
            hi = QLineEdit(f"{d['bounds_nm'][2 * k + 1]:g}")
            for e in (lo, hi):
                e.setProperty("mono", True)
                e.setFixedWidth(72)
            fitted = QLabel("")
            fitted.setProperty("muted13", True)
            self.grid.addWidget(num, k + 1, 0)
            self.grid.addWidget(lo, k + 1, 1)
            self.grid.addWidget(hi, k + 1, 2)
            self.grid.addWidget(fitted, k + 1, 3)
            self.bound_edits.append((num, lo, hi, fitted))

    def _peaks_changed(self, i: int) -> None:
        from tres_suite.lognormal import _default_bounds
        d = self._decision(self.gi, self.ci)
        n = i + 1
        if n != d["n_peaks"]:
            d["n_peaks"] = n
            d["bounds_nm"] = list(_default_bounds(n, self.ci))
            d["fit"] = {}
            d["decided"] = False
            d["accepted"] = False
            self._build_bounds(d)
            self._fit(d)
            self._draw(d)
            self._refresh_comp_buttons()

    def _read_bounds(self, d: Dict[str, Any]) -> bool:
        bounds = []
        for _, lo, hi, _ in self.bound_edits:
            try:
                a, b = float(lo.text()), float(hi.text())
            except ValueError:
                QMessageBox.warning(self, "Bounds", "Bounds must be numbers (nm).")
                return False
            if b <= a:
                QMessageBox.warning(self, "Bounds", "Each high bound must be above its low bound.")
                return False
            bounds += [a, b]
        d["bounds_nm"] = bounds
        return True

    def _fit(self, d: Dict[str, Any]) -> None:
        from tres_suite.lognormal import fit_component
        f = self._folder(self.groups[self.gi])
        sp = self.spectra[f]
        d["fit"] = fit_component(sp["wavelengths_nm"], sp["emission"][:, self.ci], d["n_peaks"], d["bounds_nm"])

    def _refit(self) -> None:
        d = self._decision(self.gi, self.ci)
        if not self._read_bounds(d):
            return
        d["decided"] = False
        d["accepted"] = False
        self._fit(d)
        self._draw(d)
        self._refresh_comp_buttons()

    def _draw(self, d: Dict[str, Any]) -> None:
        from tres_suite.lognormal import lognormal, multimodal
        g = self.groups[self.gi]
        f = self._folder(g)
        sp = self.spectra[f]
        wl, y = sp["wavelengths_nm"], sp["emission"][:, self.ci]
        fit = d.get("fit") or {}
        self.fit_title.setText(f"DAS component τ{self.ci + 1} — {' › '.join(g.group.key)}")
        fig = self.canvas.fig
        fig.clear()
        ax = fig.add_subplot(111)
        ax.plot(wl, y, "o", ms=3.5, color="#16202e", label="Data")
        colors = ["#c8372d", OK_GREEN, "#e0781c"]
        if fit.get("ok"):
            x = np.linspace(wl.min(), wl.max(), 500)
            ax.plot(x, multimodal(x, *fit["params"]), color=ACCENT, lw=2, label="Total fit")
            for k, pk in enumerate(fit["peaks"]):
                p = fit["params"][3 * k:3 * k + 3]
                ax.plot(x, lognormal(x, *p), "--", color=colors[k % 3], lw=1.5, label=f"Peak {k + 1}")
            self.fit_stats.setText(f"R² = {fit['r_squared']:.4f} · χ² = {fit['legacy_chi_squared']:.3g}")
            for k, (_, _, _, lab) in enumerate(self.bound_edits):
                pk = fit["peaks"][k]
                lab.setText(f"{pk['center_nm']:.1f} nm\narea {pk['area']:.3g}")
        else:
            self.fit_stats.setText(f"fit failed: {fit.get('reason', '?')}")
            for _, _, _, lab in self.bound_edits:
                lab.setText("—")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Amplitude")
        ax.tick_params(direction="in", which="both")
        ax.legend(frameon=False, fontsize=9)
        try:
            fig.tight_layout()
        except Exception:
            pass
        self.canvas.canvas.draw_idle()

    # ---- decisions -------------------------------------------------------------------
    def _accept(self) -> None:
        d = self._decision(self.gi, self.ci)
        if not self._read_bounds(d):
            return
        if not d.get("fit"):
            self._fit(d)
        d["decided"] = True
        d["accepted"] = bool(d["fit"].get("ok"))
        if not d["accepted"]:
            QMessageBox.information(self, "Fit failed", "This fit did not converge, so it is recorded as skipped. Change the bounds or peak count and refit to accept it.")
        self._next()

    def _skip(self) -> None:
        d = self._decision(self.gi, self.ci)
        d["decided"] = True
        d["accepted"] = False
        self._next()

    def _next(self) -> None:
        self.session.deconvolution = self.decisions
        n = self.spectra[self._folder(self.groups[self.gi])]["n_components"]
        if self.ci + 1 < n:
            self._show_component(self.ci + 1)
        elif self.gi + 1 < len(self.groups):
            self.group_combo.setCurrentIndex(self.gi + 1)
        else:
            self._refresh_comp_buttons()
            if self._all_decided():
                QMessageBox.information(self, "Review complete", "Every component has been reviewed. Use “Export fits…” to save the decisions and the fitted data.")

    def _all_decided(self) -> bool:
        for gi, g in enumerate(self.groups):
            n = self.spectra[self._folder(g)]["n_components"]
            for c in range(n):
                d = self._decision(gi, c, create=False)
                if d is None or not d.get("decided"):
                    return False
        return True

    def _accept_all(self) -> None:
        for gi, g in enumerate(self.groups):
            n = self.spectra[self._folder(g)]["n_components"]
            for c in range(n):
                d = self._decision(gi, c)
                if d.get("decided"):
                    continue
                if not d.get("fit"):
                    old = self.ci, self.gi
                    self.gi, self.ci = gi, c
                    self._fit(d)
                    self.ci, self.gi = old
                d["decided"] = True
                d["accepted"] = bool(d["fit"].get("ok"))
        self.session.deconvolution = self.decisions
        self._refresh_comp_buttons()
        QMessageBox.information(self, "Accepted", "All remaining components were accepted with their current fits. Use “Export fits…” to save them.")

    # ---- export ----------------------------------------------------------------------
    def _export(self) -> None:
        from tres_suite.advanced.deconvolution import deconvolve_group, write_decisions
        from ..widgets.dialogs import ask_overwrite
        run_dir = self.session.run_dir
        if not run_dir or not os.path.isdir(os.path.join(run_dir, "groups")):
            QMessageBox.warning(self, "No run output", "The session output of this run is missing; run the analysis again.")
            return
        undecided = not self._all_decided()
        if undecided:
            r = QMessageBox.question(self, "Components not reviewed", "Some components have not been accepted or skipped yet. Export only the accepted fits?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r != QMessageBox.Yes:
                return
        folder = QFileDialog.getExistingDirectory(self, "Export fits to folder", os.path.expanduser("~"))
        if not folder:
            return
        if not ask_overwrite(self, folder, self.session.advanced["output"]["overwrite_policy"]):
            return
        # replay the decisions through the backend so exports are identical to the CLI's
        decisions_out: Dict[str, Any] = {"groups": {}}
        try:
            for g in self.groups:
                f = self._folder(g)
                comps = self.decisions.get(f, {})
                recorded = {k: {"n_peaks": v["n_peaks"], "bounds_nm": v["bounds_nm"], "accepted": bool(v.get("decided") and v.get("accepted"))}
                            for k, v in comps.items()}
                n = self.spectra[f]["n_components"]
                for c in range(n):  # components never opened: default fit, not accepted
                    recorded.setdefault(str(c + 1), {"n_peaks": 2, "bounds_nm": self._decision(self.groups.index(g), c)["bounds_nm"], "accepted": False})
                res = deconvolve_group(run_dir, f, recorded, prompt=None, show=lambda p: None)
                decisions_out["groups"][f] = res["components"]
            path = write_decisions(run_dir, decisions_out)
            # copy to the chosen folder
            src = os.path.join(run_dir, "deconvolution")
            dst = os.path.join(folder, "deconvolution")
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"{exc.__class__.__name__}: {exc}")
            return
        QMessageBox.information(self, "Exported", f"Fits, bubble data and deconvolution_decisions.json were written to\n{dst}")
