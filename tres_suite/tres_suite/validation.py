"""Validation rules and structured diagnostics.

Policy (from the design document):

* A **failure** blocks the affected condition group from analysis and
  averaging.  Unrelated groups continue; the run is marked partially
  completed and the blocked groups are listed.  A bad replicate is never
  silently dropped so that the remaining subset looks like the full group.
* Differences *between* groups (replicate count, wavelength range, spacing)
  are **comparison warnings**, not failures.
* High chi-squared, unusually different replicates and differing anisotropy
  correlation times are **warnings**.  Their thresholds are configurable; when
  no threshold is configured the diagnostic values are reported without a
  pass/fail claim.

Every diagnostic carries severity, rule, affected group, source files,
worksheet location where available, observed values, expectation and a
corrective action.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .project import ConditionGroup, Measurement, Project


class Severity(str, Enum):
    ERROR = "error"  # blocks the group
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    severity: Severity
    rule: str
    message: str
    group_id: Optional[str] = None
    group: Optional[str] = None
    files: List[str] = field(default_factory=list)
    location: Optional[str] = None
    observed: Dict[str, Any] = field(default_factory=dict)
    expected: Optional[str] = None
    action: Optional[str] = None
    metric: Optional[str] = None

    def to_record(self) -> Dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class ValidationThresholds:
    """All numeric tolerances used by the rules.  ``None`` disables a threshold-based claim."""

    wavelength_tolerance_nm: float = 1e-6  # for comparing coordinates within a group
    allow_nonuniform_grid: bool = False
    min_wavelength_points: int = 3
    chi_sq_warning_threshold: Optional[float] = None  # e.g. 1.5; None -> report only
    chi_sq_is_reduced: Optional[bool] = True  # EzTime "Chi sq." is a reduced chi-squared (confirmed by the user)
    replicate_variation_warning_percent: Optional[float] = None  # 100*SD/|mean| above this -> warning
    replicate_variation_near_zero_mean: float = 1e-9  # |mean| below this -> percentage undefined
    replicate_variation_metrics: Sequence[str] = ("gp", "tmean_ns", "peak_delta_nu_cm-1", "peak_tau_r_ns")
    anisotropy_correlation_time_tolerance_percent: Optional[float] = None  # warn when phi differ by more
    cross_group_interval_tolerance_nm: float = 1e-6


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _paths(ms: Sequence[Measurement]) -> List[str]:
    return [m.path for m in ms]


def _fmt_intervals(wl: np.ndarray) -> List[float]:
    d = np.diff(np.sort(np.asarray(wl, float)))
    return sorted({round(float(x), 6) for x in d})


# ----------------------------------------------------------------------------
# within-group structural rules (errors)
# ----------------------------------------------------------------------------
def validate_group(group: ConditionGroup, th: ValidationThresholds) -> List[Diagnostic]:
    """Structural checks on one condition group.  Any ERROR blocks the group."""
    diags: List[Diagnostic] = []
    gid, gname = group.group_id, group.name

    if not group.measurements:
        diags.append(Diagnostic(Severity.ERROR, "empty_group", f"Group {gname} contains no workbooks", gid, gname,
                                expected="at least one readable workbook", action="Add workbooks or remove the group."))
        return diags

    # files that could not be parsed
    for m in group.measurements:
        if m.kind == "lock_file":
            diags.append(Diagnostic(Severity.INFO, "lock_file_skipped", f"Skipped temporary Excel lock file {m.filename}",
                                    gid, gname, [m.path]))
        elif m.workbook is None:
            rule = "unsupported_layout" if m.kind == "unsupported" else "unreadable_file"
            diags.append(Diagnostic(Severity.ERROR, rule, f"{m.filename}: {m.error}", gid, gname, [m.path],
                                    location=m.error_location, expected="an EzTime TRES or anisotropy export",
                                    action="Replace the file with a valid EzTime export or remove it from the group."))
    loaded = [m for m in group.measurements if m.workbook is not None]
    if not loaded:
        return diags

    # Case 6: mixed workbook types in one group
    kinds = sorted({m.workbook.kind for m in loaded})
    if len(kinds) > 1:
        diags.append(Diagnostic(
            Severity.ERROR, "mixed_workbook_types",
            f"Group {gname} mixes workbook types {kinds}", gid, gname, _paths(loaded),
            observed={m.filename: m.workbook.kind for m in loaded},
            expected="all workbooks in a condition group of the same type",
            action="Move the TRES and anisotropy workbooks into separately labelled groups (both may coexist in one project)."))
        return diags  # further comparisons are meaningless

    kind = kinds[0]
    if kind == "tres":
        diags.extend(_validate_tres_group(group, loaded, th))
    else:
        diags.extend(_validate_anisotropy_group(group, loaded, th))
    return diags


def _validate_tres_group(group: ConditionGroup, loaded: List[Measurement], th: ValidationThresholds) -> List[Diagnostic]:
    diags: List[Diagnostic] = []
    gid, gname = group.group_id, group.name

    # per-file sufficiency and grid regularity
    for m in loaded:
        w = m.workbook
        if w.n_wavelengths < th.min_wavelength_points:
            diags.append(Diagnostic(Severity.ERROR, "insufficient_wavelength_points",
                                    f"{m.filename} has {w.n_wavelengths} wavelength points", gid, gname, [m.path],
                                    location="Results", observed={"n_wavelengths": w.n_wavelengths},
                                    expected=f">= {th.min_wavelength_points} points", action="Use a workbook with a full emission series."))
        if not w.is_uniform_grid() and not th.allow_nonuniform_grid:
            diags.append(Diagnostic(Severity.ERROR, "nonuniform_wavelength_grid",
                                    f"{m.filename} has a non-uniform wavelength grid (intervals {_fmt_intervals(w.wavelengths_nm)} nm)",
                                    gid, gname, [m.path], location="Results!Wavelength/nm",
                                    observed={"intervals_nm": _fmt_intervals(w.wavelengths_nm)},
                                    expected="a single wavelength interval (set allow_nonuniform_grid=true to analyse non-uniform grids using their actual coordinates)",
                                    action="Re-export with a uniform step, or enable allow_nonuniform_grid explicitly."))
        for wtext in w.warnings:
            diags.append(Diagnostic(Severity.INFO, "parser_note", f"{m.filename}: {wtext}", gid, gname, [m.path]))
        if np.any(~np.isfinite(w.total_counts)) or np.any(w.total_counts < 0):
            diags.append(Diagnostic(Severity.ERROR, "invalid_total_counts", f"{m.filename} has non-finite or negative total counts",
                                    gid, gname, [m.path], location="Results!Total count",
                                    action="Check the export; total counts must be finite and non-negative."))
        if np.any(w.lifetimes_ns <= 0) or np.any(~np.isfinite(w.lifetimes_ns)):
            diags.append(Diagnostic(Severity.ERROR, "invalid_lifetimes", f"{m.filename} has non-positive or non-finite lifetimes {list(map(float, w.lifetimes_ns))}",
                                    gid, gname, [m.path], location="Results!Global", action="Re-fit the decays; lifetimes must be positive."))

    # Case 1: component counts
    counts = {m.filename: m.workbook.n_components for m in loaded}
    if len(set(counts.values())) > 1:
        diags.append(Diagnostic(
            Severity.ERROR, "component_count_mismatch",
            f"Group {gname}: DAS component counts differ between replicates", gid, gname, _paths(loaded),
            location="Results!Global", observed={"n_components": counts},
            expected="identical number of lifetime components in every replicate",
            action="Replace or regroup files so that all replicates were fitted with the same number of components."))

    # Case 2: wavelength range
    ranges = {m.filename: (m.workbook.wavelength_min_nm, m.workbook.wavelength_max_nm) for m in loaded}
    tol = th.wavelength_tolerance_nm
    mins = [r[0] for r in ranges.values()]
    maxs = [r[1] for r in ranges.values()]
    range_mismatch = (max(mins) - min(mins) > tol) or (max(maxs) - min(maxs) > tol)
    if range_mismatch:
        diags.append(Diagnostic(
            Severity.ERROR, "wavelength_range_mismatch",
            f"Group {gname}: wavelength ranges differ between replicates", gid, gname, _paths(loaded),
            location="Results!Wavelength/nm", observed={"min_max_nm": {k: list(v) for k, v in ranges.items()}},
            expected="identical minimum and maximum wavelength in every replicate (no padding or cropping is applied)",
            action="Regroup the files by wavelength range or re-measure the mismatching replicate."))

    # Case 3: full grid comparison (intervals and first mismatching coordinate)
    if not range_mismatch:
        ref = loaded[0]
        ref_wl = np.sort(ref.workbook.wavelengths_nm)
        for m in loaded[1:]:
            wl = np.sort(m.workbook.wavelengths_nm)
            first_mismatch = None
            if len(wl) != len(ref_wl):
                n = min(len(wl), len(ref_wl))
                idx = np.flatnonzero(np.abs(wl[:n] - ref_wl[:n]) > tol)
                first_mismatch = (float(ref_wl[idx[0]]), float(wl[idx[0]])) if len(idx) else (None, None)
            else:
                idx = np.flatnonzero(np.abs(wl - ref_wl) > tol)
                if len(idx):
                    first_mismatch = (float(ref_wl[idx[0]]), float(wl[idx[0]]))
            if first_mismatch is not None:
                diags.append(Diagnostic(
                    Severity.ERROR, "wavelength_grid_mismatch",
                    f"Group {gname}: wavelength grids differ ({ref.filename} vs {m.filename})", gid, gname, [ref.path, m.path],
                    location="Results!Wavelength/nm",
                    observed={
                        "intervals_nm": {ref.filename: _fmt_intervals(ref_wl), m.filename: _fmt_intervals(wl)},
                        "n_points": {ref.filename: int(len(ref_wl)), m.filename: int(len(wl))},
                        "first_mismatching_coordinate_nm": {ref.filename: first_mismatch[0], m.filename: first_mismatch[1]},
                    },
                    expected=f"identical wavelength coordinates (tolerance {tol} nm); grids are never resampled",
                    action="Regroup the files by wavelength grid or re-measure the mismatching replicate."))

    # Case 4: chi-squared (warning only)
    for m in loaded:
        w = m.workbook
        chi = w.global_chi_sq
        chi_wl_max = float(np.nanmax(w.chi_sq_per_wavelength)) if np.any(np.isfinite(w.chi_sq_per_wavelength)) else None
        obs = {"global_chi_sq": chi, "max_per_wavelength_chi_sq": chi_wl_max,
               "source": "Results!Global 'Chi sq.' as exported by EzTime",
               "is_reduced_chi_sq": th.chi_sq_is_reduced if th.chi_sq_is_reduced is not None else "unknown (not stated in export)",
               "threshold": th.chi_sq_warning_threshold}
        if th.chi_sq_warning_threshold is not None and chi is not None and chi > th.chi_sq_warning_threshold:
            diags.append(Diagnostic(Severity.WARNING, "high_chi_sq",
                                    f"{m.filename}: global chi-squared {chi:.4g} exceeds threshold {th.chi_sq_warning_threshold}",
                                    gid, gname, [m.path], location="Results!Global", observed=obs,
                                    expected=f"chi-squared <= {th.chi_sq_warning_threshold}",
                                    action="Inspect the fit; consider re-fitting or excluding the replicate explicitly."))
        else:
            diags.append(Diagnostic(Severity.INFO, "chi_sq_report", f"{m.filename}: global chi-squared {chi}", gid, gname,
                                    [m.path], location="Results!Global", observed=obs,
                                    expected=None if th.chi_sq_warning_threshold is None else f"<= {th.chi_sq_warning_threshold}"))
    return diags


def _validate_anisotropy_group(group: ConditionGroup, loaded: List[Measurement], th: ValidationThresholds) -> List[Diagnostic]:
    diags: List[Diagnostic] = []
    gid, gname = group.group_id, group.name
    for m in loaded:
        w = m.workbook
        for wtext in w.warnings:
            diags.append(Diagnostic(Severity.INFO, "parser_note", f"{m.filename}: {wtext}", gid, gname, [m.path]))
        if w.r_inf is None:
            diags.append(Diagnostic(Severity.ERROR, "missing_residual_anisotropy", f"{m.filename}: Rinf missing", gid, gname, [m.path],
                                    location="Results", action="Use an anisotropy export containing Rinf."))
        if np.any(w.rotational_correlation_times_ns <= 0):
            diags.append(Diagnostic(Severity.ERROR, "invalid_correlation_times",
                                    f"{m.filename}: non-positive rotational correlation time", gid, gname, [m.path], location="Results!Global"))
        obs = {"chi_sq": w.chi_sq, "source": "Results 'Chi sq.' as exported by EzTime",
               "is_reduced_chi_sq": th.chi_sq_is_reduced if th.chi_sq_is_reduced is not None else "unknown (not stated in export)",
               "threshold": th.chi_sq_warning_threshold}
        if th.chi_sq_warning_threshold is not None and w.chi_sq is not None and w.chi_sq > th.chi_sq_warning_threshold:
            diags.append(Diagnostic(Severity.WARNING, "high_chi_sq", f"{m.filename}: chi-squared {w.chi_sq:.4g} exceeds {th.chi_sq_warning_threshold}",
                                    gid, gname, [m.path], location="Results", observed=obs))
        else:
            diags.append(Diagnostic(Severity.INFO, "chi_sq_report", f"{m.filename}: chi-squared {w.chi_sq}", gid, gname, [m.path],
                                    location="Results", observed=obs))

    # Case 7: differing correlation times -> warning only; component count differences are NOT a rejection
    if len(loaded) >= 2:
        counts = {m.filename: m.workbook.n_components for m in loaded}
        if len(set(counts.values())) > 1:
            diags.append(Diagnostic(Severity.WARNING, "anisotropy_component_count_differs",
                                    f"Group {gname}: anisotropy fits use different numbers of rotational components", gid, gname,
                                    _paths(loaded), location="Results!Global", observed={"n_components": counts},
                                    expected="not enforced for anisotropy; reported for awareness",
                                    action="Check that the fits are comparable before averaging model-dependent quantities."))
        phis = {m.filename: [float(x) for x in m.workbook.rotational_correlation_times_ns] for m in loaded}
        means = {m.filename: m.workbook.mean_correlation_time_ns for m in loaded}
        vals = np.array([v for v in means.values() if v is not None and np.isfinite(v)], float)
        obs = {"rotational_correlation_times_ns": phis, "mean_correlation_time_ns": means,
               "tolerance_percent": th.anisotropy_correlation_time_tolerance_percent}
        if len(vals) >= 2:
            mean = float(np.mean(vals))
            spread_pct = 100.0 * float(np.max(vals) - np.min(vals)) / abs(mean) if abs(mean) > th.replicate_variation_near_zero_mean else float("nan")
            obs["mean_correlation_time_spread_percent"] = spread_pct
            tol = th.anisotropy_correlation_time_tolerance_percent
            if tol is not None and np.isfinite(spread_pct) and spread_pct > tol:
                diags.append(Diagnostic(Severity.WARNING, "anisotropy_lifetime_difference",
                                        f"Group {gname}: mean rotational correlation times differ by {spread_pct:.1f}% (tolerance {tol}%)",
                                        gid, gname, _paths(loaded), location="Results!Global", observed=obs,
                                        expected=f"spread <= {tol}%", action="Check replicate consistency; values are still averaged."))
            else:
                diags.append(Diagnostic(Severity.INFO, "anisotropy_lifetime_report",
                                        f"Group {gname}: mean rotational correlation times {list(means.values())}", gid, gname,
                                        _paths(loaded), observed=obs))
    return diags


# ----------------------------------------------------------------------------
# cross-group comparison warnings
# ----------------------------------------------------------------------------
def compare_groups(groups: Sequence[ConditionGroup], th: ValidationThresholds) -> List[Diagnostic]:
    """Warnings for differences between (valid) groups of the same workbook type."""
    diags: List[Diagnostic] = []
    tres = [g for g in groups if g.loaded() and all(m.workbook.kind == "tres" for m in g.loaded())]
    if len(tres) >= 2:
        n_rep = {g.name: len(g.loaded()) for g in tres}
        if len(set(n_rep.values())) > 1:
            diags.append(Diagnostic(Severity.WARNING, "replicate_count_differs_between_groups",
                                    "Groups have different replicate counts", observed={"n_replicates": n_rep},
                                    expected="not required; affects the reliability of SD comparisons",
                                    action="None required; n is reported with every summary statistic."))
        rng = {g.name: (g.loaded()[0].workbook.wavelength_min_nm, g.loaded()[0].workbook.wavelength_max_nm) for g in tres}
        if len({tuple(v) for v in rng.values()}) > 1:
            diags.append(Diagnostic(Severity.WARNING, "wavelength_range_differs_between_groups",
                                    "Groups were measured over different wavelength ranges", observed={"min_max_nm": {k: list(v) for k, v in rng.items()}},
                                    expected="not required; metrics integrated over wavelength are not strictly comparable",
                                    action="Compare such groups with care; spectra are never pooled across groups."))
        iv = {g.name: _fmt_intervals(g.loaded()[0].workbook.wavelengths_nm) for g in tres}
        if len({tuple(v) for v in iv.values()}) > 1:
            diags.append(Diagnostic(Severity.WARNING, "wavelength_interval_differs_between_groups",
                                    "Groups were measured with different wavelength spacing", observed={"intervals_nm": iv},
                                    expected="not required", action="Compare such groups with care; spectra are never resampled."))
        ncomp = {g.name: g.loaded()[0].workbook.n_components for g in tres}
        if len(set(ncomp.values())) > 1:
            diags.append(Diagnostic(Severity.INFO, "component_count_differs_between_groups",
                                    "Groups were fitted with different numbers of components", observed={"n_components": ncomp}))
    return diags


# ----------------------------------------------------------------------------
# Case 5: replicate variation (after per-replicate metrics exist)
# ----------------------------------------------------------------------------
def replicate_variation(group: ConditionGroup, per_replicate: Sequence[Dict[str, Any]], th: ValidationThresholds) -> List[Diagnostic]:
    """Report 100*SD/|mean| for selected scalar metrics.  Warning only."""
    diags: List[Diagnostic] = []
    gid, gname = group.group_id, group.name
    files = [r.get("path") or r.get("file") for r in per_replicate]
    for metric in th.replicate_variation_metrics:
        vals = np.array([r.get(metric, np.nan) for r in per_replicate], float)
        finite = np.isfinite(vals)
        n = int(finite.sum())
        obs: Dict[str, Any] = {"metric": metric, "n": n, "values": {os.path.basename(f) if f else i: (float(v) if np.isfinite(v) else None) for i, (f, v) in enumerate(zip(files, vals))},
                               "threshold_percent": th.replicate_variation_warning_percent,
                               "definition": "100 * sample SD (ddof=1) / |mean| over replicates with a finite value",
                               "near_zero_mean_tolerance": th.replicate_variation_near_zero_mean}
        if n < 2:
            diags.append(Diagnostic(Severity.INFO, "replicate_variation_insufficient", f"Group {gname}: {metric}: insufficient replicates (n={n}) for SD",
                                    gid, gname, files, observed=obs, metric=metric))
            continue
        v = vals[finite]
        mean = float(np.mean(v))
        sd = float(np.std(v, ddof=1))
        obs.update({"mean": mean, "sample_sd": sd})
        if abs(mean) <= th.replicate_variation_near_zero_mean:
            obs["sd_percent_of_mean"] = None
            diags.append(Diagnostic(Severity.INFO, "replicate_variation_undefined", f"Group {gname}: {metric}: mean is near zero; percentage undefined (mean={mean:.3g}, SD={sd:.3g})",
                                    gid, gname, files, observed=obs, metric=metric))
            continue
        pct = 100.0 * sd / abs(mean)
        obs["sd_percent_of_mean"] = pct
        thr = th.replicate_variation_warning_percent
        if thr is not None and pct > thr:
            diags.append(Diagnostic(Severity.WARNING, "replicate_variation_high",
                                    f"Group {gname}: {metric} varies by {pct:.1f}% of |mean| across {n} replicates (threshold {thr}%)",
                                    gid, gname, files, observed=obs, expected=f"<= {thr}%", metric=metric,
                                    action="Check the listed replicates; no replicate is excluded automatically and the sample is not re-assigned."))
        else:
            diags.append(Diagnostic(Severity.INFO, "replicate_variation_report", f"Group {gname}: {metric}: mean={mean:.4g}, SD={sd:.3g}, {pct:.1f}%",
                                    gid, gname, files, observed=obs, metric=metric))
    return diags


import os  # noqa: E402  (used in replicate_variation)


def project_level_checks(project: Project) -> List[Diagnostic]:
    diags: List[Diagnostic] = []
    seen: Dict[str, str] = {}
    for m in project.measurements:
        if m.measurement_id in seen:
            diags.append(Diagnostic(Severity.ERROR, "duplicate_identifier", f"Duplicate measurement identifier {m.measurement_id}",
                                    files=[seen[m.measurement_id], m.path]))
        seen[m.measurement_id] = m.path
    for s in project.skipped:
        sev = Severity.INFO if "lock file" in s["reason"] else Severity.WARNING
        diags.append(Diagnostic(sev, "file_skipped_on_import", f"{os.path.basename(s['path'])}: {s['reason']}", files=[s["path"]]))
    return diags


def group_is_blocked(diags: Sequence[Diagnostic], group_id: str) -> bool:
    return any(d.severity == Severity.ERROR and d.group_id == group_id for d in diags)
