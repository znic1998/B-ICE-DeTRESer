"""Structure-based parsing of HORIBA EzTime workbook exports.

Two workbook families are supported:

* **TRES / DAS exports** ("1-5 exponentials" global fits over an emission
  wavelength series).  Sheets: ``Summary``, ``Results`` and usually ``Data``.
* **Anisotropy exports** ("Anisotropy: R(inf) + ..." fits of the polarisation
  difference decay).  Sheets: ``Summary``, ``Results``, ``Statistics``, ``Data``.

Detection uses sheet structure and header labels, never the filename.

Design notes (see docs/legacy_inventory.md for the evidence):

* The ``Results`` sheet is the primary numeric source.  It contains the
  global lifetimes, the per-wavelength pre-exponentials ``B_i``, the signed
  normalised pre-exponentials ``α_i`` and the total counts, all at full
  precision.  The ``Summary`` sheet stores relative amplitudes and normalised
  pre-exponentials as two-decimal *strings*; the legacy scripts read those
  rounded values.  This parser reads both, uses ``Results`` by default and
  keeps the ``Summary`` values available for legacy-compatible comparison.
* Nothing here assumes a fixed number of components, a fixed wavelength
  range, a fixed spacing or a fixed row stride.  Blocks are located by their
  labels.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import openpyxl

WAVELENGTH_HEADER = "Wavelength/nm"
TOTAL_COUNT_HEADER = "Total count"
PEAK_COUNT_HEADER = "Peak count"
CHI_SQ_HEADER = "Chi sq."
AVE_T_HEADER = "Ave T/ns"

_LIFETIME_HEADER_RE = re.compile(r"^T(\d+)/ns$")
_LIFETIME_SIGMA_RE = re.compile(r"^σ\s*T(\d+)/ns$")
_B_RE = re.compile(r"^B(\d+)$")
_ALPHA_RE = re.compile(r"^(?:α|alpha|a)(\d+)$", re.IGNORECASE)
_DECAY_BLOCK_RE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*-\s*DECAY\s*$", re.IGNORECASE)
_T_ROW_RE = re.compile(r"^T(\d+)$")


class WorkbookParseError(ValueError):
    """Raised when a workbook cannot be parsed into a supported layout.

    ``location`` names the sheet / cell that triggered the problem when known.
    """

    def __init__(self, message: str, path: str = "", location: str = ""):
        self.path = path
        self.location = location
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover - formatting only
        base = super().__str__()
        parts = [base]
        if self.location:
            parts.append(f"[{self.location}]")
        if self.path:
            parts.append(f"({os.path.basename(self.path)})")
        return " ".join(parts)


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------
def _label(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _to_float(value: Any) -> Optional[float]:
    """Convert a cell value to float; return None if not numeric or not finite."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
    else:
        s = str(value).strip().replace(",", "")
        if s == "" or s.lower() in {"nan", "inf", "-inf", "none", "n/a", "na", "#n/a"}:
            return None
        try:
            f = float(s)
        except ValueError:
            return None
    return f if math.isfinite(f) else None


def _sheet_rows(ws) -> List[Tuple[Any, ...]]:
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def _cell(rows: Sequence[Tuple[Any, ...]], r: int, c: int) -> Any:
    """1-based cell access on a list of row tuples; None when out of range."""
    if r < 1 or r > len(rows):
        return None
    row = rows[r - 1]
    if c < 1 or c > len(row):
        return None
    return row[c - 1]


def _cell_ref(sheet: str, r: int, c: int) -> str:
    return f"{sheet}!{openpyxl.utils.get_column_letter(c)}{r}"


