"""Project model: measurements, user-labelled hierarchy levels, condition groups.

Vocabulary
----------
* **Measurement** -- one workbook with a stable identifier, its source path,
  its label values (one per hierarchy level) and, after loading, the parsed
  workbook or the parse error.
* **Condition group** -- the set of replicate measurements that are meant to be
  averaged (e.g. ``DOPC / 15``).  A group is identified by the tuple of label
  values of all hierarchy levels *except* the replicate level.
* **Selection** -- any subset of measurements chosen by label values
  (e.g. every group whose ``Composition`` is ``DOPC``).  A selection can span
  several condition groups; it is never averaged as a whole.

Folder depth and folder names carry no fixed scientific meaning.  The user
supplies the level names (``["Composition", "Temperature", "Replicate"]`` by
default for a three-deep tree); whichever level is named as the replicate
level (default: the last one) is excluded from the group key.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .workbook import WorkbookParseError, load_workbook

_NUM_RE = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
_TEMP_UNIT_RE = re.compile(
    r"^\s*(?P<num>[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)\s*(?P<unit>°\s*[cCfF]|deg\s*[cCfF]|[cCfF]|K|k)?\s*$"
)
LOCK_PREFIX = "~$"
WORKBOOK_EXTENSIONS = (".xlsx", ".xlsm")


@dataclass
class LabelValue:
    """A hierarchy label: original text plus a numeric interpretation when recognisable."""

    text: str
    number: Optional[float] = None
    unit: Optional[str] = None  # e.g. "degC", "K" when the text carried a unit

    @staticmethod
    def parse(text: str) -> "LabelValue":
        t = str(text).strip()
        m = _TEMP_UNIT_RE.match(t)
        if m:
            unit = m.group("unit")
            unit_norm = None
            if unit:
                u = unit.replace("°", "").replace("deg", "").strip().upper()
                unit_norm = {"C": "degC", "F": "degF", "K": "K"}.get(u)
            try:
                return LabelValue(t, float(m.group("num")), unit_norm)
            except ValueError:  # pragma: no cover
                return LabelValue(t)
        # leading number with trailing text, e.g. "17C rep" or "T17"
        m2 = re.search(r"^[A-Za-z]{0,2}\s*(" + _NUM_RE.pattern + r")\s*$", t)
        if m2:
            try:
                return LabelValue(t, float(m2.group(1)))
            except ValueError:  # pragma: no cover
                pass
        return LabelValue(t)

    def sort_key(self) -> Tuple[int, float, str]:
        if self.number is not None:
            return (0, self.number, self.text)
        return (1, float("inf"), self.text)

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "number": self.number, "unit": self.unit}


def _stable_id(path: str, prefix: str = "m") -> str:
    h = hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{h}"


@dataclass
class Measurement:
    """One workbook and its place in the hierarchy."""

    measurement_id: str
    path: str
    labels: Dict[str, LabelValue]  # level name -> value
    workbook: Any = None  # TresWorkbook | AnisotropyWorkbook | None
    error: Optional[str] = None
    error_location: Optional[str] = None
    kind: str = "unknown"  # tres | anisotropy | unsupported | unreadable | lock_file

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    def label_text(self, level: str) -> str:
        v = self.labels.get(level)
        return "" if v is None else v.text

    def load(self) -> None:
        """Parse the workbook; never raises -- failures are recorded on the measurement."""
        if self.filename.startswith(LOCK_PREFIX):
            self.kind = "lock_file"
            self.error = "temporary Excel lock file (skipped)"
            return
        try:
            self.workbook = load_workbook(self.path)
            self.kind = self.workbook.kind
            self.error = None
        except WorkbookParseError as exc:
            self.workbook = None
            self.error = str(exc)
            self.error_location = exc.location or None
            self.kind = "unsupported" if "Unsupported workbook layout" in str(exc) else "unreadable"
        except Exception as exc:  # pragma: no cover - defensive: never let one file kill the run
            self.workbook = None
            self.error = f"{exc.__class__.__name__}: {exc}"
            self.kind = "unreadable"

    def to_record(self) -> Dict[str, Any]:
        rec: Dict[str, Any] = {
            "measurement_id": self.measurement_id,
            "path": self.path,
            "filename": self.filename,
            "kind": self.kind,
            "error": self.error,
            "error_location": self.error_location,
        }
        for k, v in self.labels.items():
            rec[f"label:{k}"] = v.text
            if v.number is not None:
                rec[f"label:{k}:number"] = v.number
        if self.workbook is not None:
            rec.update({f"workbook:{k}": v for k, v in self.workbook.summary_dict().items()})
        return rec


@dataclass
class ConditionGroup:
    """Replicates meant to be averaged together."""

    group_id: str
    key: Tuple[str, ...]  # label texts of the non-replicate levels, in level order
    level_names: Tuple[str, ...]
    measurements: List[Measurement] = field(default_factory=list)

    @property
    def name(self) -> str:
        return " / ".join(self.key) if self.key else "(all)"

    @property
    def labels(self) -> Dict[str, LabelValue]:
        if not self.measurements:
            return {ln: LabelValue.parse(k) for ln, k in zip(self.level_names, self.key)}
        m = self.measurements[0]
        return {ln: m.labels[ln] for ln in self.level_names if ln in m.labels}

    def loaded(self) -> List[Measurement]:
        return [m for m in self.measurements if m.workbook is not None]

    def kinds(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for m in self.measurements:
            out[m.kind] = out.get(m.kind, 0) + 1
        return out

    def to_record(self) -> Dict[str, Any]:
        rec: Dict[str, Any] = {"group_id": self.group_id, "group": self.name}
        for ln, v in self.labels.items():
            rec[f"label:{ln}"] = v.text
            if v.number is not None:
                rec[f"label:{ln}:number"] = v.number
        rec["n_files"] = len(self.measurements)
        return rec


def _load_measurement(m: "Measurement") -> "Measurement":
    m.load()
    return m


class Project:
    """Container of measurements and their grouping."""

    def __init__(self, level_names: Sequence[str], replicate_level: Optional[str] = None):
        if not level_names:
            raise ValueError("At least one hierarchy level name is required")
        self.level_names: List[str] = list(level_names)
        self.replicate_level: str = replicate_level or self.level_names[-1]
        if self.replicate_level not in self.level_names:
            raise ValueError(f"replicate level {self.replicate_level!r} is not one of {self.level_names}")
        self.group_levels: List[str] = [ln for ln in self.level_names if ln != self.replicate_level]
        self.measurements: List[Measurement] = []
        self.skipped: List[Dict[str, str]] = []  # non-workbook / lock files encountered during import
        self._by_id: Dict[str, Measurement] = {}

    # ---- adding measurements ------------------------------------------------
    def add_file(self, path: str, labels: Dict[str, str]) -> Measurement:
        """Explicit file import with explicit label assignment."""
        missing = [ln for ln in self.level_names if ln not in labels]
        if missing:
            raise ValueError(f"labels for levels {missing} are required for {path}")
        mid = _stable_id(path)
        if mid in self._by_id:
            raise ValueError(f"duplicate measurement identifier for {path} (already imported)")
        m = Measurement(mid, os.path.abspath(path), {ln: LabelValue.parse(labels[ln]) for ln in self.level_names})
        self.measurements.append(m)
        self._by_id[mid] = m
        return m

    def import_folder(self, root: str, depth: Optional[int] = None) -> List[Measurement]:
        """Import ``root/<level1>/<level2>/.../file.xlsx``.

        With ``n`` level names, files are expected ``n-1`` folders below ``root`` when the
        replicate level is the file itself (its label is the file stem).  If the replicate
        level is a *folder* (numbered replicate folders containing one workbook each), pass
        ``depth=n`` so that the file's parent folder supplies the replicate label.
        """
        n = len(self.level_names)
        depth = n - 1 if depth is None else depth
        if depth not in (n - 1, n):
            raise ValueError(f"depth must be {n - 1} (file is the replicate) or {n} (folder is the replicate)")
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            raise FileNotFoundError(root)
        added: List[Measurement] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            rel = os.path.relpath(dirpath, root)
            parts = [] if rel == "." else rel.split(os.sep)
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                if fn.startswith(LOCK_PREFIX):
                    self.skipped.append({"path": full, "reason": "temporary Excel lock file"})
                    continue
                if fn.startswith(".") or not fn.lower().endswith(WORKBOOK_EXTENSIONS):
                    self.skipped.append({"path": full, "reason": "not a workbook (.xlsx/.xlsm)"})
                    continue
                if len(parts) != depth:
                    self.skipped.append({"path": full, "reason": f"found {len(parts)} folder level(s) below root, expected {depth}"})
                    continue
                values = list(parts) + ([os.path.splitext(fn)[0]] if depth == n - 1 else [])
                labels = dict(zip(self.level_names, values))
                try:
                    added.append(self.add_file(full, labels))
                except ValueError as exc:
                    self.skipped.append({"path": full, "reason": str(exc)})
        return added

    # ---- loading ------------------------------------------------------------
    def load_all(self, progress=None, workers: int = 1) -> None:
        """Parse every measurement.  ``workers > 1`` parses in parallel processes (results are identical)."""
        todo = [i for i, m in enumerate(self.measurements) if m.workbook is None and m.error is None]
        if workers and workers > 1 and len(todo) > 1:
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor(max_workers=int(workers)) as ex:
                for k, (i, loaded) in enumerate(zip(todo, ex.map(_load_measurement, [self.measurements[i] for i in todo], chunksize=4))):
                    self.measurements[i] = loaded
                    self._by_id[loaded.measurement_id] = loaded
                    if progress is not None:
                        progress(k + 1, len(todo), loaded)
            return
        for k, i in enumerate(todo):
            self.measurements[i].load()
            if progress is not None:
                progress(k + 1, len(todo), self.measurements[i])

    # ---- grouping and selection ----------------------------------------------
    def groups(self, measurements: Optional[Iterable[Measurement]] = None) -> List[ConditionGroup]:
        """Condition groups (deterministic order: numeric-aware sort of the key)."""
        ms = list(self.measurements if measurements is None else measurements)
        table: Dict[Tuple[str, ...], ConditionGroup] = {}
        for m in ms:
            key = tuple(m.label_text(ln) for ln in self.group_levels)
            g = table.get(key)
            if g is None:
                gid = "g_" + hashlib.sha1("\x1f".join(key).encode("utf-8")).hexdigest()[:10]
                g = ConditionGroup(gid, key, tuple(self.group_levels))
                table[key] = g
            g.measurements.append(m)
        groups = list(table.values())
        groups.sort(key=lambda g: tuple(LabelValue.parse(k).sort_key() for k in g.key))
        for g in groups:
            g.measurements.sort(key=lambda m: (m.labels[self.replicate_level].sort_key(), m.path))
        return groups

    def select(self, **criteria: Any) -> List[Measurement]:
        """Select measurements by label values.

        ``criteria`` maps a level name to a value or a list of values (matched against
        label text, or numerically when both sides parse as numbers).
        """
        unknown = [k for k in criteria if k not in self.level_names]
        if unknown:
            raise ValueError(f"unknown level(s) {unknown}; levels are {self.level_names}")
        out = []
        for m in self.measurements:
            keep = True
            for level, wanted in criteria.items():
                wanted_list = list(wanted) if isinstance(wanted, (list, tuple, set)) else [wanted]
                lv = m.labels[level]
                hit = False
                for w in wanted_list:
                    wv = LabelValue.parse(str(w))
                    if wv.text == lv.text or (wv.number is not None and lv.number is not None and wv.number == lv.number):
                        hit = True
                        break
                if not hit:
                    keep = False
                    break
            if keep:
                out.append(m)
        return out

    def by_id(self, measurement_id: str) -> Measurement:
        return self._by_id[measurement_id]

    def inventory(self) -> List[Dict[str, Any]]:
        return [m.to_record() for m in self.measurements]
