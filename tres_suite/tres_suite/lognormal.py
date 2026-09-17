"""Optional, non-interactive log-normal deconvolution of DAS emission curves.

Port of the fitting functions in ``tres1.py`` (``lognormal``, ``bimodal``,
``trimodal``) without the interactive prompts.  Peak counts and bounds are
supplied explicitly; when omitted the ``tres1.py`` "norm"-mode defaults are
used.  R² (``1 - SSE/SST``) and the legacy ``chi_squared`` (``Σ (y-ŷ)²/ŷ``,
*not* a reduced statistic) are reported for each component fit.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import curve_fit

_trapz = getattr(np, "trapezoid", None) or np.trapz  # type: ignore[attr-defined]


def lognormal(x, a0, a1, a2):
    return a0 * np.exp(-0.5 * ((np.log(x / a1) / a2) ** 2))


def multimodal(x, *params):
    y = np.zeros_like(np.asarray(x, float))
    for k in range(0, len(params), 3):
        y = y + lognormal(x, *params[k:k + 3])
    return y


def _default_bounds(n_peaks: int, component_index: int) -> List[float]:
    # tres1.py 'norm' mode defaults
    if n_peaks == 3:
        return [400, 450, 450, 500, 500, 540]
    if n_peaks == 2:
        return [400, 470, 480, 500] if component_index == 2 else [390, 490, 430, 535]
    return [390, 540]


def fit_component(wl: np.ndarray, y: np.ndarray, n_peaks: int, bounds_nm: Sequence[float]) -> Dict[str, Any]:
    x = np.asarray(wl, float)
    y = np.asarray(y, float)
    good = np.isfinite(x) & np.isfinite(y) & (x > 0)
    x, y = x[good], y[good]
    if len(x) < 3 * n_peaks + 1:
        return {"ok": False, "reason": "too few points", "n_points": int(len(x))}
    lo, hi = [], []
    p0 = []
    for k in range(n_peaks):
        l, h = float(bounds_nm[2 * k]), float(bounds_nm[2 * k + 1])
        lo += [0.0, l, 0.0]
        hi += [max(1.0, float(np.nanmax(y)) * 2), h, 1.0]
        p0 += [max(float(np.nanmax(y)) * 0.5, 1e-3), l + 2.0, 0.05]
    try:
        params, cov = curve_fit(multimodal, x, y, p0=p0, bounds=(lo, hi), maxfev=50000, ftol=1e-5)
    except Exception as exc:
        return {"ok": False, "reason": f"fit failed: {exc}", "n_points": int(len(x))}
    yhat = multimodal(x, *params)
    sse = float(np.sum((y - yhat) ** 2))
    sst = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    with np.errstate(divide="ignore", invalid="ignore"):
        chi = float(np.nansum(((y - yhat) ** 2) / yhat))
    x_fit = np.linspace(x.min(), x.max(), 500)
    peaks = []
    for k in range(n_peaks):
        pk = params[3 * k:3 * k + 3]
        peaks.append({"amplitude": float(pk[0]), "center_nm": float(pk[1]), "width": float(pk[2]),
                      "area": float(_trapz(lognormal(x_fit, *pk), x_fit))})
    return {"ok": True, "n_points": int(len(x)), "r_squared": r2, "legacy_chi_squared": chi,
            "params": [float(p) for p in params], "sigma": [float(s) for s in np.sqrt(np.diag(cov))],
            "peaks": peaks, "bounds_nm": list(map(float, bounds_nm)), "n_peaks": n_peaks,
            "r_squared_definition": "1 - SSE/SST over the fitted points"}


def fit_components(wl: np.ndarray, emission: np.ndarray, peaks_per_component: Optional[Sequence[int]],
                   bounds: Optional[Sequence[Sequence[float]]]) -> Dict[str, Any]:
    n_comp = emission.shape[1]
    ppc = list(peaks_per_component) if peaks_per_component else [2] * n_comp
    if len(ppc) != n_comp:
        raise ValueError(f"lognormal_peaks_per_component has {len(ppc)} entries for {n_comp} components")
    fits = []
    dominant = []
    for j in range(n_comp):
        b = list(bounds[j]) if bounds and j < len(bounds) and bounds[j] else _default_bounds(ppc[j], j)
        f = fit_component(wl, emission[:, j], ppc[j], b)
        fits.append(f)
        if f.get("ok"):
            best = max(f["peaks"], key=lambda p: p["area"])
            dominant.append(best["center_nm"])
        else:
            dominant.append(float("nan"))
    return {"fits": fits, "dominant_peak_nm": dominant}