# ----------------------------------------------------------------------------
# data containers
# ----------------------------------------------------------------------------
@dataclass
class ComponentTable:
    """Per-wavelength (or per-fit) component quantities aligned by lifetime rank."""

    lifetimes_ns: np.ndarray  # (n_comp,) ascending
    lifetime_sigma_ns: np.ndarray  # (n_comp,)
    original_component_index: np.ndarray  # (n_comp,) 1-based EzTime index for each rank
    pre_exponential: np.ndarray  # (n_rows, n_comp) B_i
    normalized_pre_exponential: np.ndarray  # (n_rows, n_comp) α_i signed, from Results
    relative_amplitude_percent: np.ndarray  # (n_rows, n_comp) fractional intensity, percent


@dataclass
class TresWorkbook:
    """Parsed TRES/DAS global-fit export."""

    path: str
    model_label: str
    n_components: int
    wavelengths_nm: np.ndarray  # (n_wl,) ascending (reordered together with every per-wavelength array if the sheet was not)
    components: ComponentTable
    total_counts: np.ndarray  # (n_wl,)
    peak_counts: np.ndarray  # (n_wl,)
    chi_sq_per_wavelength: np.ndarray  # (n_wl,)
    average_lifetime_per_wavelength_ns: np.ndarray  # (n_wl,) EzTime "Ave T/ns"
    background: np.ndarray  # (n_wl,) EzTime "A"
    global_chi_sq: Optional[float]
    summary_relative_amplitude_percent: Optional[np.ndarray]  # rounded values from Summary
    summary_normalized_pre_exponential: Optional[np.ndarray]  # rounded values from Summary
    relative_amplitude_source: str  # "results_derived" or "summary"
    sheets: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    kind: str = "tres"

    # ---- convenience -------------------------------------------------------
    @property
    def lifetimes_ns(self) -> np.ndarray:
        return self.components.lifetimes_ns

    @property
    def n_wavelengths(self) -> int:
        return int(len(self.wavelengths_nm))

    @property
    def wavelength_min_nm(self) -> float:
        return float(np.min(self.wavelengths_nm))

    @property
    def wavelength_max_nm(self) -> float:
        return float(np.max(self.wavelengths_nm))

    def wavelength_intervals_nm(self) -> np.ndarray:
        return np.diff(np.sort(self.wavelengths_nm))

    def is_uniform_grid(self, rel_tol: float = 1e-6, abs_tol: float = 1e-6) -> bool:
        d = self.wavelength_intervals_nm()
        if len(d) == 0:
            return True
        return bool(np.all(np.isclose(d, d[0], rtol=rel_tol, atol=abs_tol)))

    def summary_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "n_components": self.n_components,
            "n_wavelengths": self.n_wavelengths,
            "wavelength_min_nm": self.wavelength_min_nm,
            "wavelength_max_nm": self.wavelength_max_nm,
            "wavelength_intervals_nm": sorted({round(float(x), 6) for x in self.wavelength_intervals_nm()}),
            "global_chi_sq": self.global_chi_sq,
            "lifetimes_ns": [float(x) for x in self.lifetimes_ns],
            "sheets": list(self.sheets),
        }


@dataclass
class AnisotropyWorkbook:
    """Parsed anisotropy (difference-decay) export."""

    path: str
    model_label: str
    n_components: int
    rotational_correlation_times_ns: np.ndarray  # (n_comp,) ascending
    rotational_correlation_sigma_ns: np.ndarray
    original_component_index: np.ndarray
    amplitudes: np.ndarray  # (n_comp,) B_i, same order
    normalized_amplitudes: np.ndarray  # (n_comp,) α_i
    relative_amplitude_percent: Optional[np.ndarray]  # from Summary, rounded, may be None
    r_inf: Optional[float]
    r_inf_sigma: Optional[float]
    r0_fitted: Optional[float]
    r0_sigma: Optional[float]
    mean_correlation_time_ns: Optional[float]  # EzTime "Ave T/ns" (amplitude-weighted)
    chi_sq: Optional[float]
    global_chi_sq: Optional[float]
    sheets: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    kind: str = "anisotropy"

    def summary_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "n_components": self.n_components,
            "rotational_correlation_times_ns": [float(x) for x in self.rotational_correlation_times_ns],
            "r_inf": self.r_inf,
            "r0_fitted": self.r0_fitted,
            "chi_sq": self.chi_sq,
            "sheets": list(self.sheets),
        }


