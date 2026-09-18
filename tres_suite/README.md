# tres_suite

Backend for HORIBA DeltaFlex / EzTime time-resolved emission exports: TRES
reconstruction, decay-associated spectra (DAS), peak-based time-dependent
fluorescence shift (TDFS), Laurdan GP / custom intensity ratios, and
time-resolved anisotropy (with an optional, explicitly enabled
rotational-diffusion add-on).  

## Install

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .            # or: pip install -r requirements.txt
python -m pytest tests -q   # unit tests on synthetic workbooks (~10 s)
```

Requires Python ≥ 3.9 with numpy, scipy, pandas, openpyxl, matplotlib, PyYAML.
Importing `tres_suite` performs no analysis, no prompting and no file writing
(this is tested).

## Run the documented example

```bash
python -m tres_suite run examples/example_config.yaml
```

The example config expects the supplied `TEST DATA/DATA` folder two levels
above the package (edit `project.import_folders`).  Other commands:

```bash
python -m tres_suite inspect  "path/to/workbook.xlsx"   # what the parser reads (type, components, grid, lifetimes)
python -m tres_suite validate config.yaml                # import + all validation rules, no analysis, no writing
python -m tres_suite run config.yaml --output OUT --overwrite
python -m tres_suite deconvolve OUT [--group "DOPC / 15"] [--peaks 2,2,3] [--replay OUT/deconvolution/deconvolution_decisions.json] [--no-prompt]
                                                         # advanced: terminal fit review (preview -> edit bounds -> refit -> accept -> export)
```

Advanced features are off by default: `time_gated.enabled: true` adds the
IRF-limited time-gated spectra / measured metrics from the raw `Data` sheet;
`project.workers: N` parses workbooks in parallel; `wobble.enabled: true`
adds the anisotropy microviscosity add-on (volume with unit, temperature,
r₀ from literature 0.39 / fitted / user).

## Data organisation

* A **measurement** is one workbook.  Its identifier is a stable hash of its
  path; the original labels and path are kept in every export.
* Folder levels are named by you (`project.level_names`, e.g.
  `[Composition, Temperature, Replicate]`).  Names carry no fixed scientific
  meaning.  The last level is the replicate level by default; with
  `folder_depth = len(level_names)` numbered replicate *folders* each holding a
  workbook are supported.  Files can also be added explicitly with labels
  (`project.files`).
* A **condition group** = replicates to be averaged (all levels except the
  replicate level).  A **selection** is any set of groups chosen by label
  values (e.g. every `DOPC` temperature); selections are plotted as series,
  never pooled.
* Labels that look numeric (`5`, `15`, `100`, `17C`, `23.5 °C`, `300K`) get a
  numeric value and unit for sorting and plotting; the original text is kept.
* Temporary Excel lock files (`~$…`) are skipped; non-workbook files are listed
  in the inventory as skipped.

## Validation policy

An **error** blocks its condition group (the group is listed as blocked, the
run is *partially completed*, nothing is averaged from a reduced subset).
**Warnings** never block.  See `docs/validation_rules.md` for every rule, the
seven intentional error cases and the configurable thresholds.  When a
threshold is not configured the values are reported without any pass/fail claim.

## Outputs

`docs/output_schema.md` documents every file and column with units.  In short:
`tres_replicates.csv` / `tres_summary.csv` (legacy-style tables), `records.csv`
(long format with identifiers, units, n, status), `metric_tables/` (wide tables
per metric), `groups/<group>/` (DAS spectra, bubble quantities, TDFS
trajectories, reconstructed TRES/TRANES per replicate), `plots/` (PNG + SVG +
the exact plotted values + metadata), `legacy/` (tres1/tdfs big layouts),
`inventory.csv`, `coverage_report.csv`, `diagnostics.csv/json`, `run_config.json`,
`environment.json`, `run_manifest.json`.


## Documentation

* `docs/methods.md` – equations, conventions, intentional changes from the legacy scripts
* `docs/validation_rules.md` – diagnostics, thresholds, error-case behaviour
* `docs/output_schema.md` – files, columns, units
* `docs/legacy_inventory.md` – what the legacy scripts did and where each part went
* `docs/validation_report.md` – comparison against the supplied reference outputs and coverage of all supplied files
* `docs/open_questions.md` – decisions taken, remaining questions, unsupported inputs, deferred features
