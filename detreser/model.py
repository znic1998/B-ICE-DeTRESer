"""Session model: imported folders, folder levels, the run configuration and the run result.

Everything analytical is delegated to ``tres_suite``; this module only maps folders to
``project.files`` entries with labels, keeps the user's options and turns them into a
:class:`tres_suite.config.RunConfig`.
"""
from __future__ import annotations

import copy
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from tres_suite.config import RunConfig, config_from_dict
from tres_suite.project import LabelValue, LOCK_PREFIX, WORKBOOK_EXTENSIONS

# ------------------------------------------------------------------------------
# folder tree
# ------------------------------------------------------------------------------


@dataclass
class Node:
    """A folder (level >= 1) or a workbook (level == 0 is never used; files are leaves with ``is_file``)."""

    name: str
    path: str
    level: int  # 1 = imported root folder; files carry the level of their parent folder + 1
    is_file: bool = False
    children: List["Node"] = field(default_factory=list)
    parent: Optional["Node"] = None
    status: str = ""  # "" | "ok" | "blocked" (set on group-level folders after a run)
    block_reason: str = ""

    @property
    def labels(self) -> List[str]:
        """Folder names from the root down to (and including) this node (file stem for files)."""
        chain = []
        n: Optional[Node] = self
        while n is not None:
            chain.append(os.path.splitext(n.name)[0] if n.is_file else n.name)
            n = n.parent
        return list(reversed(chain))

    def files(self) -> List["Node"]:
        out = []
        for c in self.children:
            out += [c] if c.is_file else c.files()
        return out

    def folders_at(self, level: int) -> List["Node"]:
        if self.is_file:
            return []
        if self.level == level:
            return [self]
        out = []
        for c in self.children:
            out += c.folders_at(level)
        return out

    def key(self) -> Tuple[str, ...]:
        return tuple(self.labels)


def _is_workbook(fn: str) -> bool:
    return (not fn.startswith(".")) and (not fn.startswith(LOCK_PREFIX)) and fn.lower().endswith(WORKBOOK_EXTENSIONS)


def scan_folder(root: str) -> Node:
    """Build the tree below ``root`` (hidden entries skipped; empty folders kept so the user sees them)."""
    root = os.path.abspath(root)
    node = Node(os.path.basename(root.rstrip(os.sep)) or root, root, 1)

    def walk(n: Node) -> None:
        try:
            entries = sorted(os.listdir(n.path), key=lambda s: LabelValue.parse(os.path.splitext(s)[0]).sort_key())
        except OSError:
            return
        for e in entries:
            if e.startswith("."):
                continue
            p = os.path.join(n.path, e)
            if os.path.isdir(p):
                c = Node(e, p, n.level + 1, parent=n)
                n.children.append(c)
                walk(c)
            elif _is_workbook(e):
                n.children.append(Node(e, p, n.level + 1, is_file=True, parent=n))

    walk(node)
    return node


def file_depths(root: Node) -> List[int]:
    """Folder depth (root = 1) of every workbook's parent folder."""
    return sorted({f.level - 1 for f in root.files()})


# ------------------------------------------------------------------------------
# metrics offered on the comparison pages (label, backend metric key)
# ------------------------------------------------------------------------------
TRES_METRICS = [
    ("Mean lifetime ⟨τ⟩ (ns)", "tmean_ns"),
    ("GP", "gp"),
    ("Δν, peak (cm⁻¹)", "peak_delta_nu_cm-1"),
    ("τr, peak (ns)", "peak_tau_r_ns"),
    ("τ FWHM (ns)", "tau_fwhm_ns"),
    ("Δν, centre of mass (cm⁻¹)", "com_delta_nu_cm-1"),
    ("τr, centre of mass (ns)", "com_tau_r_ns"),
    ("FWHM maximum (cm⁻¹)", "fwhm_max_cm-1"),
    ("Global χ²", "global_chi_sq"),
]
ANISO_METRICS = [
    ("r∞ (limiting anisotropy)", "r_inf"),
    ("Rotational correlation time ⟨φ⟩ (ns)", "phi_mean_ns"),
    ("Microviscosity (Pa·s)", "wobble_eta_Pa_s"),
]
DEFAULT_AXIS_TITLES = {
    "tmean_ns": "⟨τ⟩ (ns)", "gp": "GP", "peak_delta_nu_cm-1": "Δν, peak (cm⁻¹)", "peak_tau_r_ns": "τr, peak (ns)", "tau_fwhm_ns": "τ FWHM (ns)",
    "com_delta_nu_cm-1": "Δν, COM (cm⁻¹)", "com_tau_r_ns": "τr, COM (ns)", "fwhm_max_cm-1": "FWHM max (cm⁻¹)", "global_chi_sq": "χ²",
    "r_inf": "r∞", "phi_mean_ns": "⟨φ⟩ (ns)", "wobble_eta_Pa_s": "Microviscosity (Pa·s)",
}

