# Open questions, unsupported inputs, deferred features

## Decisions taken with the user (2026-09-17) and how they are implemented

| # | Question | Decision | Implementation |
|---|---|---|---|
| 1 | Molecular area vs effective volume in η = k_B T/(6 D⊥ V_eff) | The intended quantity is the effective hydrodynamic volume; the legacy constant `161e-22` was written in an ad-hoc unit | `wobble.effective_volume` + `effective_volume_unit` ∈ {A3, nm3, cm3, m3}; the legacy value ≡ 161 Å³ (output in Poise is exported alongside Pa·s) |
| 2 | Which r₀ | Selectable: literature 0.39 or the workbook’s fitted R0 | `wobble.r0_source: literature` (default, `r0_literature: 0.39`) / `fitted` / `user` (`r0`) |
| 3 | Which φ for multi-exponential anisotropy | The amplitude-weighted mean (approximation anyway) | `wobble.phi_selection: mean` (default) |
| 4 | ν₀ for peak TDFS | User-supplied literature value (e.g. ≈23 800 cm⁻¹ for Laurdan) or the apparent estimate **with a warning** | `tdfs.nu0_cm1`; when null, every analysed group gets a `tdfs_nu0_apparent` warning and `peak_nu0_source` = apparent |
| 5 | Boundary-pinned peaks | User decides per probe/experiment | `peak_at_boundary_fraction` column + `tdfs_peak_at_acquisition_boundary` info diagnostic; nothing is filtered |
| 6 | Is EzTime "Chi sq." reduced? | Yes | `validation.chi_sq_is_reduced` defaults to `true` and is stated in every χ² diagnostic |
| 7 | SD convention | Choose the most robust | sample SD (ddof = 1, unbiased for small n) everywhere; documented where `tres1.py` differed |
| 8 | Bubble region classes | Not needed | `region` column kept empty; no `regions.npz` dependency anywhere |
| 9 | `Peak shift data.csv` origin | Not reconstructible; accepted | not used for validation |
| – | Non-uniform wavelength grids | A constant interval is expected | rejected by default (`allow_nonuniform_grid: false`) |
| – | `Data` sheet | Not needed for the core analysis | used only by the advanced time-gated feature |
| – | Steady-state spectrum | Total photon counts per wavelength are the pseudo-emission spectrum | only supported intensity source |
| – | Advanced statistics (`stats.py`, `graph.py`) | Not needed now | not ported |
| – | Log-normal deconvolution | Advanced, mildly interactive, terminal-driven, reproducible, no regions | `python -m tres_suite deconvolve OUT_DIR …` (see README) |
| – | Time-gated spectra / measured metrics | Advanced feature | `time_gated.enabled: true` (see methods §9) |
| – | Parallel workbook loading | Add if possible | `project.workers: N` (process pool; results identical) |

## Still open

* **Apparent ν₀ definition**: the first reconstructed spectrum at t ≥ 0.1 ns. A
  time-zero estimate by the Fee–Maroncelli procedure would need absorption and
  steady-state spectra that the exports do not contain.
* The Kinosita polynomial is used outside its intended single-time context when
  a mean φ is inserted (accepted as an approximation).
* Peak-based TDFS values for gel-phase / boundary-pinned spectra are numerically
  fragile (validation report §4B); the boundary fraction is reported for the user’s judgement.

## Inputs that are not supported / not validated

* Workbooks whose `Results` sheet lacks the `Global` block, the `Name` table
  header, `Wavelength/nm` (TRES) or `Rinf` (anisotropy) are reported as unsupported.
* Non-uniform grids (rejected by design unless explicitly allowed; untested on real data).
* Component counts above 5 parse in principle but were not seen in any export.

## Deferred

* GUI (entry points in README), `stats.py`/`graph.py` statistics, a GUI front-end
  for the deconvolution review (the numerical layer is already separated from the prompts).
