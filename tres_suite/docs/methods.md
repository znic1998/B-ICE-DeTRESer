# Methods, conventions and intentional changes

All symbols refer to one replicate workbook unless stated otherwise.

## 1. What is read from an EzTime TRES export

| Quantity | Source | Notes |
|---|---|---|
| λ_k (nm) | `Results` table, column `Wavelength/nm` | read as-is, any range, any spacing; no 300–800 nm cutoff |
| τ_i (ns), σ(τ_i) | `Results` "Global" block (`T<i>/ns`, `σ T<i>/ns`) | full precision. The `Summary` sheet stores the same lifetimes as 6-significant-digit strings, which the legacy scripts used |
| B_i(λ) | `Results` columns `B<i>` | signed pre-exponentials |
| α_i(λ) | `Results` columns `α<i>` | signed normalised pre-exponentials, α_i = B_i / Σ_j |B_j| (verified against real exports) |
| RA_i(λ) (%) | derived: 100·|B_i|τ_i / Σ_j |B_j| τ_j | EzTime's unsigned "Relative Amplitude"; agrees with the `Summary` sheet to within its 2-decimal rounding (max 0.005 over 481 files) |
| F(λ) | `Results` column `Total count` | integrated photons per wavelength = steady-state proxy |
| χ² | `Results` Global `Chi sq.` and per-wavelength `Chi sq.` | reported as exported; whether it is reduced is not stated by EzTime |
| Summary RA_i, NPE_i | `Summary` blocks, columns 8 and 9 | 2-decimal strings; kept for legacy comparison (`das.amplitude_source: summary`) |

Components are ranked by ascending lifetime; every component-indexed column is
permuted consistently (`original_component_index` records the EzTime index).
Across replicates components are aligned **by lifetime rank** (τ1 = shortest).
Nothing else (e.g. amplitude sign pattern) is used for alignment; this is the
legacy convention and is documented rather than changed.

## 2. DAS quantities

* F_norm(λ) = F(λ)/max F;  F_area(λ) = F(λ)/∫F dλ (trapezoid over the actual λ).
* DAS emission of component i: **E_i(λ) = RA_i(λ)/100 · F_norm(λ)**; total E = Σ_i E_i.
* Component weight W_i = ∫ E_i(λ) dλ (trapezoid over actual coordinates; the
  legacy `dx=interval` gives the same ratios on a uniform grid).
* **Mean lifetime** ⟨τ⟩ = Σ_i τ_i W_i / Σ_i W_i (emission-weighted; the paper's
  definition; no Laurdan-specific assumption).
* Area percent (bubble size) = 100·W_i / Σ_j W_j.
* Component peak position: parabolic interpolation around the maximum of
  E_i(λ) (`single laurdan.py` method).  Optional non-interactive log-normal
  deconvolution (`das.bubble_method: lognormal_fit`) ports the `tres1.py`
  fitting functions with explicit peak counts and bounds and reports R² and the
  legacy χ² for each fit.
* Signed α_i(λ) are exported as the normalised-pre-exponential representation.

## 3. Intensity ratios (GP and custom)

GP = (I_blue − I_red)/(I_blue + I_red) with defaults 440/490 nm, on the
total-count spectrum, **enabled explicitly** (`das.gp_enabled`).  Any ratio can
be written as a restricted expression over `I(λ)` (`+ − * /`, parentheses,
numbers) – parsed with the `ast` module, never executed.  Intensities are
linearly interpolated **only inside the measured range**; an out-of-range
wavelength or a zero denominator makes the metric unavailable with a stated
reason (exported as an empty value plus `<metric>_available=False` and
`<metric>_reason`).  The legacy `np.interp` clamping to the endpoint is removed.

## 4. TRES reconstruction and TDFS

Reconstruction (impulse response pinned to the steady-state proxy):

    I(λ,t) = F_area(λ) · Σ_i α_i(λ) e^{−t/τ_i} / Σ_i α_i(λ) τ_i

so that ∫₀^∞ I(λ,t) dt = F_area(λ).  Wavelengths with Σ_i α_i τ_i ≤ 10⁻¹² are
masked to zero and listed (`recon_wavelengths_masked`, `recon_masked_wavelengths_nm`).
Time grid: 0 … max(35 ns, 6·τ_max) in steps of 0.01 ns (all configurable).