# single-sample plots: (section, label, plot type, extra PlotConfig fields)
SINGLE_PLOTS = [
    ("Spectra", "Normalized spectrum", "steady_state_spectrum", {}),
    ("Spectra", "Full TRES", "tdfs_spectra", {"extra": {"normalise": "none"}}),
    ("Spectra", "TRANES", "tdfs_spectra", {"extra": {"normalise": "area"}}),
    ("DAS", "Relative amplitude", "das_spectra", {"representation": "relative_amplitude"}),
    ("DAS", "Pre-exponential", "das_spectra", {"representation": "normalized_pre_exponential"}),
    ("DAS", "Bubble plot", "bubble", {}),
    ("TDFS", "Δν (spectral shift)", "tdfs_peak_vs_time", {"coordinate": "peak"}),
    ("TDFS", "FWHM", "tdfs_fwhm_vs_time", {}),
    ("TDFS", "τr (relaxation time)", "tdfs_relaxation", {"coordinate": "peak"}),
]
SINGLE_DEFAULTS = {"Normalized spectrum", "TRANES", "τr (relaxation time)"}


# ------------------------------------------------------------------------------
# advanced settings (defaults are the backend defaults)
# ------------------------------------------------------------------------------
def default_advanced() -> Dict[str, Any]:
    from tres_suite.tdfs import TdfsSettings
    from tres_suite.das import DasSettings
    from tres_suite.anisotropy import WobbleSettings
    from tres_suite.validation import ValidationThresholds
    from tres_suite.advanced.time_gated import TimeGatedSettings
    from tres_suite.config import OutputConfig
    td, da, wo, va, tg, ou = TdfsSettings(), DasSettings(), WobbleSettings(), ValidationThresholds(), TimeGatedSettings(), OutputConfig()
    return {
        "tdfs": {"recon_dt_ns": td.recon_dt_ns, "metric_tmin_ns": td.metric_tmin_ns, "tail_points": td.tail_points, "intensity_floor": td.intensity_floor,
                 "fwhm_smooth_window_ns": td.fwhm_smooth_window_ns, "clip_negative_c": td.clip_negative_c, "compute_com": td.compute_com},
        "das": {"amplitude_source": da.amplitude_source, "bubble_method": da.bubble_method, "gp_blue_nm": da.gp_blue_nm, "gp_red_nm": da.gp_red_nm},
        "wobble": {"phi_selection": wo.phi_selection, "r0_literature": wo.r0_literature},
        "validation": {"chi_sq_warning_threshold": 1.5, "chi_sq_is_reduced": True, "replicate_variation_warning_percent": 20.0,
                       "replicate_variation_metrics": list(va.replicate_variation_metrics), "anisotropy_correlation_time_tolerance_percent": 20.0,
                       "wavelength_tolerance_nm": va.wavelength_tolerance_nm, "min_wavelength_points": va.min_wavelength_points,
                       "allow_nonuniform_grid": va.allow_nonuniform_grid},
        "output": {"png": "png" in ou.image_formats, "svg": "svg" in ou.image_formats, "dpi": ou.dpi, "overwrite_policy": "ask",
                   "legacy_compatible": ou.legacy_compatible, "write_reconstructed_spectra": ou.write_reconstructed_spectra, "write_trajectories": ou.write_trajectories},
        "time_gated": {"enabled": tg.enabled, "gates_ns": [list(g) for g in tg.gates_ns], "gate_mode": tg.gate_mode},
        "project": {"workers": 4},
    }


