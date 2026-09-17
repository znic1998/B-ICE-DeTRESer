"""Simple statistics: unweighted linear fit with intercept and R².

R² = 1 − SSE/SST with SSE = Σ(y − ŷ)², SST = Σ(y − ȳ)².  The model, fit
range, number of points and definition are reported with every result.
Advanced statistics (the legacy ``stats.py`` correlation/bootstrap machinery)
are deliberately out of scope for this backend.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import numpy as np


@dataclass
class LinearFit:
    available: bool
    reason: Optional[str]
    model: str = "y = slope * x + intercept (unweighted least squares)"
    slope: float = float("nan")
    intercept: float = float("nan")
    r_squared: float = float("nan")
    r_squared_definition: str = "1 - SSE/SST"
    n_points: int = 0
    x_min: float = float("nan")
    x_max: float = float("nan")
    slope_se: float = float("nan")
    intercept_se: float = float("nan")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.slope * np.asarray(x, float) + self.intercept


def linear_fit(x: np.ndarray, y: np.ndarray) -> LinearFit:
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    n = int(len(x))
    if n < 3:
        return LinearFit(False, f"insufficient points for a linear fit with R² (n={n} < 3)", n_points=n)
    if np.ptp(x) == 0:
        return LinearFit(False, "x is constant; slope undefined", n_points=n)
    A = np.column_stack([x, np.ones(n)])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    yhat = A @ coef
    sse = float(np.sum((y - yhat) ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    if sst == 0:
        return LinearFit(False, "y is constant; R² undefined (SST = 0)", slope=float(coef[0]), intercept=float(coef[1]), n_points=n,
                         x_min=float(x.min()), x_max=float(x.max()))
    r2 = 1.0 - sse / sst
    dof = n - 2
    s2 = sse / dof if dof > 0 else float("nan")
    sxx = float(np.sum((x - x.mean()) ** 2))
    slope_se = float(np.sqrt(s2 / sxx)) if dof > 0 else float("nan")
    int_se = float(np.sqrt(s2 * (1.0 / n + x.mean() ** 2 / sxx))) if dof > 0 else float("nan")
    return LinearFit(True, None, slope=float(coef[0]), intercept=float(coef[1]), r_squared=float(r2), n_points=n,
                     x_min=float(x.min()), x_max=float(x.max()), slope_se=slope_se, intercept_se=int_se)
