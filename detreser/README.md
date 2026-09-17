# B-ICE DeTRESer — user guide

DeTRESer analyses HORIBA DeltaFlex / EzTime exports: time-resolved emission spectra (TRES), decay-associated spectra (DAS), time-dependent fluorescence shift (TDFS), Laurdan GP or a custom intensity ratio, and time-resolved anisotropy with an optional microviscosity calculation. Every number is computed by the `tres_suite` backend; this program collects your choices, runs it, and shows the results.

## 1. Organise your data

The program reads the folder structure, so arrange the workbooks before you start:

    laurdan/                      ← the folder you drop (Level 1)
      DOPC 5 DPPC 5/              ← Level 2
        17/   1.xlsx  2.xlsx      ← Level 3: one condition group; the workbooks in it are the replicates
        20/   1.xlsx  2.xlsx
      dopc/
        17/   …

Rules:

* The workbooks in the deepest folders are averaged as replicates. Everything above them is a label.
* Every folder you drop must have the same depth (you cannot mix a two-level and a three-level folder).
* Folder names that look like numbers (`17`, `23.5`, `17C`, `300K`) are used as numeric positions on comparison axes, so name temperature or concentration folders with plain numbers.
* Do not mix TRES and anisotropy workbooks in the same group; such a group is blocked.
* Temporary Excel files (`~$…`) and non-Excel files are ignored.

## 2. Start screen

Drop one or more data folders onto the dashed area, or click **Browse for folder…**. You can add more folders later with **Add folder…** under the folder tree, and remove one with the × next to its name.

## 3. Options

**Folder level names** — give each level a name (for example *Probe*, *Composition*, *Temperature*). The names appear on axes and in the exports; they carry no scientific meaning.

**Measurement type** is detected from the workbooks. The radio button only shows what was found.

**Probe name** is recorded in the exports.

TRES options:

* **Ratio measure** — *GP (440 / 490 nm)* for Laurdan, or a *Custom* expression written with intensities at wavelengths in nm, e.g. `I(510) / I(430)`. The GP wavelengths can be changed under *Advanced › Analysis*.
* **ν₀ for TDFS** — the time-zero peak frequency in cm⁻¹ that Δν and τr are referenced to. *Custom* uses a literature value (≈ 23 800 cm⁻¹ for Laurdan). *Apparent* uses the first reconstructed spectrum instead and flags every group with a warning, because the results are then finite-window apparent values.

Anisotropy options:

* **Microviscosity** — *Calculate* turns on the rotational-diffusion add-on: η = k_B T / (6 D⊥ V_eff) with D⊥ from the Kinosita polynomial in r∞ / r₀. *Skip* keeps only r∞, φ and the amplitudes.
* **Effective volume** with its unit. The legacy constant `161e-22` equals 161 Å³.
* **Temperature** — *From folder level* reads each group's temperature from the numeric folder name of the chosen level (plain numbers are °C; `300K` or `17C` keep their unit). *Fixed* uses one value in kelvin for the whole run.
* **r₀ source** — literature (0.39, editable under *Advanced*), the R0 that EzTime fitted in each workbook, or a custom value.

**Start over** clears the loaded folders and results (Advanced settings are kept). **Run analysis** starts the run.

## 4. Running

A popup shows the files being loaded and analysed; **Cancel** stops between files. Expect roughly one second per workbook on a laptop.

When the run finishes:

* If some groups could not be analysed, a popup lists each one with the reason and the files involved (different numbers of fit components, mismatched wavelength ranges or spacing, mixed workbook types, unreadable files). Those groups are shown greyed out with ✕ in the folder tree and are left out of every average; the rest of the run is complete. Fix the files and run again.
* Warnings (high χ², large replicate variation, …) never block anything. The popup shows how many there are; the details are in `diagnostics.csv` of every export.

## 5. TRES results — Single sample

Tick the plots you want, then drag one deepest-level folder from the tree onto the drop zone. The graph viewer opens with the plots along the bottom.

