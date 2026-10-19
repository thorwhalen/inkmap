# Validation

Every number here is reproducible with `python scripts/validate.py` (synthetic, no
network) and `python scripts/corpus_eval.py` (real photographs, needs the cached
corpus). Medians over 12 scenes per condition unless stated.

## Why synthetic scenes are not optional

A coverage map cannot be validated against photographs. Nobody can hand-label what
fraction of a pixel is foreground, and no public dataset carries per-pixel coverage
ground truth for printed marks — the document-binarisation benchmarks (DIBCO) are
binary.

So `inkmap.synth` renders the image **from** the coverage map: supersample the model
through a known transform to get exact coverage, then form the clean image as
`255 * (1 - coverage)`. Ground truth and stimulus are the same object by construction.
Degradations applied afterwards (blur, noise, illumination gradient, glare, JPEG) leave
the ground truth correct.

This works for *any* model, so a text or logo pipeline is validated exactly as a QR one
is. Real photographs then answer the question synthetic scenes cannot: does detection
survive a curved bottle under a sodium lamp.

## Geometric accuracy

Corner RMS error against the known transform. "Locator corners" is the best of the
cascade; "refined" adds ECC alignment of the rendered model.

| condition | locator corners (px RMS) | refined (px RMS) | gain |
|---|---|---|---|
| clean, frontal | 0.87 | 0.02 | 42× |
| mild perspective | 1.05 | 0.02 | 53× |
| strong perspective | 1.08 | 0.05 | 23× |
| defocused (σ=3) | 0.99 | 0.08 | 12× |
| noisy + gradient | 1.31 | 0.10 | 14× |
| glare + JPEG q70 | 0.90 | 0.21 | 4× |

Locators return integer corner coordinates, so ~1 px is their floor regardless of image
quality. Four corners are four observations; the model has thousands.

### Three half-pixel conventions have to agree

This cost 50× in accuracy during development. Each is invisible on inspection — the
mask still looks right:

1. **Pixel centre vs pixel corner.** OpenCV treats integer coordinate `x` as the
   *centre* of a pixel spanning `[x-0.5, x+0.5)`. Rasterising `[x, x+1)` instead — the
   natural array-indexing reading — offsets the entire coverage map by half a pixel.
2. **The template raster.** A model rendered at `s` px per unit puts template pixel `t`
   over `[t/s, (t+1)/s)` in model units, so its *centre* is `(t+0.5)/s`. Omitting that
   half-pixel puts a fixed 0.71 px bias into every refinement.
3. **Locator corner conventions differ.** OpenCV's QR corners are the integer index of
   the last *contained* pixel, so its quad spans `N·s − 1`. zxing-cpp returns the
   continuous outer boundary, spanning `N·s`. Measured directly, not read from docs.

A symptom worth recognising: if refinement error grows with the mark's rotation angle
in the pattern `R(d) − d`, the residual `d` is a coordinate-convention offset, not
noise.

### The template needs a margin

Blurring a template that stops at the mark's edge makes the blur kernel reflect interior
content across the border, inventing an edge profile the photograph does not have. ECC
then shifts the whole fit to match the artefact — a ~0.45 px bias. Rendering two units
of clear margin removes it.

## Coverage accuracy

Mean absolute error against exact ground truth, at 9.7 px per unit.

| condition | overall MAE | MAE on mixed pixels |
|---|---|---|
| clean | 0.0000 | 0.000 |
| mild perspective | 0.0000 | 0.003 |
| strong perspective | 0.0001 | 0.009 |
| glare + JPEG q70 | 0.0005 | 0.042 |

"Mixed pixels" are those with true coverage strictly between 0.02 and 0.98 — the ones
straddling an edge. They are the only place error accumulates, which is consistent:
coverage error is dominated by residual transform error, and only edge pixels are
sensitive to it.

Across model kinds, on the same conditions (perspective 0.02, blur 1.0, noise 2), MAE:
matrix 4e-5, raster 1.1e-5, polygon 7.7e-5, bars 1.3e-4, glyph 4.4e-5. The pipeline does
not care what shape it is given.

## Photometric bias — the result that drives the design

Recovering a foreground-only signal (true value 100) from a frame blurred by the camera
point spread function, so foreground signal bleeds into neighbouring background pixels.
Bias in percent:

