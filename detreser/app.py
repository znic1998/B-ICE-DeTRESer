"""B-ICE DeTRESer — desktop GUI on top of the tres_suite backend.

Run with ``python -m detreser`` (or the packaged app).  Pages are stacked in one window; the
session object (folders, options, run result) is shared by all of them.
"""
from __future__ import annotations

import logging
import os
import sys
import traceback

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMainWindow, QMessageBox, QStackedWidget

from .model import Session
from .theme import app_stylesheet, load_fonts
from .worker import DetectWorker, RunWorker

PAGE_MAIN, PAGE_OPTIONS, PAGE_TRES, PAGE_ANISO, PAGE_GRAPH, PAGE_COMPARE, PAGE_LOGNORMAL = range(7)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("B-ICE DeTRESer")
        self.resize(1280, 760)
        self.setMinimumSize(QSize(1100, 680))
        self.session = Session()
        self._worker = None
        self._detect = None
        self._loading = None
        self._previous_page = PAGE_OPTIONS
        from .pages.main_page import MainPage
        from .pages.options_page import OptionsPage
        from .pages.results_page import ResultsPage
        from .pages.graph_view import GraphViewPage
        from .pages.compare_graph import CompareGraphPage
        from .pages.lognormal_page import LogNormalPage
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.main_page = MainPage(self.session, self.show_readme)
        self.options_page = OptionsPage(self.session, self.show_readme)
        self.tres_page = ResultsPage(self.session, "tres", self.show_readme)
        self.aniso_page = ResultsPage(self.session, "anisotropy", self.show_readme)
        self.graph_page = GraphViewPage(self.session, self.show_readme)
        self.compare_page = CompareGraphPage(self.session, self.show_readme)
        self.lognormal_page = LogNormalPage(self.session, self.show_readme)
        for p in (self.main_page, self.options_page, self.tres_page, self.aniso_page, self.graph_page, self.compare_page, self.lognormal_page):
            self.stack.addWidget(p)
        # wiring
        self.main_page.folders_added.connect(self._folders_added)
        self.options_page.tree.changed.connect(self._folders_changed)
        self.options_page.run_requested.connect(self.run_analysis)
        self.options_page.advanced_requested.connect(self.show_advanced)
        self.options_page.start_over_requested.connect(self.start_over)
        for page in (self.tres_page, self.aniso_page):
            page.advanced_requested.connect(self.show_advanced)
            page.export_full_requested.connect(self.export_full)
            page.single_requested.connect(self.show_single)
            page.compare_requested.connect(self.show_compare)
            page.options_requested.connect(self._back_to_options)
        self.graph_page.back_requested.connect(lambda: self.goto(PAGE_TRES))
        self.graph_page.export_full_requested.connect(self.export_full)
        self.compare_page.back_requested.connect(self._back_from_compare)
        self.compare_page.advanced_requested.connect(self.show_advanced)
        self.compare_page.export_full_requested.connect(self.export_full)
        self.lognormal_page.back_requested.connect(lambda: self.goto(self._previous_page))
        self.goto(PAGE_MAIN)

    # ---- navigation ------------------------------------------------------------------
    def goto(self, page: int) -> None:
        self.stack.setCurrentIndex(page)

    def _back_to_options(self) -> None:
        self.options_page.refresh()
        self.goto(PAGE_OPTIONS)

    def start_over(self) -> None:
        """Forget the loaded folders, options and results and return to the start screen."""
        if QMessageBox.question(self, "Start over", "Remove all loaded folders and results and go back to the start screen?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        old = self.session
        self.session = Session()
        self.session.advanced = old.advanced  # keep the advanced settings
        old.cleanup()
        for p in (self.main_page, self.options_page, self.tres_page, self.aniso_page, self.graph_page, self.compare_page, self.lognormal_page):
            p.session = self.session
        for p in (self.options_page, self.tres_page, self.aniso_page):
            p.tree.session = self.session
        for z in (self.tres_page.single_zone, self.tres_page.x_group.zone, self.tres_page.y_group.zone, self.tres_page.vv_zone,
                  self.aniso_page.x_group.zone, self.aniso_page.y_group.zone, self.aniso_page.vv_zone):
            z.session = self.session
            z.clear()
        for w in (self.tres_page.x_group, self.tres_page.y_group, self.tres_page.x_value, self.tres_page.y_value,
                  self.aniso_page.x_group, self.aniso_page.y_group, self.aniso_page.x_value, self.aniso_page.y_value):
            w.session = self.session
        self.options_page.refresh()
        self.goto(PAGE_MAIN)

    def _folders_added(self) -> None:
        self.options_page.refresh()
        self._detect_kind()
        self.goto(PAGE_OPTIONS)

    def _folders_changed(self) -> None:
        self.options_page.refresh()
        if not self.session.roots:
            self.goto(PAGE_MAIN)
            return
        self._detect_kind()

    def _detect_kind(self) -> None:
        files = self.session.all_files()
        if not files:
            return
        # sample: first file of every root plus a few more, capped
        sample = []
        for r in self.session.roots:
            fs = r.files()
            sample += fs[:2] + fs[-1:]
        paths = []
        for f in sample:
            if f.path not in paths:
                paths.append(f.path)
        self.options_page.set_kind(self.session.kind, "Detecting from the workbooks…")
        self._detect = DetectWorker(paths[:12], self)
        self._detect.detected.connect(self._kind_detected)
        self._detect.start()

    def _kind_detected(self, kind: str, detail: str) -> None:
        self.options_page.set_kind(kind, detail)

    # ---- run ------------------------------------------------------------------------
    def run_analysis(self) -> None:
        from .widgets.dialogs import RunLoadingDialog
        s = self.session
        if s.kind == "unknown":
            QMessageBox.warning(self, "Unknown workbooks", "None of the sampled workbooks looks like a TRES or anisotropy export.")
            return
        try:
            cfg = s.build_config()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid settings", f"{exc}")
            return
        if s.kind == "anisotropy" and s.visc_calculate:
            miss = cfg.wobble.missing()
            if miss:
                QMessageBox.warning(self, "Microviscosity settings", "Missing or invalid: " + ", ".join(miss))
                return
        run_dir = s.new_run_dir()
        logging.getLogger("detreser").info("run: %d files, workers=%d, kind=%s, session dir %s", len(cfg.project.files), cfg.project.workers, s.kind, run_dir)
        self._loading = RunLoadingDialog(self)
        self._worker = RunWorker(cfg, run_dir, self)
        self._worker.progress.connect(self._loading.set_progress)
        self._worker.message.connect(self._on_message)
        self._worker.finished_ok.connect(self._run_finished)
        self._worker.failed.connect(self._run_failed)
        self._worker.cancelled.connect(self._run_cancelled)
        self._loading.cancel_requested.connect(self._worker.cancel)
        self._loading.show()
        self._worker.start()

    def _on_message(self, text: str) -> None:
        if self._loading and text.startswith("writing"):
            self._loading.set_message("Writing session output…")

    def _close_loading(self) -> None:
        if self._loading is not None:
            self._loading.close()
            self._loading.deleteLater()
            self._loading = None

    def _run_failed(self, text: str) -> None:
        logging.getLogger("detreser").error("run failed: %s", text)
        self._close_loading()
        QMessageBox.critical(self, "Analysis failed", text)

    def _run_cancelled(self) -> None:
        self._close_loading()

    def _run_finished(self, result) -> None:
        from .widgets.dialogs import RunErrorsDialog
        self._close_loading()
        s = self.session
        s.result = result
        s.run_dir = self._worker.run_dir if self._worker else None
        s.plots_made = []
        s.deconvolution = {}
        s.mark_groups()
        kinds = {g.kind for g in result.groups if g.status == "ok"}
        if kinds == {"anisotropy"}:
            s.kind = "anisotropy"
        elif "tres" in kinds:
            s.kind = "tres"
        blocked = s.blocked_summaries()
        if result.status == "failed":
            if blocked:
                RunErrorsDialog(self, blocked, s.warning_count()).exec()
            else:
                QMessageBox.critical(self, "Nothing analysed", "No condition group could be analysed. Check that the folders contain EzTime exports.")
            self.options_page.refresh()
            return
        if blocked:
            dlg = RunErrorsDialog(self, blocked, s.warning_count())
            if dlg.exec() != int(QDialog.DialogCode.Accepted):
                self.options_page.refresh()
                return
        self._show_results()

    def _show_results(self) -> None:
        s = self.session
        page = self.aniso_page if s.kind == "anisotropy" else self.tres_page
        page.refresh()
        self.goto(PAGE_ANISO if s.kind == "anisotropy" else PAGE_TRES)

    # ---- results pages ------------------------------------------------------------
    def show_single(self, node, plots) -> None:
        self.graph_page.show_plots(node, plots)
        self.goto(PAGE_GRAPH)

    def show_compare(self, spec) -> None:
        self._previous_page = PAGE_ANISO if spec.kind == "anisotropy" else PAGE_TRES
        self.compare_page.show_spec(spec)
        self.goto(PAGE_COMPARE)

    def _back_from_compare(self) -> None:
        self.goto(self._previous_page)

    # ---- dialogs -------------------------------------------------------------------
    def show_advanced(self) -> None:
        from .widgets.dialogs import AdvancedDialog
        dlg = AdvancedDialog(self, self.session)
        dlg.open_fit_review.connect(self.show_fit_review)
        dlg.exec()

    def show_fit_review(self) -> None:
        cur = self.stack.currentIndex()
        if cur in (PAGE_TRES, PAGE_ANISO, PAGE_OPTIONS, PAGE_GRAPH, PAGE_COMPARE):
            self._previous_page = cur if cur != PAGE_GRAPH else PAGE_TRES
        if self.lognormal_page.start():
            self.goto(PAGE_LOGNORMAL)

    def show_readme(self) -> None:
        from .widgets.dialogs import ReadMeDialog
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, "README.md")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = "# B-ICE DeTRESer\n\nREADME.md was not found next to the program."
        ReadMeDialog(self, text).exec()

    def export_full(self) -> None:
        """Export full data: write_run (+ every plot made in this session) into a folder chosen by the user."""
        from .widgets.dialogs import ask_overwrite
        from tres_suite.export import write_run
        from tres_suite.plotting import render_plots
        s = self.session
        if s.result is None:
            QMessageBox.information(self, "Nothing to export", "Run an analysis first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Export full data to folder", os.path.expanduser("~"))
        if not folder:
            return
        if not ask_overwrite(self, folder, s.advanced["output"]["overwrite_policy"]):
            return
        try:
            cfg = s.result.config
            cfg.output.directory = folder
            cfg.output.overwrite = True
            cfg.plots = [p for p in s.plots_made]
            outs = []
            plot_dir = os.path.join(folder, "plots")
            for pc in cfg.plots:
                try:
                    outs.extend(render_plots(s.result, plot_dir, [pc]))
                except Exception as exc:
                    outs.append(type("PO", (), {"as_manifest": lambda self, e=exc, n=pc.name: {"name": n, "files": [], "description": f"FAILED: {e}"}})())
            manifest = write_run(s.result, folder, [p.as_manifest() for p in outs], check=False)
            if s.run_dir and os.path.isdir(os.path.join(s.run_dir, "deconvolution")):
                import shutil
                dst = os.path.join(folder, "deconvolution")
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(os.path.join(s.run_dir, "deconvolution"), dst)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"{exc.__class__.__name__}: {exc}\n\n{traceback.format_exc(limit=4)}")
            return
        n_plots = len(cfg.plots)
        QMessageBox.information(self, "Exported", f"Full data written to\n{folder}\n\n{manifest['n_errors']} errors, {manifest['n_warnings']} warnings "
                                f"(see diagnostics.csv); {n_plots} plot{'s' if n_plots != 1 else ''} from this session in plots/.")

    def closeEvent(self, ev) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self.session.cleanup()
        super().closeEvent(ev)


