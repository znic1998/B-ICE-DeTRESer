"""Replicate aggregation: arithmetic mean, sample SD (ddof=1) and n.

* One replicate -> SD is undefined (NaN), never zero.
* Only numeric measurement values are aggregated; identifiers, booleans,
  text and component indices are never averaged.
* Spectra and trajectories are averaged point-wise only when the replicate
  grids are identical (validated upstream); SD is per point.  The averaging
  order is: per-replicate quantity first, then mean/SD across replicates.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

SD_DDOF = 1  # sample standard deviation (Excel STDEV.S); tres1.py used population SD (ddof=0)


def _is_numeric(v: Any) -> bool:
    if isinstance(v, bool) or v is None:
        return False
    return isinstance(v, (int, float, np.integer, np.floating))


def summarize_scalars(rows: Sequence[Dict[str, Any]], exclude: Sequence[str] = ()) -> Dict[str, Any]:
    """``{metric}_mean``, ``{metric}_std``, ``{metric}_n`` for every numeric metric in ``rows``."""
    out: Dict[str, Any] = {}
    keys: List[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    for k in keys:
        if k in exclude or k.endswith("_available") or k.endswith("_reason") or k.endswith("_source"):
            continue
        vals = [r.get(k) for r in rows]
        if not any(_is_numeric(v) for v in vals):
            continue
        if any(isinstance(v, bool) for v in vals):
            continue
        arr = np.array([float(v) if _is_numeric(v) else np.nan for v in vals], float)
        arr = arr[np.isfinite(arr)]
        n = int(len(arr))
        out[f"{k}_mean"] = float(np.mean(arr)) if n else np.nan
        out[f"{k}_std"] = float(np.std(arr, ddof=SD_DDOF)) if n > SD_DDOF else np.nan
        out[f"{k}_n"] = n
    return out


def summarize_arrays(arrays: Sequence[np.ndarray]) -> Dict[str, np.ndarray]:
    """Point-wise mean / SD / n over replicate arrays of identical shape."""
    stack = np.array([np.asarray(a, float) for a in arrays])
    finite = np.isfinite(stack)
    n = finite.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, np.nansum(np.where(finite, stack, 0.0), axis=0) / np.maximum(n, 1), np.nan)
        dev = np.where(finite, stack - mean[None, ...], 0.0)
        var = np.where(n > SD_DDOF, (dev ** 2).sum(axis=0) / np.maximum(n - SD_DDOF, 1), np.nan)
    return {"mean": mean, "std": np.sqrt(var), "n": n}


def align_trajectories(times: Sequence[np.ndarray], values: Sequence[np.ndarray], t_common: Optional[np.ndarray] = None):
    """Interpolate replicate trajectories onto a common time grid (their intersection) before averaging.

    Returns (t_common, mean, std, n).  Each replicate contributes only inside its own time range;
    no extrapolation.
    """
    if t_common is None:
        t0 = max(float(np.nanmin(t)) for t in times)
        t1 = min(float(np.nanmax(t)) for t in times)
        dt = min(float(np.nanmedian(np.diff(t))) for t in times if len(t) > 1)
        if t1 <= t0:
            return np.array([]), np.array([]), np.array([]), np.array([])
        t_common = np.arange(t0, t1 + dt / 2, dt)
    rows = []
    for t, v in zip(times, values):
        good = np.isfinite(t) & np.isfinite(v)
        if good.sum() < 2:
            rows.append(np.full_like(t_common, np.nan))
            continue
        vi = np.interp(t_common, t[good], v[good], left=np.nan, right=np.nan)
        rows.append(vi)
    s = summarize_arrays(rows)
    return t_common, s["mean"], s["std"], s["n"]