| px/feature | PSF σ | `coverage > 0.5` | `coverage == 1.0` | `weight` (2σ erosion) |
|---|---|---|---|---|
| 12 | 0.0 | −1.75% | −0.01% | +0.00% |
| 12 | 1.0 | −6.61% | −4.10% | **−0.07%** |
| 12 | 2.0 | −12.87% | −10.47% | **−0.37%** |
| 12 | 3.0 | −18.86% | −16.76% | **−0.49%** |
| 6 | 0.0 | −3.45% | −0.02% | +0.00% |
| 6 | 1.0 | −12.89% | −8.53% | **−0.26%** |
| 6 | 2.0 | −24.40% | −21.05% | **−0.63%** |
| 6 | 3.0 | −33.78% | −31.52% | **−1.40%** |

Three things follow, and they are why the API looks the way it does:

1. **A thresholded mask is not good enough.** `coverage > 0.5` — what any binarisation
   gives you — is biased by up to 34%.
2. **Geometric purity is necessary but not sufficient.** `coverage == 1.0` still carries
   up to 32% bias, because the PSF drags background signal into pixels entirely under
   foreground. Coverage and optical contamination have different footprints, so no
   coverage-based weighting can fix it. Only spatial erosion can.
3. **Erosion by ~2σ works, until it doesn't.** It holds bias below ~0.5% while features
   are large relative to the blur. As `px/feature ÷ σ` falls toward ~2, erosion consumes
   the feature and nothing uncontaminated remains. That is the classic partial-volume
   result, and it is why `measurability()` refuses rather than returning a number.

## Blur estimation

Estimated from the mark's own edges by matching observed edge softness against the
modelled ideal.

| true σ | estimated (median) |
|---|---|
| 0.5 | 0.30 |
| 1.0 | 0.92 |
| 1.5 | 1.54 |
| 2.0 | 2.16 |
| 3.0 | 2.78 |

Accurate between about 1 and 2 px. At σ=0.5 the estimate hits the bottom of the search
grid — harmless, since the resulting erosion radius is 1 px either way. At σ=3 it
underestimates by ~7%; if you know your optics, pass `margin=` explicitly.

A minimum at the *top* of the search range is reported as `nan` rather than as a
measurement: it means the modelled shape and the photograph do not correspond (bad
transform, wrong model, heavy damage), and reporting the boundary value would silently
size the measurement margin from noise.

## Square registration marks

`inkmap.find_square_marks` on `synth.mark_sheet()`: three bullseyes (rings 0.64, 0.32) and a solid square at the corners of a card, two QR finder patterns (7:5:3) inside it, rendered at ~60 px per mark in a 1200 × 900 frame with noise σ = 2. Twelve scenes per row, at random in-plane rotations, and again axis-aligned (0°), which is the hard case for sub-pixel edges: along a side that runs with the pixel grid, quantisation does not average out. "Perspective" jitters each corner of the card by up to that share of its span. A mark cut by the frame is not expected, and is correctly not reported. The error is the distance from the true projective centre, from the scene's own transform.

| rotation | perspective | blur (px) | marks found | misclassified | false marks | centre error median (px) | p95 (px) | max (px) |
|---|---|---|---|---|---|---|---|---|
| random | 0.00 | 0.5 | 60/60 | 0 | 0 | 0.009 | 0.026 | 0.032 |
| random | 0.00 | 1.0 | 60/60 | 0 | 0 | 0.006 | 0.030 | 0.040 |
| random | 0.00 | 1.5 | 60/60 | 0 | 0 | 0.010 | 0.033 | 0.048 |
| random | 0.00 | 2.0 | 60/60 | 0 | 0 | 0.016 | 0.035 | 0.070 |
| random | 0.05 | 0.5 | 65/65 | 0 | 0 | 0.008 | 0.024 | 0.047 |
| random | 0.05 | 1.0 | 65/65 | 0 | 0 | 0.008 | 0.016 | 0.019 |
| random | 0.05 | 1.5 | 65/65 | 0 | 0 | 0.011 | 0.027 | 0.032 |
| random | 0.05 | 2.0 | 65/65 | 0 | 0 | 0.018 | 0.033 | 0.055 |
| random | 0.10 | 0.5 | 65/65 | 0 | 0 | 0.009 | 0.036 | 0.097 |
| random | 0.10 | 1.0 | 65/65 | 0 | 0 | 0.008 | 0.027 | 0.048 |
| random | 0.10 | 1.5 | 65/65 | 0 | 0 | 0.013 | 0.033 | 0.052 |
| random | 0.10 | 2.0 | 63/65 | 0 | 0 | 0.020 | 0.045 | 0.051 |
| random | 0.15 | 0.5 | 65/65 | 0 | 0 | 0.008 | 0.045 | 0.061 |
| random | 0.15 | 1.0 | 65/65 | 0 | 0 | 0.010 | 0.052 | 0.066 |
| random | 0.15 | 1.5 | 65/65 | 0 | 0 | 0.013 | 0.066 | 0.071 |
| random | 0.15 | 2.0 | 64/65 | 0 | 0 | 0.023 | 0.068 | 0.085 |
| 0° | 0.00 | 1.0 | 72/72 | 0 | 0 | 0.016 | 0.092 | 0.101 |
| 0° | 0.00 | 1.5 | 72/72 | 0 | 0 | 0.017 | 0.073 | 0.082 |
| 0° | 0.05 | 1.0 | 72/72 | 0 | 0 | 0.019 | 0.070 | 0.092 |
| 0° | 0.05 | 1.5 | 72/72 | 0 | 0 | 0.018 | 0.057 | 0.077 |
| 0° | 0.10 | 1.0 | 72/72 | 0 | 0 | 0.013 | 0.045 | 0.092 |
| 0° | 0.10 | 1.5 | 72/72 | 0 | 0 | 0.013 | 0.053 | 0.104 |
| 0° | 0.15 | 1.0 | 72/72 | 0 | 0 | 0.010 | 0.048 | 0.128 |
| 0° | 0.15 | 1.5 | 71/72 | 0 | 0 | 0.012 | 0.048 | 0.118 |

