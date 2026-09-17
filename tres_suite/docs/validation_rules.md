# Validation rules and diagnostics

Every diagnostic record has: `severity` (error | warning | info), `rule`,
`message`, `group_id`, `group`, `files` (all conflicting files, never a guess
at "the wrong one"), `location` (sheet / cell where available), `observed`,
`expected`, `action`, `metric`.  They are written to `diagnostics.csv` and
`diagnostics.json`.

**Error → the group is blocked** (no analysis, no averaging, listed in
`groups.csv` and `run_manifest.json`; the run status becomes
`partially_completed`, or `failed` if every group is blocked).
**Warning / info → never blocks.**

| Rule | Severity | Scope | Trigger |
|---|---|---|---|
| `empty_group` | error | group | no workbook in the group |
| `unreadable_file` / `unsupported_layout` | error | file | cannot be opened / not an EzTime TRES or anisotropy export (reason + location) |
| `lock_file_skipped` | info | file | `~$` temporary file |
| `insufficient_wavelength_points` | error | file | fewer than `min_wavelength_points` (3) |
| `nonuniform_wavelength_grid` | error | file | intervals differ, unless `allow_nonuniform_grid: true` (then the actual coordinates are used) |
| `invalid_total_counts`, `invalid_lifetimes` | error | file | non-finite / negative counts, non-positive lifetimes |
| `mixed_workbook_types` (**case 6**) | error | group | TRES and anisotropy exports in one group; detected types listed |
| `component_count_mismatch` (**case 1**) | error | group | different DAS component counts; each file and count listed; action: regroup/replace |
| `wavelength_range_mismatch` (**case 2**) | error | group | min/max differ beyond `wavelength_tolerance_nm`; each file's min and max listed |
| `wavelength_grid_mismatch` (**case 3**) | error | group | same range but coordinates differ: intervals, point counts and first mismatching coordinate listed |
| `high_chi_sq` (**case 4**) | warning | file | global χ² > `chi_sq_warning_threshold` (only when configured); observed value, source, whether reduced (unknown unless `chi_sq_is_reduced` is set), threshold. Otherwise `chi_sq_report` (info) |
| `replicate_variation_high` (**case 5**) | warning | group/metric | 100·SD/\|mean\| > `replicate_variation_warning_percent` for a metric in `replicate_variation_metrics`; reports mean, sample SD, %, values per file. n<2 → `replicate_variation_insufficient`; near-zero mean → `replicate_variation_undefined` (tolerance `replicate_variation_near_zero_mean`). The sample is never re-assigned or excluded |
| `anisotropy_lifetime_difference` (**case 7**) | warning | group | spread of mean rotational correlation times > `anisotropy_correlation_time_tolerance_percent`; values and tolerance listed. `anisotropy_component_count_differs` is a warning too – the TRES component-count rule is **not** applied to anisotropy |
| `analysis_failed` | error | file/group | an exception during calculation (message kept; the report is not erased) |
| `replicate_count_differs_between_groups`, `wavelength_range_differs_between_groups`, `wavelength_interval_differs_between_groups` | warning | cross-group | differences between valid groups; never a failure; spectra are never pooled across groups |
| `component_count_differs_between_groups` | info | cross-group | |
| `duplicate_identifier`, `file_skipped_on_import` | error / warning | project | |
| `parser_note` | info | file | e.g. Summary values unavailable |

## Thresholds (`validation:` section)

```yaml
validation:
  wavelength_tolerance_nm: 1e-6
  allow_nonuniform_grid: false
  min_wavelength_points: 3
  chi_sq_warning_threshold: null        # e.g. 1.5 ; null -> report values only
  chi_sq_is_reduced: null               # true/false if you know how EzTime defines "Chi sq."
  replicate_variation_warning_percent: null   # e.g. 20
  replicate_variation_near_zero_mean: 1e-9
  replicate_variation_metrics: [gp, tmean_ns, peak_delta_nu_cm-1, peak_tau_r_ns]
  anisotropy_correlation_time_tolerance_percent: null   # e.g. 20
```

No universal thresholds are built in.  With `null`, the diagnostic values are
still exported (as `info` records) without a pass/fail claim.

## Behaviour on the supplied `Error/1–7` fixtures (tested)

| Case | Folder | Result |
|---|---|---|
| 1 | 2-component + 5-component fits | blocked: `component_count_mismatch` {2 fit.xlsx: 2, 5 fit.xlsx: 5} |
| 2 | 435–525 nm vs 420–540 nm | blocked: `wavelength_range_mismatch` with both ranges |
| 3 | 1 nm vs 5 nm spacing | blocked: `wavelength_grid_mismatch`, intervals [1.0]/[5.0], first mismatch 421 vs 425 nm |
| 4 | 21 files, χ² up to 1.65 | analysed; `high_chi_sq` warnings for the five files above 1.5 (with a 1.5 threshold) |
| 5 | 3 files, one from another condition | analysed; `replicate_variation_high` warnings with mean/SD/% and per-file values |
| 6 | anisotropy + TRES | blocked: `mixed_workbook_types` {2.xlsx: anisotropy, 3.xlsx: tres} |
| 7 | 1- and 2-component anisotropy fits | analysed; warnings `anisotropy_component_count_differs`, `anisotropy_lifetime_difference` (40 % spread vs 20 % tolerance) |
