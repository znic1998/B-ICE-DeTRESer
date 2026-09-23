"""TRES reconstruction and time-dependent fluorescence shift (TDFS).

Equations (documented in docs/methods.md; the paper SI supplied with this
project uses the same conventions):

Reconstruction (impulse response pinned to the steady-state proxy)::

    I(λ, t) = F(λ) · Σ_i α_i(λ) exp(-t/τ_i) / Σ_i α_i(λ) τ_i

* ``F(λ)``   total-count spectrum normalised to unit area (steady-state proxy).
* ``α_i(λ)`` **signed** normalised pre-exponentials (rise terms negative).
* ``τ_i``    global lifetimes.
* ``τ̄(λ) = Σ_i α_i(λ) τ_i`` is the amplitude-weighted mean lifetime at λ.  The
  time integral of I(λ,t) then equals F(λ).  Wavelengths with ``τ̄ ≤ eps`` would
  flip sign; they are masked to zero and counted (``recon_wavelengths_masked``).

Spectral coordinates: each time slice is converted to wavenumber density,
``S(ν) = I(λ) λ²`` with ``ν = 10⁷/λ`` (cm⁻¹), spline-interpolated on a fine ν grid
(clipped at zero) and characterised by its **peak** (primary), centre of mass
(secondary) and FWHM.

TDFS metrics on the metric window ``t ≥ metric_tmin_ns`` while the positive
spectral area is ≥ ``intensity_floor`` × its t=0 value::

    ν_∞  = mean of the last ``tail_points`` values of ν(t)
    ν_0  = user-supplied value (cm⁻¹), or the first ν(t) in the metric window
           ("apparent" mode; recorded with its time)
    Δν   = ν_0 − ν_∞
    C(t) = (ν(t) − ν_∞) / Δν        (clipped at 0 when ``clip_negative_c``)
    τ_r  = ∫ C(t) dt  over the metric window (trapezoid); with a user-supplied ν_0
           the integral starts at t = 0 with C(0) = 1 (``tau_r_from_zero_with_user_nu0``)

No literature ν₀ is ever substituted silently.  The former heuristic
physical-validity classification is computed only as *unevaluated legacy
diagnostics* (``legacy_*`` keys, ``legacy_gate_evaluated = False``) and never
gates any output.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from scipy.interpolate import UnivariateSpline
from scipy.signal import savgol_filter

_trapz = getattr(np, "trapezoid", None) or np.trapz  # type: ignore[attr-defined]


@dataclass
class TdfsSettings:
    recon_dt_ns: float = 0.01
    recon_tmax_min_ns: float = 35.0
    recon_tmax_tau_factor: float = 6.0
    metric_tmin_ns: float = 0.1
    tail_points: int = 5
    intensity_floor: float = 0.01  # fraction of the t=0 positive spectral area
    clip_negative_c: bool = True
    fine_nu_points: int = 1000
    clip_negative_spectrum: bool = True
    nu0_cm1: Optional[float] = None  # user-supplied peak ν0; None -> apparent ν0
    com_nu0_cm1: Optional[float] = None  # user-supplied COM ν0 (rarely meaningful); None -> apparent
    compute_com: bool = True
    compute_fwhm: bool = True
    fwhm_smooth_window_ns: float = 0.25
    fwhm_smooth_polyorder: int = 2
    legacy_diagnostics: bool = True
    export_times_ns: Sequence[float] = (0.05, 0.10, 0.25, 0.50, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0)
    trajectory_stride: int = 1  # evaluate spectral moments every N reconstructed steps
    com_window_initial_ns: float = 0.25  # legacy finite-window COM shift
    com_window_final_ns: float = 10.0
    tau_bar_eps: float = 1e-12
    # With a user-supplied nu0, nu(0) = nu0 by definition, so C(0) = 1 and tau_r integrates from t = 0
    # (the point (0, 1) is prepended to the metric window).  False reproduces the legacy integral from metric_tmin_ns.
    tau_r_from_zero_with_user_nu0: bool = True

    @property
    def nu0_mode(self) -> str:
        return "user" if self.nu0_cm1 is not None else "apparent"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["export_times_ns"] = list(self.export_times_ns)
        d["nu0_mode"] = self.nu0_mode
        return d


# ----------------------------------------------------------------------------
# reconstruction
# ----------------------------------------------------------------------------
def reconstruct_tres(wl: np.ndarray, tau: np.ndarray, alpha: np.ndarray, fss: np.ndarray, t: np.ndarray,
                     eps: float = 1e-12):
    """Return (tres (n_t, n_wl), tau_bar (n_wl,), masked (bool n_wl))."""
    wl = np.asarray(wl, float)
    tau = np.asarray(tau, float)
    alpha = np.asarray(alpha, float)
    fss = np.asarray(fss, float)
    t = np.asarray(t, float)
    tau_bar = alpha @ tau
    good = tau_bar > eps
    scale = np.zeros_like(tau_bar)
    scale[good] = fss[good] / tau_bar[good]
    decay = np.exp(-t[:, None] / tau[None, :]) @ alpha.T
    return decay * scale[None, :], tau_bar, ~good


# ----------------------------------------------------------------------------
# spectral moments
# ----------------------------------------------------------------------------
@dataclass
class _NuGrid:
    nu_sorted: np.ndarray
    lam_sorted: np.ndarray
    order: np.ndarray
    fine_nu: np.ndarray


def _make_grid(wl: np.ndarray, n_fine: int) -> _NuGrid:
    wl = np.asarray(wl, float)
    nu = 1e7 / wl
    order = np.argsort(nu)
    nu_s = nu[order]
    return _NuGrid(nu_s, wl[order], order, np.linspace(nu_s.min(), nu_s.max(), int(n_fine)))


def _fwhm_connected(fine_x: np.ndarray, fine_y: np.ndarray) -> float:
    """FWHM of the contiguous half-maximum region around the main peak (NaN if it touches an edge)."""
    if fine_y.size == 0:
        return float("nan")
    p = int(np.argmax(fine_y))
    mx = float(fine_y[p])
    if not np.isfinite(mx) or mx <= 0:
        return float("nan")
    half = 0.5 * mx
    l = p
    while l > 0 and fine_y[l] >= half:
        l -= 1
    r = p
    while r < len(fine_y) - 1 and fine_y[r] >= half:
        r += 1
    if (l == p and p > 0) or (r == p and p < len(fine_y) - 1):
        return float("nan")
    if (l == 0 and fine_y[0] >= half) or (r == len(fine_y) - 1 and fine_y[-1] >= half):
        return float("nan")  # half-maximum region reaches the acquisition edge

    def cross(i1, i2):
        x1, y1 = float(fine_x[i1]), float(fine_y[i1])
        x2, y2 = float(fine_x[i2]), float(fine_y[i2])
        return x1 if y2 == y1 else x1 + (half - y1) * (x2 - x1) / (y2 - y1)

    return float(cross(r - 1, r) - cross(l, l + 1))


def spectral_moments(spec_lam: np.ndarray, grid: _NuGrid, clip: bool = True):
    """(peak_cm1, com_cm1, fwhm_cm1, negative_area_fraction, boundary_peak) of one λ-spectrum."""
    s = np.asarray(spec_lam, float)[grid.order]
    pos = np.clip(s, 0.0, None)
    neg = np.clip(-s, 0.0, None)
    # lam_sorted is descending (sorted by ν); take |∫| so the sign convention does not matter
    pa = float(np.abs(_trapz(pos, grid.lam_sorted)))
    na = float(np.abs(_trapz(neg, grid.lam_sorted)))
    neg_frac = na / (pa + na) if (pa + na) > 0 else float("nan")
    spec_nu = s * grid.lam_sorted ** 2
    if not np.any(np.isfinite(spec_nu)) or np.nanmax(spec_nu) <= 0:
        return float("nan"), float("nan"), float("nan"), neg_frac, True
    try:
        spline = UnivariateSpline(grid.nu_sorted, spec_nu, s=0, k=3)
        fine = spline(grid.fine_nu)
    except Exception:
        fine = np.interp(grid.fine_nu, grid.nu_sorted, spec_nu)
    if clip:
        fine = np.clip(fine, 0.0, None)
    ipk = int(np.argmax(fine))
    peak = float(grid.fine_nu[ipk])
    area = float(_trapz(fine, grid.fine_nu))
    com = float(_trapz(fine * grid.fine_nu, grid.fine_nu) / area) if area > 0 else float("nan")
    fwhm = _fwhm_connected(grid.fine_nu, fine)
    raw_pk = int(np.argmax(pos))
    boundary = bool(raw_pk <= 1 or raw_pk >= len(pos) - 2)
    return peak, com, fwhm, neg_frac, boundary


# ----------------------------------------------------------------------------
# results
# ----------------------------------------------------------------------------
@dataclass
class TdfsMetric:
    """Δν / τ_r for one spectral coordinate (peak or com)."""

    coordinate: str
    available: bool
    reason: Optional[str]
    nu0_cm1: float = float("nan")
    nu0_source: str = ""
    nu0_time_ns: float = float("nan")
    nu_first_measured_cm1: float = float("nan")
    nuinf_cm1: float = float("nan")
    delta_nu_cm1: float = float("nan")
    tau_r_ns: float = float("nan")
    n_points: int = 0
    window_tmin_ns: float = float("nan")
    window_tmax_ns: float = float("nan")
    tail_points: int = 0
    c_clipped_fraction: float = float("nan")  # fraction of C(t) samples clipped at 0

    def record(self) -> Dict[str, Any]:
        p = self.coordinate
        return {
            f"{p}_delta_nu_cm-1": self.delta_nu_cm1, f"{p}_tau_r_ns": self.tau_r_ns, f"{p}_nu0_cm-1": self.nu0_cm1,
            f"{p}_nu0_source": self.nu0_source, f"{p}_nu0_time_ns": self.nu0_time_ns,
            f"{p}_nu_initial_measured_cm-1": self.nu_first_measured_cm1, f"{p}_nuinf_cm-1": self.nuinf_cm1,
            f"{p}_n_points": self.n_points, f"{p}_metric_tmin_ns": self.window_tmin_ns, f"{p}_metric_tmax_ns": self.window_tmax_ns,
            f"{p}_metric_tail_points": self.tail_points, f"{p}_available": self.available, f"{p}_reason": self.reason,
            f"{p}_c_clipped_fraction": self.c_clipped_fraction,
        }


@dataclass
class TdfsResult:
    t_ns: np.ndarray  # full reconstruction grid
    wavelengths_nm: np.ndarray
    tres: np.ndarray  # (n_t, n_wl)
    n_masked: int
    masked_wavelengths_nm: List[float]
    total_intensity: np.ndarray  # positive spectral area per time
    usable: np.ndarray  # bool per time (intensity floor)
    traj_t_ns: np.ndarray  # times at which moments were evaluated (usable, strided)
    traj_peak_cm1: np.ndarray
    traj_com_cm1: np.ndarray
    traj_fwhm_cm1: np.ndarray
    traj_c_peak: np.ndarray
    traj_c_com: np.ndarray
    peak: TdfsMetric
    com: Optional[TdfsMetric]
    tau_fwhm_ns: float
    fwhm_max_cm1: float
    peak_at_boundary_fraction: float  # fraction of usable spectra whose raw maximum sits at the acquisition edge
    settings: TdfsSettings
    legacy: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def scalar_record(self) -> Dict[str, Any]:
        rec: Dict[str, Any] = {"recon_wavelengths_masked": self.n_masked, "recon_masked_wavelengths_nm": ";".join(f"{w:g}" for w in self.masked_wavelengths_nm),
                               "recon_dt_ns": self.settings.recon_dt_ns, "recon_tmax_ns": float(self.t_ns[-1]),
                               "tdfs_intensity_floor": self.settings.intensity_floor, "tdfs_usable_tmax_ns": float(self.traj_t_ns[-1]) if len(self.traj_t_ns) else np.nan,
                               "tau_fwhm_ns": self.tau_fwhm_ns, "fwhm_max_cm-1": self.fwhm_max_cm1,
                               "peak_at_boundary_fraction": self.peak_at_boundary_fraction}
        rec.update(self.peak.record())
        if self.com is not None:
            rec.update(self.com.record())
        rec.update(self.legacy)
        return rec

    def spectrum_at(self, t_ns: float) -> np.ndarray:
        k = int(np.argmin(np.abs(self.t_ns - t_ns)))
        return self.tres[k]


def _metric(coord: str, t: np.ndarray, nu: np.ndarray, settings: TdfsSettings, nu0_user: Optional[float]) -> TdfsMetric:
    good = np.isfinite(nu)
    t_all, nu_all = t[good], nu[good]
    mask = t_all >= settings.metric_tmin_ns
    tm, num = t_all[mask], nu_all[mask]
    need = int(settings.tail_points) + 3
    if len(tm) < need:
        return TdfsMetric(coord, False, f"too few usable points in the metric window ({len(tm)} < {need})", n_points=int(len(tm)))
    tail_n = min(int(settings.tail_points), len(num))
    nuinf = float(np.mean(num[-tail_n:]))
    nu_first = float(num[0])
    if nu0_user is not None:
        nu0, src, t0 = float(nu0_user), "user_supplied", float("nan")
    else:
        nu0, src, t0 = nu_first, f"apparent: first reconstructed spectrum at t >= {settings.metric_tmin_ns:g} ns", float(tm[0])
    delta = nu0 - nuinf
    if not np.isfinite(delta) or abs(delta) < 1e-12:
        return TdfsMetric(coord, False, "zero spectral shift (nu0 == nu_inf)", nu0, src, t0, nu_first, nuinf, delta, float("nan"),
                          int(len(tm)), float(tm[0]), float(tm[-1]), tail_n)
    c = (num - nuinf) / delta
    clipped = float(np.mean(c < 0)) if len(c) else float("nan")
    if settings.clip_negative_c:
        c = np.clip(c, 0.0, None)
    if nu0_user is not None and settings.tau_r_from_zero_with_user_nu0:
        # user nu0 is the time-zero frequency: start the integral at C(0) = 1, t = 0
        if tm[0] > 0:
            tau_r = float(_trapz(np.concatenate(([1.0], c)), np.concatenate(([0.0], tm))))
        else:  # metric window already starts at t = 0: C(0) = 1 by definition
            c0 = c.copy()
            c0[0] = 1.0
            tau_r = float(_trapz(c0, tm))
    else:
        tau_r = float(_trapz(c, tm))
    return TdfsMetric(coord, True, None, nu0, src, t0, nu_first, nuinf, float(delta), tau_r, int(len(tm)), float(tm[0]), float(tm[-1]), tail_n, clipped)


def _smooth_by_time(t: np.ndarray, y: np.ndarray, window_ns: float, polyorder: int) -> np.ndarray:
    good = np.isfinite(t) & np.isfinite(y)
    if good.sum() < 5:
        return y.copy()
    tg, yg = t[good], y[good]
    dt = float(np.nanmedian(np.diff(tg)))
    if not np.isfinite(dt) or dt <= 0:
        return y.copy()
    nwin = max(5, int(round(window_ns / dt)))
    if nwin % 2 == 0:
        nwin += 1
    if nwin > len(yg):
        nwin = len(yg) if len(yg) % 2 == 1 else len(yg) - 1
    if nwin < 5:
        return y.copy()
    out = y.copy()
    out[good] = savgol_filter(yg, window_length=nwin, polyorder=min(polyorder, nwin - 2), mode="interp")
    return out


def compute_tdfs(wl: np.ndarray, tau: np.ndarray, alpha: np.ndarray, fss_area_norm: np.ndarray,
                 settings: TdfsSettings, tmean_ns: Optional[float] = None) -> TdfsResult:
    """Full reconstruction + TDFS analysis for one replicate.

    ``alpha`` must be the signed normalised pre-exponentials (n_wl, n_comp).
    """
    wl = np.asarray(wl, float)
    tau = np.asarray(tau, float)
    alpha = np.asarray(alpha, float)
    fss = np.asarray(fss_area_norm, float)
    notes: List[str] = []

    tmax = max(settings.recon_tmax_min_ns, settings.recon_tmax_tau_factor * float(np.nanmax(tau)))
    t = np.arange(0.0, tmax + settings.recon_dt_ns, settings.recon_dt_ns)
    tres, tau_bar, masked = reconstruct_tres(wl, tau, alpha, fss, t, settings.tau_bar_eps)
    masked_wl = [float(w) for w in wl[masked]]
    if masked.any():
        notes.append(f"{int(masked.sum())} wavelength(s) masked to zero in reconstruction (tau_bar <= eps): {masked_wl}")

    order = np.argsort(wl)
    total = np.abs(_trapz(np.clip(tres[:, order], 0.0, None), wl[order], axis=1))
    total0 = total[0] if total[0] > 0 else float(np.nanmax(total))
    usable = total >= settings.intensity_floor * total0
    # the usable window is contiguous from t=0 (intensity decays monotonically for a sum of decays,
    # but rise terms can make early total intensity increase); keep everything up to the last usable index
    last = int(np.flatnonzero(usable)[-1]) if usable.any() else -1
    idx = np.arange(0, last + 1, max(1, int(settings.trajectory_stride)))
    if last >= 0 and idx[-1] != last:
        idx = np.append(idx, last)

    grid = _make_grid(wl, settings.fine_nu_points)
    peak = np.full(len(idx), np.nan)
    com = np.full(len(idx), np.nan)
    fwhm = np.full(len(idx), np.nan)
    negfrac = np.full(len(idx), np.nan)
    boundary = np.zeros(len(idx), bool)
    for k, i in enumerate(idx):
        p, c, f, nf, b = spectral_moments(tres[i], grid, settings.clip_negative_spectrum)
        peak[k], com[k], fwhm[k], negfrac[k], boundary[k] = p, c, f, nf, b
    tt = t[idx]

    pk_metric = _metric("peak", tt, peak, settings, settings.nu0_cm1)
    com_metric = _metric("com", tt, com, settings, settings.com_nu0_cm1) if settings.compute_com else None

    def c_of(metric: Optional[TdfsMetric], nu: np.ndarray) -> np.ndarray:
        if metric is None or not metric.available:
            return np.full_like(nu, np.nan)
        c = (nu - metric.nuinf_cm1) / metric.delta_nu_cm1
        return np.clip(c, 0.0, None) if settings.clip_negative_c else c

    # FWHM trajectory and tau_FWHM (time of maximum of the smoothed FWHM), over the usable window from t=0
    tau_fwhm = fwhm_max = float("nan")
    if settings.compute_fwhm and np.sum(np.isfinite(fwhm)) >= 5:
        sm = _smooth_by_time(tt, fwhm, settings.fwhm_smooth_window_ns, settings.fwhm_smooth_polyorder)
        fin = np.isfinite(sm)
        imax = int(np.nanargmax(np.where(fin, sm, -np.inf)))
        tau_fwhm, fwhm_max = float(tt[imax]), float(sm[imax])

    legacy: Dict[str, Any] = {}
    if settings.legacy_diagnostics:
        legacy = legacy_diagnostics(wl, tau, alpha, tt, peak, com, fwhm, negfrac, boundary, pk_metric, com_metric, settings, tmean_ns)

    # legacy finite-window COM shift (0.25 -> 10 ns), secondary output
    try:
        ti, tf = settings.com_window_initial_ns, settings.com_window_final_ns
        if ti >= t[0] and tf <= t[-1]:
            si = np.array([np.interp(ti, t, tres[:, j]) for j in range(tres.shape[1])])
            sf = np.array([np.interp(tf, t, tres[:, j]) for j in range(tres.shape[1])])
            _, ci, _, _, _ = spectral_moments(si, grid, settings.clip_negative_spectrum)
            _, cf, _, _, _ = spectral_moments(sf, grid, settings.clip_negative_spectrum)
            ai = float(np.abs(_trapz(np.clip(si[order], 0, None), wl[order])))
            af = float(np.abs(_trapz(np.clip(sf[order], 0, None), wl[order])))
            legacy.update({"com_0p25ns_cm-1": ci, "com_10ns_cm-1": cf, "com_shift_0p25_to_10ns_cm-1": ci - cf if np.isfinite(ci) and np.isfinite(cf) else np.nan,
                           "com_intensity_fraction_10ns": af / ai if ai > 0 else np.nan})
        else:
            legacy.update({"com_0p25ns_cm-1": np.nan, "com_10ns_cm-1": np.nan, "com_shift_0p25_to_10ns_cm-1": np.nan, "com_intensity_fraction_10ns": np.nan})
    except Exception as exc:  # pragma: no cover
        notes.append(f"finite-window COM shift failed: {exc}")

    boundary_fraction = float(np.mean(boundary)) if len(boundary) else float("nan")
    return TdfsResult(t, wl, tres, int(masked.sum()), masked_wl, total, usable, tt, peak, com, fwhm,
                      c_of(pk_metric, peak), c_of(com_metric, com), pk_metric, com_metric, tau_fwhm, fwhm_max, boundary_fraction,
                      settings, legacy, notes)


# ----------------------------------------------------------------------------
# legacy diagnostics: computed, reported, NEVER evaluated as a gate
# ----------------------------------------------------------------------------
def legacy_diagnostics(wl, tau, alpha, t, peak, com, fwhm, negfrac, boundary, pk: TdfsMetric, cm: Optional[TdfsMetric],
                       settings: TdfsSettings, tmean_ns: Optional[float]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"legacy_gate_evaluated": False,
                           "legacy_gate_status": "unevaluated (heuristic physical-validity classification disabled by design)"}
    # kinetic screen from the signed pre-exponentials
    order = np.argsort(wl)
    neg = np.clip(-alpha[order], 0.0, None)
    pos = np.clip(alpha[order], 0.0, None)
    rise = np.abs(_trapz(neg, wl[order], axis=0))
    posi = np.abs(_trapz(pos, wl[order], axis=0))
    rise_total = float(rise.sum())
    amp_total = float(rise.sum() + posi.sum())
    out["legacy_rise_fraction"] = rise_total / amp_total if amp_total > 0 else np.nan
    if rise_total > 0:
        tau_relax = float((rise * tau).sum() / rise_total)
        x = tau_relax / tmean_ns if tmean_ns and tmean_ns > 0 else np.nan
        out.update({"legacy_tau_relax_ns": tau_relax, "legacy_x_kinetic": x, "legacy_captured_fraction": 1.0 / (1.0 + x) if np.isfinite(x) else np.nan})
    else:
        out.update({"legacy_tau_relax_ns": np.nan, "legacy_x_kinetic": np.nan, "legacy_captured_fraction": np.nan})

    # curve diagnostics per coordinate (values only)
    for name, nu, metric in (("peak", peak, pk), ("com", com, cm)):
        if metric is None:
            continue
        good = np.isfinite(nu)
        tg, ng = t[good], nu[good]
        pre = f"legacy_{name}_"
        if len(tg) < 8:
            out.update({pre + "late_slope_cm_per_ns": np.nan, pre + "tail_span_cm-1": np.nan, pre + "nuinf_sensitivity_cm-1": np.nan,
                        pre + "nonmonotonic_fraction": np.nan, pre + "negative_C_fraction": np.nan, pre + "overshoot_cm-1": np.nan})
            continue
        tail = tg >= tg[-1] - 1.0
        if tail.sum() < 3:
            tail = np.zeros(len(tg), bool)
            tail[-3:] = True
        prev = (tg >= tg[-1] - 2.0) & (tg < tg[-1] - 1.0)
        nuinf = float(np.mean(ng[tail]))
        out[pre + "late_slope_cm_per_ns"] = float(np.polyfit(tg[tail], ng[tail], 1)[0])
        out[pre + "tail_span_cm-1"] = float(np.max(ng[tail]) - np.min(ng[tail]))
        out[pre + "nuinf_sensitivity_cm-1"] = float(abs(nuinf - np.mean(ng[prev]))) if prev.sum() >= 3 else np.nan
        delta = float(ng[0] - nuinf)
        if abs(delta) > 1e-12:
            c_raw = (ng - nuinf) / delta
            out[pre + "negative_C_fraction"] = float(np.mean(c_raw < -0.05))
            d = np.diff(ng)
            nt = np.abs(d) > 5.0
            wrong = nt & (np.sign(d) == np.sign(delta))
            out[pre + "nonmonotonic_fraction"] = float(wrong.sum() / max(nt.sum(), 1))
            over = float(np.max(nuinf - ng)) if delta > 0 else float(np.max(ng - nuinf))
            out[pre + "overshoot_cm-1"] = max(0.0, over)
        else:
            out.update({pre + "negative_C_fraction": np.nan, pre + "nonmonotonic_fraction": np.nan, pre + "overshoot_cm-1": np.nan})

    out["legacy_max_negative_spectral_area_fraction"] = float(np.nanmax(negfrac)) if np.any(np.isfinite(negfrac)) else np.nan
    out["legacy_boundary_peak_fraction"] = float(np.mean(boundary)) if len(boundary) else np.nan
    ff = fwhm[np.isfinite(fwhm)]
    out["legacy_fwhm_span_fraction"] = float((ff.max() - ff.min()) / np.median(ff)) if len(ff) >= 2 and np.median(ff) > 0 else np.nan
    if pk.available and cm is not None and cm.available:
        dd = abs(pk.delta_nu_cm1 - cm.delta_nu_cm1)
        out["legacy_peak_com_delta_disagreement_cm-1"] = dd
        out["legacy_peak_com_delta_disagreement_fraction"] = dd / max(abs(pk.delta_nu_cm1), abs(cm.delta_nu_cm1), 1e-12)
    return out
