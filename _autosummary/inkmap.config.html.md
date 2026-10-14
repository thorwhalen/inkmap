# inkmap.config

Tunable defaults, in one place.

Every number the algorithms depend on lives here rather than inline, so behaviour can
be adjusted without editing logic and the meaning of each constant is documented
exactly once. Functions take these as keyword-only defaults; nothing reads the module
at call time, so overriding one is a call-site concern, not global mutable state.

### Module Attributes

| [`SUPERSAMPLES`](#inkmap.config.SUPERSAMPLES)                  | Sub-samples per pixel per axis when computing area coverage.                                                                                                                                                                                                                                                                                                                            |
|--------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`ECC_TEMPLATE_BLUR_FRAC`](#inkmap.config.ECC_TEMPLATE_BLUR_FRAC)        | Gaussian smoothing of the ECC template, as a fraction of one model unit's rendered size.                                                                                                                                                                                                                                                                                                |
| [`ECC_MIN_CORRELATION`](#inkmap.config.ECC_MIN_CORRELATION)           | Minimum ECC correlation for a refinement to be accepted.                                                                                                                                                                                                                                                                                                                                |
| [`ECC_MIN_SCALE`](#inkmap.config.ECC_MIN_SCALE)                 | The template is rendered at the observed pixels-per-unit, clamped here.                                                                                                                                                                                                                                                                                                                 |
| [`TEMPLATE_MARGIN_UNITS`](#inkmap.config.TEMPLATE_MARGIN_UNITS)         | Clear margin rendered around the ECC template, in model units.                                                                                                                                                                                                                                                                                                                          |
| [`MARGIN_UNITS`](#inkmap.config.MARGIN_UNITS)                  | Default clear margin around a mark, in model units, labelled Region.MARGIN.                                                                                                                                                                                                                                                                                                             |
| [`PURE_COVERAGE_TOL`](#inkmap.config.PURE_COVERAGE_TOL)             | Coverage within this of 1.0 (or 0.0) counts as pure.                                                                                                                                                                                                                                                                                                                                    |
| [`EDGE_MARGIN_SIGMAS`](#inkmap.config.EDGE_MARGIN_SIGMAS)            | Default erosion of the pure-foreground mask, in multiples of the estimated blur sigma.                                                                                                                                                                                                                                                                                                  |
| [`DEFAULT_BLUR_SIGMA`](#inkmap.config.DEFAULT_BLUR_SIGMA)            | Fallback blur sigma (px) when it cannot be estimated from the image.                                                                                                                                                                                                                                                                                                                    |
| [`MIN_SCALE_OVER_SIGMA`](#inkmap.config.MIN_SCALE_OVER_SIGMA)          | Below this ratio of pixels-per-unit to blur sigma, no erosion can recover an uncontaminated measurement -- the blur is wide relative to a unit and every pixel is mixed.                                                                                                                                                                                                                |
| [`SATURATION_LEVEL`](#inkmap.config.SATURATION_LEVEL)              | Pixels at or above this 8-bit level are treated as clipped and excluded.                                                                                                                                                                                                                                                                                                                |
| [`BLACK_CLIP_LEVEL`](#inkmap.config.BLACK_CLIP_LEVEL)              | Pixels at or below this level are treated as crushed black and excluded.                                                                                                                                                                                                                                                                                                                |
| [`DEFAULT_LOCATORS`](#inkmap.config.DEFAULT_LOCATORS)              | Locator strategies tried by default, in order.                                                                                                                                                                                                                                                                                                                                          |
| [`LOCATE_RETRY_PADDING`](#inkmap.config.LOCATE_RETRY_PADDING)          | a coarse placement that was not decoded, or is under `MIN_COARSE_PIXELS_PER_FEATURE`, is retried on a full-resolution crop around it, padded on each side by this fraction of the placement's larger bounding-box side.                                                                                                                                                                 |
| [`MIN_COARSE_PIXELS_PER_FEATURE`](#inkmap.config.MIN_COARSE_PIXELS_PER_FEATURE) | below this many image pixels per model feature (a QR module, a barcode's narrowest bar) *in the downscaled frame*, the model a locator reads off that frame is unreliable even when the code decodes -- with modules at 2 px a 25 x 25 QR is read as 21 x 21, at 2.5-3.5 px tens of its 625 modules flip, and only from 4 px are they all right (synthetic pages, `locate(scale=0.5)`). |

### inkmap.config.BLACK_CLIP_LEVEL *= 2*

Pixels at or below this level are treated as crushed black and excluded.

### inkmap.config.DEFAULT_BLUR_SIGMA *= 1.0*

Fallback blur sigma (px) when it cannot be estimated from the image.

### inkmap.config.DEFAULT_LOCATORS *= ('qr_zxing', 'qr_aruco', 'qr_opencv', 'barcode_zxing')*

Locator strategies tried by default, in order. Measured on 189 real photographs of
QR codes: zxing 74%, aruco 68%, opencv 43%, union 80% – the cascade is worth ~37
points of recall over OpenCV alone.

### inkmap.config.ECC_MIN_CORRELATION *= 0.5*

Minimum ECC correlation for a refinement to be accepted. Below this the refined
transform is discarded and the locator’s own corners kept.

### inkmap.config.ECC_MIN_SCALE *= 2*

The template is rendered at the observed pixels-per-unit, clamped here. Matching the
observed scale matters: rendering far below it aliases the comparison and the
refinement gets *worse* than the unrefined corners.

### inkmap.config.ECC_TEMPLATE_BLUR_FRAC *= 0.25*

Gaussian smoothing of the ECC template, as a fraction of one model unit’s rendered
size. Photographed edges are soft; a perfectly sharp template correlates poorly.

### inkmap.config.EDGE_MARGIN_SIGMAS *= 2.0*

Default erosion of the pure-foreground mask, in multiples of the estimated blur
sigma. The point spread function spreads signal across boundaries, so geometric
purity is necessary but not sufficient. ~2 sigma holds bias below 0.5%, ~3 below 0.1%.

### inkmap.config.LOCATE_RETRY_PADDING *= 0.5*

a coarse placement that was
not decoded, or is under `MIN_COARSE_PIXELS_PER_FEATURE`, is retried on a full-resolution crop around it, padded on each
side by this fraction of the placement’s larger bounding-box side. 0.5 comfortably
holds a QR quiet zone (4 modules of a symbol at least 21 wide) plus the coarse
pass’s position error, while keeping the crop a small fraction of the frame.

* **Type:**
  Coarse-to-fine locating (`locate(..., scale=s)`)

### inkmap.config.MARGIN_UNITS *= 4.0*

Default clear margin around a mark, in model units, labelled Region.MARGIN.
4 matches the QR quiet zone required by ISO/IEC 18004.

### inkmap.config.MIN_COARSE_PIXELS_PER_FEATURE *= 4.0*

below this many image pixels per model feature (a QR
module, a barcode’s narrowest bar) *in the downscaled frame*, the model a locator
reads off that frame is unreliable even when the code decodes – with modules at
2 px a 25 x 25 QR is read as 21 x 21, at 2.5-3.5 px tens of its 625 modules flip,
and only from 4 px are they all right (synthetic pages, `locate(scale=0.5)`).
Such placements are re-located on a full-resolution crop. See `locate`.

* **Type:**
  Coarse-to-fine locating

### inkmap.config.MIN_SCALE_OVER_SIGMA *= 6.0*

Below this ratio of pixels-per-unit to blur sigma, no erosion can recover an
uncontaminated measurement – the blur is wide relative to a unit and every pixel is
mixed. Results are flagged rather than silently returned. See docs/validation.md.

### inkmap.config.PURE_COVERAGE_TOL *= 0.001*

Coverage within this of 1.0 (or 0.0) counts as pure. Not exactly 1.0, to tolerate
float rounding in the raster.

### inkmap.config.SATURATION_LEVEL *= 250*

Pixels at or above this 8-bit level are treated as clipped and excluded.

### inkmap.config.SUPERSAMPLES *= 8*

Sub-samples per pixel per axis when computing area coverage. A pixel’s coverage is
quantised to 1/SUPERSAMPLES\*\*2, so 4 -> 17 levels, 8 -> 65. Below 4 the quantisation
itself becomes a bias source.

### inkmap.config.TEMPLATE_MARGIN_UNITS *= 2.0*

Clear margin rendered around the ECC template, in model units. Without it the blur
kernel reflects interior content across the border and biases alignment ~0.45 px.