# ------------------------------------------------------------------------------
# session
# ------------------------------------------------------------------------------
class Session:
    """Everything the pages share."""

    def __init__(self):
        self.roots: List[Node] = []
        self.level_names: List[str] = []  # user names for folder levels 1..N ("" -> "Level k")
        self.kind: str = "tres"  # detected measurement type: tres | anisotropy | mixed | unknown
        self.kind_detail: str = ""
        # options page
        self.probe: str = ""
        self.ratio_mode: str = "gp"  # gp | custom | none
        self.ratio_expression: str = "I(510) / I(430)"
        self.nu0_mode: str = "custom"  # apparent | custom
        self.nu0_value: str = "23800"
        self.visc_calculate: bool = True
        self.volume_value: str = "161"
        self.volume_unit: str = "A3"
        self.temp_mode: str = "level"  # level | fixed
        self.temp_level: int = 2
        self.temp_fixed: str = "293"
        self.r0_source: str = "literature"  # literature | fitted | user
        self.r0_custom: str = "0.40"
        self.advanced: Dict[str, Any] = default_advanced()
        # results
        self.result = None  # tres_suite.pipeline.RunResult
        self.run_dir: Optional[str] = None  # session output folder written after every run (used by exports and the fit review)
        self.plots_made: List[Any] = []  # PlotConfigs viewed or exported in this session (written with "Export full data")
        self.deconvolution: Dict[str, Any] = {}  # decisions per group folder (fit review)
        self._tmp_root = tempfile.mkdtemp(prefix="B-ICE-DeTRESer-")

    # ---- folders ---------------------------------------------------------------
    @property
    def n_levels(self) -> int:
        depths = sorted({d for r in self.roots for d in file_depths(r)})
        return depths[-1] if depths else 0

    def add_root(self, path: str) -> Optional[str]:
        """Add a data folder; returns an error message when it cannot be used."""
        path = os.path.abspath(path)
        if any(r.path == path for r in self.roots):
            return f"{os.path.basename(path)} is already loaded."
        for r in self.roots:
            if path.startswith(r.path + os.sep) or r.path.startswith(path + os.sep):
                return f"{os.path.basename(path)} overlaps the loaded folder {r.name}. Add sibling folders, not a folder and its parent."
        node = scan_folder(path)
        depths = file_depths(node)
        if not depths:
            return f"No Excel workbooks (.xlsx / .xlsm) were found inside {node.name}."
        if len(depths) > 1:
            return (f"{node.name} mixes workbooks at different folder depths ({', '.join(str(d) for d in depths)} levels). "
                    "Every replicate workbook must sit at the same depth.")
        if self.roots and depths[0] != self.n_levels:
            return (f"{node.name} has {depths[0]} folder level(s) but the loaded data has {self.n_levels}. "
                    "All data folders must have the same structure.")
        self.roots.append(node)
        self.roots.sort(key=lambda n: LabelValue.parse(n.name).sort_key())
        self.invalidate_result()
        return None

    def remove_root(self, path: str) -> None:
        self.roots = [r for r in self.roots if r.path != path]
        self.invalidate_result()

    def level_name(self, level: int) -> str:
        if 1 <= level <= len(self.level_names) and self.level_names[level - 1].strip():
            return self.level_names[level - 1].strip()
        return f"Level {level}"

    def all_level_names(self) -> List[str]:
        names = [self.level_name(k) for k in range(1, self.n_levels + 1)]
        # the replicate level must not collide with a user name
        rep = "Replicate"
        while rep in names:
            rep += "_"
        return names + [rep]

    def replicate_level_name(self) -> str:
        return self.all_level_names()[-1]

    def group_level(self) -> int:
        """Folder level whose folders are condition groups (the deepest folder level)."""
        return self.n_levels

    def all_files(self) -> List[Node]:
        return [f for r in self.roots for f in r.files()]

    # ---- config ----------------------------------------------------------------
    def build_config(self, output_dir: Optional[str] = None) -> RunConfig:
        names = self.all_level_names()
        files = []
        for f in self.all_files():
            labels = dict(zip(names, f.labels))
            files.append({"path": f.path, "labels": labels})
        adv = copy.deepcopy(self.advanced)
        das = {"amplitude_source": adv["das"]["amplitude_source"], "bubble_method": adv["das"]["bubble_method"],
               "gp_blue_nm": float(adv["das"]["gp_blue_nm"]), "gp_red_nm": float(adv["das"]["gp_red_nm"]),
               "gp_enabled": self.ratio_mode == "gp", "custom_ratios": {}}
        if self.ratio_mode == "custom" and self.ratio_expression.strip():
            das["custom_ratios"] = {"custom_ratio": self.ratio_expression.strip()}
        tdfs = dict(adv["tdfs"])
        tdfs["tail_points"] = int(tdfs["tail_points"])
        tdfs["nu0_cm1"] = _float_or_none(self.nu0_value) if self.nu0_mode == "custom" else None
        wobble = {"enabled": False}
        if self.kind == "anisotropy":
            wobble = {"enabled": bool(self.visc_calculate), "effective_volume": _float_or_none(self.volume_value), "effective_volume_unit": self.volume_unit,
                      "r0_source": self.r0_source, "r0_literature": float(adv["wobble"]["r0_literature"]), "phi_selection": adv["wobble"]["phi_selection"]}
            if self.r0_source == "user":
                wobble["r0"] = _float_or_none(self.r0_custom)
            if self.temp_mode == "level":
                wobble["temperature_level"] = self.level_name(self.temp_level)
                wobble["temperature_level_unit"] = "degC"
            else:
                wobble["temperature_K"] = _float_or_none(self.temp_fixed)
        val = dict(adv["validation"])
        val["replicate_variation_metrics"] = list(val.get("replicate_variation_metrics") or [])
        out = adv["output"]
        formats = [f for f, on in (("png", out["png"]), ("svg", out["svg"])) if on] or ["png"]
        d = {
            "project": {"level_names": names, "files": files, "workers": int(adv["project"]["workers"])},
            "output": {"directory": output_dir or os.path.join(self._tmp_root, "run"), "image_formats": formats, "dpi": int(out["dpi"]),
                       "legacy_compatible": bool(out["legacy_compatible"]), "write_reconstructed_spectra": bool(out["write_reconstructed_spectra"]),
                       "write_trajectories": bool(out["write_trajectories"]), "overwrite": True},
            "das": das, "tdfs": tdfs, "wobble": wobble, "validation": val,
            "time_gated": {"enabled": bool(adv["time_gated"]["enabled"]), "gates_ns": [list(map(float, g)) for g in adv["time_gated"]["gates_ns"]],
                           "gate_mode": adv["time_gated"]["gate_mode"]},
            "plots": [],
        }
        return config_from_dict(d)

    def new_run_dir(self) -> str:
        d = os.path.join(self._tmp_root, "run")
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        return d

    def invalidate_result(self) -> None:
        self.result = None
        self.run_dir = None
        self.plots_made = []
        self.deconvolution = {}
        for r in self.roots:
            for n in r.folders_at(self.n_levels):
                n.status, n.block_reason = "", ""

    # ---- results helpers --------------------------------------------------------
    def group_for_node(self, node: Node):
        """GroupResult whose key equals the folder chain of ``node`` (a group-level folder)."""
        if self.result is None:
            return None
        key = node.key()
        for g in self.result.groups:
            if tuple(g.group.key) == key:
                return g
        return None

    def mark_groups(self) -> None:
        if self.result is None:
            return
        for r in self.roots:
            for n in r.folders_at(self.group_level()):
                g = self.group_for_node(n)
                if g is None:
                    n.status, n.block_reason = "", ""
                else:
                    n.status = g.status
                    n.block_reason = ", ".join(g.block_reasons)

    def select_for_node(self, node: Node) -> Dict[str, str]:
        """Backend ``select`` criteria for every group below ``node``."""
        names = self.all_level_names()
        return {names[i]: v for i, v in enumerate(node.labels)}

    def blocked_summaries(self) -> List[Dict[str, Any]]:
        """For the Run-Errors popup: one entry per blocked group with reason and files."""
        if self.result is None:
            return []
        from tres_suite.validation import Severity
        out = []
        for g in self.result.groups:
            if g.status != "blocked":
                continue
            diags = [d for d in self.result.diagnostics if d.group_id == g.group.group_id and d.severity == Severity.ERROR]
            reasons = []
            details = []
            for d in diags:
                reasons.append(_friendly_rule(d.rule, d.message))
                obs = d.observed or {}
                if obs:
                    details.append(_friendly_observed(obs))
                elif d.files:
                    details.append(" · ".join(os.path.basename(f) for f in d.files[:4]))
            out.append({"name": " › ".join(g.group.key), "reasons": reasons or [", ".join(g.block_reasons)], "details": [x for x in details if x]})
        return out

    def warning_count(self) -> int:
        if self.result is None:
            return 0
        from tres_suite.validation import Severity
        return sum(1 for d in self.result.diagnostics if d.severity == Severity.WARNING)

    def metrics(self) -> List[Tuple[str, str]]:
        """(label, key) list for the comparison dropdown: the standard metrics first, then every other numeric metric."""
        base = list(ANISO_METRICS if self.kind == "anisotropy" else TRES_METRICS)
        if self.kind != "anisotropy" and self.ratio_mode == "custom":
            base.insert(2, (f"Custom ratio {self.ratio_expression.strip()}", "custom_ratio"))
        if self.result is None:
            return base
        keys = {k for _, k in base}
        extra = sorted({k[:-5] for g in self.result.ok_groups(self.kind if self.kind in ("tres", "anisotropy") else None) for k in g.summary
                        if k.endswith("_mean") and not k.startswith("label:")})
        return base + [(k, k) for k in extra if k not in keys and not k.startswith("legacy_")]

    def cleanup(self) -> None:
        shutil.rmtree(self._tmp_root, ignore_errors=True)


