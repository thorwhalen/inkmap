"""Tunable defaults, in one place.

Every number the algorithms depend on lives here rather than inline, so behaviour can
be adjusted without editing logic and the meaning of each constant is documented
exactly once. Functions take these as keyword-only defaults; nothing reads the module
at call time, so overriding one is a call-site concern, not global mutable state.
"""

from __future__ import annotations

# --- Coverage rasterisation ------------------------------------------------- #

#: Sub-samples per pixel per axis when computing area coverage. A pixel's coverage is
#: quantised to 1/SUPERSAMPLES**2, so 4 -> 17 levels, 8 -> 65. Below 4 the quantisation
#: itself becomes a bias source.
SUPERSAMPLES = 8

# --- Transform refinement --------------------------------------------------- #

ECC_ITERATIONS = 200
ECC_EPS = 1e-7

#: Gaussian smoothing of the ECC template, as a fraction of one model unit's rendered
#: size. Photographed edges are soft; a perfectly sharp template correlates poorly.
ECC_TEMPLATE_BLUR_FRAC = 0.25

#: Minimum ECC correlation for a refinement to be accepted. Below this the refined
#: transform is discarded and the locator's own corners kept.
ECC_MIN_CORRELATION = 0.5

#: The template is rendered at the observed pixels-per-unit, clamped here. Matching the
#: observed scale matters: rendering far below it aliases the comparison and the
#: refinement gets *worse* than the unrefined corners.
ECC_MIN_SCALE = 2
ECC_MAX_SCALE = 16

#: Clear margin rendered around the ECC template, in model units. Without it the blur
#: kernel reflects interior content across the border and biases alignment ~0.45 px.
TEMPLATE_MARGIN_UNITS = 2.0

# --- Regions ---------------------------------------------------------------- #

#: Default clear margin around a mark, in model units, labelled Region.MARGIN.
#: 4 matches the QR quiet zone required by ISO/IEC 18004.
MARGIN_UNITS = 4.0

# --- Measurement safety ----------------------------------------------------- #

#: Coverage within this of 1.0 (or 0.0) counts as pure. Not exactly 1.0, to tolerate
#: float rounding in the raster.
PURE_COVERAGE_TOL = 1e-3

#: Default erosion of the pure-foreground mask, in multiples of the estimated blur
#: sigma. The point spread function spreads signal across boundaries, so geometric
#: purity is necessary but not sufficient. ~2 sigma holds bias below 0.5%, ~3 below 0.1%.
EDGE_MARGIN_SIGMAS = 2.0

#: Fallback blur sigma (px) when it cannot be estimated from the image.
DEFAULT_BLUR_SIGMA = 1.0

#: Below this ratio of pixels-per-unit to blur sigma, no erosion can recover an
#: uncontaminated measurement -- the blur is wide relative to a unit and every pixel is
#: mixed. Results are flagged rather than silently returned. See docs/validation.md.
MIN_SCALE_OVER_SIGMA = 6.0

# --- Photometry ------------------------------------------------------------- #

#: Pixels at or above this 8-bit level are treated as clipped and excluded.
SATURATION_LEVEL = 250

#: Pixels at or below this level are treated as crushed black and excluded.
BLACK_CLIP_LEVEL = 2

# --- Location --------------------------------------------------------------- #

#: Locator strategies tried by default, in order. Measured on 189 real photographs of
#: QR codes: zxing 74%, aruco 68%, opencv 43%, union 80% -- the cascade is worth ~37
#: points of recall over OpenCV alone.
DEFAULT_LOCATORS = ("qr_zxing", "qr_aruco", "qr_opencv", "barcode_zxing")

#: Coarse-to-fine locating (``locate(..., scale=s)``): a coarse placement that was
#: found but not decoded is retried on a full-resolution crop around it, padded on each
#: side by this fraction of the placement's larger bounding-box side. 0.5 comfortably
#: holds a QR quiet zone (4 modules of a symbol at least 21 wide) plus the coarse
#: pass's position error, while keeping the crop a small fraction of the frame.
LOCATE_RETRY_PADDING = 0.5