Workbook = Any  # TresWorkbook | AnisotropyWorkbook


# ----------------------------------------------------------------------------
# detection
# ----------------------------------------------------------------------------
def _open(path: str):
    if os.path.basename(path).startswith("~$"):
        raise WorkbookParseError("Temporary Excel lock file, not a workbook", path)
    try:
        return openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:  # openpyxl raises many different types
        raise WorkbookParseError(f"Unreadable workbook: {exc.__class__.__name__}: {exc}", path) from exc


def _find_results_header(rows: Sequence[Tuple[Any, ...]]) -> Optional[int]:
    """Return 1-based row index of the per-fit table header (first cell 'Name')."""
    for i, row in enumerate(rows[:60], start=1):
        if row and _label(row[0]) == "Name":
            return i
    return None


def detect_workbook_type(path: str) -> Tuple[str, Dict[str, Any]]:
    """Classify a workbook as ``'tres'``, ``'anisotropy'`` or ``'unsupported'``.

    Returns ``(kind, evidence)``.  Evidence lists the structural facts used.
    """
    wb = _open(path)
    try:
        evidence: Dict[str, Any] = {"sheets": list(wb.sheetnames)}
        if "Results" not in wb.sheetnames:
            evidence["reason"] = "no 'Results' sheet"
            return "unsupported", evidence
        rows = _sheet_rows(wb["Results"])
        hdr_i = _find_results_header(rows)
        if hdr_i is None:
            evidence["reason"] = "no per-fit table header row (first cell 'Name') in Results"
            return "unsupported", evidence
        header = [_label(c) for c in rows[hdr_i - 1]]
        evidence["results_header"] = [h for h in header if h]
        model = _label(rows[2][0]) if len(rows) >= 3 and rows[2] else ""
        evidence["model_label"] = model
        if WAVELENGTH_HEADER in header:
            return "tres", evidence
        if "Rinf" in header or model.lower().startswith("anisotropy"):
            return "anisotropy", evidence
        evidence["reason"] = "Results table has neither a wavelength column nor anisotropy fields"
        return "unsupported", evidence
    finally:
        wb.close()


# ----------------------------------------------------------------------------
# shared table parsing
# ----------------------------------------------------------------------------
def _parse_global(rows: Sequence[Tuple[Any, ...]], path: str, sheet: str = "Results"):
    """Parse the 'Global' block: lifetimes, sigmas, chi-sq.  Returns (taus, sigmas, chi)."""
    for i, row in enumerate(rows[:60], start=1):
        if row and _label(row[0]) == "Global":
            hdr = [_label(c) for c in rows[i]] if i < len(rows) else []
            vals = list(rows[i + 1]) if i + 1 < len(rows) else []
            taus: Dict[int, float] = {}
            sigmas: Dict[int, float] = {}
            chi = None
            for c, h in enumerate(hdr):
                v = _to_float(vals[c]) if c < len(vals) else None
                m = _LIFETIME_HEADER_RE.match(h)
                if m:
                    if v is None:
                        raise WorkbookParseError(
                            f"Global lifetime {h} is missing or non-numeric", path, _cell_ref(sheet, i + 2, c + 1)
                        )
                    taus[int(m.group(1))] = v
                    continue
                m = _LIFETIME_SIGMA_RE.match(h)
                if m:
                    sigmas[int(m.group(1))] = v if v is not None else float("nan")
                    continue
                if h == CHI_SQ_HEADER:
                    chi = v
            if not taus:
                raise WorkbookParseError("Global block has no 'T<i>/ns' lifetime columns", path, _cell_ref(sheet, i + 1, 1))
            idx = sorted(taus)
            if idx != list(range(1, len(idx) + 1)):
                raise WorkbookParseError(f"Global lifetime indices are not contiguous: {idx}", path, _cell_ref(sheet, i + 1, 1))
            return (
                np.array([taus[k] for k in idx], float),
                np.array([sigmas.get(k, float("nan")) for k in idx], float),
                chi,
                idx,
            )
    raise WorkbookParseError("No 'Global' block found in Results sheet", path, f"{sheet}!A1:A60")


