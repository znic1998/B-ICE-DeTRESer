"""Reusable plot functions.  Every plot writes its image(s) and the exact plotted values.

All functions take a :class:`RunResult` plus a :class:`PlotConfig` and return a
:class:`PlotOutput` holding the data table that was drawn (x, y, SD, n, series
label, units, fit curve, bubble attributes).  Replicate SD is drawn as error
bars or bands where available; ``n`` is stated in the legend.  Fitting
uncertainty (``sigma`` of the EzTime lifetimes) is never mixed with replicate SD.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg", force=False)  # a GUI that already chose a backend keeps it; figures are saved through Agg either way
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import PlotConfig, SeriesConfig  # noqa: E402
from .export import safe_name, unit_of, write_json  # noqa: E402
from .pipeline import GroupResult, RunResult  # noqa: E402
from .project import LabelValue  # noqa: E402
from .stats import linear_fit  # noqa: E402

DEFAULT_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#000000"]
DEFAULT_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]

AXIS_LABELS = {
    "gp": "Generalized polarization [-]", "tmean_ns": r"$\langle\tau\rangle$ [ns]",
    "peak_delta_nu_cm-1": r"$\Delta\nu_{peak}$ [cm$^{-1}$]", "peak_tau_r_ns": r"$\tau_{r,peak}$ [ns]",
    "com_delta_nu_cm-1": r"$\Delta\nu_{COM}$ [cm$^{-1}$]", "com_tau_r_ns": r"$\tau_{r,COM}$ [ns]",
    "tau_fwhm_ns": r"$\tau_{FWHM}$ [ns]", "phi_mean_ns": r"$\langle\phi\rangle$ [ns]", "r_inf": r"$r_\infty$ [-]",
    "wobble_eta_poise": r"$\eta$ [P]",
}


@dataclass
class PlotOutput:
    name: str
    files: List[str] = field(default_factory=list)
    data: Optional[pd.DataFrame] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def as_manifest(self) -> Dict[str, Any]:
        return {"name": self.name, "files": self.files, "description": self.description}


def _axis_label(key: Optional[str], override: Optional[str], project) -> str:
    if override:
        return override
    if key is None:
        return ""
    if key in project.level_names:
        return key
    return AXIS_LABELS.get(key, f"{key} [{unit_of(key) or '-'}]")


def _style(i: int, s: Optional[SeriesConfig]):
    color = (s.color if s and s.color else DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
    if isinstance(color, int):
        color = DEFAULT_COLORS[color % len(DEFAULT_COLORS)]
    marker = (s.marker if s and s.marker else DEFAULT_MARKERS[i % len(DEFAULT_MARKERS)])
    return color, marker


def select_groups(result: RunResult, select: Optional[Dict[str, Any]], kind: str = "tres") -> List[GroupResult]:
    out = []
    for g in result.ok_groups(kind):
        ok = True
        for level, wanted in (select or {}).items():
            wl = list(wanted) if isinstance(wanted, (list, tuple, set)) else [wanted]
            have = g.summary.get(f"label:{level}")
            hv = LabelValue.parse(have) if have is not None else None
            hit = any(hv is not None and (LabelValue.parse(str(w)).text == hv.text or
                                          (LabelValue.parse(str(w)).number is not None and hv.number is not None and LabelValue.parse(str(w)).number == hv.number)) for w in wl)
            if not hit:
                ok = False
                break
        if ok:
            out.append(g)
    return out


FIGSIZES = {"bubble": (5.5, 4.5), "stacked_area_bar": (7, 3.5)}


@dataclass
class DrawResult:
    """What :func:`draw_plot` drew on an axes: the exact plotted values plus axis keys (for a GUI canvas)."""
    data: pd.DataFrame
    meta: Dict[str, Any]
    x_key: Optional[str]
    y_key: Optional[str]


def apply_axes(ax, pc: PlotConfig, result: RunResult, x_key, y_key) -> None:
    """Axis titles, limits, title, ticks and legend from the PlotConfig (blank limits = automatic)."""
    ax.set_xlabel(_axis_label(x_key, pc.x_label, result.project))
    ax.set_ylabel(_axis_label(y_key, pc.y_label, result.project))
    if pc.x_limits:
        ax.set_xlim(*pc.x_limits)
    if pc.y_limits:
        ax.set_ylim(*pc.y_limits)
    if pc.title:
        ax.set_title(pc.title)
    ax.tick_params(direction="in", which="both")
    if ax.get_legend() is None and ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, fontsize=9)


def draw_plot(result: RunResult, pc: PlotConfig, ax) -> DrawResult:
    """Draw ``pc`` on an existing matplotlib axes (no file writing).  Used by the GUI; :func:`render_plots` uses it too."""
    fn = DRAW_FUNCTIONS.get(pc.type)
    if fn is None:
        raise ValueError(f"unknown plot type {pc.type!r}; known: {sorted(DRAW_FUNCTIONS)}")
    data, meta, xk, yk = fn(result, pc, ax)
    apply_axes(ax, pc, result, xk, yk)
    return DrawResult(data, meta, xk, yk)


def _finish(fig, ax, pc: PlotConfig, out_dir: str, result: RunResult, data: pd.DataFrame, meta: Dict[str, Any], x_key, y_key) -> PlotOutput:
    apply_axes(ax, pc, result, x_key, y_key)
    fig.tight_layout()
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, safe_name(pc.name))
    files = []
    for fmt in result.config.output.image_formats:
        p = f"{stem}.{fmt}"
        fig.savefig(p, dpi=result.config.output.dpi)
        files.append(p)
    plt.close(fig)
    data.to_csv(f"{stem}_data.csv", index=False, float_format="%.17g")
    files.append(f"{stem}_data.csv")
    meta = dict(meta, plot=pc.name, type=pc.type, x=x_key, y=y_key, x_unit=unit_of(x_key or ""), y_unit=unit_of(y_key or ""),
                x_label=_axis_label(x_key, pc.x_label, result.project), y_label=_axis_label(y_key, pc.y_label, result.project),
                x_limits=pc.x_limits, y_limits=pc.y_limits, image_formats=list(result.config.output.image_formats))
    write_json(f"{stem}_meta.json", meta)
    files.append(f"{stem}_meta.json")
    return PlotOutput(pc.name, files, data, meta, description=f"{pc.type}: {y_key} vs {x_key}")


# ----------------------------------------------------------------------------
def draw_metric_comparison(result: RunResult, pc: PlotConfig, ax):
    """metric_vs_label (x = a hierarchy label, numeric) or metric_vs_metric (SD on both axes)."""
    kind = pc.extra.get("kind", "tres")
    x_is_label = pc.type == "metric_vs_label"
    transpose = bool(x_is_label and pc.extra.get("label_axis") == "y")  # label on the y axis, metric on the x axis
    rows = []
    fits = {}
    series = pc.series or [SeriesConfig(label="all groups")]
    for i, s in enumerate(series):
        color, marker = _style(i, s)
        groups = select_groups(result, s.select, kind)
        xs, ys, xe, ye, ns, names = [], [], [], [], [], []
        for g in groups:
            if x_is_label:
                lv = LabelValue.parse(g.summary.get(f"label:{pc.x}", ""))
                if lv.number is None:
                    continue
                x, xsd = lv.number, np.nan
            else:
                x, xsd = g.summary.get(f"{pc.x}_mean", np.nan), g.summary.get(f"{pc.x}_std", np.nan)
            y, ysd, n = g.summary.get(f"{pc.y}_mean", np.nan), g.summary.get(f"{pc.y}_std", np.nan), g.summary.get(f"{pc.y}_n", 0)
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            xs.append(x); ys.append(y); xe.append(xsd); ye.append(ysd); ns.append(n); names.append(g.group.name)
            rows.append({"series": s.label, "group_id": g.group.group_id, "group": g.group.name, "x": x, "x_sd": xsd, "y": y, "y_sd": ysd, "n": n})
        if not xs:
            continue
        order = np.argsort(xs)
        xs, ys = np.array(xs)[order], np.array(ys)[order]
        xe, ye = np.array(xe, float)[order], np.array(ye, float)[order]
        n_txt = f"n={min(ns)}" if min(ns) == max(ns) else f"n={min(ns)}-{max(ns)}"
        px, py, pxe, pye = (ys, xs, ye, xe) if transpose else (xs, ys, xe, ye)
        ax.errorbar(px, py, yerr=(pye if (pc.error_bars and (transpose or True) and np.any(np.isfinite(pye))) else None),
                    xerr=(pxe if (pc.error_bars and np.any(np.isfinite(pxe))) else None),
                    fmt=marker, color=color, ecolor=color, capsize=2, elinewidth=0.8, markersize=5, ls="-" if x_is_label else "none", lw=0.8,
                    label=f"{s.label} ({n_txt})")
        if pc.fit:
            f = linear_fit(px, py)
            fits[s.label] = f.to_dict()
            if f.available:
                xx = np.linspace(px.min(), px.max(), 50)
                ax.plot(xx, f.predict(xx), color=color, ls="--", lw=1, label=f"{s.label} fit R²={f.r_squared:.3f}")
                for a, b in zip(xx, f.predict(xx)):
                    rows.append({"series": s.label + " (fit)", "x": a, "y": b})
    data = pd.DataFrame(rows)
    if transpose and len(data):
        data = data.rename(columns={"x": "y", "y": "x", "x_sd": "y_sd", "y_sd": "x_sd"})
    meta = {"fits": fits, "error_bar": "replicate sample SD (ddof=1); n per point in the data table",
            "label_axis": ("y" if transpose else "x") if x_is_label else None}
    return data, meta, (pc.y if transpose else pc.x), (pc.x if transpose else pc.y)


def draw_das_spectra(result: RunResult, pc: PlotConfig, ax):
    groups = select_groups(result, pc.group or (pc.series[0].select if pc.series else {}))
    if not groups:
        raise ValueError(f"plot {pc.name}: no analysed TRES group matches {pc.group}")
    g = groups[0]
    sp = g.das_spectra
    wl = sp["wavelengths_nm"]
    n = sp["n_components"]
    rows = []
    npe = pc.representation == "normalized_pre_exponential"
    for j in range(n):
        y = sp["npe_mean"][:, j] if npe else sp["emission_mean"][:, j]
        sd = sp["npe_std"][:, j] if npe else sp["emission_std"][:, j]
        color, _ = _style(j, None)
        lab = rf"$\tau_{j + 1}$ = {sp['lifetimes_mean'][j]:.2f} ± {sp['lifetimes_std'][j]:.2f} ns" if np.isfinite(sp['lifetimes_std'][j]) else rf"$\tau_{j + 1}$ = {sp['lifetimes_mean'][j]:.2f} ns"
        ax.plot(wl, y, color=color, label=lab)
        if pc.error_bars and np.any(np.isfinite(sd)):
            ax.fill_between(wl, y - sd, y + sd, color=color, alpha=0.15, lw=0)
        for w, a, b in zip(wl, y, sd):
            rows.append({"series": f"tau{j + 1}", "lifetime_ns_mean": sp["lifetimes_mean"][j], "wavelength_nm": w, "y": a, "y_sd": b, "n": sp["n_replicates"]})
    if not npe:
        ax.plot(wl, sp["total_mean"], color="k", label="total")
        if pc.error_bars:
            ax.fill_between(wl, sp["total_mean"] - sp["total_std"], sp["total_mean"] + sp["total_std"], color="k", alpha=0.1, lw=0)
        for w, a, b in zip(wl, sp["total_mean"], sp["total_std"]):
            rows.append({"series": "total", "wavelength_nm": w, "y": a, "y_sd": b, "n": sp["n_replicates"]})
        ax.set_ylim(bottom=0)
    else:
        ax.axhline(0, color="k", lw=1)
    ax.set_xlim(wl.min(), wl.max())
    ax.set_title(pc.title or f"{g.group.name} (n={sp['n_replicates']})")
    pc.title = ax.get_title()
    ykey = "normalized_pre_exponential" if npe else "das_emission"
    if not pc.y_label:
        pc.y_label = "Normalized amplitude [-]" if npe else "Normalized intensity [-]"
    if not pc.x_label:
        pc.x_label = "Wavelength [nm]"
    return pd.DataFrame(rows), {"group": g.group.name, "representation": pc.representation}, "wavelength_nm", ykey


def draw_bubble(result: RunResult, pc: PlotConfig, ax):
    series = pc.series or [SeriesConfig(label="group", select=pc.group or {})]
    rows = []
    handles = []
    scale = float(pc.extra.get("bubble_size_scale", 40.0))
    for i, s in enumerate(series):
        groups = select_groups(result, s.select)
        for g in groups:
            color, marker = _style(i, s)
            comps = g.bubble["components"]
            x = np.array([c["lifetime_ns_mean"] for c in comps]); y = np.array([c["peak_nm_mean"] for c in comps])
            a = np.array([c["area_percent_mean"] for c in comps])
            ax.scatter(x, y, s=a * scale, facecolors=color, alpha=0.35, edgecolors=color, lw=1.2)
            # legend entry with a fixed-size marker (a scatter handle would draw a bubble at data size, i.e. a fake 4th bubble)
            from matplotlib.lines import Line2D
            handles.append(Line2D([], [], marker=marker if marker in "osD^v" else "o", ls="", ms=8, mfc=color, mec=color, alpha=0.6,
                                  label=f"{s.label if len(groups) == 1 else g.group.name} (n={comps[0]['n']})"))
            if pc.error_bars:
                ax.errorbar(x, y, xerr=[c["lifetime_ns_std"] for c in comps], yerr=[c["peak_nm_std"] for c in comps], fmt="none", ecolor="k", elinewidth=0.6, capsize=2)
            ax.scatter(x, y, c="k", s=3)
            for c in comps:
                rows.append({"series": s.label, "group": g.group.name, "component": c["component"], "lifetime_ns": c["lifetime_ns_mean"], "lifetime_ns_sd": c["lifetime_ns_std"],
                             "peak_nm": c["peak_nm_mean"], "peak_nm_sd": c["peak_nm_std"], "area_percent": c["area_percent_mean"], "area_percent_sd": c["area_percent_std"],
                             "marker_size_pt2": c["area_percent_mean"] * scale, "n": c["n"], "region": c["region"]})
    ax.grid(ls="--", alpha=0.3)
    if handles:
        ax.legend(handles=handles, frameon=False, fontsize=9)
    if not pc.x_limits:
        ax.set_xlim(0, max(8.0, float(np.nanmax([r["lifetime_ns"] for r in rows])) * 1.15) if rows else 8.0)
    if not pc.y_limits and rows:
        ys = np.array([r["peak_nm"] for r in rows], float)
        ax.set_ylim(min(410.0, np.nanmin(ys) - 10), max(540.0, np.nanmax(ys) + 10))
    pc.x_label = pc.x_label or "Lifetime [ns]"
    pc.y_label = pc.y_label or "Peak position [nm]"
    return pd.DataFrame(rows), {"bubble_size": f"area_percent * {scale} pt^2", "region": "unassigned (regions.npz not supplied)"}, "lifetime_ns", "peak_nm"


def draw_tdfs_spectra(result: RunResult, pc: PlotConfig, ax):
    groups = select_groups(result, pc.group or (pc.series[0].select if pc.series else {}))
    if not groups:
        raise ValueError(f"plot {pc.name}: no analysed TRES group matches {pc.group}")
    g = groups[0]
    reps = [r for r in g.replicates if r.tdfs is not None]
    if not reps:
        raise ValueError(f"plot {pc.name}: TDFS not computed for {g.group.name}")
    times = list(pc.times_ns or result.config.tdfs.export_times_ns)
    wl = reps[0].tdfs.wavelengths_nm
    order = np.argsort(wl)
    trap = getattr(np, "trapezoid", None) or np.trapz  # type: ignore[attr-defined]
    normalise = pc.extra.get("normalise", "area")  # area | none
    cmap = plt.get_cmap("viridis")
    rows = []
    tmax_all = min(r.tdfs.t_ns[-1] for r in reps)
    times = [t for t in times if t <= tmax_all]
    for k, t in enumerate(times):
        specs = []
        for r in reps:
            s = r.tdfs.spectrum_at(t)
            if normalise == "area":
                a = float(trap(s[order], wl[order]))
                s = s / a if a != 0 else np.full_like(s, np.nan)
            specs.append(s)
        arr = np.array(specs)
        m = np.nanmean(arr, axis=0)
        sd = np.nanstd(arr, axis=0, ddof=1) if len(reps) > 1 else np.full_like(m, np.nan)
        color = cmap(k / max(len(times) - 1, 1))
        ax.plot(wl, m, color=color, label=f"{t:g} ns")
        if pc.error_bars and len(reps) > 1:
            ax.fill_between(wl, m - sd, m + sd, color=color, alpha=0.12, lw=0)
        for w, a, b in zip(wl, m, sd):
            rows.append({"series": f"t={t:g} ns", "time_ns": t, "wavelength_nm": w, "y": a, "y_sd": b, "n": len(reps)})
    ax.set_xlim(wl.min(), wl.max())
    ax.set_title(pc.title or f"{g.group.name}: reconstructed spectra (n={len(reps)})")
    pc.title = ax.get_title()
    pc.x_label = pc.x_label or "Wavelength [nm]"
    pc.y_label = pc.y_label or ("Area-normalised intensity [-]" if normalise == "area" else "Reconstructed intensity [-]")
    return pd.DataFrame(rows), {"group": g.group.name, "normalisation": normalise, "averaging": "replicate reconstructions averaged point-wise at each time"}, "wavelength_nm", "reconstructed_intensity"


def draw_tdfs_trajectory(result: RunResult, pc: PlotConfig, ax):
    """tdfs_peak_vs_time (ν(t) of peak or COM) or tdfs_relaxation (C(t))."""
    coord = pc.coordinate
    relax = pc.type == "tdfs_relaxation"
    fwhm = pc.type == "tdfs_fwhm_vs_time"
    key = "fwhm_cm-1" if fwhm else (("C_peak" if coord == "peak" else "C_com") if relax else f"{coord}_cm-1")
    series = pc.series or [SeriesConfig(label="group", select=pc.group or {})]
    rows = []
    i = 0
    for s in series:
        for g in select_groups(result, s.select):
            tr = g.tdfs_trajectory
            if tr is None:
                continue
            color, _ = _style(i, s)
            i += 1
            t, m, sd, n = tr["t_ns"], tr[f"{key}_mean"], tr[f"{key}_std"], tr["n"]
            lab = s.label if len(series) > 1 and len(select_groups(result, s.select)) == 1 else g.group.name
            ax.plot(t, m, color=color, label=f"{lab} (n={int(np.nanmax(n))})")
            if pc.error_bars:
                ax.fill_between(t, m - sd, m + sd, color=color, alpha=0.15, lw=0)
            for a, b, c, d in zip(t, m, sd, n):
                rows.append({"series": lab, "group": g.group.name, "time_ns": a, "y": b, "y_sd": c, "n": d})
    if relax:
        ax.axhline(0, color="gray", ls="--", lw=0.8)
    if pc.extra.get("log_x"):
        ax.set_xscale("log")
    pc.x_label = pc.x_label or "Time [ns]"
    pc.y_label = pc.y_label or ("FWHM [cm$^{-1}$]" if fwhm else (f"C(t) [{coord}]" if relax else (r"$\nu_{peak}$ [cm$^{-1}$]" if coord == "peak" else r"$\nu_{COM}$ [cm$^{-1}$]")))
    return pd.DataFrame(rows), {"coordinate": coord, "band": "replicate SD of the point-wise mean trajectory"}, "time_ns", key


def draw_steady_state_spectrum(result: RunResult, pc: PlotConfig, ax):
    """Pseudo steady-state emission spectrum (total photon counts per wavelength, normalised to its maximum), replicate mean ± SD."""
    series = pc.series or [SeriesConfig(label="group", select=pc.group or {})]
    rows = []
    i = 0
    for s in series:
        for g in select_groups(result, s.select):
            sp = g.das_spectra
            if sp is None:
                continue
            color, _ = _style(i, s)
            i += 1
            wl, m, sd = sp["wavelengths_nm"], sp["fss_norm_mean"], sp["fss_norm_std"]
            lab = s.label if len(series) > 1 and len(select_groups(result, s.select)) == 1 else g.group.name
            ax.plot(wl, m, color=color, label=f"{lab} (n={sp['n_replicates']})")
            if pc.error_bars and np.any(np.isfinite(sd)):
                ax.fill_between(wl, m - sd, m + sd, color=color, alpha=0.15, lw=0)
            for w, a, b in zip(wl, m, sd):
                rows.append({"series": lab, "group": g.group.name, "wavelength_nm": w, "y": a, "y_sd": b, "n": sp["n_replicates"]})
    ax.set_ylim(bottom=0)
    pc.x_label = pc.x_label or "Wavelength [nm]"
    pc.y_label = pc.y_label or "Normalized intensity [-]"
    return pd.DataFrame(rows), {"source": "total photon counts per wavelength (pseudo steady-state spectrum), normalised to its maximum per replicate, then averaged"}, "wavelength_nm", "fss_norm"


def draw_stacked_area_bar(result: RunResult, pc: PlotConfig, ax):
    """Horizontal stacked bars of DAS area percent per lifetime component, one bar per group (no region classes)."""
    series = pc.series or [SeriesConfig(label="all groups")]
    groups = []
    for s in series:
        groups += [g for g in select_groups(result, s.select) if g not in groups]
    rows = []
    labels = [g.group.name for g in groups]
    n_max = max((len(g.bubble["components"]) for g in groups), default=0)
    left = np.zeros(len(groups))
    from matplotlib.patches import Patch
    handles = []
    for j in range(n_max):
        vals = np.array([g.bubble["components"][j]["area_percent_mean"] if j < len(g.bubble["components"]) else 0.0 for g in groups])
        sds = np.array([g.bubble["components"][j]["area_percent_std"] if j < len(g.bubble["components"]) else np.nan for g in groups])
        color, _ = _style(j, None)
        bars = ax.barh(labels, vals, left=left, color=color, edgecolor="white")
        handles.append(Patch(facecolor=color, label=rf"$\tau_{j + 1}$"))
        ax.bar_label(bars, [f"{v:.0f}%" if v > 4 else "" for v in vals], label_type="center", color="white", fontsize=8)
        for g, v, sd, l in zip(groups, vals, sds, left):
            rows.append({"group": g.group.name, "component": j + 1, "lifetime_ns": g.bubble["components"][j]["lifetime_ns_mean"] if j < len(g.bubble["components"]) else np.nan,
                         "area_percent": v, "area_percent_sd": sd, "bar_start": l, "n": g.bubble["components"][0]["n"]})
        left = left + vals
    ax.set_xlim(0, 100)
    ax.invert_yaxis()
    ax.legend(handles=handles, frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    pc.x_label = pc.x_label or "DAS area [%]"
    pc.y_label = pc.y_label or ""
    return pd.DataFrame(rows), {"stack": "area percent per lifetime component (replicate mean); SD in data table"}, "area_percent", "group"


DRAW_FUNCTIONS = {
    "metric_vs_label": draw_metric_comparison, "metric_vs_metric": draw_metric_comparison,
    "das_spectra": draw_das_spectra, "bubble": draw_bubble, "tdfs_spectra": draw_tdfs_spectra,
    "tdfs_peak_vs_time": draw_tdfs_trajectory, "tdfs_relaxation": draw_tdfs_trajectory, "tdfs_fwhm_vs_time": draw_tdfs_trajectory,
    "stacked_area_bar": draw_stacked_area_bar, "steady_state_spectrum": draw_steady_state_spectrum,
}


def figure_size(pc: PlotConfig, result: RunResult) -> tuple:
    fs = pc.extra.get("figsize")
    if fs and len(fs) == 2:
        return (float(fs[0]), float(fs[1]))
    if pc.type == "stacked_area_bar":
        n = 0
        for s in (pc.series or [SeriesConfig(label="all groups")]):
            n += len(select_groups(result, s.select))
        return (7, max(2.5, 0.45 * n + 1))
    return FIGSIZES.get(pc.type, (5.5, 4.2))


def render_plot(result: RunResult, pc: PlotConfig, out_dir: str) -> PlotOutput:
    """Draw ``pc`` on a fresh figure and write image(s), the plotted data table and metadata."""
    fig, ax = plt.subplots(figsize=figure_size(pc, result))
    fn = DRAW_FUNCTIONS.get(pc.type)
    if fn is None:
        plt.close(fig)
        raise ValueError(f"unknown plot type {pc.type!r}; known: {sorted(DRAW_FUNCTIONS)}")
    data, meta, xk, yk = fn(result, pc, ax)
    return _finish(fig, ax, pc, out_dir, result, data, meta, xk, yk)


PLOT_FUNCTIONS = {k: render_plot for k in DRAW_FUNCTIONS}


def render_plots(result: RunResult, out_dir: str, plots: Optional[Sequence[PlotConfig]] = None) -> List[PlotOutput]:
    outs: List[PlotOutput] = []
    for pc in (plots if plots is not None else result.config.plots):
        outs.append(render_plot(result, pc, out_dir))
    return outs
