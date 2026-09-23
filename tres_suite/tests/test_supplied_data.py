"""Integration tests against the supplied data (skipped when it is not available)."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from conftest import LEGACY, needs_legacy

from tres_suite.config import config_from_dict
from tres_suite.das import DasSettings, compute_das
from tres_suite.pipeline import run_project
from tres_suite.tdfs import TdfsSettings, compute_tdfs
from tres_suite.validation import Severity
from tres_suite.workbook import load_workbook

pytestmark = needs_legacy


@pytest.fixture(scope="module")
def error_run():
    cfg = config_from_dict({"project": {"level_names": ["Case", "Replicate"], "import_folders": [os.path.join(LEGACY, "Error")]},
                            "validation": {"chi_sq_warning_threshold": 1.5, "replicate_variation_warning_percent": 15.0,
                                           "anisotropy_correlation_time_tolerance_percent": 20},
                            "tdfs": {"trajectory_stride": 4}})
    return run_project(cfg)


def _rules(res, case, severity=None):
    return {d.rule for d in res.diagnostics if d.group == case and (severity is None or d.severity == severity)}


def test_error_cases(error_run):
    res = error_run
    status = {g.group.name: g.status for g in res.groups}
    assert res.status == "partially_completed"
    assert status == {"1": "blocked", "2": "blocked", "3": "blocked", "4": "ok", "5": "ok", "6": "blocked", "7": "ok"}
    assert "component_count_mismatch" in _rules(res, "1", Severity.ERROR)
    d = [x for x in res.diagnostics if x.group == "1" and x.rule == "component_count_mismatch"][0]
    assert d.observed["n_components"] == {"2 fit.xlsx": 2, "5 fit.xlsx": 5}
    assert "wavelength_range_mismatch" in _rules(res, "2", Severity.ERROR)
    d = [x for x in res.diagnostics if x.group == "2" and x.rule == "wavelength_range_mismatch"][0]
    assert d.observed["min_max_nm"] == {"1.xlsx": [435.0, 525.0], "2.xlsx": [420.0, 540.0]}
    assert "wavelength_grid_mismatch" in _rules(res, "3", Severity.ERROR)
    d = [x for x in res.diagnostics if x.group == "3" and x.rule == "wavelength_grid_mismatch"][0]
    assert d.observed["intervals_nm"] == {"1.xlsx": [1.0], "2.xlsx": [5.0]}
    assert _rules(res, "4", Severity.ERROR) == set() and "high_chi_sq" in _rules(res, "4", Severity.WARNING)
    assert _rules(res, "5", Severity.ERROR) == set() and "replicate_variation_high" in _rules(res, "5", Severity.WARNING)
    d = [x for x in res.diagnostics if x.group == "5" and x.rule == "replicate_variation_high" and x.metric == "tmean_ns"][0]
    assert {"mean", "sample_sd", "sd_percent_of_mean", "values"} <= set(d.observed)
    assert "mixed_workbook_types" in _rules(res, "6", Severity.ERROR)
    assert _rules(res, "7", Severity.ERROR) == set() and {"anisotropy_lifetime_difference", "anisotropy_component_count_differs"} <= _rules(res, "7", Severity.WARNING)
    # blocked groups have no summary; ok groups report n
    assert all(g.summary == {} for g in res.groups if g.status == "blocked")
    assert res.group_by_id([g.group.group_id for g in res.groups if g.group.name == "4"][0]).summary["tmean_ns_n"] == 21


def test_legacy_reference_reproduced_with_legacy_settings():
    ref = pd.read_csv(os.path.join(LEGACY, "TEST DATA/RESULTS/TDFS FOLDER/TDFS_TEST_out_replicates.csv"))
    rows = ref[ref.file.isin(["dopc 3 200 um tempo 3mm.xlsx", "dppc 2 200um tempo 3mm.xlsx"])]
    assert len(rows) == 2
    for _, r in rows.iterrows():
        path = os.path.join(LEGACY, "TEST DATA/DATA", r["composition"], str(r["temperature"]), r["file"])
        wb = load_workbook(path)
        das = compute_das(wb, DasSettings(amplitude_source="summary"))
        # legacy tau_r integrated from metric_tmin_ns even with a user nu0
        td = compute_tdfs(wb.wavelengths_nm, das.lifetimes_ns, das.normalized_pre_exponential, das.fss_area_norm,
                          TdfsSettings(nu0_cm1=23800.0, tau_r_from_zero_with_user_nu0=False), das.mean_lifetime_ns)
        rec = td.scalar_record()
        assert das.metrics["gp"].value == pytest.approx(r["gp"], abs=1e-9)
        assert das.mean_lifetime_ns == pytest.approx(r["tmean_ns"], abs=1e-5)  # legacy used 6-digit Summary lifetimes
        assert rec["peak_delta_nu_cm-1"] == pytest.approx(r["peak_delta_nu_cm-1"], abs=1.0)
        assert rec["peak_tau_r_ns"] == pytest.approx(r["peak_tau_r_ns"], abs=1e-3)
        assert rec["com_delta_nu_cm-1"] == pytest.approx(r["com_delta_nu_cm-1"], abs=1.0)
        assert rec["com_tau_r_ns"] == pytest.approx(r["com_tau_r_ns"], abs=1e-3)
        assert rec["legacy_x_kinetic"] == pytest.approx(r["x_kinetic"], rel=1e-4)


def test_all_supported_component_counts_in_supplied_data():
    for rel, n in [("Error/1/2 fit.xlsx", 2), ("TEST DATA/DATA/DOPC TEMPO Raw Data/0/dopc 2 200um.xlsx", 3), ("Error/1/5 fit.xlsx", 5),
                   ("Error/7/26 1.xlsx", 1), ("Error/7/23 1.xlsx", 2)]:
        wb = load_workbook(os.path.join(LEGACY, rel))
        assert wb.n_components == n


def test_four_component_workbooks_parse_and_analyse():
    folder = os.path.join(LEGACY, "4 fit")
    if not os.path.isdir(folder):
        pytest.skip("4-component folder not available")
    cfg = config_from_dict({"project": {"level_names": ["Replicate"], "import_folders": [folder], "workers": 2},
                            "tdfs": {"trajectory_stride": 4}})
    res = run_project(cfg)
    g = res.groups[0]
    assert res.status == "completed" and g.n_replicates == 21
    for r in g.replicates:
        assert r.das.n_components == 4 and np.all(np.diff(r.das.lifetimes_ns) >= 0)
        assert r.das.area_percent.sum() == pytest.approx(100.0) and np.isfinite(r.scalars["tmean_ns"])
        assert r.tdfs.peak.available
        wb = r.measurement.workbook
        assert np.nanmax(np.abs(wb.summary_relative_amplitude_percent - wb.components.relative_amplitude_percent)) <= 0.0051


def test_time_gated_advanced_feature():
    from tres_suite.advanced.time_gated import analyse_time_gated, TimeGatedSettings, read_data_sheet
    d = os.path.join(LEGACY, "TEST DATA/DATA/DOPC TEMPO Raw Data/0")
    paths = sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".xlsx"))
    t, wl, data = read_data_sheet(paths[0])
    assert len(wl) == 25 and data.shape == (len(t), 25) and 0 < t[1] - t[0] < 0.1  # ns
    out = analyse_time_gated(paths, TimeGatedSettings(enabled=True))
    assert out["avg_matrix"].shape == (1040, 25) and out["gated_spectra"].shape == (3, 25)
    assert np.allclose(np.abs(np.trapz(out["gated_spectra"], wl, axis=1)) if hasattr(np, "trapz") else np.abs(np.trapezoid(out["gated_spectra"], wl, axis=1)), 1.0)
    assert len(out["metric_time_ns"]) > 10 and np.isfinite(out["C_t"]).any()
