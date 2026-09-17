"""Offscreen end-to-end drive of the GUI: loads folders, runs, visits every page, saves screenshots.

    QT_QPA_PLATFORM=offscreen python tests_gui/drive_gui.py <data root with laurdan/ and tma/ (Error/ beside it)> <screenshot dir>
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tres_suite"))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication

import detreser.app as appmod
from detreser.pages.results_page import CompareSpec, SeriesStyle, default_style

DATA = os.path.abspath(sys.argv[1])
SHOTS = os.path.abspath(sys.argv[2])
os.makedirs(SHOTS, exist_ok=True)


def pump(ms=200):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def shot(win, name):
    pump(150)
    win.grab().save(os.path.join(SHOTS, name + ".png"))
    print("shot", name, flush=True)


def wait_for(cond, timeout=600):
    t0 = time.time()
    while not cond():
        pump(100)
        if time.time() - t0 > timeout:
            raise TimeoutError("timed out")


app = QApplication([])
appmod.load_fonts()
app.setStyleSheet(appmod.app_stylesheet())
win = appmod.MainWindow()
win.resize(1280, 760)
win.show()
shot(win, "01_main")

# ---- TRES run ---------------------------------------------------------------------
win.main_page.add_paths([os.path.join(DATA, "laurdan")])
wait_for(lambda: win.session.kind_detail and "Detect" in win.session.kind_detail and "…" not in win.session.kind_detail, 60)
for e, t in zip(win.options_page.level_edits, ["Probe", "Composition", "Temperature"]):
    e.setText(t)
    e.editingFinished.emit()
win.options_page.probe.setText("Laurdan")
shot(win, "02_options_tres")
win.options_page._run()
pump(500)
shot(win, "03_run_loading")
wait_for(lambda: win.session.result is not None, 900)
pump(300)
res = win.session.result
print("status", res.status, "groups", len(res.groups), "kind", win.session.kind)
assert win.stack.currentIndex() == appmod.PAGE_TRES, win.stack.currentIndex()
shot(win, "04_results_single")
# single sample: drop the first group-level folder
root = win.session.roots[0]
node = root.folders_at(win.session.group_level())[0]
for cb in win.tres_page.single_checks.values():
    cb.setChecked(True)
win.tres_page.single_zone.set_nodes([node])
pump(300)
assert win.stack.currentIndex() == appmod.PAGE_GRAPH
for i in range(win.graph_page.switcher.count()):
    win.graph_page.switcher.set_current(i, emit=True)
    pump(200)
    assert win.graph_page.canvas.error is None, (i, win.graph_page.canvas.error)
    if i in (0, 2, 8):
        shot(win, f"05_graph_view_{i}")
win.graph_page.view_toggle.set_current(0, emit=True)
shot(win, "05_graph_view_table")
win.graph_page.axes.x_min.setText("430"); win.graph_page.axes.x_max.setText("520"); win.graph_page.axes.fig_w.setText("5"); win.graph_page.axes.fig_h.setText("4"); win.graph_page.axes.changed.emit()
win.graph_page.view_toggle.set_current(1, emit=True)
shot(win, "05_graph_view_limits")
win.graph_page.back_requested.emit()
# comparison X group / Y value
win.tres_page.mode.set_current(1, emit=True)
lvl2 = [n for r in win.session.roots for n in r.folders_at(2)]
win.tres_page.x_group.zone.set_nodes(lvl2)
shot(win, "06_compare_x")
win.tres_page.axis_tabs.set_current(1, emit=True)
win.tres_page.y_value.set_metric("gp")
win.tres_page.y_value.fit.setChecked(True)
shot(win, "07_compare_y")
win.tres_page._plot()
pump(300)
assert win.stack.currentIndex() == appmod.PAGE_COMPARE
assert win.compare_page.canvas.error is None, win.compare_page.canvas.error
shot(win, "08_compare_graph")
# value vs value
win.compare_page.back_requested.emit()
win.tres_page.axis_modes.groups["x"].buttons()[0].setChecked(True)
win.tres_page.axis_modes.changed.emit()
win.tres_page.axis_tabs.set_current(0, emit=True)
win.tres_page.x_value.set_metric("tmean_ns")
win.tres_page.vv_zone.nodes = lvl2
win.tres_page.vv_zone._refresh_chips()
shot(win, "06b_compare_value_value")
win.tres_page._plot()
pump(300)
assert win.compare_page.canvas.error is None, win.compare_page.canvas.error
shot(win, "08b_compare_graph_gp_vs_tmean")
# group on Y
win.compare_page.back_requested.emit()
win.tres_page.axis_modes.groups["y"].buttons()[1].setChecked(True)
win.tres_page.axis_modes.changed.emit()
win.tres_page.axis_tabs.set_current(1, emit=True)
win.tres_page.y_group.zone.set_nodes(lvl2)
win.tres_page._plot()
pump(300)
assert win.compare_page.canvas.error is None, win.compare_page.canvas.error
shot(win, "08c_compare_graph_group_on_y")
# advanced dialog
from detreser.widgets.dialogs import AdvancedDialog
dlg = AdvancedDialog(win, win.session)
dlg.show(); pump(200)
for i, name in enumerate(["analysis", "validation", "output", "extras"]):
    dlg.tabs.set_current(i, emit=True); pump(100)
    dlg.grab().save(os.path.join(SHOTS, f"09_adv_{name}.png"))
dlg._save()
# log-normal review
assert win.lognormal_page.start()
win.goto(appmod.PAGE_LOGNORMAL)
shot(win, "10_lognormal")
from detreser.pages import lognormal_page as lp
import tempfile
out = tempfile.mkdtemp(prefix="detreser-export-")
lp.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: out)
lp.QMessageBox.information = staticmethod(lambda *a, **k: None)
lp.QMessageBox.question = staticmethod(lambda *a, **k: lp.QMessageBox.Yes)
win.lognormal_page._accept()
win.lognormal_page.n_peaks.setCurrentIndex(2)
pump(200)
shot(win, "10_lognormal_3peaks")
win.lognormal_page._accept_all()
# export via backend replay into a temp folder
win.lognormal_page._export()
print("deconvolution export:", sorted(os.listdir(os.path.join(out, "deconvolution")))[:6])
assert os.path.exists(os.path.join(out, "deconvolution", "deconvolution_decisions.json"))
# export full data
out2 = tempfile.mkdtemp(prefix="detreser-full-")
appmod.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: out2)
appmod.QMessageBox.information = staticmethod(lambda *a, **k: None)
win.export_full()
print("full export:", sorted(os.listdir(out2)))
assert os.path.exists(os.path.join(out2, "tres_summary.csv"))
print("plots exported:", sorted(os.listdir(os.path.join(out2, "plots")))[:10])
# run-errors popup rendering (synthetic)
from detreser.widgets.dialogs import RunErrorsDialog
d = RunErrorsDialog(win, [{"name": "DPPC › 35", "reasons": ["Replicates have different numbers of components"], "details": ["2fit.xlsx = 2 · 5fit.xlsx = 5"]},
                          {"name": "DOPC › 45", "reasons": ["Wavelength ranges don’t match"], "details": ["sample_1.xlsx 435–525 nm · sample_2.xlsx 420–540 nm"]}], 3)
d.show(); pump(200); d.grab().save(os.path.join(SHOTS, "11_run_errors.png")); d.reject()
# readme
win.show_readme = lambda: None

# ---- anisotropy run ----------------------------------------------------------------
win.goto(appmod.PAGE_OPTIONS)
win.options_page.tree.remove_root(win.session.roots[0])
win.main_page.add_paths([os.path.join(DATA, "tma")])
wait_for(lambda: win.session.kind == "anisotropy", 60)
for e, t in zip(win.options_page.level_edits, ["Probe", "Composition", "Temperature"]):
    e.setText(t); e.editingFinished.emit()
win.options_page.temp_level.setCurrentIndex(2)
shot(win, "12_options_aniso")
win.options_page._run()
wait_for(lambda: win.session.result is not None, 300)
pump(300)
print("aniso status", win.session.result.status, "page", win.stack.currentIndex())
assert win.stack.currentIndex() == appmod.PAGE_ANISO
shot(win, "13_aniso_x")
lvl2 = [n for r in win.session.roots for n in r.folders_at(2)]
win.aniso_page.axis_tabs.set_current(1, emit=True)
win.aniso_page.y_group.zone.set_nodes(lvl2)
shot(win, "14_aniso_y")
win.aniso_page.axis_tabs.set_current(0, emit=True)
win.aniso_page.x_value.set_metric("wobble_eta_Pa_s")
win.aniso_page._plot()
pump(300)
assert win.compare_page.canvas.error is None, win.compare_page.canvas.error
shot(win, "15_aniso_graph")
g = win.session.result.groups[0]
print("eta", g.summary.get("wobble_eta_Pa_s_mean"), "T", g.summary.get("wobble_temperature_K_mean"))

# ---- blocked groups (Error fixtures) -------------------------------------------------
from detreser.widgets import dialogs as dl
def fake_exec(self):
    self.show(); pump(200); self.grab().save(os.path.join(SHOTS, "16_run_errors_real.png")); self.hide()
    return 1
dl.RunErrorsDialog.exec = fake_exec
win.goto(appmod.PAGE_OPTIONS)
win.options_page.tree.remove_root(win.session.roots[0])
win.main_page.add_paths([os.path.join(DATA, "..", "Error")])
wait_for(lambda: win.session.kind_detail and "…" not in win.session.kind_detail, 60)
print("error kind:", win.session.kind, win.session.kind_detail, "levels", win.session.n_levels)
win.options_page._run()
wait_for(lambda: win.session.result is not None, 600)
pump(300)
res = win.session.result
print("error status", res.status, [(g.group.name, g.status) for g in res.groups])
print("blocked:", [b["name"] for b in win.session.blocked_summaries()])
print("page", win.stack.currentIndex())
shot(win, "17_results_after_errors")
assert any(n.status == "blocked" for r in win.session.roots for n in r.folders_at(win.session.group_level()))
# readme
from detreser.widgets.dialogs import ReadMeDialog
rd = ReadMeDialog(win, open(os.path.join(ROOT, "detreser", "README.md")).read())
rd.show(); pump(200); rd.grab().save(os.path.join(SHOTS, "18_readme.png")); rd.hide()
print("ALL OK")
win.close()