def log_path() -> str:
    """Log file next to the program (falls back to the home folder)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for d in (here, os.path.expanduser("~")):
        if os.access(d, os.W_OK):
            return os.path.join(d, "detreser.log")
    return os.path.join(os.path.expanduser("~"), "detreser.log")


def setup_logging() -> None:
    path = log_path()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stderr)])
    logging.getLogger("detreser").info("B-ICE DeTRESer starting; python %s; platform %s; log at %s", sys.version.split()[0], sys.platform, path)

    def excepthook(t, v, tb):
        logging.getLogger("detreser").error("uncaught exception", exc_info=(t, v, tb))
        sys.__excepthook__(t, v, tb)
    sys.excepthook = excepthook


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    setup_logging()
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True) if hasattr(Qt, "AA_UseHighDpiPixmaps") else None
    app = QApplication(argv)
    app.setApplicationName("B-ICE DeTRESer")
    app.setOrganizationName("B-ICE")
    load_fonts()
    app.setStyleSheet(app_stylesheet())
    win = MainWindow()
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    win.show()
    # folders passed on the command line (e.g. drag onto the app icon)
    paths = [a for a in argv[1:] if os.path.isdir(a)]
    if paths:
        QTimer.singleShot(0, lambda: win.main_page.add_paths(paths))
    return app.exec()