Each time slice is converted to a wavenumber-density spectrum S(ν) = I(λ)·λ²,
ν = 10⁷/λ (cm⁻¹), interpolated with a cubic spline on 1000 points, clipped at
zero, and characterised by its **peak** (primary), centre of mass (secondary)
and FWHM (connected half-maximum region; NaN when it reaches the acquisition edge).

Usable window: times for which the positive spectral area ≥ 1 % of its t = 0
value (`intensity_floor`).  Metric window: t ≥ 0.1 ns (`metric_tmin_ns`).

    ν_∞  = mean of the last 5 ν(t) values in the metric window (tail_points)
    ν_0  = user value (cm⁻¹, `tdfs.nu0_cm1`)  or  ν(t_first ≥ 0.1 ns)  ("apparent", recorded with its time)
    Δν   = ν_0 − ν_∞
    C(t) = (ν(t) − ν_∞)/Δν,  clipped at 0 (`clip_negative_c`, legacy convention)
    τ_r  = ∫ C(t) dt over the metric window (trapezoid)

`peak_nu0_source` states which mode produced ν_0.  **No literature value is
substituted silently**: with `nu0_cm1: null` the apparent mode is used, reported,
and every analysed group receives a `tdfs_nu0_apparent` warning stating that Δν
and τ_r are finite-window apparent quantities.  `peak_at_boundary_fraction`
(fraction of usable spectra whose raw maximum sits at the wavelength-range
edge) is exported with an info diagnostic so that the user can judge whether
peak metrics are meaningful for their probe; nothing is filtered.  The COM coordinate always uses its own apparent ν_0 unless
`com_nu0_cm1` is given (a peak-based literature ν_0 is not a COM value).
τ_FWHM = time of the maximum of the Savitzky–Golay-smoothed FWHM trajectory
(0.25 ns window, order 2) over the usable window from t = 0.

Also exported: the full ν_peak(t), ν_COM(t), FWHM(t), C(t) trajectories; the
reconstructed TRES and area-normalised TRANES at the configured times; the
legacy finite-window COM shift (0.25 → 10 ns).

### Removed validity gate

The heuristic "kinetic / curve / joint" physical-validity classification of
`tdfs big.py` is **not evaluated**.  Its ingredient values are still computed
and exported under `legacy_*` names (late slope, tail span, ν_∞ sensitivity,
non-monotonic fraction, negative-C fraction, overshoot, negative spectral area,
boundary-peak fraction, FWHM span, rise fraction, τ_relax, x_kinetic, captured
fraction) together with `legacy_gate_evaluated = False`.  They never filter Δν,
τ_r, GP or ⟨τ⟩.  The legacy wide tables keep a `Valid` column containing the
literal `UNEVALUATED`.

## 5. Anisotropy

Base quantities for any probe: φ_i (ranked ascending), σ(φ_i), B_i, α_i, RA_i,
r_∞, σ(r_∞), fitted r(0) = r_∞ + ΣB_i, amplitude-weighted ⟨φ⟩ (EzTime
`Ave T/ns`), χ².  Nothing DPH-specific is applied.

Optional add-on (`wobble.enabled: true`; blocked, not the base analysis, when a
parameter is missing):

    k = r_∞ / r_0
    D⊥ = (0.1674 − 0.1066 k − 0.0062 k²) / φ           [ns⁻¹]   (Kinosita et al. approximation, as in the paper)
    η  = k_B T / (6 D⊥ V_eff)                          [Pa·s]; also ×10 in Poise

Required: `effective_volume` + `effective_volume_unit` (A3 | nm3 | cm3 | m3;
the legacy `161e-22` constant with Poise output ≡ 161 Å³), `temperature_K`, and
the fundamental anisotropy via `r0_source`: `literature` (default, `r0_literature`
= 0.39 as in the legacy `dph()`), `fitted` (the workbook R0 = r∞ + ΣB_i) or `user` (`r0`).
`phi_selection` chooses which correlation time enters (`mean` = legacy
behaviour, `longest`, `shortest`, `component:k`).  With the legacy inputs
(161 Å³, 293 K, r_0 = 0.39, mean φ) the result equals the legacy `dph()` value
in Poise (tested).

## 6. Replicate statistics