| Plot | What it shows |
|---|---|
| Normalized spectrum | Pseudo steady-state spectrum (total counts per wavelength, normalised to its maximum), replicate mean ± SD |
| Full TRES | Reconstructed spectra at the export times |
| TRANES | The same spectra, each normalised to unit area |
| Relative amplitude | DAS as relative amplitude per lifetime component |
| Pre-exponential | DAS as normalised pre-exponential factors (can be negative) |
| Bubble plot | Lifetime vs DAS peak position; bubble area = DAS area. A peak at the first or last wavelength means the component's DAS keeps rising to the edge of the measured range |
| Δν (spectral shift) | Peak frequency of the reconstructed spectrum vs time |
| FWHM | Width of the reconstructed spectrum vs time |
| τr (relaxation time) | Relaxation function C(t) of the peak shift |

In the viewer you can edit the axis titles, set a range (blank = automatic) and set a fixed plot size in inches; **Data table** shows exactly the numbers that were drawn.

## 6. Comparison (TRES and anisotropy)

Choose what each axis is:

* **Group** — drag folders one level above the groups (e.g. compositions) onto the drop zone. Each folder becomes one line; the numeric names of its subfolders (e.g. temperatures) are the positions on the axis. *Values from* picks the level when there are more than three.
* **Value** — a metric, one point per group averaged over replicates, with the sample SD as error bars. TRES metrics: GP or custom ratio, ⟨τ⟩, Δν, τr, τ FWHM and the centre-of-mass variants; anisotropy metrics: r∞, ⟨φ⟩, microviscosity. *Linear fit + R²* adds a fit per series.
* **Value vs Value** (e.g. GP against ⟨τ⟩) plots one point per group with SD on both axes. Drag folders to split the points into series, or drag nothing to plot every group.

Press **Plot →**. On the graph page you can change each series' colour and marker, add or remove series, and edit the axes and plot size. **← Back to setup** keeps your selection.

## 7. Exports

* **Export graph as…** — PNG, SVG or PDF of the graph exactly as shown. Resolution: *Advanced › Output*.
* **Export data as…** — CSV of the plotted values (x, y, SD, n per point).
* **Export full data…** — everything the backend produces, in a folder you choose: `tres_summary.csv` / `anisotropy_summary.csv` (per-group mean, SD, n for every metric), the per-replicate tables, `records.csv`, per-metric tables, per-group DAS / bubble / TDFS files, legacy-style tables, `diagnostics.csv`, `inventory.csv`, `run_config.json` (every setting, so the run can be repeated exactly), and every graph you looked at in this session under `plots/`. If the folder already contains files you are asked first.

## 8. Advanced settings

The values shown are the defaults; **Reset tab to defaults** restores them.

* **Analysis** — TDFS reconstruction step, metric start time, tail points, intensity floor, FWHM smoothing, clipping of negative C(t), centre-of-mass metrics; DAS amplitude source (full precision vs the 2-decimal Summary values) and bubble peak method; GP wavelengths; which φ enters the viscosity and the literature r₀.
* **Validation** — warning thresholds (χ², replicate variation and which metrics are checked, anisotropy φ spread) and the structural tolerances. Leave a box empty to report without warning.
* **Output** — image formats and DPI, overwrite policy, which optional file groups the full export contains.
* **Extras** — time-gated spectra from the raw *Data* sheet, the number of parallel workers (more is faster; results are identical), and the log-normal fit review.

## 9. Log-normal fit review

Splits every DAS component into 1–3 log-normal peaks so you can locate sub-populations within a component. For each group and component: check the fit, change the number of peaks or the low/high bounds in nm, **Refit**, then **Accept →** or **Skip component**. **Accept all remaining as-is** takes the current fit of everything not yet reviewed. **Export fits…** writes, per group, the fit figures, `bub data.csv`, `bubble_data_full.csv` and a bubble plot, plus `deconvolution_decisions.json`, which reproduces the whole review without any prompts. The same files are included in *Export full data*.

## 10. If something goes wrong

* The program writes `detreser.log` next to itself (or in your home folder). It records every run, the progress, and any error with a traceback — send it along with a description of what you clicked.
* A blocked group is almost always a data problem: compare the files listed in the popup.
* A plot that says "This plot is not available" names the reason (for example TDFS was not computed for an anisotropy group).

Backend documentation (methods, validation rules, output columns) is in `tres_suite/docs/`. Fonts: IBM Plex (SIL Open Font License).