def _table_columns(header: Sequence[str]) -> Dict[str, int]:
    cols: Dict[str, int] = {}
    for c, h in enumerate(header):
        if h and h not in cols:
            cols[h] = c
    return cols


def _read_table(rows: Sequence[Tuple[Any, ...]], hdr_i: int) -> List[Tuple[int, Tuple[Any, ...]]]:
    """Rows of the per-fit table following the header until the Name cell is empty."""
    out = []
    for r in range(hdr_i + 1, len(rows) + 1):
        row = rows[r - 1]
        if not row or _label(row[0]) == "":
            break
        out.append((r, row))
    return out


# ----------------------------------------------------------------------------
# TRES parsing
# ----------------------------------------------------------------------------
def _parse_summary_blocks(rows: Sequence[Tuple[Any, ...]], path: str):
    """Parse the Summary sheet wavelength blocks.

    Returns (wavelengths, ra_percent (n_wl, n_comp), npe (n_wl, n_comp), n_comp) using the
    original EzTime component order.  Values are whatever EzTime wrote (2-decimal strings).
    """
    wls: List[float] = []
    ra_rows: List[List[Optional[float]]] = []
    npe_rows: List[List[Optional[float]]] = []
    i = 0
    n = len(rows)
    while i < n:
        row = rows[i]
        a = _label(row[0]) if row else ""
        m = _DECAY_BLOCK_RE.match(a)
        if not m:
            i += 1
            continue
        wl = _to_float(_cell(rows, i + 1, 4))
        if wl is None:
            wl = float(m.group(1))
        ra: List[Optional[float]] = []
        npe: List[Optional[float]] = []
        j = i + 1
        while j < n:
            lab = _label(rows[j][0]) if rows[j] else ""
            if _T_ROW_RE.match(lab):
                ra.append(_to_float(_cell(rows, j + 1, 8)))
                npe.append(_to_float(_cell(rows, j + 1, 9)))
                j += 1
                continue
            if lab in ("", "Value") or lab.startswith("Wavelength"):
                j += 1
                if lab == "" and ra:
                    break
                continue
            break
        wls.append(wl)
        ra_rows.append(ra)
        npe_rows.append(npe)
        i = j if j > i else i + 1
    if not wls:
        return None
    n_comp = max(len(r) for r in ra_rows)
    ra_arr = np.full((len(wls), n_comp), np.nan)
    npe_arr = np.full((len(wls), n_comp), np.nan)
    for k, (ra, npe) in enumerate(zip(ra_rows, npe_rows)):
        for c in range(len(ra)):
            ra_arr[k, c] = np.nan if ra[c] is None else ra[c]
            npe_arr[k, c] = np.nan if npe[c] is None else npe[c]
    return np.array(wls, float), ra_arr, npe_arr, n_comp


