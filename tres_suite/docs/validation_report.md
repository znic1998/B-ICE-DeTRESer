# Validation and comparison report

Generated with `tools/compare_reference.py` and `tools/coverage_all_files.py`
on the supplied `TRES Program` folder (2026-09-17).  Raw tables are in
`reports/`.

## 1. Test suite

`python -m pytest tests -q` → **44 passed** (39 unit tests on synthetic EzTime-style
workbooks, 5 integration tests on the supplied data; the latter are skipped
when the data folder is absent).  Covered: import side-effect freedom; parsing
of 1–5 components, unsorted lifetimes, 300–800 nm coverage, non-uniform grids,
missing/non-finite cells with cell locations, unsupported spreadsheets, lock
files; label parsing and numeric sorting; folder and numbered-replicate-folder
import; explicit file assignment and duplicate identifiers; every error case
(1–7) on synthetic and on the supplied fixtures; the restricted expression
parser (rejects calls, powers, names, statements); unavailable ratios
(out-of-range wavelength, zero denominator); GP and mean-lifetime definitions;
reconstruction integrating to the steady-state proxy; user vs apparent ν₀;
COM not inheriting the peak ν₀; absence of any `23800` constant in the
source; masked wavelengths; the anisotropy add-on (isolation from base
quantities, blocking on missing parameters, equality with the legacy `dph()`
arithmetic, fitted-r₀ mode); single-replicate SD undefined; no boolean/text
averaging; linear-fit R² edge cases; end-to-end run with all eight plot types;
exported plot data equal to the summary table; `Valid` = UNEVALUATED; identical
numbers on a repeated run; a group with an unreadable replicate is blocked and
never averaged from the remaining subset; r₀ source options and volume units of the
add-on; identical results from parallel loading; the apparent-ν₀ warning and the
boundary-fraction column; a scripted deconvolution review (reject → new bounds →
accept) with replay equality and region-free bubble export; the stacked area
bar; the time-gated feature on supplied data; the 4-component set; and regressions for the review findings: reversed wavelength order normalised at parse time, unique replicate export names (`<file>__<measurement_id>`), a fresh CLI run with plots writing its manifest and refusing a non-empty folder before doing any work, exact config round-trip (`config_from_dict(cfg.to_dict()) == cfg`, old `run_config.json` files still load), wide tables preserving every grouping level.

## 2. Coverage of every supplied workbook (`reports/coverage_all_files.csv`)

| Folder | Kind | Components | Range (nm) | Interval | Status | Files |
|---|---|---|---|---|---|---|
| Anon ANI Data | anisotropy | 1 / 2 | – | – | processed | 23 / 183 |
| Anon TRES DATA | tres | 2 | 420–520 / 420–540 | 5 | processed | 3 / 33 |
| Anon TRES DATA | tres | 3 | 410–540 / 420–540 | 5 | processed | 22 / 259 |
| Error | anisotropy | 1 / 2 | – | – | processed (then validated) | 2 / 1 |
| Error | tres | 2 / 3 / 3 / 3 / 5 | 420–540 / 420–540 (1 nm) / 420–540 / 435–525 / 420–540 | 5 / 1 / 5 / 5 / 5 | processed (then validated) | 22 / 1 / 6 / 1 / 1 |
| TEST DATA | tres | 3 | 420–540 | 5 | processed | 134 |
| TEST DATA/RESULTS | – | – | – | – | rejected: no `Results` sheet (not EzTime exports) | 3 |

All 691 EzTime exports parse; the 3 rejected files are result spreadsheets.
Lock files (`~$…`) present in the original folder are skipped on import
(tested).  A 4-component set was supplied afterwards; see §2b.

## 2b. Four-component exports (`robust guy/4 fit`, 21 workbooks, supplied later)

All 21 parse as 4-component TRES exports (420–540 nm, 5 nm, χ² 0.92–1.00):
the `Results` total-count column is 25 as the legacy stride table assumed, the
lifetimes are exported unsorted (e.g. T1 = 1.34 ns, T2 = 0.06 ns) and are
re-ranked with all component columns permuted consistently, the EzTime
RA/α conventions hold within 2-decimal rounding (max |Δ| 0.005), and the full
pipeline (DAS, ⟨τ⟩, GP, reconstruction, peak/COM TDFS, time-gated add-on,
plots, deconvolution review) runs on them (asserted by
`test_four_component_workbooks_parse_and_analyse`).  The 21 files are
different samples, not replicates, so their group statistics are not
meaningful and no reference outputs exist for them; support is validated at
the parsing/structural level and by the invariants above.

## 3. Error fixtures

See `docs/validation_rules.md` § "Behaviour on the supplied Error/1–7 fixtures"
(asserted by `tests/test_supplied_data.py::test_error_cases`).

## 4. Comparison with `tdfs big.py` reference outputs (134 replicates, 42 conditions)

Tolerances were declared in `tools/compare_reference.py` before evaluation:
gp/⟨τ⟩/τ_i abs 1e-9; ν values abs 1 cm⁻¹ or rel 1e-4; τ_r abs 1e-3 ns or rel
1e-3; COM finite-window fraction abs 1e-4 / rel 1e-3; point counts exact;
legacy kinetic diagnostics abs 1e-6 / rel 1e-4.

