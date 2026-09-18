"""Run configuration (loaded from YAML or JSON, or built in code by a GUI)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence

from .advanced.time_gated import TimeGatedSettings
from .anisotropy import WobbleSettings
from .das import DasSettings
from .tdfs import TdfsSettings
from .validation import ValidationThresholds


@dataclass
class FileEntry:
    path: str
    labels: Dict[str, str]


@dataclass
class ProjectConfig:
    level_names: List[str] = field(default_factory=lambda: ["Composition", "Temperature", "Replicate"])
    replicate_level: Optional[str] = None
    folder_depth: Optional[int] = None  # None -> len(level_names)-1 (workbook file is the replicate)
    import_folders: List[str] = field(default_factory=list)
    files: List[FileEntry] = field(default_factory=list)
    numeric_levels: List[str] = field(default_factory=list)  # levels whose labels should parse as numbers (checked)
    workers: int = 1  # parallel workbook parsing processes (1 = sequential; results are identical)


@dataclass
class OutputConfig:
    directory: str = "tres_suite_output"
    image_formats: List[str] = field(default_factory=lambda: ["png", "svg"])
    dpi: int = 300
    legacy_compatible: bool = True
    write_reconstructed_spectra: bool = True
    write_trajectories: bool = True
    overwrite: bool = False  # refuse to write into a non-empty directory unless true


@dataclass
class SeriesConfig:
    label: str
    select: Dict[str, Any] = field(default_factory=dict)  # level -> value(s); empty = every group
    color: Optional[str] = None  # default palette index or hex
    marker: Optional[str] = None
    line_style: Optional[str] = None
    line_width: Optional[float] = None


@dataclass
class PlotConfig:
    type: str  # metric_vs_label | metric_vs_metric | das_spectra | bubble | tdfs_spectra | tdfs_peak_vs_time | tdfs_relaxation | tdfs_trajectory
    name: str
    series: List[SeriesConfig] = field(default_factory=list)
    x: Optional[str] = None  # metric name or level name
    y: Optional[str] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    x_limits: Optional[List[float]] = None
    y_limits: Optional[List[float]] = None
    error_bars: bool = True
    fit: bool = False  # linear fit + R² for metric_vs_metric / metric_vs_label
    group: Optional[Dict[str, Any]] = None  # single group selection for DAS/bubble/TDFS plots
    times_ns: Optional[List[float]] = None  # for tdfs_spectra
    representation: str = "relative_amplitude"  # or normalized_pre_exponential (das_spectra)
    coordinate: str = "peak"  # peak | com (tdfs_relaxation / peak_vs_time)
    title: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunConfig:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    das: DasSettings = field(default_factory=DasSettings)
    tdfs: TdfsSettings = field(default_factory=TdfsSettings)
    tdfs_enabled: bool = True
    wobble: WobbleSettings = field(default_factory=WobbleSettings)
    validation: ValidationThresholds = field(default_factory=ValidationThresholds)
    time_gated: TimeGatedSettings = field(default_factory=TimeGatedSettings)  # advanced, off by default
    plots: List[PlotConfig] = field(default_factory=list)
    seed: int = 0  # no randomised procedure is used; recorded for completeness

    def to_dict(self) -> Dict[str, Any]:
        """Serialise so that ``config_from_dict(cfg.to_dict())`` reproduces ``cfg`` exactly."""
        d = asdict(self)
        tdfs = asdict(self.tdfs)
        tdfs["export_times_ns"] = list(self.tdfs.export_times_ns)
        tdfs["enabled"] = bool(self.tdfs_enabled)  # stored inside the tdfs section, where the loader reads it
        d.pop("tdfs_enabled", None)
        d["tdfs"] = tdfs
        d["time_gated"] = self.time_gated.to_dict()
        d["validation"]["replicate_variation_metrics"] = list(self.validation.replicate_variation_metrics)
        return d


def _build(cls, data: Optional[Dict[str, Any]], path: str = ""):
    data = dict(data or {})
    fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    unknown = sorted(set(data) - fields)
    if unknown:
        raise ValueError(f"unknown key(s) {unknown} in config section '{path or cls.__name__}'; allowed: {sorted(fields)}")
    return cls(**data)


def config_from_dict(d: Dict[str, Any]) -> RunConfig:
    d = dict(d or {})
    proj = dict(d.get("project", {}))
    files = [FileEntry(**f) if isinstance(f, dict) else f for f in proj.pop("files", [])]
    project = _build(ProjectConfig, proj, "project")
    project.files = files
    plots_raw = d.get("plots", [])
    plots = []
    for p in plots_raw:
        p = dict(p)
        series = [SeriesConfig(**s) if isinstance(s, dict) else s for s in p.pop("series", [])]
        pc = _build(PlotConfig, p, f"plots[{p.get('name', '?')}]")
        pc.series = series
        plots.append(pc)
    tdfs_raw = dict(d.get("tdfs", {}))
    tdfs_raw.pop("nu0_mode", None)  # derived, read-only field written by older run_config.json files
    tdfs_enabled = bool(tdfs_raw.pop("enabled", d.get("tdfs_enabled", True)))
    if "export_times_ns" in tdfs_raw:
        tdfs_raw["export_times_ns"] = tuple(tdfs_raw["export_times_ns"])
    val_raw = dict(d.get("validation", {}))
    if "replicate_variation_metrics" in val_raw:
        val_raw["replicate_variation_metrics"] = tuple(val_raw["replicate_variation_metrics"])
    tg_raw = dict(d.get("time_gated", {}))
    if "gates_ns" in tg_raw:
        tg_raw["gates_ns"] = tuple(tuple(g) for g in tg_raw["gates_ns"])
    if "common_time_ns" in tg_raw:
        tg_raw["common_time_ns"] = tuple(tg_raw["common_time_ns"])
    cfg = RunConfig(
        project=project,
        output=_build(OutputConfig, d.get("output"), "output"),
        das=_build(DasSettings, d.get("das"), "das"),
        tdfs=_build(TdfsSettings, tdfs_raw, "tdfs"),
        tdfs_enabled=tdfs_enabled,
        wobble=_build(WobbleSettings, d.get("wobble"), "wobble"),
        validation=_build(ValidationThresholds, val_raw, "validation"),
        time_gated=_build(TimeGatedSettings, tg_raw, "time_gated"),
        plots=plots,
        seed=int(d.get("seed", 0)),
    )
    return cfg


def load_config(path: str) -> RunConfig:
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as fh:
        if ext in (".yaml", ".yml"):
            import yaml  # PyYAML

            data = yaml.safe_load(fh) or {}
        else:
            data = json.load(fh)
    cfg = config_from_dict(data)
    # resolve relative paths against the config file location
    base = os.path.dirname(os.path.abspath(path))
    cfg.project.import_folders = [f if os.path.isabs(f) else os.path.join(base, f) for f in cfg.project.import_folders]
    for fe in cfg.project.files:
        if not os.path.isabs(fe.path):
            fe.path = os.path.join(base, fe.path)
    if not os.path.isabs(cfg.output.directory):
        cfg.output.directory = os.path.join(base, cfg.output.directory)
    return cfg
