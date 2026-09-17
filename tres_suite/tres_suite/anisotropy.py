"""Time-resolved anisotropy: base quantities and the optional rotational-diffusion add-on.

Base quantities are read from the EzTime fit and reported for **any** probe::

    r(t) = r_inf + Σ_i B_i exp(-t/φ_i),    r(0) = r_inf + Σ_i B_i

* ``φ_i``   rotational correlation times (ns), ranked ascending
* ``B_i``   amplitudes;  ``α_i = B_i / Σ|B_j|``;  ``RA_i`` percent (from Summary)
* ``r_inf`` residual (limiting) anisotropy
* ``r0_fitted``  fitted time-zero anisotropy ``r_inf + Σ B_i``
* ``phi_mean_ns``  amplitude-weighted mean correlation time ``Σ α_i φ_i`` (EzTime "Ave T/ns")

Optional add-on (``WobbleSettings.enabled``): apparent microviscosity by the
Stokes-Einstein-Debye-type formalism used in the supplied paper::

    k   = r_inf / r0
    D⊥  = (0.1674 − 0.1066·k − 0.0062·k²) / φ        [ns⁻¹]  (Kinosita wobbling-in-cone approximation)
    η   = k_B T / (6 · D⊥ · V_eff)                     [Pa·s]; also reported in Poise (×10)

The add-on requires ``effective_volume`` with a unit (``A3``/``nm3``/``cm3``/``m3``;
the legacy constant ``161e-22`` with output in Poise corresponds to 161 Å³) and
``temperature_K`` explicitly; r_0 comes from ``r0_source``.
Which correlation time enters as ``φ`` is chosen by ``phi_selection``
(``"mean"`` reproduces the legacy behaviour, which used EzTime's average).

The model uses an effective hydrodynamic *volume* (the "molecular area" wording
of the brief was confirmed to mean this quantity, entered in a selectable unit).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import numpy as np

from .workbook import AnisotropyWorkbook

K_B = 1.380649e-23  # J/K (CODATA 2018 exact)
_VOLUME_UNITS = {"m3": 1.0, "cm3": 1e-6, "nm3": 1e-27, "a3": 1e-30, "å3": 1e-30, "angstrom3": 1e-30}
LITERATURE_R0_DEFAULT = 0.39  # fundamental anisotropy used by the legacy dph() (DPH/TMA-DPH literature value)


@dataclass
class WobbleSettings:
    enabled: bool = False
    effective_volume: Optional[float] = None
    effective_volume_unit: Optional[str] = None  # "A3" | "nm3" | "m3"
    temperature_K: Optional[float] = None
    temperature_level: Optional[str] = None  # read T per group from this hierarchy level's numeric label instead of temperature_K
    temperature_level_unit: str = "degC"  # unit assumed for labels without one ("degC" | "K"); labels like "17C"/"300K" carry their own
    r0: Optional[float] = None  # fundamental anisotropy for r0_source == "user"
    r0_source: str = "literature"  # "literature" (r0_literature, default 0.39) | "fitted" (workbook R0) | "user" (r0)
    r0_literature: float = LITERATURE_R0_DEFAULT
    phi_selection: str = "mean"  # "mean" | "longest" | "shortest" | "component:<k>"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def missing(self) -> List[str]:
        miss: List[str] = []
        if self.effective_volume is None or not np.isfinite(self.effective_volume) or self.effective_volume <= 0:
            miss.append("effective_volume (positive number)")
        if not self.effective_volume_unit or self.effective_volume_unit.lower() not in _VOLUME_UNITS:
            miss.append("effective_volume_unit (A3, nm3, cm3 or m3)")
        if self.temperature_level:
            if self.temperature_level_unit not in ("degC", "K"):
                miss.append("temperature_level_unit must be 'degC' or 'K'")
        elif self.temperature_K is None or not np.isfinite(self.temperature_K) or self.temperature_K <= 0:
            miss.append("temperature_K (positive)")
        if self.r0_source == "user" and (self.r0 is None or not np.isfinite(self.r0) or self.r0 <= 0):
            miss.append("r0 (fundamental anisotropy) for r0_source='user'")
        if self.r0_source == "literature" and (self.r0_literature is None or not np.isfinite(self.r0_literature) or self.r0_literature <= 0):
            miss.append("r0_literature (positive) for r0_source='literature'")
        if self.r0_source not in ("user", "fitted", "literature"):
            miss.append("r0_source must be 'literature', 'fitted' or 'user'")
        return miss


@dataclass
class AnisotropyResult:
    n_components: int
    phi_ns: np.ndarray
    phi_sigma_ns: np.ndarray
    amplitudes: np.ndarray
    normalized_amplitudes: np.ndarray
    relative_amplitude_percent: Optional[np.ndarray]
    r_inf: Optional[float]
    r_inf_sigma: Optional[float]
    r0_fitted: Optional[float]
    phi_mean_ns: Optional[float]
    chi_sq: Optional[float]
    wobble: Dict[str, Any]

    def scalar_record(self) -> Dict[str, Any]:
        rec: Dict[str, Any] = {"n_comp": self.n_components, "r_inf": self.r_inf, "r_inf_sigma": self.r_inf_sigma,
                               "r0_fitted": self.r0_fitted, "phi_mean_ns": self.phi_mean_ns, "chi_sq": self.chi_sq}
        for i in range(self.n_components):
            rec[f"phi{i + 1}_ns"] = float(self.phi_ns[i])
            rec[f"phi{i + 1}_sigma_ns"] = float(self.phi_sigma_ns[i])
            rec[f"B{i + 1}"] = float(self.amplitudes[i])
            rec[f"alpha{i + 1}"] = float(self.normalized_amplitudes[i])
            if self.relative_amplitude_percent is not None:
                rec[f"ra{i + 1}_percent"] = float(self.relative_amplitude_percent[i])
        rec.update({f"wobble_{k}": v for k, v in self.wobble.items()})
        return rec


def _select_phi(res: "AnisotropyResult", selection: str) -> Optional[float]:
    if selection == "mean":
        return res.phi_mean_ns
    if selection == "longest":
        return float(np.max(res.phi_ns))
    if selection == "shortest":
        return float(np.min(res.phi_ns))
    if selection.startswith("component:"):
        k = int(selection.split(":", 1)[1])
        if 1 <= k <= len(res.phi_ns):
            return float(res.phi_ns[k - 1])
    return None


def temperature_from_label(label, ws: "WobbleSettings") -> Optional[float]:
    """Kelvin from a hierarchy :class:`LabelValue` (``17``, ``17C``, ``300K``); ``None`` when the label is not numeric."""
    if label is None or getattr(label, "number", None) is None:
        return None
    unit = label.unit or ws.temperature_level_unit
    if unit == "K":
        return float(label.number)
    if unit == "degC":
        return float(label.number) + 273.15
    if unit == "degF":
        return (float(label.number) - 32.0) * 5.0 / 9.0 + 273.15
    return None


def compute_anisotropy(wb: AnisotropyWorkbook, wobble: Optional[WobbleSettings] = None) -> AnisotropyResult:
    phi_mean = wb.mean_correlation_time_ns
    if phi_mean is None and np.all(np.isfinite(wb.normalized_amplitudes)):
        phi_mean = float(np.dot(wb.normalized_amplitudes, wb.rotational_correlation_times_ns))
    res = AnisotropyResult(
        wb.n_components, np.asarray(wb.rotational_correlation_times_ns, float), np.asarray(wb.rotational_correlation_sigma_ns, float),
        np.asarray(wb.amplitudes, float), np.asarray(wb.normalized_amplitudes, float), wb.relative_amplitude_percent,
        wb.r_inf, wb.r_inf_sigma, wb.r0_fitted, phi_mean, wb.chi_sq, {},
    )
    res.wobble = apply_wobble(res, wobble)
    return res


def apply_wobble(res: AnisotropyResult, ws: Optional[WobbleSettings]) -> Dict[str, Any]:
    """Return the add-on record.  Base quantities are never touched."""
    if ws is None or not ws.enabled:
        return {"enabled": False, "status": "disabled"}
    miss = ws.missing()
    if miss:
        return {"enabled": True, "status": "blocked: missing parameters", "missing": miss}
    if ws.temperature_K is None or not np.isfinite(ws.temperature_K) or ws.temperature_K <= 0:
        return {"enabled": True, "status": f"unavailable: no numeric temperature label at level {ws.temperature_level!r}",
                "temperature_level": ws.temperature_level}
    r0 = {"fitted": res.r0_fitted, "user": ws.r0, "literature": ws.r0_literature}[ws.r0_source]
    phi = _select_phi(res, ws.phi_selection)
    out: Dict[str, Any] = {"enabled": True, "r0_used": r0, "r0_source": ws.r0_source, "phi_selection": ws.phi_selection,
                           "phi_used_ns": phi, "temperature_K": ws.temperature_K, "temperature_source": (f"level:{ws.temperature_level}" if ws.temperature_level else "fixed"),
                           "effective_volume_m3": ws.effective_volume * _VOLUME_UNITS[ws.effective_volume_unit.lower()],
                           "model": "D_perp = (0.1674 - 0.1066 k - 0.0062 k^2)/phi, k = r_inf/r0; eta = kB T / (6 D_perp V_eff)"}
    if res.r_inf is None or r0 is None or r0 <= 0 or phi is None or phi <= 0:
        out["status"] = "unavailable: r_inf, r0 or phi missing/non-positive"
        return out
    k = res.r_inf / r0
    out["k_rinf_over_r0"] = k
    if k < 0 or k > 1:
        out["note"] = "r_inf/r0 outside [0, 1]; the polynomial approximation is not meant for this range"
    d_perp_ns = (0.1674 - 0.1066 * k - 0.0062 * k * k) / phi
    out["D_perp_per_ns"] = d_perp_ns
    if d_perp_ns <= 0:
        out["status"] = "unavailable: non-positive D_perp"
        return out
    eta_pa_s = K_B * ws.temperature_K / (6.0 * d_perp_ns * 1e9 * out["effective_volume_m3"])
    out.update({"eta_Pa_s": eta_pa_s, "eta_poise": eta_pa_s * 10.0, "status": "ok"})
    return out
