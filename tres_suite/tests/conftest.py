"""Test fixtures: synthetic EzTime-style workbooks built with openpyxl.

The synthetic writer mirrors the real export layout (Summary blocks, Results
'Global' block and per-fit table) so the structure-based parser is exercised
without the large supplied data set.  Integration tests use the real data when
``TRES_LEGACY_INPUT`` points at the supplied folder (or the default location).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import openpyxl
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

LEGACY = os.environ.get("TRES_LEGACY_INPUT", os.path.join(os.path.dirname(__file__), "..", "..", "legacy_input"))


def has_legacy() -> bool:
    return os.path.isdir(os.path.join(LEGACY, "Error")) and os.path.isdir(os.path.join(LEGACY, "TEST DATA"))


needs_legacy = pytest.mark.skipif(not has_legacy(), reason="supplied legacy data not available")


def make_tres_workbook(path, wavelengths, taus, B, counts, chi_global=1.0, chi_wl=None, with_summary=True, sigma=None):
    """Write a synthetic TRES export.  B: (n_wl, n_comp) signed pre-exponentials."""
    wavelengths = np.asarray(wavelengths, float)
    taus = np.asarray(taus, float)
    B = np.asarray(B, float)
    counts = np.asarray(counts, float)
    n = len(taus)
    sigma = np.full(n, 0.01) if sigma is None else np.asarray(sigma, float)
    chi_wl = np.ones(len(wavelengths)) if chi_wl is None else np.asarray(chi_wl, float)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Summary"
    model = "1-5 exponentials: A+ " + "+ ".join(f"B{i + 1}*exp(-i/T{i + 1})" for i in range(n))
    if with_summary:
        ws.cell(1, 1, model)
        r = 3
        for k, wl in enumerate(wavelengths):
            ws.cell(r, 1, f"{wl:g}-DECAY"); ws.cell(r, 2, k + 1); ws.cell(r, 3, "Wavelength/nm"); ws.cell(r, 4, float(wl))
            ws.cell(r + 1, 3, "Value"); ws.cell(r + 1, 4, "±"); ws.cell(r + 1, 5, "3σ"); ws.cell(r + 1, 8, "Relative Amplitude"); ws.cell(r + 1, 9, "Normalised pre-exponential")
            btau = np.abs(B[k]) * taus
            ra = 100 * btau / btau.sum() if btau.sum() else np.zeros(n)
            al = B[k] / np.abs(B[k]).sum() if np.abs(B[k]).sum() else np.zeros(n)
            for i in range(n):
                ws.cell(r + 2 + i, 1, f"T{i + 1}"); ws.cell(r + 2 + i, 2, "="); ws.cell(r + 2 + i, 3, f"{taus[i]:.6g}")
                ws.cell(r + 2 + i, 4, "±"); ws.cell(r + 2 + i, 5, f"{3 * sigma[i]:.6g}"); ws.cell(r + 2 + i, 6, "ns")
                ws.cell(r + 2 + i, 8, f"{ra[i]:.2f}"); ws.cell(r + 2 + i, 9, f"{al[i]:.2f}")
            ws.cell(r + 2 + n, 1, "A"); ws.cell(r + 2 + n, 2, "="); ws.cell(r + 2 + n, 3, "0")
            ws.cell(r + 3 + n, 1, "Average LifeTime"); ws.cell(r + 3 + n, 2, "="); ws.cell(r + 3 + n, 3, f"{float(al @ taus):.6g}")
            ws.cell(r + 4 + n, 1, "Chi sq."); ws.cell(r + 4 + n, 2, f"{chi_wl[k]:.5g}")
            r += n + 6
    rs = wb.create_sheet("Results")
    rs.cell(1, 1, "Fit Name"); rs.cell(2, 1, "Fit"); rs.cell(3, 1, model)
    rs.cell(8, 1, "Global")
    hdr = []
    for i in range(n):
        hdr += [f"T{i + 1}/ns", f"σ T{i + 1}/ns"]
    hdr.append("Chi sq.")
    vals = []
    for i in range(n):
        vals += [float(taus[i]), float(sigma[i])]
    vals.append(float(chi_global))
    for c, h in enumerate(hdr, start=1):
        rs.cell(9, c, h); rs.cell(10, c, vals[c - 1])
    cols = ["Name", "Number", "Chi sq.", "Wavelength/nm", "ShiftLimit/ns", "σ ShiftLimit/ns", "Shift/ns", "σ Shift/ns", "A", "σ A"]
    cols += [f"B{i + 1}" for i in range(n)] + [f"σ B{i + 1}" for i in range(n)] + [f"α{i + 1}" for i in range(n)] + ["Ave T/ns", "Peak count", "Total count"]
    for c, h in enumerate(cols, start=1):
        rs.cell(12, c, h)
    for k, wl in enumerate(wavelengths):
        al = B[k] / np.abs(B[k]).sum() if np.abs(B[k]).sum() else np.zeros(n)
        row = [f"{wl:g}-DECAY", k + 1, float(chi_wl[k]), float(wl), 0.16, 0, 0.0, 0.0, 0.0, 0.0]
        row += [float(x) for x in B[k]] + [0.001] * n + [float(x) for x in al] + [float(al @ taus), float(counts[k] / 50), float(counts[k])]
        for c, v in enumerate(row, start=1):
            rs.cell(13 + k, c, v)
    wb.create_sheet("Data").cell(1, 1, "Bin")
    wb.save(path)
    return path


def make_anisotropy_workbook(path, phis, B, r_inf, r0, chi=1.0):
    phis = np.asarray(phis, float); B = np.asarray(B, float); n = len(phis)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Summary"
    ws.cell(1, 1, "Anisotropy: R(inf)+ " + "+ ".join(f"B{i + 1}*exp(-i/T{i + 1})" for i in range(n)) + " with: R(0) = R(inf) + " + "+ ".join(f"B{i + 1}" for i in range(n)))
    ws.cell(3, 1, "Difference"); ws.cell(3, 2, 1)
    ws.cell(4, 3, "Value"); ws.cell(4, 8, "Relative Amplitude"); ws.cell(4, 9, "Normalised pre-exponential")
    al = B / np.abs(B).sum(); ra = 100 * np.abs(B) * phis / (np.abs(B) * phis).sum()
    r = 5
    for i in range(n):
        ws.cell(r, 1, f"T{i + 1}"); ws.cell(r, 2, "="); ws.cell(r, 3, f"{phis[i]:.6g}"); ws.cell(r, 6, "ns"); ws.cell(r, 8, f"{ra[i]:.2f}"); ws.cell(r, 9, f"{al[i]:.2f}"); r += 1
    ws.cell(r, 1, "Rinf"); ws.cell(r, 2, "="); ws.cell(r, 3, f"{r_inf:.6g}"); r += 1
    ws.cell(r, 1, "R0"); ws.cell(r, 2, "="); ws.cell(r, 3, f"{r0:.6g}"); r += 1
    ws.cell(r, 1, "Average LifeTime"); ws.cell(r, 2, "="); ws.cell(r, 3, f"{float(al @ phis):.6g}"); r += 1
    ws.cell(r, 1, "Chi sq."); ws.cell(r, 2, f"{chi:.5g}")
    rs = wb.create_sheet("Results")
    rs.cell(1, 1, "Fit Name"); rs.cell(3, 1, "Anisotropy: R(inf)+ B1*exp(-i/T1)")
    rs.cell(8, 1, "Global")
    hdr = []
    for i in range(n):
        hdr += [f"T{i + 1}/ns", f"σ T{i + 1}/ns"]
    hdr.append("Chi sq.")
    vals = []
    for i in range(n):
        vals += [float(phis[i]), 0.1]
    vals.append(float(chi))
    for c, h in enumerate(hdr, start=1):
        rs.cell(9, c, h); rs.cell(10, c, vals[c - 1])
    cols = ["Name", "Number", "Chi sq.", "ShiftLimit/ns", "σ ShiftLimit/ns", "Shift/ns", "σ Shift/ns", "Rinf", "σ Rinf", "R0", "σ R0"]
    cols += [f"B{i + 1}" for i in range(n)] + [f"σ B{i + 1}" for i in range(n)] + [f"α{i + 1}" for i in range(n)] + ["Ave T/ns", "Peak count", "Total count"]
    row = ["Difference", 1, float(chi), 0.16, 0, 0.0, 0.0, float(r_inf), 0.001, float(r0), 0.002] + [float(x) for x in B] + [0.01] * n + [float(x) for x in al] + [float(al @ phis), 1000, 50000]
    for c, h in enumerate(cols, start=1):
        rs.cell(12, c, h); rs.cell(13, c, row[c - 1])
    wb.create_sheet("Statistics").cell(1, 2, "Relative Amplitude")
    wb.create_sheet("Data").cell(1, 1, "Bin")
    wb.save(path)
    return path


def synthetic_tres_params(wavelengths, taus=(0.2, 1.5, 3.5), rise=True, seed=0):
    """Plausible Laurdan-like DAS: blue-edge short component, red-edge rise term."""
    wl = np.asarray(wavelengths, float)
    rng = np.random.default_rng(seed)
    x = (wl - wl.min()) / max(wl.max() - wl.min(), 1)
    n = len(taus)
    B = np.zeros((len(wl), n))
    B[:, 0] = 0.06 * (1 - x) - (0.02 * x if rise else 0)
    if n > 1:
        B[:, 1] = 0.015 * np.exp(-((x - 0.3) / 0.25) ** 2) - (0.005 * x if rise else 0)
    if n > 2:
        B[:, 2] = 0.002 + 0.006 * x
    for j in range(3, n):
        B[:, j] = 0.001 * (j + 1) * np.ones(len(wl))
    B += rng.normal(0, 1e-5, B.shape)
    counts = 1e5 * np.exp(-((wl - 470) / 45) ** 2) + 5000
    return np.asarray(taus, float), B, counts


@pytest.fixture
def synthetic_group(tmp_path):
    """Three replicate TRES workbooks in a Composition/Temperature/ tree plus two anisotropy files."""
    wl = np.arange(420, 545, 5)
    root = tmp_path / "data"
    for cond in ("15", "25"):
        d = root / "DOPC" / cond
        d.mkdir(parents=True)
        for rep in (1, 2, 3):
            taus, B, counts = synthetic_tres_params(wl, seed=rep + (0 if cond == "15" else 10))
            make_tres_workbook(str(d / f"{rep}.xlsx"), wl, taus * (1 + 0.02 * rep), B, counts * (1 + 0.05 * rep))
    a = root / "DPH" / "15"
    a.mkdir(parents=True)
    make_anisotropy_workbook(str(a / "1.xlsx"), [2.0], [0.30], 0.05, 0.35)
    make_anisotropy_workbook(str(a / "2.xlsx"), [2.2], [0.29], 0.06, 0.35)
    return root