### A. Legacy-equivalent settings (`amplitude_source: summary`, `nu0_cm1: 23800`)

| Metric | n | fail | max |Δ| | max rel |
|---|---|---|---|---|
| gp | 134 | 0 | 1e-16 | 2e-14 |
| tmean_ns | 134 | **134** | 4.8e-6 ns | 2.1e-6 |
| tau1/2/3_ns | 134 | **134/133/134** | 5.0e-6 ns | 4.2e-6 |
| peak_delta_nu_cm-1, peak_nuinf, peak_nu_initial | 134 | 0 | 4e-12 | 2e-16 |
| peak_tau_r_ns | 134 | 0 | 3.6e-5 ns | 4.2e-5 |
| com_delta_nu_cm-1, com_nuinf, com_nu0 | 134 | 0 | 2.8e-3 cm⁻¹ | 1.5e-6 |
| com_tau_r_ns | 134 | 0 | 1.0e-5 ns | 4.8e-6 |
| com_0p25ns, com_10ns, com_shift, com_intensity_fraction_10ns | 134 | 0 | 2.3e-3 cm⁻¹ | 1.4e-5 |
| recon_wavelengths_masked, peak/com_n_points | 134 | 0 | 0 | 0 |
| x_kinetic, tau_relax_ns, rise_fraction, captured_fraction | 134 | 0 | 4.8e-6 | 3.2e-6 |

**Explanation of the failed rows:** the reference read lifetimes from the
`Summary` sheet, where EzTime writes them as 6-significant-digit strings
(e.g. `0.0771439`); `tres_suite` reads the full-precision `Results` values
(`0.07714388574961983`).  The 1e-9 tolerance was set expecting identical
inputs and is kept as declared; the ≤ 5e-6 ns discrepancy is entirely this
source difference and is intended.  Everything else reproduces the reference
within numerical noise (the ≤ 3e-3 cm⁻¹ COM differences come from the
spline/trapezoid evaluation order).

### B. Default settings (`amplitude_source: results`, i.e. full-precision α_i)

Intended difference; reported, not pass/fail:

| Metric | DOPC (fluid) median / max rel | DPPC (gel) median / max rel |
|---|---|---|
| tmean_ns | 0.0006 % / 0.002 % | 0.0006 % / 0.002 % |
| peak_delta_nu_cm-1 | 0.16 % / 1.1 % (max 37 cm⁻¹) | 0.73 % / 5.5 % (max 79 cm⁻¹) |
| peak_tau_r_ns | 1.1 % / 9.2 % | 7.0 % / **65 %** (max 0.19 ns) |
| com_delta_nu_cm-1 | 0.33 % / 3.8 % | 0.66 % / 3.7 % |
| com_tau_r_ns | 0.16 % / 0.56 % | 0.40 % / 5.4 % |
| gp | identical | identical |

The 2-decimal rounding of the signed normalised pre-exponentials in the
`Summary` sheet (e.g. `0.02` for a true `0.016`) changes the reconstructed
red-edge rise terms.  For DPPC, where the early reconstructed peak sits at the
420 nm acquisition edge, the peak-based metrics are numerically fragile and the
rounding matters a lot; for DOPC the effect is at the ~1 % level.  The
full-precision source is the correct one and is the default; the legacy
values are reproducible with `amplitude_source: summary`.  See
`docs/open_questions.md` item 5 about flagging boundary-pinned peaks.

## 5. Comparison with `tres1.py` reference outputs (42 conditions)

| Quantity | n | fail | max |Δ| |
|---|---|---|---|
| mean DAS emission spectra (`spectra raw`) | 42 | 0 | 3e-16 |
| mean total emission | 42 | 0 | 3e-16 |
| mean lifetimes (spectra-raw header) | 42 | 32 | 3.3e-6 ns (same Summary-vs-Results lifetime source as above) |
| DAS area percent (`full data`, tolerance 0.05 % points; the legacy area origin is not in the supplied scripts) | 42 | 0 | 0.0016 % points |

`full_std` is not compared (population vs sample SD, documented).
`Peak shift data.csv` could not be attributed to a supplied script and was not used.

## 6. Reproducibility and provenance

* Two runs on the same inputs and settings produce identical numbers
  (asserted in `test_pipeline_end_to_end_and_reproducible`); no randomised
  procedure is used (`seed` recorded anyway).
* `inventory.csv` carries the SHA-256 of every source workbook and its
  labels/identifier; `records.csv` and every group/replicate file carry the
  identifiers; `run_config.json` and `environment.json` record settings and
  versions; `run_manifest.json` lists every file written.  Source workbooks are
  opened read-only and never modified.
* Example output set: `example_output/` produced by
  `python -m tres_suite run examples/example_config.yaml` on `TEST DATA/DATA`
  (134 workbooks, 42 groups, 855 files, ~3 min).

## 7. What was *not* validated

* Non-uniform grids on real data (rejected by design).
* Physical validity of the TDFS parameters (the gate was removed by design;
  the papers describe the criteria but no ground truth was supplied).
* The anisotropy add-on beyond arithmetic equality with the legacy `dph()`.
* The log-normal deconvolution against the interactive legacy fits.
