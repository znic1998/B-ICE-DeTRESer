"""Write a :class:`RunResult` to disk: compatible CSVs, machine-readable records, manifest.

Nothing in this module runs on import.  ``write_run(result)`` is the only
entry point; every file it writes is listed in ``run_manifest.json``.
Source workbooks are never opened for writing.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import sys
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from . import __version__
from .pipeline import GroupResult, RunResult
from .project import LabelValue

# ----------------------------------------------------------------------------
# units for the machine-readable records
# ----------------------------------------------------------------------------
UNITS: Dict[str, str] = {
    "gp": "-", "tmean_ns": "ns", "global_chi_sq": "-", "max_wavelength_chi_sq": "-",
    "wavelength_min_nm": "nm", "wavelength_max_nm": "nm", "n_wavelengths": "count", "n_comp": "count",
    "tau_fwhm_ns": "ns", "fwhm_max_cm-1": "cm^-1", "recon_wavelengths_masked": "count", "recon_dt_ns": "ns", "recon_tmax_ns": "ns",
    "tdfs_usable_tmax_ns": "ns", "r_inf": "-", "r_inf_sigma": "-", "r0_fitted": "-", "phi_mean_ns": "ns", "chi_sq": "-",
    "wobble_eta_Pa_s": "Pa*s", "wobble_eta_poise": "P", "wobble_D_perp_per_ns": "ns^-1", "wobble_k_rinf_over_r0": "-",
}
_UNIT_PATTERNS = [
    (re.compile(r"^(tau\d+|phi\d+)(_sigma)?_ns$"), "ns"), (re.compile(r"^area\d+_percent$"), "%"), (re.compile(r"^peak\d+_nm$"), "nm"),
    (re.compile(r"^(peak|com)_(delta_nu|nu0|nuinf|nu_initial_measured)_cm-1$"), "cm^-1"), (re.compile(r"^(peak|com)_tau_r_ns$"), "ns"),
    (re.compile(r"^(peak|com)_(metric_tmin|metric_tmax|nu0_time)_ns$"), "ns"), (re.compile(r"^(peak|com)_n_points$"), "count"),
    (re.compile(r"^(B\d+|alpha\d+)$"), "-"), (re.compile(r"^ra\d+_percent$"), "%"), (re.compile(r"_cm-1$"), "cm^-1"), (re.compile(r"_ns$"), "ns"),
    (re.compile(r"_fraction$"), "-"), (re.compile(r"_percent$"), "%"),
]


def unit_of(metric: str) -> str:
    if metric in UNITS:
        return UNITS[metric]
    for pat, u in _UNIT_PATTERNS:
        if pat.search(metric):
            return u
    return ""


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def safe_name(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("._")
    return s or "unnamed"


def _json_default(o: Any):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, np.ndarray):
        return [_json_default(x) if isinstance(x, (np.floating, float)) else x for x in o.tolist()]
    if is_dataclass(o):
        return asdict(o)
    if isinstance(o, (set, tuple)):
        return list(o)
    if hasattr(o, "value"):
        return o.value
    return str(o)


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=_json_default, ensure_ascii=False)


def write_csv_records(path: str, records: Sequence[Dict[str, Any]], columns: Optional[Sequence[str]] = None) -> None:
    """CSV with a stable header; missing values are written as empty fields (never as 0)."""
    if columns is None:
        columns = []
        for r in records:
            for k in r:
                if k not in columns:
                    columns.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
        w.writeheader()
        for r in records:
            row = {}
            for k in columns:
                v = r.get(k)
                if v is None or (isinstance(v, (float, np.floating)) and not np.isfinite(v)):
                    row[k] = ""
                elif isinstance(v, (dict, list, tuple)):
                    row[k] = json.dumps(v, default=_json_default)
                elif isinstance(v, (float, np.floating)):
                    row[k] = repr(float(v))  # full precision; rounding belongs to display
                else:
                    row[k] = v
            w.writerow(row)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def environment_info() -> Dict[str, Any]:
    import matplotlib
    import openpyxl
    import scipy

    return {"tres_suite": __version__, "python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
            "scipy": scipy.__version__, "pandas": pd.__version__, "openpyxl": openpyxl.__version__, "matplotlib": matplotlib.__version__}


# ----------------------------------------------------------------------------
# main writer
# ----------------------------------------------------------------------------
class Writer:
    def __init__(self, out_dir: str):
        self.out_dir = out_dir
        self.files: List[Dict[str, Any]] = []

    def path(self, *parts: str) -> str:
        p = os.path.join(self.out_dir, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def register(self, path: str, description: str) -> str:
        self.files.append({"path": os.path.relpath(path, self.out_dir), "description": description})
        return path

    def csv(self, rel: str, records: Sequence[Dict[str, Any]], description: str, columns=None) -> str:
        p = self.path(rel)
        write_csv_records(p, records, columns)
        return self.register(p, description)

    def json(self, rel: str, data: Any, description: str) -> str:
        p = self.path(rel)
        write_json(p, data)
        return self.register(p, description)

    def frame(self, rel: str, df: pd.DataFrame, description: str, **kw) -> str:
        p = self.path(rel)
        df.to_csv(p, index=False, float_format="%.17g", **kw)
        return self.register(p, description)


def _wide_table(result: RunResult, metric: str, stat: str, kind: str = "tres") -> Optional[pd.DataFrame]:
    """Columns = first group level; one row per combination of ALL remaining group levels.

    Every grouping level is preserved (one column each), so two groups can never share a cell.
    With a single group level the table has one value column named ``value``; with no group
    level (one group) the row is labelled ``group``.
    """
    levels = list(result.project.group_levels)
    groups = result.ok_groups(kind)
    col = f"{metric}_{stat}"
    if not groups or not any(col in g.summary for g in groups):
        return None
    if len(levels) >= 2:
        col_level, row_levels = levels[0], levels[1:]
    elif len(levels) == 1:
        col_level, row_levels = None, [levels[0]]
    else:
        col_level, row_levels = None, ["group"]

    def row_key(g):
        return tuple(g.summary.get(f"label:{ln}", g.group.name if ln == "group" else "") for ln in row_levels)

    rows = sorted({row_key(g) for g in groups}, key=lambda k: tuple(LabelValue.parse(x).sort_key() for x in k))
    cols = sorted({g.summary.get(f"label:{col_level}", "") for g in groups}, key=lambda s: LabelValue.parse(s).sort_key()) if col_level else ["value"]
    table = {r: {c: np.nan for c in cols} for r in rows}
    seen = set()
    for g in groups:
        r, c = row_key(g), (g.summary.get(f"label:{col_level}", "") if col_level else "value")
        if (r, c) in seen:  # cannot happen when every group level is a row or column, but never overwrite silently
            raise ValueError(f"wide export ambiguous: two groups map to the same cell {r} / {c}")
        seen.add((r, c))
        table[r][c] = g.summary.get(col, np.nan)
    df = pd.DataFrame([list(r) + [table[r][c] for c in cols] for r in rows], columns=row_levels + cols)
    return df


def check_destination(out_dir: str, overwrite: bool) -> None:
    """Refuse a non-empty destination unless overwrite is set.  Call once, before plots and exports."""
    if os.path.isdir(out_dir) and os.listdir(out_dir) and not overwrite:
        raise FileExistsError(f"output directory {out_dir} is not empty; set output.overwrite=true to write into it")


def write_run(result: RunResult, out_dir: Optional[str] = None, plots: Optional[List[Dict[str, Any]]] = None,
              check: bool = True) -> Dict[str, Any]:
    cfg = result.config
    out_dir = out_dir or cfg.output.directory
    if check:
        check_destination(out_dir, cfg.output.overwrite)
    os.makedirs(out_dir, exist_ok=True)
    W = Writer(out_dir)
    project = result.project

    # --- configuration, environment ------------------------------------------
    W.json("run_config.json", cfg.to_dict(), "effective run configuration (all settings)")
    W.json("environment.json", environment_info(), "software and dependency versions")

    # --- inventory and coverage -------------------------------------------------
    inv = []
    for m in project.measurements:
        rec = m.to_record()
        rec["sha256"] = _sha256(m.path) if os.path.exists(m.path) else ""
        g = next((gr for gr in result.groups if m in gr.group.measurements), None)
        rec["group_id"] = g.group.group_id if g else ""
        rec["group"] = g.group.name if g else ""
        rec["group_status"] = g.status if g else ""
        rec["processing_status"] = ("processed" if (g and g.status == "ok" and m.workbook is not None)
                                    else ("rejected: " + m.error if m.error else ("blocked: " + ",".join(g.block_reasons) if g else "unassigned")))
        inv.append(rec)
    for s in project.skipped:
        inv.append({"path": s["path"], "filename": os.path.basename(s["path"]), "kind": "skipped", "error": s["reason"], "processing_status": "skipped: " + s["reason"]})
    W.csv("inventory.csv", inv, "every input file with identifier, labels, detected type, status and reason")
    cov: Dict[tuple, int] = {}
    for r in inv:
        key = (r.get("kind"), r.get("workbook:n_components"), r.get("workbook:wavelength_min_nm"), r.get("workbook:wavelength_max_nm"),
               json.dumps(r.get("workbook:wavelength_intervals_nm")) if r.get("workbook:wavelength_intervals_nm") is not None else "",
               r.get("processing_status", "").split(":")[0])
        cov[key] = cov.get(key, 0) + 1
    W.csv("coverage_report.csv", [dict(zip(["kind", "n_components", "wavelength_min_nm", "wavelength_max_nm", "wavelength_intervals_nm", "status", "n_files"], k + (n,)))
                                  for k, n in sorted(cov.items(), key=lambda kv: [str(x) for x in kv[0]])], "compact coverage by workbook type, component count, range, interval and status")

    # --- diagnostics and groups -----------------------------------------------------
    W.csv("diagnostics.csv", [d.to_record() for d in result.diagnostics], "all diagnostics (severity, rule, group, files, location, observed, expected, action)")
    W.json("diagnostics.json", [d.to_record() for d in result.diagnostics], "diagnostics, machine-readable")
    W.csv("groups.csv", [dict(g.group.to_record(), kind=g.kind, status=g.status, block_reasons=";".join(g.block_reasons), n_analysed=g.n_replicates) for g in result.groups],
          "condition groups with status and blocking reasons")

    # --- replicate and summary tables ------------------------------------------------
    for kind in ("tres", "anisotropy"):
        reps = result.replicate_records(kind)
        if reps:
            W.csv(f"{kind}_replicates.csv", reps, f"per-replicate {kind} metrics (one row per workbook)")
        summ = result.summary_records(kind)
        if summ:
            W.csv(f"{kind}_summary.csv", summ, f"per-group {kind} mean / sample SD (ddof=1) / n for every numeric metric")

    # --- long-format records ------------------------------------------------------------
    long: List[Dict[str, Any]] = []
    for g in result.groups:
        labels = {k: v for k, v in g.summary.items() if k.startswith("label:")} if g.summary else {f"label:{k}": v.text for k, v in g.group.labels.items()}
        for r in g.replicates:
            for k, v in r.scalars.items():
                if k in ("measurement_id", "path", "file", "group_id", "group", "replicate", "replicate_index", "kind") or k.startswith("label:"):
                    continue
                if isinstance(v, bool) or v is None or isinstance(v, str):
                    continue
                if isinstance(v, (int, float, np.integer, np.floating)):
                    avail = r.scalars.get(f"{k}_available", True) if f"{k}_available" in r.scalars else np.isfinite(float(v))
                    long.append({"level": "replicate", "measurement_id": r.measurement.measurement_id, "group_id": g.group.group_id, "group": g.group.name,
                                 **labels, "metric": k, "unit": unit_of(k), "value": v if np.isfinite(float(v)) else None, "n": 1,
                                 "status": "available" if avail else ("unavailable: " + str(r.scalars.get(f"{k}_reason", "")))})
        if g.status == "ok":
            for k, v in g.summary.items():
                if k.endswith("_mean"):
                    base = k[:-5]
                    long.append({"level": "group", "measurement_id": "", "group_id": g.group.group_id, "group": g.group.name, **labels,
                                 "metric": base, "unit": unit_of(base), "value": v if isinstance(v, (int, float)) and np.isfinite(v) else None,
                                 "sd": g.summary.get(f"{base}_std"), "n": g.summary.get(f"{base}_n"), "status": "available" if g.summary.get(f"{base}_n", 0) else "unavailable"})
    W.csv("records.csv", long, "long-format records: identifiers, labels, metric, unit, value, SD, n, status",
          columns=["level", "measurement_id", "group_id", "group"] + [f"label:{ln}" for ln in project.level_names] + ["metric", "unit", "value", "sd", "n", "status"])

    # --- per-metric wide tables (clean) and legacy graph_data ------------------------------
    metrics = sorted({k[:-5] for g in result.ok_groups("tres") for k in g.summary if k.endswith("_mean")})
    for metric in metrics:
        for stat in ("mean", "std", "n"):
            df = _wide_table(result, metric, stat)
            if df is not None:
                W.frame(f"metric_tables/{safe_name(metric)}_{stat}.csv", df, f"{metric} {stat} by group labels (wide)")
    if cfg.output.legacy_compatible:
        _write_legacy(W, result)

    # --- per-group spectra and trajectories ------------------------------------------------
    for g in result.ok_groups("tres"):
        gdir = os.path.join("groups", safe_name(g.group.name))
        _write_group_tres(W, g, gdir, cfg)

    # --- plots (already rendered by plotting; register their files) -------------------------
    for p in plots or []:
        for f in p.get("files", []):
            W.register(f, f"plot {p.get('name')}: {p.get('description', '')}")

    manifest = {"status": result.status, "tres_suite": __version__, "started": result.started, "finished": result.finished,
                "seconds": result.finished - result.started, "output_directory": os.path.abspath(out_dir),
                "n_measurements": len(project.measurements), "n_groups": len(result.groups),
                "blocked_groups": [{"group": g.group.name, "reasons": g.block_reasons} for g in result.groups if g.status == "blocked"],
                "n_errors": sum(1 for d in result.diagnostics if d.severity.value == "error"),
                "n_warnings": sum(1 for d in result.diagnostics if d.severity.value == "warning"),
                "files": W.files}
    write_json(os.path.join(out_dir, "run_manifest.json"), manifest)
    return manifest


# ----------------------------------------------------------------------------
def _write_group_tres(W: Writer, g: GroupResult, gdir: str, cfg) -> None:
    sp = g.das_spectra
    if sp is not None:
        wl = sp["wavelengths_nm"]
        n = sp["n_components"]
        df = pd.DataFrame({"wavelength_nm": wl})
        for j in range(n):
            df[f"ra_tau{j + 1}_emission_mean"] = sp["emission_mean"][:, j]
            df[f"ra_tau{j + 1}_emission_std"] = sp["emission_std"][:, j]
        df["ra_total_mean"] = sp["total_mean"]
        df["ra_total_std"] = sp["total_std"]
        for j in range(n):
            df[f"npe_tau{j + 1}_mean"] = sp["npe_mean"][:, j]
            df[f"npe_tau{j + 1}_std"] = sp["npe_std"][:, j]
        df["fss_norm_mean"] = sp["fss_norm_mean"]
        df["n"] = sp["emission_n"][:, 0]
        W.frame(f"{gdir}/das_spectra.csv", df, f"{g.group.name}: replicate-mean DAS emission (RA/100*F/max F), signed NPE, total; SD ddof=1")
        W.csv(f"{gdir}/das_bubble_summary.csv", [dict(c, lifetime_label=f"tau{c['component']}") for c in g.bubble["components"]],
              f"{g.group.name}: bubble-plot quantities per component (lifetime, peak position, area %, n; region unassigned)")
    tg = g.time_gated
    if tg is not None:
        wl = tg["wavelengths_nm"]
        cols = [f"{w:g}" for w in wl]
        for key, desc in (("avg_matrix", "replicate-mean aligned decay surface (IRF-limited)"), ("avg_matrix_smooth", "Gaussian-smoothed surface")):
            df = pd.DataFrame(tg[key], columns=cols); df.insert(0, "time_ns", tg["time_ns"])
            W.frame(f"{gdir}/time_gated/{key}.csv", df, f"{g.group.name}: {desc}")
        df = pd.DataFrame({"wavelength_nm": wl})
        for lab, spec in zip(tg["gate_labels"], tg["gated_spectra"]):
            df[f"gate_{lab.replace(' ', '').replace('-', '_to_')}"] = spec
        W.frame(f"{gdir}/time_gated/time_gated_spectra.csv", df, f"{g.group.name}: area-normalised time-gated spectra (measured, IRF-limited)")
        W.frame(f"{gdir}/time_gated/energy_metrics_measured.csv", pd.DataFrame({"time_ns": tg["metric_time_ns"], "peak_cm-1": tg["peak_cm-1"], "com_cm-1": tg["com_cm-1"], "fwhm_cm-1": tg["fwhm_cm-1"]}),
                f"{g.group.name}: measured (IRF-limited) spectral trajectory from the smoothed decay surface")
        W.frame(f"{gdir}/time_gated/v_t_C_t_measured.csv", pd.DataFrame({"time_ns": tg["ct_time_ns"], "v_t_cm-1": tg["v_t_cm-1"], "C_t": tg["C_t"]}),
                f"{g.group.name}: measured v(t) (first-minimum truncated) and C(t)")
    tr = g.tdfs_trajectory
    if tr is not None and cfg.output.write_trajectories:
        df = pd.DataFrame({"time_ns": tr["t_ns"], "n": tr["n"]})
        for k in ("peak_cm-1", "com_cm-1", "fwhm_cm-1"):
            df[f"{k}_mean"] = tr[f"{k}_mean"]
            df[f"{k}_std"] = tr[f"{k}_std"]
        df["peak_nm_mean"] = np.where(tr["peak_cm-1_mean"] > 0, 1e7 / tr["peak_cm-1_mean"], np.nan)
        for k in ("C_peak", "C_com"):
            df[f"{k}_mean"] = tr[f"{k}_mean"]
            df[f"{k}_std"] = tr[f"{k}_std"]
        W.frame(f"{gdir}/tdfs_trajectory_mean.csv", df, f"{g.group.name}: replicate-mean TDFS trajectories ({tr['averaging_order']})")
    for r in g.replicates:
        if r.tdfs is None:
            continue
        stem = f"{safe_name(os.path.splitext(r.measurement.filename)[0])}__{r.measurement.measurement_id}"
        td = r.tdfs
        if cfg.output.write_trajectories:
            df = pd.DataFrame({"time_ns": td.traj_t_ns, "peak_cm-1": td.traj_peak_cm1, "peak_nm": np.where(td.traj_peak_cm1 > 0, 1e7 / td.traj_peak_cm1, np.nan),
                               "com_cm-1": td.traj_com_cm1, "fwhm_cm-1": td.traj_fwhm_cm1, "C_peak": td.traj_c_peak, "C_com": td.traj_c_com,
                               "total_positive_intensity": td.total_intensity[np.searchsorted(td.t_ns, td.traj_t_ns)]})
            W.frame(f"{gdir}/replicates/{stem}_tdfs_trajectory.csv", df, f"{r.measurement.filename}: reconstructed spectral trajectory")
        if cfg.output.write_reconstructed_spectra:
            times = [t for t in cfg.tdfs.export_times_ns if t <= td.t_ns[-1]]
            df = pd.DataFrame({"wavelength_nm": td.wavelengths_nm})
            df2 = pd.DataFrame({"wavelength_nm": td.wavelengths_nm})
            order = np.argsort(td.wavelengths_nm)
            trap = getattr(np, "trapezoid", None) or np.trapz  # type: ignore[attr-defined]
            for t in times:
                s = td.spectrum_at(t)
                df[f"t_{t:g}ns"] = s
                a = float(trap(s[order], td.wavelengths_nm[order]))
                df2[f"t_{t:g}ns"] = s / a if a != 0 else np.nan
            W.frame(f"{gdir}/replicates/{stem}_TRES_reconstructed.csv", df, f"{r.measurement.filename}: reconstructed TRES I(lambda,t) at selected times (area-pinned to the steady-state proxy)")
            W.frame(f"{gdir}/replicates/{stem}_TRANES_reconstructed.csv", df2, f"{r.measurement.filename}: area-normalised reconstructed spectra (TRANES) at selected times")


def _write_legacy(W: Writer, result: RunResult) -> None:
    """Legacy-layout outputs.  Validity columns are kept but explicitly UNEVALUATED."""
    note = {"status": "Legacy graph_data layout. The 'Valid' columns of tdfs big.py were a heuristic physical-validity gate; "
                      "it is disabled by design and the column now contains the literal UNEVALUATED. Do not interpret it as physical validation.",
            "sd_definition": "sample SD, ddof=1 (tdfs big.py convention; tres1.py used population SD)",
            "metric_manifest": []}
    metrics = ["gp", "tmean_ns", "peak_delta_nu_cm-1", "peak_tau_r_ns", "com_delta_nu_cm-1", "com_tau_r_ns"]
    for metric in metrics:
        for stat in ("mean", "std"):
            df = _wide_table(result, metric, stat)
            if df is None:
                continue
            n_row = max(1, len(result.project.group_levels) - 1)
            cols = list(df.columns)
            header = [""] * n_row if n_row == 1 else [str(c) for c in cols[:n_row]]
            for c in cols[n_row:]:
                header += [str(c), "Valid"]
            p = W.path(f"legacy/graph_data/{safe_name(metric)}_{stat}.csv")
            with open(p, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(header)
                for _, row in df.iterrows():
                    line = [row[c] for c in cols[:n_row]]
                    for c in cols[n_row:]:
                        v = row[c]
                        line += ["" if (v is None or (isinstance(v, float) and not np.isfinite(v))) else repr(float(v)), "UNEVALUATED"]
                    w.writerow(line)
            W.register(p, f"legacy wide table for {metric} ({stat}); Valid=UNEVALUATED")
        note["metric_manifest"].append({"metric": metric, "mean_file": f"{safe_name(metric)}_mean.csv", "std_file": f"{safe_name(metric)}_std.csv", "validity_source": "UNEVALUATED"})
    W.json("legacy/graph_data/README.json", note, "status of the legacy validity columns")
    # tres1.py-style outputs: spectra raw + full data / full_std
    rows_mean, rows_std = [], []
    for g in result.ok_groups("tres"):
        sp = g.das_spectra
        if sp is None:
            continue
        n = sp["n_components"]
        taus = sp["lifetimes_mean"]
        df = pd.DataFrame({"Wavelength": sp["wavelengths_nm"]})
        for j in range(n):
            df[f"{taus[j]!r}"] = sp["emission_mean"][:, j]
        df["total"] = sp["total_mean"]
        W.frame(f"legacy/spectra_raw/{safe_name(g.group.name)}.csv", df, f"tres1.py 'spectra raw' layout for {g.group.name} (column headers are mean lifetimes in ns)")
        lab = g.group.key[-1] if g.group.key else g.group.name
        rm: Dict[str, Any] = {"Condition": lab, "Group": g.group.name}
        rs: Dict[str, Any] = {"Condition": lab, "Group": g.group.name}
        for j, c in enumerate(g.bubble["components"]):
            rm[f"tau {j + 1}"] = c["lifetime_ns_mean"]
            rs[f"tau {j + 1}"] = c["lifetime_ns_std"]
        for j, c in enumerate(g.bubble["components"]):
            rm[f"em{j + 1} area"] = c["area_percent_mean"]
            rs[f"em{j + 1} area"] = c["area_percent_std"]
        rows_mean.append(rm)
        rows_std.append(rs)
    if rows_mean:
        W.csv("legacy/full_data.csv", rows_mean, "tres1.py 'full data' layout: mean lifetimes and DAS area percent per group (per-replicate mean)")
        W.csv("legacy/full_std.csv", rows_std, "tres1.py 'full_std' layout: sample SD (ddof=1; tres1.py used population SD)")
