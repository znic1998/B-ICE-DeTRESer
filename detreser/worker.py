"""Background thread that runs the backend pipeline and writes the session output folder."""
from __future__ import annotations

import logging
import time
import traceback

from PySide6.QtCore import QThread, Signal

log = logging.getLogger("detreser.worker")


class RunWorker(QThread):
    progress = Signal(int, int, str)  # done, total, stage
    message = Signal(str)
    finished_ok = Signal(object)  # RunResult
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, config, run_dir: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.run_dir = run_dir
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        from tres_suite.pipeline import run_project, RunCancelled
        from tres_suite.export import write_run
        t0 = time.time()
        last = {"t": t0}

        def _fp(d, t, st):
            self.progress.emit(d, t, st)
            if d in (0, 1, t) or time.time() - last["t"] > 10:
                last["t"] = time.time()
                log.info("%s %d/%d (%.0f s)", st, d, t, time.time() - t0)

        def _msg(text):
            log.info(text)
            self.message.emit(text)

        try:
            result = run_project(self.config, progress=_msg, file_progress=_fp, should_cancel=lambda: self._cancel)
            log.info("run finished: %s in %.0f s", result.status, time.time() - t0)
            if self._cancel:
                self.cancelled.emit()
                return
            self.message.emit("writing session output")
            try:
                write_run(result, self.run_dir, [], check=False)
            except Exception as exc:  # the in-memory result is still usable; exports will retry
                self.message.emit(f"session output could not be written: {exc}")
            self.finished_ok.emit(result)
        except RunCancelled:
            log.info("run cancelled")
            self.cancelled.emit()
        except Exception as exc:
            log.exception("run failed")
            self.failed.emit(f"{exc.__class__.__name__}: {exc}\n\n{traceback.format_exc(limit=6)}")


class DetectWorker(QThread):
    """Detects the measurement type of a few workbooks without blocking the window."""

    detected = Signal(str, str)  # kind, detail

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths = list(paths)

    def run(self) -> None:
        from tres_suite.workbook import detect_workbook_type
        kinds = {}
        for p in self.paths:
            try:
                k, _ = detect_workbook_type(p)
            except Exception:
                k = "unreadable"
            kinds[k] = kinds.get(k, 0) + 1
        known = {k: v for k, v in kinds.items() if k in ("tres", "anisotropy")}
        if not known:
            self.detected.emit("unknown", "No readable TRES or anisotropy workbook found in the sampled files")
        elif len(known) == 1:
            k = next(iter(known))
            self.detected.emit(k, f"Detected from {sum(kinds.values())} sampled workbook(s)")
        else:
            self.detected.emit("mixed", "Both TRES and anisotropy workbooks were found; groups that mix them will be blocked")
