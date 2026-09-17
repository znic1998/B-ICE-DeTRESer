# Output schema and units

All CSVs use UTF-8, full numeric precision (`repr` of the double; rounding is
for display) and an **empty field for a missing/unavailable value – never 0**.
Every file written is listed with a description in `run_manifest.json`.

## Top level

| File | Content |
|---|---|
| `run_config.json` | the complete effective configuration (every setting, incl. defaults) |
| `environment.json` | Python and dependency versions |
| `run_manifest.json` | status (`completed` / `partially_completed` / `failed`), timings, blocked groups with reasons, error/warning counts, list of every file written |
| `inventory.csv` | one row per input file: `measurement_id`, `path`, `filename`, `label:<level>` (+ `:number`), `kind` (tres / anisotropy / unsupported / unreadable / lock_file / skipped), `error`, `error_location`, workbook facts (`workbook:n_components`, `workbook:wavelength_min_nm`, `workbook:wavelength_max_nm`, `workbook:wavelength_intervals_nm`, `workbook:global_chi_sq`, `workbook:lifetimes_ns`, …), `sha256`, `group_id`, `group`, `group_status`, `processing_status` (processed / rejected: … / blocked: … / skipped: …) |
| `coverage_report.csv` | counts by `kind`, `n_components`, wavelength range, interval and status |
| `groups.csv` | `group_id`, `group`, labels, `n_files`, `kind`, `status`, `block_reasons`, `n_analysed` |
| `diagnostics.csv`, `diagnostics.json` | see `validation_rules.md` |
| `tres_replicates.csv` | one row per analysed TRES workbook (legacy `*_replicates.csv` role) – columns below |
| `tres_summary.csv` | one row per analysed TRES group: `<metric>_mean`, `<metric>_std` (sample SD, ddof=1), `<metric>_n` for every numeric metric, plus labels and `n_replicates` |
| `anisotropy_replicates.csv`, `anisotropy_summary.csv` | same for anisotropy workbooks |
| `records.csv` | long format: `level` (replicate / group), `measurement_id`, `group_id`, `group`, `label:<level>`, `metric`, `unit`, `value`, `sd`, `n`, `status` (available / unavailable: reason) |
| `metric_tables/<metric>_{mean,std,n}.csv` | wide table: columns = first group level; one row per combination of **all** remaining group levels (one column each, numeric order), so no two groups share a cell |

## Replicate metric columns (`tres_replicates.csv`, `records.csv` metric names)

| Column | Unit | Meaning |
|---|---|---|
| `measurement_id`, `path`, `file`, `group_id`, `group`, `replicate`, `replicate_index`, `kind`, `label:*` | – | identity |
| `n_comp` | count | DAS components |
| `tau<i>_ns`, `tau<i>_sigma_ns` | ns | lifetime by rank (τ1 shortest) and its EzTime σ (fit uncertainty, not replicate SD) |
| `tmean_ns` | ns | emission-weighted mean lifetime |
| `area<i>_percent` | % | DAS area of component i (bubble size) |
| `peak<i>_nm` | nm | DAS emission peak of component i |
| `gp`, `gp_available`, `gp_reason` | – | Laurdan GP (when enabled) and availability |
| `<ratio>`, `<ratio>_available`, `<ratio>_reason` | – | each custom ratio |
| `global_chi_sq`, `max_wavelength_chi_sq` | – | as exported by EzTime |
| `wavelength_min_nm`, `wavelength_max_nm`, `n_wavelengths` | nm, count | |
| `recon_wavelengths_masked`, `recon_masked_wavelengths_nm` | count, nm | wavelengths zeroed in the reconstruction |
| `recon_dt_ns`, `recon_tmax_ns`, `tdfs_intensity_floor`, `tdfs_usable_tmax_ns` | ns, –, ns | reconstruction grid and usable window |
| `peak_delta_nu_cm-1`, `peak_tau_r_ns` | cm⁻¹, ns | **primary TDFS outputs** |
| `peak_nu0_cm-1`, `peak_nu0_source`, `peak_nu0_time_ns` | cm⁻¹, –, ns | ν₀ used, its origin (user_supplied / apparent …) and time |
| `peak_nu_initial_measured_cm-1`, `peak_nuinf_cm-1` | cm⁻¹ | first usable ν and terminal ν |
| `peak_n_points`, `peak_metric_tmin_ns`, `peak_metric_tmax_ns`, `peak_metric_tail_points`, `peak_c_clipped_fraction`, `peak_available`, `peak_reason` | | window bookkeeping |
| `com_*` | | same set for the centre-of-mass coordinate (secondary) |
| `tau_fwhm_ns`, `fwhm_max_cm-1` | ns, cm⁻¹ | time of maximum spectral width |
| `peak_at_boundary_fraction` | – | fraction of usable reconstructed spectra whose raw maximum is at the wavelength-range edge (user judgement) |
| `com_0p25ns_cm-1`, `com_10ns_cm-1`, `com_shift_0p25_to_10ns_cm-1`, `com_intensity_fraction_10ns` | cm⁻¹, – | legacy finite-window COM shift |
| `legacy_gate_evaluated` (False), `legacy_gate_status`, `legacy_*` | | unevaluated legacy diagnostics (never a gate) |

