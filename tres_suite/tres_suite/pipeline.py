"""Orchestration: import -> validate -> analyse -> aggregate.  No file writing here.

``run_project(config)`` returns a :class:`RunResult`; :mod:`tres_suite.export`
writes it to disk and :mod:`tres_suite.plotting` draws from it.  A GUI can call
these three steps separately.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from .aggregate import align_trajectories, summarize_arrays, summarize_scalars
from .anisotropy import AnisotropyResult, compute_anisotropy, temperature_from_label
from .config import RunConfig
from .das import DasResult, compute_das
from .project import ConditionGroup, Measurement, Project
from .tdfs import TdfsResult, compute_tdfs
from .validation import (Diagnostic, Severity, compare_groups, group_is_blocked, project_level_checks,
                         replicate_variation, validate_group)

NON_METRIC_KEYS = {"measurement_id", "path", "file", "group_id", "group", "replicate", "kind"}


@dataclass
class ReplicateResult:
    measurement: Measurement
    das: Optional[DasResult] = None
    tdfs: Optional[TdfsResult] = None
    aniso: Optional[AnisotropyResult] = None
    scalars: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class GroupResult:
    group: ConditionGroup
    kind: str  # tres | anisotropy | mixed | empty
    status: str  # ok | blocked
    block_reasons: List[str] = field(default_factory=list)
    replicates: List[ReplicateResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    das_spectra: Optional[Dict[str, Any]] = None
    tdfs_trajectory: Optional[Dict[str, Any]] = None
    bubble: Optional[Dict[str, Any]] = None
    time_gated: Optional[Dict[str, Any]] = None  # advanced feature

    @property
    def n_replicates(self) -> int:
        return len([r for r in self.replicates if r.error is None])


@dataclass
class RunResult:
    config: RunConfig
    project: Project
    groups: List[GroupResult]
    diagnostics: List[Diagnostic]
    status: str  # completed | partially_completed | failed | cancelled
    started: float
    finished: float

    def group_by_id(self, gid: str) -> GroupResult:
        for g in self.groups:
            if g.group.group_id == gid:
                return g
        raise KeyError(gid)

    def ok_groups(self, kind: Optional[str] = None) -> List[GroupResult]:
        return [g for g in self.groups if g.status == "ok" and (kind is None or g.kind == kind)]

    def replicate_records(self, kind: str = "tres") -> List[Dict[str, Any]]:
        out = []
        for g in self.groups:
            if g.kind != kind:
                continue
            for r in g.replicates:
                out.append(dict(r.scalars, group_status=g.status))
        return out

    def summary_records(self, kind: str = "tres") -> List[Dict[str, Any]]:
        return [dict(g.summary) for g in self.groups if g.kind == kind and g.status == "ok"]


# ----------------------------------------------------------------------------
def build_project(cfg: RunConfig) -> Project:
    p = Project(cfg.project.level_names, cfg.project.replicate_level)
    for folder in cfg.project.import_folders:
        p.import_folder(folder, cfg.project.folder_depth)
    for fe in cfg.project.files:
        p.add_file(fe.path, fe.labels)
    return p


def _label_fields(m: Measurement, project: Project) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    for ln in project.level_names:
        lv = m.labels[ln]
        d[f"label:{ln}"] = lv.text
        if lv.number is not None:
            d[f"label:{ln}:number"] = lv.number
    return d


def analyse_replicate(m: Measurement, cfg: RunConfig) -> ReplicateResult:
    rr = ReplicateResult(m)
    wb = m.workbook
    try:
        if wb.kind == "tres":
            das = compute_das(wb, cfg.das)
            rr.das = das
            rr.scalars.update(das.scalar_record())
            rr.scalars["global_chi_sq"] = wb.global_chi_sq
            rr.scalars["max_wavelength_chi_sq"] = float(np.nanmax(wb.chi_sq_per_wavelength)) if np.any(np.isfinite(wb.chi_sq_per_wavelength)) else np.nan
            rr.scalars["wavelength_min_nm"] = wb.wavelength_min_nm
            rr.scalars["wavelength_max_nm"] = wb.wavelength_max_nm
            rr.scalars["n_wavelengths"] = wb.n_wavelengths
            if cfg.tdfs_enabled:
                td = compute_tdfs(wb.wavelengths_nm, das.lifetimes_ns, das.normalized_pre_exponential, das.fss_area_norm, cfg.tdfs, das.mean_lifetime_ns)
                rr.tdfs = td
                rr.scalars.update(td.scalar_record())
        elif wb.kind == "anisotropy":
            ws = cfg.wobble
            if ws.enabled and ws.temperature_level:
                ws = replace(ws, temperature_K=temperature_from_label(m.labels.get(ws.temperature_level), ws))
            an = compute_anisotropy(wb, ws)
            rr.aniso = an
            rr.scalars.update(an.scalar_record())
        else:  # pragma: no cover
            rr.error = f"unknown workbook kind {wb.kind}"
    except Exception as exc:
        rr.error = f"{exc.__class__.__name__}: {exc}"
        rr.scalars["analysis_error"] = rr.error
        rr.scalars["analysis_traceback"] = traceback.format_exc(limit=3)
    return rr


def _aggregate_tres_group(gr: GroupResult, cfg: RunConfig) -> None:
    reps = [r for r in gr.replicates if r.error is None and r.das is not None]
    if not reps:
        return
    wl = reps[0].das.wavelengths_nm
    n_comp = reps[0].das.n_components
    em = summarize_arrays([r.das.emission for r in reps])
    npe = summarize_arrays([r.das.normalized_pre_exponential for r in reps])
    tot = summarize_arrays([r.das.emission_total for r in reps])
    fss = summarize_arrays([r.das.fss_norm_max for r in reps])
    gr.das_spectra = {"wavelengths_nm": wl, "n_components": n_comp, "n_replicates": len(reps),
                      "emission_mean": em["mean"], "emission_std": em["std"], "emission_n": em["n"],
                      "npe_mean": npe["mean"], "npe_std": npe["std"],
                      "total_mean": tot["mean"], "total_std": tot["std"],
                      "fss_norm_mean": fss["mean"], "fss_norm_std": fss["std"],
                      "lifetimes_mean": np.mean([r.das.lifetimes_ns for r in reps], axis=0),
                      "lifetimes_std": np.std([r.das.lifetimes_ns for r in reps], axis=0, ddof=1) if len(reps) > 1 else np.full(n_comp, np.nan)}
    # bubble: per-replicate statistics (primary) and legacy mean-spectrum variant
    from .das import peak_center_quadratic
    order = np.argsort(wl)
    trap = getattr(np, "trapezoid", None) or np.trapz  # type: ignore[attr-defined]
    w_mean = np.array([float(trap(em["mean"][order, j], wl[order])) for j in range(n_comp)])
    comps = []
    for j in range(n_comp):
        taus = np.array([r.das.lifetimes_ns[j] for r in reps])
        pk = np.array([r.das.peak_position_nm[j] for r in reps])
        ar = np.array([r.das.area_percent[j] for r in reps])
        comps.append({"component": j + 1,
                      "lifetime_ns_mean": float(np.mean(taus)), "lifetime_ns_std": float(np.std(taus, ddof=1)) if len(reps) > 1 else np.nan,
                      "peak_nm_mean": float(np.nanmean(pk)), "peak_nm_std": float(np.nanstd(pk, ddof=1)) if len(reps) > 1 else np.nan,
                      "area_percent_mean": float(np.nanmean(ar)), "area_percent_std": float(np.nanstd(ar, ddof=1)) if len(reps) > 1 else np.nan,
                      "n": len(reps),
                      "peak_nm_from_mean_spectrum": peak_center_quadratic(wl, em["mean"][:, j]),
                      "area_percent_from_mean_spectrum": 100.0 * w_mean[j] / w_mean.sum() if w_mean.sum() > 0 else np.nan,
                      "region": None})
    gr.bubble = {"components": comps, "peak_method": reps[0].das.peak_method,
                 "region_note": "region/category assignment unavailable: regions.npz was not supplied with the legacy scripts"}
    # TDFS trajectories
    tds = [r.tdfs for r in reps if r.tdfs is not None]
    if tds:
        t_c, pk_m, pk_s, n = align_trajectories([t.traj_t_ns for t in tds], [t.traj_peak_cm1 for t in tds])
        _, com_m, com_s, _ = align_trajectories([t.traj_t_ns for t in tds], [t.traj_com_cm1 for t in tds], t_c)
        _, fw_m, fw_s, _ = align_trajectories([t.traj_t_ns for t in tds], [t.traj_fwhm_cm1 for t in tds], t_c)
        _, cp_m, cp_s, _ = align_trajectories([t.traj_t_ns for t in tds], [t.traj_c_peak for t in tds], t_c)
        _, cc_m, cc_s, _ = align_trajectories([t.traj_t_ns for t in tds], [t.traj_c_com for t in tds], t_c)
        gr.tdfs_trajectory = {"t_ns": t_c, "n": n, "peak_cm-1_mean": pk_m, "peak_cm-1_std": pk_s, "com_cm-1_mean": com_m, "com_cm-1_std": com_s,
                              "fwhm_cm-1_mean": fw_m, "fwhm_cm-1_std": fw_s, "C_peak_mean": cp_m, "C_peak_std": cp_s, "C_com_mean": cc_m, "C_com_std": cc_s,
                              "averaging_order": "per-replicate trajectory first (each from its own reconstruction and its own nu_inf/nu_0), then point-wise mean and sample SD on the common time grid (intersection of replicate windows, no extrapolation)"}


def _tdfs_notes(g: ConditionGroup, gr: GroupResult, cfg: RunConfig) -> List[Diagnostic]:
    """Warnings that accompany TDFS values: apparent nu0 (no user value) and boundary-pinned peaks."""
    out: List[Diagnostic] = []
    files = [r.measurement.path for r in gr.replicates]
    if cfg.tdfs.nu0_cm1 is None:
        out.append(Diagnostic(Severity.WARNING, "tdfs_nu0_apparent",
                              f"Group {g.name}: no user-supplied nu0; peak Delta-nu and tau_r are APPARENT values referenced to the first reconstructed "
                              f"spectrum at t >= {cfg.tdfs.metric_tmin_ns:g} ns, not to a time-zero estimate",
                              g.group_id, g.name, files, observed={"nu0_source": "apparent", "peak_nu0_cm-1": [r.scalars.get("peak_nu0_cm-1") for r in gr.replicates]},
                              expected="a probe-specific time-zero peak frequency in cm^-1 (tdfs.nu0_cm1), e.g. a literature value",
                              action="Supply tdfs.nu0_cm1 to obtain values referenced to an estimated time-zero spectrum; otherwise treat Delta-nu and tau_r as finite-window apparent quantities."))
    bf = {r.measurement.filename: r.scalars.get("peak_at_boundary_fraction") for r in gr.replicates}
    if any(v is not None and np.isfinite(v) and v > 0 for v in bf.values()):
        out.append(Diagnostic(Severity.INFO, "tdfs_peak_at_acquisition_boundary",
                              f"Group {g.name}: the reconstructed spectral maximum sits at the wavelength-range edge for part of the usable window",
                              g.group_id, g.name, files, observed={"peak_at_boundary_fraction": bf},
                              expected="user judgement: peak-based Delta-nu/tau_r are numerically fragile when the maximum is pinned to the acquisition boundary",
                              action="Decide for your probe/experiment whether peak metrics are meaningful here; COM metrics are exported alongside."))
    return out


class RunCancelled(Exception):
    """Raised inside :func:`run_project` when ``should_cancel()`` returns true."""


def _analyse_pair(args):
    m, cfg = args
    return analyse_replicate(m, cfg)


def run_project(cfg: RunConfig, progress: Optional[Callable[[str], None]] = None,
                file_progress: Optional[Callable[[int, int, str], None]] = None,
                should_cancel: Optional[Callable[[], bool]] = None) -> RunResult:
    """Import, validate, analyse and aggregate.

    ``progress(message)`` receives human-readable stage messages; ``file_progress(done, total, stage)``
    receives per-workbook counts (``stage`` is ``"loading"`` or ``"analysing"``); ``should_cancel()`` is polled
    between workbooks and raises :class:`RunCancelled` when it returns true.  With ``project.workers > 1``
    both parsing and the per-replicate analysis run in parallel processes (results are identical).
    """
    started = time.time()
    log = progress or (lambda s: None)
    fp = file_progress or (lambda d, t, st: None)
    cancel = should_cancel or (lambda: False)
    project = build_project(cfg)
    diags: List[Diagnostic] = project_level_checks(project)
    n_files = len(project.measurements)
    log(f"loading {n_files} workbooks")

    def _load_progress(k, n, m):
        fp(k, n, "loading")
        if cancel():
            raise RunCancelled()

    project.load_all(progress=_load_progress, workers=cfg.project.workers)
    if cancel():
        raise RunCancelled()
    # per-replicate analysis (optionally in parallel; each replicate is independent of every other)
    analysed: Dict[str, ReplicateResult] = {}
    todo = [m for g in project.groups() if not group_is_blocked(validate_group(g, cfg.validation), g.group_id) for m in g.loaded()]
    fp(0, len(todo), "analysing")
    if cfg.project.workers and cfg.project.workers > 1 and len(todo) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=int(cfg.project.workers)) as ex:
            for k, rr in enumerate(ex.map(_analyse_pair, [(m, cfg) for m in todo], chunksize=1), start=1):
                analysed[rr.measurement.measurement_id] = rr
                fp(k, len(todo), "analysing")
                if cancel():
                    ex.shutdown(cancel_futures=True)
                    raise RunCancelled()
    groups: List[GroupResult] = []
    k_done = 0
    for g in project.groups():
        gd = validate_group(g, cfg.validation)
        diags.extend(gd)
        kinds = {m.workbook.kind for m in g.loaded()}
        kind = "mixed" if len(kinds) > 1 else (next(iter(kinds)) if kinds else "empty")
        gr = GroupResult(g, kind, "ok")
        if group_is_blocked(gd, g.group_id):
            gr.status = "blocked"
            gr.block_reasons = [d.rule for d in gd if d.severity == Severity.ERROR]
            groups.append(gr)
            continue
        log(f"analysing {g.name} ({len(g.loaded())} files)")
        for m in g.loaded():
            rr = analysed.get(m.measurement_id)
            if rr is not None:
                rr.measurement = m  # keep the project's own Measurement object (the pool returned a pickled copy)
            else:
                if cancel():
                    raise RunCancelled()
                rr = analyse_replicate(m, cfg)
                k_done += 1
                fp(k_done, len(todo), "analysing")
            gr.replicates.append(rr)
        failed = [r for r in gr.replicates if r.error is not None]
        for r in failed:
            diags.append(Diagnostic(Severity.ERROR, "analysis_failed", f"{r.measurement.filename}: {r.error}", g.group_id, g.name,
                                    [r.measurement.path], action="Inspect the workbook; the group is blocked because a replicate could not be analysed."))
        if failed:
            gr.status = "blocked"
            gr.block_reasons = ["analysis_failed"]
            groups.append(gr)
            continue
        # scalar records with identifiers/labels
        for i, r in enumerate(gr.replicates, start=1):
            base = {"measurement_id": r.measurement.measurement_id, "path": r.measurement.path, "file": r.measurement.filename,
                    "group_id": g.group_id, "group": g.name, "replicate": r.measurement.label_text(project.replicate_level),
                    "replicate_index": i, "kind": kind}
            base.update(_label_fields(r.measurement, project))
            r.scalars = {**base, **r.scalars}
        if kind == "tres" and cfg.tdfs_enabled:
            diags.extend(_tdfs_notes(g, gr, cfg))
        # Case 5 replicate variation (warnings only)
        diags.extend(replicate_variation(g, [r.scalars for r in gr.replicates], cfg.validation))
        summ = summarize_scalars([r.scalars for r in gr.replicates], exclude=list(NON_METRIC_KEYS) + ["replicate_index"])
        head = {"group_id": g.group_id, "group": g.name, "kind": kind, "n_replicates": len(gr.replicates)}
        head.update({k: v for k, v in gr.replicates[0].scalars.items() if k.startswith("label:")})
        gr.summary = {**head, **summ}
        if kind == "tres":
            _aggregate_tres_group(gr, cfg)
            if cfg.time_gated.enabled:
                from .advanced.time_gated import analyse_time_gated
                try:
                    gr.time_gated = analyse_time_gated([r.measurement.path for r in gr.replicates], cfg.time_gated)
                except Exception as exc:
                    diags.append(Diagnostic(Severity.WARNING, "time_gated_unavailable", f"Group {g.name}: time-gated analysis skipped: {exc}",
                                            g.group_id, g.name, [r.measurement.path for r in gr.replicates],
                                            action="Time-gated spectra need the raw 'Data' sheet with identical wavelengths in every replicate."))
        groups.append(gr)
    diags.extend(compare_groups([gr.group for gr in groups if gr.status == "ok"], cfg.validation))
    n_blocked = sum(1 for gr in groups if gr.status == "blocked")
    if not groups or n_blocked == len(groups):
        status = "failed"
    elif n_blocked:
        status = "partially_completed"
    else:
        status = "completed"
    return RunResult(cfg, project, groups, diags, status, started, time.time())
