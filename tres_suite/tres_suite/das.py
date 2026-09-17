"""Decay-associated spectra (DAS), mean lifetime and bubble-plot quantities.

Definitions (all per replicate; see docs/methods.md):

* ``RA_i(λ)``   relative amplitude, percent, EzTime convention
  ``100·|B_i(λ)|τ_i / Σ_j |B_j(λ)|τ_j`` (fractional intensity of component i).
* ``α_i(λ)``    signed normalised pre-exponential ``B_i(λ) / Σ_j |B_j(λ)|``;
  negative lobes are rise terms and are used, signed, for reconstruction.
* ``F(λ)``      total-count spectrum (integrated photons per wavelength); the
  steady-state proxy.  ``F_norm = F / max(F)``.
* DAS emission  ``E_i(λ) = RA_i(λ)/100 · F_norm(λ)``; total ``E(λ) = Σ_i E_i(λ)``.
* Component weight ``W_i = ∫ E_i(λ) dλ`` (trapezoid over the *actual* wavelength
  coordinates; the legacy code used a constant ``dx`` which is identical for a
  uniform grid up to a common factor that cancels in every ratio below).
* Mean lifetime ``⟨τ⟩ = Σ_i τ_i W_i / Σ_i W_i`` (emission-weighted; the paper's
  definition; the formula is general and does not assume Laurdan).
* Area percent ``100·W_i / Σ_j W_j`` (bubble size).
* Component peak position: quadratic interpolation around the maximum of
  ``E_i(λ)`` (the non-interactive method of ``single laurdan.py``).  An optional
  log-normal deconvolution (from ``tres1.py``) is provided as a separate,
  explicitly enabled method.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .expressions import MetricResult, evaluate_expression, gp_expression
from .workbook import TresWorkbook

# numpy>=2 renamed trapz
_trapz = getattr(np, "trapezoid", None) or np.trapz  # type: ignore[attr-defined]


@dataclass
class DasSettings:
    amplitude_source: str = "results"  # "results" (full precision) | "summary" (legacy 2-decimal values)
    gp_enabled: bool = True
    gp_blue_nm: float = 440.0
    gp_red_nm: float = 490.0
    custom_ratios: Dict[str, str] = field(default_factory=dict)  # name -> expression
    intensity_source: str = "total_counts"  # only supported source; documented
    bubble_method: str = "quadratic_peak"  # or "lognormal_fit"
    lognormal_peaks_per_component: Optional[Sequence[int]] = None  # e.g. [2, 2, 2]
    lognormal_bounds_nm: Optional[Sequence[Sequence[float]]] = None  # per component: [lo1, hi1, lo2, hi2, ...]


@dataclass
class DasResult:
    wavelengths_nm: np.ndarray
    lifetimes_ns: np.ndarray
    lifetime_sigma_ns: np.ndarray
    relative_amplitude_percent: np.ndarray  # (n_wl, n_comp)
    normalized_pre_exponential: np.ndarray  # (n_wl, n_comp) signed
    total_counts: np.ndarray
    fss_norm_max: np.ndarray  # F / max(F)
    fss_area_norm: np.ndarray  # F / ∫F dλ  (used for reconstruction)
    emission: np.ndarray  # (n_wl, n_comp) E_i
    emission_total: np.ndarray  # (n_wl,)
    weights: np.ndarray  # (n_comp,) W_i
    mean_lifetime_ns: Optional[float]
    area_percent: np.ndarray  # (n_comp,)
    peak_position_nm: np.ndarray  # (n_comp,)
    peak_method: str
    metrics: Dict[str, MetricResult]
    amplitude_source: str
    notes: List[str] = field(default_factory=list)
    lognormal: Optional[Dict[str, Any]] = None

    @property
    def n_components(self) -> int:
        return int(len(self.lifetimes_ns))

    def scalar_record(self) -> Dict[str, Any]:
        rec: Dict[str, Any] = {
            "n_comp": self.n_components,
            "tmean_ns": self.mean_lifetime_ns if self.mean_lifetime_ns is not None else np.nan,
        }
        for i in range(self.n_components):
            rec[f"tau{i + 1}_ns"] = float(self.lifetimes_ns[i])
            rec[f"tau{i + 1}_sigma_ns"] = float(self.lifetime_sigma_ns[i])
            rec[f"area{i + 1}_percent"] = float(self.area_percent[i])
            rec[f"peak{i + 1}_nm"] = float(self.peak_position_nm[i])
        for name, m in self.metrics.items():
            rec[name] = m.value if m.available else np.nan
            rec[f"{name}_available"] = m.available
            rec[f"{name}_reason"] = m.reason
        return rec


def peak_center_quadratic(wl: np.ndarray, y: np.ndarray) -> float:
    """Parabolic interpolation of the maximum; endpoint maxima are returned as the endpoint."""
    wl = np.asarray(wl, float)
    y = np.asarray(y, float)
    if len(y) == 0 or not np.any(np.isfinite(y)):
        return float("nan")
    i = int(np.nanargmax(y))
    if i == 0 or i == len(y) - 1:
        return float(wl[i])
    y1, y2, y3 = y[i - 1], y[i], y[i + 1]
    denom = y1 - 2 * y2 + y3
    if denom == 0:
        return float(wl[i])
    dx = (wl[i + 1] - wl[i - 1]) / 2.0
    return float(wl[i] + 0.5 * (y1 - y3) / denom * dx)


def compute_das(wb: TresWorkbook, settings: DasSettings) -> DasResult:
    notes: List[str] = []
    wl = np.asarray(wb.wavelengths_nm, float)
    taus = np.asarray(wb.lifetimes_ns, float)
    if settings.amplitude_source == "summary":
        if wb.summary_relative_amplitude_percent is None or wb.summary_normalized_pre_exponential is None:
            raise ValueError(f"{wb.path}: Summary amplitude values unavailable; use amplitude_source='results'")
        ra = np.asarray(wb.summary_relative_amplitude_percent, float)
        npe = np.asarray(wb.summary_normalized_pre_exponential, float)
        src = "summary (EzTime 2-decimal values, legacy)"
    elif settings.amplitude_source == "results":
        ra = np.asarray(wb.components.relative_amplitude_percent, float)
        npe = np.asarray(wb.components.normalized_pre_exponential, float)
        src = "results (full precision)"
    else:
        raise ValueError(f"unknown amplitude_source {settings.amplitude_source!r}")

    counts = np.asarray(wb.total_counts, float)
    cmax = np.nanmax(counts)
    if not np.isfinite(cmax) or cmax <= 0:
        raise ValueError(f"{wb.path}: total counts have no positive maximum")
    f_norm = counts / cmax
    order = np.argsort(wl)
    area_f = float(_trapz(counts[order], wl[order]))
    fss_area = counts / area_f if area_f > 0 else counts.copy()
    if area_f <= 0:
        notes.append("total-count spectrum has non-positive area; reconstruction uses unnormalised counts")

    emission = ra / 100.0 * f_norm[:, None]
    emission_total = emission.sum(axis=1)
    weights = np.array([float(_trapz(emission[order, j], wl[order])) for j in range(len(taus))])
    wsum = float(weights.sum())
    tmean = float(np.dot(taus, weights) / wsum) if wsum > 0 else None
    if tmean is None:
        notes.append("sum of component weights is not positive; mean lifetime unavailable")
    area_pct = 100.0 * weights / wsum if wsum > 0 else np.full_like(weights, np.nan)

    metrics: Dict[str, MetricResult] = {}
    if settings.intensity_source != "total_counts":
        raise ValueError("only intensity_source='total_counts' is supported")
    if settings.gp_enabled:
        metrics["gp"] = evaluate_expression("gp", gp_expression(settings.gp_blue_nm, settings.gp_red_nm), wl, counts)
    for name, expr in settings.custom_ratios.items():
        if name in metrics:
            raise ValueError(f"custom ratio name {name!r} collides with a built-in metric")
        metrics[name] = evaluate_expression(name, expr, wl, counts)

    lognormal = None
    if settings.bubble_method == "lognormal_fit":
        from .lognormal import fit_components
        lognormal = fit_components(wl, emission, settings.lognormal_peaks_per_component, settings.lognormal_bounds_nm)
        peaks = np.array(lognormal["dominant_peak_nm"], float)
        method = "lognormal_fit (dominant peak of the fitted log-normal components)"
    else:
        peaks = np.array([peak_center_quadratic(wl, emission[:, j]) for j in range(len(taus))])
        method = "quadratic_peak (parabolic interpolation of the DAS emission maximum)"

    return DasResult(
        wavelengths_nm=wl, lifetimes_ns=taus, lifetime_sigma_ns=np.asarray(wb.components.lifetime_sigma_ns, float),
        relative_amplitude_percent=ra, normalized_pre_exponential=npe, total_counts=counts,
        fss_norm_max=f_norm, fss_area_norm=fss_area, emission=emission, emission_total=emission_total,
        weights=weights, mean_lifetime_ns=tmean, area_percent=area_pct, peak_position_nm=peaks,
        peak_method=method, metrics=metrics, amplitude_source=src, notes=notes, lognormal=lognormal,
    )