def _parse_tres(wb, path: str) -> TresWorkbook:
    rows = _sheet_rows(wb["Results"])
    model = _label(rows[2][0]) if len(rows) >= 3 and rows[2] else ""
    taus_raw, sig_raw, global_chi, comp_idx = _parse_global(rows, path)
    n_comp = len(taus_raw)

    hdr_i = _find_results_header(rows)
    header = [_label(c) for c in rows[hdr_i - 1]]
    cols = _table_columns(header)
    for required in (WAVELENGTH_HEADER, TOTAL_COUNT_HEADER):
        if required not in cols:
            raise WorkbookParseError(f"Results table lacks '{required}' column", path, _cell_ref("Results", hdr_i, 1))
    b_cols = {int(_B_RE.match(h).group(1)): c for h, c in cols.items() if _B_RE.match(h)}
    a_cols = {int(_ALPHA_RE.match(h).group(1)): c for h, c in cols.items() if _ALPHA_RE.match(h)}
    if sorted(b_cols) != comp_idx:
        raise WorkbookParseError(
            f"Pre-exponential columns {sorted(b_cols)} do not match global lifetimes {comp_idx}",
            path, _cell_ref("Results", hdr_i, 1),
        )
    if sorted(a_cols) != comp_idx:
        raise WorkbookParseError(
            f"Normalised pre-exponential (α) columns {sorted(a_cols)} do not match global lifetimes {comp_idx}",
            path, _cell_ref("Results", hdr_i, 1),
        )

    table = _read_table(rows, hdr_i)
    if len(table) < 2:
        raise WorkbookParseError("Results table has fewer than two wavelength rows", path, _cell_ref("Results", hdr_i + 1, 1))

    warnings: List[str] = []
    wl, tot, pk, chi, avet, bg = [], [], [], [], [], []
    B = np.zeros((len(table), n_comp))
    A = np.zeros((len(table), n_comp))

    def _req(row, r, key):
        v = _to_float(row[cols[key]]) if cols[key] < len(row) else None
        if v is None:
            raise WorkbookParseError(f"'{key}' missing or non-numeric", path, _cell_ref("Results", r, cols[key] + 1))
        return v

    def _opt(row, key):
        if key not in cols or cols[key] >= len(row):
            return float("nan")
        v = _to_float(row[cols[key]])
        return float("nan") if v is None else v

    for k, (r, row) in enumerate(table):
        wl.append(_req(row, r, WAVELENGTH_HEADER))
        tot.append(_req(row, r, TOTAL_COUNT_HEADER))
        pk.append(_opt(row, PEAK_COUNT_HEADER))
        chi.append(_opt(row, CHI_SQ_HEADER))
        avet.append(_opt(row, AVE_T_HEADER))
        bg.append(_opt(row, "A"))
        for j, ci in enumerate(comp_idx):
            bv = _to_float(row[b_cols[ci]]) if b_cols[ci] < len(row) else None
            av = _to_float(row[a_cols[ci]]) if a_cols[ci] < len(row) else None
            if bv is None:
                raise WorkbookParseError(f"B{ci} missing or non-numeric", path, _cell_ref("Results", r, b_cols[ci] + 1))
            if av is None:
                raise WorkbookParseError(f"α{ci} missing or non-numeric", path, _cell_ref("Results", r, a_cols[ci] + 1))
            B[k, j] = bv
            A[k, j] = av

    wl_arr = np.array(wl, float)
    if len(np.unique(wl_arr)) != len(wl_arr):
        raise WorkbookParseError("Duplicate wavelength entries in Results table", path, _cell_ref("Results", hdr_i + 1, cols[WAVELENGTH_HEADER] + 1))
    if np.any(np.diff(wl_arr) <= 0):
        # Reorder every per-wavelength array together so that all downstream code (validation, DAS,
        # reconstruction, replicate averaging, export) works on one ascending grid.
        wl_order = np.argsort(wl_arr, kind="stable")
        wl_arr = wl_arr[wl_order]
        B = B[wl_order]
        A = A[wl_order]
        tot = [tot[i] for i in wl_order]
        pk = [pk[i] for i in wl_order]
        chi = [chi[i] for i in wl_order]
        avet = [avet[i] for i in wl_order]
        bg = [bg[i] for i in wl_order]
        warnings.append("Wavelengths in Results were not ascending; all per-wavelength data were reordered to ascending wavelength.")

    # lifetime ranking (ascending) applied consistently to every component column
    order = np.argsort(taus_raw, kind="stable")
    taus = taus_raw[order]
    sig = sig_raw[order]
    orig = np.array([comp_idx[i] for i in order], int)
    B = B[:, order]
    A = A[:, order]

    # Relative amplitude (percent) derived from Results.  EzTime's convention, verified
    # against the Summary sheet of real exports (docs/legacy_inventory.md):
    #     RA_i = 100 * |B_i| tau_i / sum_j |B_j| tau_j      (unsigned)
    #     alpha_i = B_i / sum_j |B_j|                      (signed, "Normalised pre-exponential")
    btau = np.abs(B) * taus[None, :]
    denom = btau.sum(axis=1)
    ra_derived = np.full_like(btau, np.nan)
    ok = denom != 0
    ra_derived[ok] = 100.0 * btau[ok] / denom[ok, None]
    if np.any(~ok):
        warnings.append(f"{int(np.sum(~ok))} wavelength(s) have sum(|B_i|*tau_i)=0; relative amplitude undefined there.")
    a_check = np.abs(B).sum(axis=1)
    if np.all(a_check > 0):
        d_alpha = float(np.nanmax(np.abs(B / a_check[:, None] - A)))
        if d_alpha > 1e-3:
            warnings.append(f"Results α_i differ from B_i/Σ|B_j| by up to {d_alpha:.4f}; α convention may differ from the documented one.")

    # Summary sheet (rounded legacy values) -- optional
    s_ra = s_npe = None
    if "Summary" in wb.sheetnames:
        parsed = _parse_summary_blocks(_sheet_rows(wb["Summary"]), path)
        if parsed is None:
            warnings.append("Summary sheet has no '<wl>-DECAY' blocks; Summary values unavailable.")
        else:
            s_wl, s_ra_raw, s_npe_raw, s_n = parsed
            s_order = np.argsort(s_wl, kind="stable")
            s_wl, s_ra_raw, s_npe_raw = s_wl[s_order], s_ra_raw[s_order], s_npe_raw[s_order]
            if s_n != n_comp:
                warnings.append(f"Summary blocks list {s_n} components but Results has {n_comp}; Summary values ignored.")
            elif len(s_wl) != len(wl_arr) or not np.allclose(s_wl, wl_arr, atol=1e-6):
                warnings.append("Summary block wavelengths differ from Results wavelengths; Summary values ignored.")
            else:
                s_ra = s_ra_raw[:, order]
                s_npe = s_npe_raw[:, order]
                if np.all(np.isfinite(s_ra)):
                    d = np.nanmax(np.abs(s_ra - ra_derived))
                    if d > 0.011:  # beyond 2-decimal rounding
                        warnings.append(f"Summary relative amplitudes differ from Results-derived values by up to {d:.3f} % points.")
                else:
                    warnings.append("Some Summary relative-amplitude cells are non-numeric.")
    else:
        warnings.append("No Summary sheet; legacy rounded amplitude values unavailable (Results used).")

    comps = ComponentTable(
        lifetimes_ns=taus,
        lifetime_sigma_ns=sig,
        original_component_index=orig,
        pre_exponential=B,
        normalized_pre_exponential=A,
        relative_amplitude_percent=ra_derived,
    )
    return TresWorkbook(
        path=path,
        model_label=model,
        n_components=n_comp,
        wavelengths_nm=wl_arr,
        components=comps,
        total_counts=np.array(tot, float),
        peak_counts=np.array(pk, float),
        chi_sq_per_wavelength=np.array(chi, float),
        average_lifetime_per_wavelength_ns=np.array(avet, float),
        background=np.array(bg, float),
        global_chi_sq=global_chi,
        summary_relative_amplitude_percent=s_ra,
        summary_normalized_pre_exponential=s_npe,
        relative_amplitude_source="results_derived",
        sheets=list(wb.sheetnames),
        warnings=warnings,
    )