Arithmetic mean, **sample SD (ddof = 1)** and n for every numeric metric
(tdfs big.py convention; `tres1.py` used population SD – documented
difference).  One replicate → SD undefined (empty), never 0.  Booleans, text,
identifiers and component indices are never averaged.  Spectra and
trajectories: per-replicate quantity first, then point-wise mean/SD (grids are
validated identical; trajectories are interpolated onto the intersection of
the replicate time windows, no extrapolation).  Fit uncertainties (σ from
EzTime) are exported separately and never mixed with replicate SD.

Case-5 replicate variation: 100·SD/|mean| per configured scalar metric; n < 2 →
"insufficient replicates"; |mean| ≤ `replicate_variation_near_zero_mean`
(default 1e-9) → percentage undefined, mean and SD shown.

## 7. Simple statistics

`stats.linear_fit`: unweighted least squares y = a·x + b; R² = 1 − SSE/SST; the
model, range, n, definition and standard errors are exported with every fit.
n < 3, constant x or constant y are reported as unavailable with the reason.

## 8. Intentional changes from the legacy code (and why)

| Change | Legacy | Now | Effect |
|---|---|---|---|
| Amplitude precision | 2-decimal Summary strings | full-precision Results columns (default); `amplitude_source: summary` reproduces legacy | see validation report: Δν/τ_r differ by ≤ 1 % for fluid DOPC but up to 5 % / 65 % for gel DPPC where the peak sits at the acquisition edge |
| Lifetime precision | 6-significant-digit Summary strings | full precision from Results | ≤ 5·10⁻⁶ ns |
| GP outside range | endpoint value (np.interp clamp) | unavailable with reason | none inside range |
| Peak ν_0 | hard-coded 23 800 cm⁻¹ | user value or apparent, recorded | same numbers when the user supplies 23 800 |
| Validity gate | filters graph exports | unevaluated diagnostics | nothing hidden |
| Wavelength parsing | 300–800 nm cutoff, stride tables per component count | label-based, any count/range/spacing; every per-wavelength array is reordered to ascending wavelength at parse time | none on supplied files |
| RA definition | read from Summary | derived from B_i, τ_i with the verified EzTime convention | ≤ 0.005 % points |
| Trajectory sampling for τ_FWHM | 200 sampled spectra | every reconstructed step | ≤ 0.03 ns |
| SD | ddof=1 (tdfs big) / ddof=0 (tres1) | ddof=1 everywhere | tres1 comparison only |
| Grid handling | pad with NaN / assume uniform | reject mismatched grids; non-uniform only when allowed explicitly | none on valid groups |

## 9. Advanced features (explicitly enabled)

### Time-gated spectra and measured energy metrics (`time_gated.enabled: true`)

Port of `single laurdan.py` sections 1/4/4a/4b on the raw `Data` sheet: each
replicate's decays are normalised by their photon sum, aligned so that the
summed-intensity maximum is at t = 0, interpolated on −2…50 ns / 0.05 ns,
averaged, Gaussian-smoothed (σ = 5 time steps, 1 wavelength step), then:
area-normalised time-gated spectra (default gates 0–0.5, 0.5–2, 2–7 ns;
integral or mean), and for t ≥ t_peak while the summed intensity ≥ 5 % of its
maximum the wavenumber-domain peak/COM/FWHM, v(t) truncated at its first
minimum and C(t) with v_0/v_∞ = means of the first/last three points.  These
are IRF-limited (~250 ps) comparison quantities, never used for the TDFS parameters.
Outputs: `groups/<group>/time_gated/*.csv`.

### Log-normal deconvolution review (`python -m tres_suite deconvolve OUT_DIR`)

Port of the `fitter()`/`deconvol()` terminal workflow of `tres1.py`: for each
DAS component of a finished run's group the fit (1–3 log-normals,
`lognormal.fit_component`) is previewed as `fit_tau<i>.png` with peak centres,
areas, R² and the legacy χ²; the user accepts, or edits the peak count and
bounds and refits.  Accepted settings and parameters go to
`deconvolution/deconvolution_decisions.json`; `--replay` reproduces the exports
without prompts; `--no-prompt` accepts the first fits.  Exports per group:
`bub data.csv` (`lifetime, peakposition, area, region` – area in % of all
fitted peak areas, region empty), `bubble_data_full.csv`, `bub plot.png`.
The interaction layer (`advanced/deconvolution.py`) is separate from the
numerical layer so a GUI can drive it.  A `stacked_area_bar` plot type stacks
DAS area % per lifetime component (replacing the region-based stacked bar).
