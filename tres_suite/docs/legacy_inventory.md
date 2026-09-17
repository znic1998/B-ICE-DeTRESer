# Legacy inventory

Source files supplied in `TRES Program/` (filenames preserved):

| File | Lines | Role | Runs on import? | Hard-coded paths / dependencies |
|---|---|---|---|---|
| `tdfs big.py` | 1229 | TRES workbook extraction, GP, mean lifetime, reconstruction, COM/peak TDFS, two-layer validity gate, replicate summary, graph-ready wide CSVs | yes (`batch_laurdan_tdfs` under `__main__`; module-level settings) | `root="pufa"`, `out_csv`, `graph_output_dir`; numpy/pandas/openpyxl/scipy |
| `tres1.py` | 1041 | EzTime "Excel cleaning" (DAS emission spectra, averaging with NaN padding), interactive log-normal deconvolution, bubble plot with solvent-region colouring, stacked bar, `dph()` anisotropy/viscosity | **yes**: creates a global figure, registers a colormap, `np.load("regions.npz")` and calls `dph(dph_path)` at import | `regions.npz` (**not supplied**), `tres data/…`, `dph/`, `dphout/`; matplotlib, scipy.optimize |
| `single laurdan.py` | 1304 | Script (no functions for the main flow): reads the `Data` sheet decays (time-gated spectra, measured energy metrics), DAS extraction with `detect_das_format` (7,1)/(8,1) label check, reconstruction, TRANES, DAS/NPE/bubble figures, per-folder CSVs | **yes**: scans the current directory and processes every subfolder | `root_directory='.'`; writes into the data folders |
| `stats.py` | 841 | Condition-level correlation/regression analysis with cluster bootstrap on the graph-ready CSVs | no (`main()` guarded) | reads `tdfs big.py` graph_data with `Valid` flags |
| `graph.py` | 201 | Condition-level scatter plotter for the stats merged tables | yes | absolute paths under `/Users/zacharynicolella/PycharmProjects/single laurdan/…` |

Papers supplied: `TDFS Paper.pdf` (Scollo et al. 2021 review: definitions of
Δν and τ, TRES maxima analysis, FWHM/time-zero checks), `DAS PAPER.pdf` and
`DAS PAPER SI.pdf` (Nicolella et al.: EzTime global fit, ⟨τ⟩ definition,
reconstruction, peak/COM ν(t), ν_initial rules, Δν_app, C(t), τ_r,app, τ_FWHM,
the 12 validity criteria, anisotropy model and the SED microviscosity formula).

Data supplied: 481 TRES exports (58 two-component, 422 three-component, 1
five-component), 209 anisotropy exports (25 one-component, 184 two-component),
3 non-EzTime spreadsheets, 2 lock files.  Reference outputs: `TDFS_TEST_out*.csv`
+ 112 `graph_data` CSVs (from `tdfs big.py`, 134 replicates / 42 conditions),
`spectra raw` CSVs, `full data`/`full_std`/`Peak shift data` (from `tres1.py`
or a variant; the peak-shift CSV's origin is not reconstructible from the
supplied scripts).  **Not supplied:** `regions.npz`, a 4-component workbook,
the "more than 80 paired inputs" beyond the 134 in `TEST DATA` (the 134 are
the ones used), any measured steady-state spectra.

## Where each legacy function went

| Legacy | New location | Change |
|---|---|---|
| `detect_das_format` (label at (7,1)/(8,1), stride table) | `workbook._parse_global`, `_parse_summary_blocks` | label-based block parsing, any component count |
| `get_result_wavelengths` (300–800 cutoff) | `workbook._parse_tres` | header-based, no cutoff |
| `extract_one_workbook` | `workbook.load_workbook` + `das.compute_das` | Results-sheet precision; Summary kept as option |
| `intensity_at_wavelength` (clamping) | `expressions.intensity_at` | inside-range only |
| GP | `expressions.gp_expression` + `das` | explicit option, custom ratios |
| `reconstruct_tres` / `reconstruct_tres_tranes` | `tdfs.reconstruct_tres` | identical equation |
| `spectral_moments_from_lambda_spectrum`, `_spectrum_shape_qc`, `_fwhm_connected_region` | `tdfs.spectral_moments` | one pass: peak, COM, FWHM, negative area, boundary flag |
| `compute_tdfs_from_tres` (23800 for peak) | `tdfs._metric` | user/apparent ν₀, COM separate |
| `kinetic_validity`, `classify_tdfs_curve`, `classify_joint_tdfs`, `combine_verdict` | `tdfs.legacy_diagnostics` | values only, `legacy_gate_evaluated=False` |
| `finite_window_com_shift` | `tdfs.compute_tdfs` (legacy block) | unchanged |
| `summarize_replicates` | `aggregate.summarize_scalars` | ddof=1, no boolean aggregation, validity fields dropped |
| `build_graph_metric_table`, `write_graph_ready_outputs` | `export._wide_table`, `export._write_legacy` | `Valid` = UNEVALUATED |
| `batch_laurdan_tdfs` | `pipeline.run_project` + `export.write_run` | groups, validation, no printing |
| `tres1.excel`, `average` (NaN padding) | `das.compute_das`, `aggregate.summarize_arrays` | mismatched grids are rejected, not padded |
| `tres1.main_graph_csv` | `plotting.plot_das_spectra`, `legacy/spectra_raw` | |
| `tres1.lognormal/bimodal/trimodal/fitter/bound_finder` (interactive) | `lognormal.py` (non-interactive, optional) | explicit bounds; R² and legacy χ² reported |
| `tres1.region_assign`, `bub_plot` colouring | `pipeline._aggregate_tres_group` (`region=None`) | needs `regions.npz` |
| `tres1.stack_bar` | not ported (depends on regions) | deferred |
| `tres1.dph` | `anisotropy.compute_anisotropy` + `apply_wobble` | generalised, add-on gated on explicit inputs |
| `single laurdan.py` Data-sheet time-gated spectra and measured (IRF-limited) energy metrics | not ported | design: reconstruction, not time gating, is used for TDFS |
| `single laurdan.py` DAS bubble (quadratic peak, area %) | `das.peak_center_quadratic`, `pipeline` bubble | per-replicate stats + mean-spectrum variant |
| `stats.py`, `graph.py` | not ported | advanced statistics deferred; `stats.linear_fit` covers R² |