def _float_or_none(s: str) -> Optional[float]:
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


_RULE_TEXT = {
    "component_count_mismatch": "Replicates have different numbers of components",
    "wavelength_range_mismatch": "Wavelength ranges don’t match",
    "wavelength_grid_mismatch": "Wavelength grids don’t match",
    "nonuniform_wavelength_grid": "Uneven wavelength spacing",
    "mixed_workbook_types": "TRES and anisotropy files are mixed in one group",
    "empty_group": "No readable workbook in the group",
    "duplicate_identifier": "The same file is listed twice",
    "insufficient_wavelength_points": "Too few wavelength points",
    "invalid_lifetimes": "Invalid lifetimes in a workbook",
    "invalid_total_counts": "Invalid total counts in a workbook",
    "invalid_correlation_times": "Invalid rotational correlation times",
    "missing_residual_anisotropy": "Residual anisotropy (r∞) missing",
    "analysis_failed": "A replicate could not be analysed",
}


def _friendly_rule(rule: str, message: str) -> str:
    for k, v in _RULE_TEXT.items():
        if rule.startswith(k) or k in rule:
            return v
    return rule.replace("_", " ").capitalize()


def _friendly_observed(obs: Dict[str, Any]) -> str:
    parts = []
    for k, v in obs.items():
        if isinstance(v, dict):
            parts.append(" · ".join(f"{os.path.basename(str(kk))} {_short(vv, k)}" for kk, vv in v.items()))
        else:
            parts.append(f"{os.path.basename(str(k))} {_short(v, k)}")
    return " · ".join(parts)[:400]


def _short(v: Any, key: str = "") -> str:
    unit = " nm" if key.endswith("_nm") else ""
    if isinstance(v, float):
        return f"= {v:g}{unit}"
    if isinstance(v, (list, tuple)):
        if len(v) == 2 and key in ("min_max_nm", "range_nm") and all(isinstance(x, (int, float)) for x in v):
            return f"{v[0]:g}–{v[1]:g}{unit}"
        if key == "intervals_nm":
            return "step " + ", ".join(f"{x:g}" for x in v[:6]) + unit
        return "= [" + ", ".join(_short(x).lstrip("= ") for x in v[:6]) + ("…" if len(v) > 6 else "") + "]"
    return f"= {v}{unit}" if key.endswith("_nm") and isinstance(v, (int, float)) else f"= {v}"