# ----------------------------------------------------------------------------
# anisotropy parsing
# ----------------------------------------------------------------------------
def _parse_anisotropy(wb, path: str) -> AnisotropyWorkbook:
    rows = _sheet_rows(wb["Results"])
    model = _label(rows[2][0]) if len(rows) >= 3 and rows[2] else ""
    phis_raw, sig_raw, global_chi, comp_idx = _parse_global(rows, path)
    n_comp = len(phis_raw)
    hdr_i = _find_results_header(rows)
    header = [_label(c) for c in rows[hdr_i - 1]]
    cols = _table_columns(header)
    table = _read_table(rows, hdr_i)
    if not table:
        raise WorkbookParseError("Anisotropy Results table has no fit rows", path, _cell_ref("Results", hdr_i + 1, 1))
    warnings: List[str] = []
    if len(table) > 1:
        warnings.append(f"Anisotropy Results table has {len(table)} fit rows; only the first is used.")
    r, row = table[0]

    def _opt(key):
        if key not in cols or cols[key] >= len(row):
            return None
        return _to_float(row[cols[key]])

    b_cols = {int(_B_RE.match(h).group(1)): c for h, c in cols.items() if _B_RE.match(h)}
    a_cols = {int(_ALPHA_RE.match(h).group(1)): c for h, c in cols.items() if _ALPHA_RE.match(h)}
    B = np.array([_to_float(row[b_cols[i]]) if i in b_cols and b_cols[i] < len(row) else None for i in comp_idx], dtype=object)
    Al = np.array([_to_float(row[a_cols[i]]) if i in a_cols and a_cols[i] < len(row) else None for i in comp_idx], dtype=object)
    if any(v is None for v in B):
        raise WorkbookParseError("Anisotropy amplitude B_i missing or non-numeric", path, _cell_ref("Results", r, 1))
    if any(v is None for v in Al):
        warnings.append("Normalised amplitudes α_i missing; derived from B_i.")
        Bf = np.array(B, float)
        Al = Bf / Bf.sum() if Bf.sum() != 0 else np.full(n_comp, np.nan)
    order = np.argsort(phis_raw, kind="stable")

    # Summary relative amplitudes (optional, rounded)
    s_ra = None
    if "Summary" in wb.sheetnames:
        srows = _sheet_rows(wb["Summary"])
        vals: Dict[int, Optional[float]] = {}
        for i, srow in enumerate(srows, start=1):
            lab = _label(srow[0]) if srow else ""
            m = _T_ROW_RE.match(lab)
            if m:
                vals[int(m.group(1))] = _to_float(_cell(srows, i, 8))
        if vals and sorted(vals) == comp_idx:
            s_ra = np.array([np.nan if vals[i] is None else vals[i] for i in comp_idx], float)[order]

    return AnisotropyWorkbook(
        path=path,
        model_label=model,
        n_components=n_comp,
        rotational_correlation_times_ns=phis_raw[order],
        rotational_correlation_sigma_ns=sig_raw[order],
        original_component_index=np.array([comp_idx[i] for i in order], int),
        amplitudes=np.array(B, float)[order],
        normalized_amplitudes=np.array(Al, float)[order],
        relative_amplitude_percent=s_ra,
        r_inf=_opt("Rinf"),
        r_inf_sigma=_opt("σ Rinf"),
        r0_fitted=_opt("R0"),
        r0_sigma=_opt("σ R0"),
        mean_correlation_time_ns=_opt(AVE_T_HEADER),
        chi_sq=_opt(CHI_SQ_HEADER),
        global_chi_sq=global_chi,
        sheets=list(wb.sheetnames),
        warnings=warnings,
    )


# ----------------------------------------------------------------------------
# public entry point
# ----------------------------------------------------------------------------
def load_workbook(path: str) -> Workbook:
    """Detect and parse a workbook.  Raises :class:`WorkbookParseError` on failure."""
    kind, evidence = detect_workbook_type(path)
    if kind == "unsupported":
        raise WorkbookParseError(f"Unsupported workbook layout: {evidence.get('reason', 'unknown')}", path, "Results")
    wb = _open(path)
    try:
        if kind == "tres":
            return _parse_tres(wb, path)
        return _parse_anisotropy(wb, path)
    finally:
        wb.close()
