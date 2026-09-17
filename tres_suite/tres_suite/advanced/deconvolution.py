"""Terminal-driven log-normal deconvolution review (advanced CLI feature).

Reuses the ``fitter()`` / ``deconvol()`` workflow of ``tres1.py``: for each DAS
component curve of a condition group the user previews the fit, edits the
peak count / bounds, refits, accepts and exports.  The numerical work is in
:mod:`tres_suite.lognormal` (``fit_component``); this module only drives the
interaction, so a GUI can call the same functions with its own prompts.

Reproducibility: every accepted fit (peak count, bounds, resulting parameters)
is written to ``deconvolution_decisions.json`` in the output folder.  Passing
that file back with ``--replay`` reproduces the exports without prompts.
Region classification is not required and not performed.

Inputs are a finished run's ``groups/<group>/das_spectra.csv`` files
(replicate-mean DAS emission per component), so no workbook is re-parsed.
Exports per group (in ``<out>/deconvolution/<group>/``):

* ``fit_<component>.png``        the review figure (raw, fit, individual peaks, R², legacy chi²)
* ``bub data.csv``               ``lifetime, peakposition, area, region`` (tres1 layout; area in % of all fitted peak
                                 areas of the group, region left empty), plus ``bubble_data_full.csv`` with every fitted peak
* ``bub plot.png``               the bubble plot
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from ..lognormal import fit_component, lognormal, multimodal
from ..export import safe_name

Prompt = Callable[[str], str]


@dataclass
class ComponentDecision:
    component: int
    lifetime_ns: float
    n_peaks: int
    bounds_nm: List[float]
    fit: Dict[str, Any] = field(default_factory=dict)
    accepted: bool = False


def _default_bounds(n_peaks: int, component_index: int) -> List[float]:
    from ..lognormal import _default_bounds as d
    return d(n_peaks, component_index)


def load_group_spectra(out_dir: str, group_folder: str) -> Dict[str, Any]:
    df = pd.read_csv(os.path.join(out_dir, "groups", group_folder, "das_spectra.csv"))
    bub = pd.read_csv(os.path.join(out_dir, "groups", group_folder, "das_bubble_summary.csv"))
    n = int(bub["component"].max())
    wl = df["wavelength_nm"].values.astype(float)
    em = np.column_stack([df[f"ra_tau{j + 1}_emission_mean"].values for j in range(n)])
    taus = bub.sort_values("component")["lifetime_ns_mean"].values.astype(float)
    return {"wavelengths_nm": wl, "emission": em, "lifetimes_ns": taus, "n_components": n}


def group_spectra_from_result(gr) -> Dict[str, Any]:
    """Same content as :func:`load_group_spectra`, taken from an in-memory :class:`~tres_suite.pipeline.GroupResult` (GUI use)."""
    sp = gr.das_spectra
    if sp is None:
        raise ValueError(f"group {gr.group.name}: no DAS spectra (blocked or not a TRES group)")
    return {"wavelengths_nm": np.asarray(sp["wavelengths_nm"], float), "emission": np.asarray(sp["emission_mean"], float),
            "lifetimes_ns": np.asarray(sp["lifetimes_mean"], float), "n_components": int(sp["n_components"])}


def decisions_path(out_dir: str) -> str:
    return os.path.join(out_dir, "deconvolution", "deconvolution_decisions.json")


def write_decisions(out_dir: str, decisions: Dict[str, Any]) -> str:
    """Write ``deconvolution_decisions.json`` (the replay file) and return its path."""
    path = decisions_path(out_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, indent=2, default=lambda o: float(o) if isinstance(o, (np.floating,)) else str(o))
    return path


def review_figure(path: str, wl: np.ndarray, y: np.ndarray, fit: Dict[str, Any], title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.plot(wl, y, lw=2, label="Raw")
    if fit.get("ok"):
        x_fit = np.linspace(wl.min(), wl.max(), 500)
        ax.plot(x_fit, multimodal(x_fit, *fit["params"]), "--", lw=2, label="Fit")
        for k, pk in enumerate(fit["peaks"], start=1):
            p = fit["params"][3 * (k - 1):3 * k]
            ax.plot(x_fit, lognormal(x_fit, *p), ":", lw=2, label=f"Peak {k} ({pk['center_nm']:.1f} nm)")
        ax.set_xlabel(f"Wavelength [nm]    R²: {fit['r_squared']:.4f}    legacy χ²: {fit['legacy_chi_squared']:.4g}")
    else:
        ax.set_xlabel(f"Wavelength [nm]    fit failed: {fit.get('reason')}")
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _ask_number(prompt: Prompt, text: str) -> float:
    while True:
        s = prompt(text).strip()
        try:
            return float(s)
        except ValueError:
            print("Value was not numeric")


def review_component(wl, y, decision: ComponentDecision, out_png: str, title: str, prompt: Optional[Prompt], show: Callable[[str], None]) -> ComponentDecision:
    """Fit -> preview -> (edit bounds / peak count -> refit)* -> accept.  ``prompt=None`` accepts the first fit."""
    while True:
        decision.fit = fit_component(wl, y, decision.n_peaks, decision.bounds_nm)
        review_figure(out_png, wl, y, decision.fit, title)
        show(out_png)
        f = decision.fit
        if f.get("ok"):
            print(f"  {title}: " + " | ".join(f"peak {k + 1}: {p['center_nm']:.1f} nm, area {p['area']:.4g}" for k, p in enumerate(f["peaks"]))
                  + f" | R²={f['r_squared']:.4f} | legacy χ²={f['legacy_chi_squared']:.4g}")
        else:
            print(f"  {title}: fit failed ({f.get('reason')})")
        if prompt is None:
            decision.accepted = bool(f.get("ok"))
            return decision
        ans = prompt("Is this fitting satisfactory? (yes/no, q to skip this component) ").strip().lower()
        if ans in ("y", "yes"):
            decision.accepted = bool(f.get("ok"))
            return decision
        if ans == "q":
            decision.accepted = False
            return decision
        n = int(_ask_number(prompt, f"Number of peaks (1-3) [current {decision.n_peaks}]: ") or decision.n_peaks)
        n = min(max(n, 1), 3)
        bounds: List[float] = []
        cur = decision.bounds_nm if n == decision.n_peaks else _default_bounds(n, decision.component - 1)
        print(f"  Current bounds: " + ", ".join(f"peak {k + 1}: {cur[2 * k]:g}-{cur[2 * k + 1]:g}" for k in range(n)))
        for k in range(n):
            lo = _ask_number(prompt, f"New peak {k + 1} low [nm]: ")
            hi = _ask_number(prompt, f"New peak {k + 1} high [nm]: ")
            bounds += [lo, hi]
        decision.n_peaks, decision.bounds_nm = n, bounds


def deconvolve_group(out_dir: str, group_folder: str, decisions: Optional[Dict[str, Any]] = None, prompt: Optional[Prompt] = None,
                     peaks_per_component: Optional[Sequence[int]] = None, bounds: Optional[Sequence[Sequence[float]]] = None,
                     show: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Run the review for one group.  ``decisions`` (from a replay file) suppresses prompts for recorded components."""
    show = show or (lambda p: print(f"  preview written: {p}"))
    spec = load_group_spectra(out_dir, group_folder)
    wl, em, taus, n = spec["wavelengths_nm"], spec["emission"], spec["lifetimes_ns"], spec["n_components"]
    gdir = os.path.join(out_dir, "deconvolution", group_folder)
    os.makedirs(gdir, exist_ok=True)
    results: List[ComponentDecision] = []
    for j in range(n):
        rec = (decisions or {}).get(str(j + 1))
        if rec is not None:
            d = ComponentDecision(j + 1, float(taus[j]), int(rec["n_peaks"]), list(rec["bounds_nm"]))
            d.fit = fit_component(wl, em[:, j], d.n_peaks, d.bounds_nm)
            d.accepted = bool(rec.get("accepted", True)) and bool(d.fit.get("ok"))
            review_figure(os.path.join(gdir, f"fit_tau{j + 1}.png"), wl, em[:, j], d.fit, f"{group_folder} | tau{j + 1} = {taus[j]:.3f} ns")
        else:
            npk = peaks_per_component[j] if peaks_per_component and j < len(peaks_per_component) else 2
            b = list(bounds[j]) if bounds and j < len(bounds) and bounds[j] else _default_bounds(npk, j)
            d = review_component(wl, em[:, j], ComponentDecision(j + 1, float(taus[j]), npk, b), os.path.join(gdir, f"fit_tau{j + 1}.png"),
                                 f"{group_folder} | tau{j + 1} = {taus[j]:.3f} ns", prompt, show)
        results.append(d)
    # bubble data: every fitted peak of every accepted component; area as % of the total fitted area (tres1 convention)
    rows = []
    for d in results:
        if not d.accepted:
            continue
        for k, pk in enumerate(d.fit["peaks"], start=1):
            rows.append({"lifetime": d.lifetime_ns, "peakposition": pk["center_nm"], "area_raw": pk["area"], "component": d.component, "peak": k,
                         "amplitude": pk["amplitude"], "width": pk["width"], "r_squared": d.fit["r_squared"], "legacy_chi_squared": d.fit["legacy_chi_squared"]})
    total = sum(r["area_raw"] for r in rows)
    for r in rows:
        r["area"] = 100.0 * r["area_raw"] / total if total > 0 else np.nan
        r["region"] = ""
    with open(os.path.join(gdir, "bub data.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["lifetime", "peakposition", "area", "region"])
        for r in rows:
            w.writerow([repr(r["lifetime"]), repr(r["peakposition"]), repr(r["area"]), ""])
    pd.DataFrame(rows).to_csv(os.path.join(gdir, "bubble_data_full.csv"), index=False, float_format="%.17g")
    _bubble_plot(os.path.join(gdir, "bub plot.png"), rows, group_folder)
    out = {"group": group_folder, "components": {str(d.component): {"lifetime_ns": d.lifetime_ns, "n_peaks": d.n_peaks, "bounds_nm": d.bounds_nm,
                                                                      "accepted": d.accepted, "fit": d.fit} for d in results},
           "bubble_rows": rows, "output_dir": gdir}
    return out


def _bubble_plot(path: str, rows: List[Dict[str, Any]], title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MultipleLocator
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    if rows:
        x = np.array([r["lifetime"] for r in rows]); y = np.array([r["peakposition"] for r in rows]); a = np.array([r["area"] for r in rows])
        ax.scatter(x, y, s=a * 75, alpha=0.8, c="#4FADEA", edgecolors="black", lw=1)
        ax.scatter(x, y, c="black", s=1)
        ax.set_xlim(0, max(8.0, float(np.nanmax(x)) * 1.15))
        ax.set_ylim(min(390.0, float(np.nanmin(y)) - 10), max(540.0, float(np.nanmax(y)) + 10))
    ax.xaxis.set_major_locator(MultipleLocator(1)); ax.xaxis.set_minor_locator(MultipleLocator(0.5))
    ax.grid(which="both", ls="--", c="grey", alpha=0.3)
    ax.tick_params(direction="in", which="both")
    ax.set_xlabel("Lifetime [ns]"); ax.set_ylabel("Peak position [nm]"); ax.set_title(title)
    fig.tight_layout(); fig.savefig(path, dpi=300); plt.close(fig)


def run_deconvolution(out_dir: str, groups: Optional[Sequence[str]] = None, replay: Optional[str] = None, interactive: bool = True,
                      peaks_per_component: Optional[Sequence[int]] = None, bounds: Optional[Sequence[Sequence[float]]] = None,
                      prompt: Optional[Prompt] = None, show: Optional[Callable[[str], None]] = None) -> str:
    """Review every (or the selected) analysed group of a finished run; write the decisions file and return its path."""
    gdir = os.path.join(out_dir, "groups")
    available = sorted(d for d in os.listdir(gdir) if os.path.exists(os.path.join(gdir, d, "das_spectra.csv"))) if os.path.isdir(gdir) else []
    wanted = [safe_name(g) for g in groups] if groups else available
    missing = [g for g in wanted if g not in available]
    if missing:
        raise FileNotFoundError(f"no DAS spectra for group(s) {missing}; available: {available}")
    recorded = json.load(open(replay, encoding="utf-8")) if replay else {}
    prompt_fn = prompt if prompt is not None else (input if interactive else None)
    decisions: Dict[str, Any] = {"groups": {}}
    for g in wanted:
        print(f"=== {g} ===")
        res = deconvolve_group(out_dir, g, recorded.get("groups", {}).get(g), prompt_fn, peaks_per_component, bounds, show)
        decisions["groups"][g] = res["components"]
    return write_decisions(out_dir, decisions)