Anisotropy replicate columns: `n_comp`, `phi<i>_ns`, `phi<i>_sigma_ns`, `B<i>`,
`alpha<i>`, `ra<i>_percent`, `r_inf`, `r_inf_sigma`, `r0_fitted`,
`phi_mean_ns`, `chi_sq`, and `wobble_*` (`wobble_enabled`, `wobble_status`,
`wobble_missing`, `wobble_r0_used`, `wobble_phi_used_ns`, `wobble_D_perp_per_ns`,
`wobble_eta_Pa_s`, `wobble_eta_poise`, `wobble_effective_volume_m3`, …).

## Per group (`groups/<group>/`)

| File | Columns |
|---|---|
| `das_spectra.csv` | `wavelength_nm`, `ra_tau<i>_emission_{mean,std}` (E_i, replicate mean/SD), `ra_total_{mean,std}`, `npe_tau<i>_{mean,std}` (signed α_i), `fss_norm_mean`, `n` |
| `das_bubble_summary.csv` | per component: `lifetime_ns_{mean,std}`, `peak_nm_{mean,std}`, `area_percent_{mean,std}`, `n`, `peak_nm_from_mean_spectrum`, `area_percent_from_mean_spectrum`, `region` (empty: unassigned) |
| `tdfs_trajectory_mean.csv` | `time_ns`, `n`, `peak_cm-1_{mean,std}`, `peak_nm_mean`, `com_cm-1_{mean,std}`, `fwhm_cm-1_{mean,std}`, `C_peak_{mean,std}`, `C_com_{mean,std}` |
| `replicates/<file>__<measurement_id>_tdfs_trajectory.csv` | `time_ns`, `peak_cm-1`, `peak_nm`, `com_cm-1`, `fwhm_cm-1`, `C_peak`, `C_com`, `total_positive_intensity` |
| `replicates/<file>__<measurement_id>_TRES_reconstructed.csv` | `wavelength_nm`, `t_<time>ns` … reconstructed I(λ,t) (integrates over t to the area-normalised steady-state proxy) |
| `replicates/<file>__<measurement_id>_TRANES_reconstructed.csv` | same, each spectrum area-normalised over λ |
| `time_gated/avg_matrix.csv`, `avg_matrix_smooth.csv` (advanced) | `time_ns` × wavelength columns: aligned, replicate-mean decay surface (raw / smoothed) |
| `time_gated/time_gated_spectra.csv` (advanced) | `wavelength_nm`, `gate_<lo>_to_<hi>ns` area-normalised spectra |
| `time_gated/energy_metrics_measured.csv`, `v_t_C_t_measured.csv` (advanced) | IRF-limited peak/COM/FWHM trajectory; v(t), C(t) |
| `deconvolution/<group>/bub data.csv`, `bubble_data_full.csv`, `bub plot.png`, `fit_tau<i>.png`; `deconvolution/deconvolution_decisions.json` (advanced, via `deconvolve`) | tres1 bubble layout (area % of all fitted peaks, region empty), full fit table, review figures, accepted settings for replay |

## Plots (`plots/`)

For each configured plot: `<name>.png`, `<name>.svg` (formats configurable),
`<name>_data.csv` with **exactly the plotted values** (`series`, `group`, `x`,
`x_sd`, `y`, `y_sd`, `n`, fit curve rows as series `"<label> (fit)"`, bubble
rows with `lifetime_ns`, `peak_nm`, `area_percent`, `marker_size_pt2`,
`region`), and `<name>_meta.json` (axis labels, units, limits, fit results with
R² definition, error-bar definition, averaging order).

## Legacy layouts (`legacy/`, when `output.legacy_compatible: true`)

* `graph_data/<metric>_{mean,std}.csv` – `tdfs big.py` wide layout
  (`, <comp>, Valid, <comp>, Valid…`; with more than two grouping levels the extra levels become leading named columns).  **`Valid` contains `UNEVALUATED`**; see
  `graph_data/README.json`.
* `spectra_raw/<group>.csv` – `tres1.py` layout (`Wavelength, <τ1>, <τ2>, …, total`).
* `full_data.csv`, `full_std.csv` – `tres1.py` layout (mean lifetimes and DAS
  area %; SD is sample SD, `tres1.py` used population SD).