The two refinements that earn these numbers, measured on the same layout while developing: fitting each side to the grey image's mid-level edge crossings rather than to the binary contour's pixels (axis-aligned worst case 0.57 px → 0.16 px), and taking a nested mark's centre as the side-weighted mean of its squares' centres, which a homography maps to one point (nested worst case 0.16 px → 0.10 px). Reproduce with `python scripts/validate.py marks`.

Where it stops: each ring must be several blur widths across. With the same layout at ~30 px per mark, blur 1.5 px merges a bullseye's rings and it is lost; a mark wider than the local-mean window (12% of the frame's shorter side) is hollowed by its own ink. A disc under ~10 px radius cannot be told from a square of its size.

## Real photographs

189 CC-licensed photographs of QR codes in the wild from Wikimedia Commons — signs,
posters, packaging, business cards, stickers, billboards, menus, tickets, screens.
Downscaled to 1600 px on the long side first.

**Detection**:

| locator | images with a detection |
|---|---|
| zxing-cpp | 74% |
| OpenCV `QRCodeDetectorAruco` | 68% |
| OpenCV `QRCodeDetector` | 43% |
| **cascade (union)** | **80%** |

OpenCV's classic detector alone forfeits ~37 points of recall. 38 of the 189 images
contain more than one mark, so `find_all` is the honest default.

**End to end:**

| metric | value |
|---|---|
| images with ≥1 mark | 152 / 189 (80%) |
| marks found | 192 |
| refinement converged | 185 / 192 (96%) |
| judged measurable | 97 / 192 (51%) |
| median runtime | 252 ms |

**Polarity check** — for every mark with enough measurable pixels, does the foreground
read darker than the background? This is the end-to-end correctness check visual
inspection cannot give: a mask that is rotated or half a unit off still *looks* right,
but it mixes the classes and the separation collapses.

| metric | value |
|---|---|
| marks measured | 176 |
| correct polarity | 176 / 176 (100%) |
| separation > 50 grey levels | 171 / 176 (97%) |
| median separation | 156 grey levels |

That the measurability gate rejects 49% is the point, not a defect: most web photographs
of QR codes sit at 2–4 px/module, where no honest measurement is possible.

## Known limits

- **Micro QR and rMQR are ignored, not fitted.** Different module counts; fitting one as
  a full QR would silently produce a wrong grid.
- **Halftoned/screened prints.** A modelled coverage reports *nominal* geometry. If the
  material is screened rather than solid-fill, a nominally-covered cell is only partly
  covered, and `observed_coverage` is the one that reflects reality. Several images in
  the real corpus are screened — check with `viz.panel`.
- **Non-planar substrates.** A single homography assumes a plane. On a bottle or a
  wrinkled label the fit degrades toward the edges. QR alignment patterns (version ≥ 2)
  would support piecewise correction; not implemented.
- **Coverage is geometric, not optical.** It says where foreground *should* be. It
  cannot see material that failed to deposit — for that, compare against
  `observed_coverage`, whose disagreement with `coverage` is exactly the defect signal.
- **Text location is manual.** `GlyphModel` models printed text, but nothing here finds
  it: pass `quad=` from your own OCR or layout analysis.
