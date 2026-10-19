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
#: not decoded, or is under ``MIN_COARSE_PIXELS_PER_FEATURE``, is retried on a full-resolution crop around it, padded on each
#: side by this fraction of the placement's larger bounding-box side. 0.5 comfortably
#: holds a QR quiet zone (4 modules of a symbol at least 21 wide) plus the coarse
#: pass's position error, while keeping the crop a small fraction of the frame.
LOCATE_RETRY_PADDING = 0.5

#: Coarse-to-fine locating: below this many image pixels per model feature (a QR
#: module, a barcode's narrowest bar) *in the downscaled frame*, the model a locator
#: reads off that frame is unreliable even when the code decodes -- with modules at
#: 2 px a 25 x 25 QR is read as 21 x 21, at 2.5-3.5 px tens of its 625 modules flip,
#: and only from 4 px are they all right (synthetic pages, ``locate(scale=0.5)``).
#: Such placements are re-located on a full-resolution crop. See ``locate``.
MIN_COARSE_PIXELS_PER_FEATURE = 4.0

# --- Square registration marks ---------------------------------------------- #

#: A pixel is foreground when it is darker than this share of the local mean
#: brightness. Relative rather than absolute, so that an unevenly lit sheet (3.5:1 from
#: one side to the other) and a dim frame are binarised alike.
MARK_DARK_SHARE = 0.72

#: ...and darker than the local mean by at least this many grey levels (of 255).
#: Without a floor, sensor noise on a near-black table is "darker than 72% of the local
#: mean" everywhere, and the contour search drowns in blobs.
MARK_MIN_CONTRAST = 6.0

#: The local mean is taken over a window this share of the frame's shorter side: wider
#: than any mark, so a mark's own ink does not raise the threshold inside it.
MARK_LOCAL_WINDOW_SHARE = 0.12

#: A contour within this many pixels of the frame's edge is cut by it. Its shape is not
#: the mark's, and a clipped mark's centre is wrong by a share of its side, so it is
#: dropped rather than measured.
MARK_BORDER_PX = 2

#: A contour is a quadrilateral when a polygon within this share of its perimeter fits
#: it with four vertices (``cv2.approxPolyDP``'s epsilon).
MARK_POLY_EPSILON_SHARE = 0.04

#: A quadrilateral whose opposite sides differ by more than this factor is not a square
#: seen at any plausible incidence.
MARK_MAX_SIDE_RATIO = 2.5

#: A hole smaller than this share of its square's area is noise: the square is solid.
MARK_MIN_HOLE_AREA_SHARE = 0.02

#: Contour points within this share of a side's length from either corner are left out
#: of that side's line fit: the corner is where binarisation rounds the outline.
MARK_CORNER_TRIM_SHARE = 0.15

#: Each side's line is refined against the grey image along profiles this many pixels
#: either side of it (and no more than MARK_EDGE_PROFILE_SHARE of the side's length),
#: long enough to bracket a blurred edge, short enough not to reach a ring's next edge.
MARK_EDGE_PROFILE_PX = 2.5
MARK_EDGE_PROFILE_SHARE = 0.15

#: Spacing of the samples along each edge profile, in pixels.
MARK_EDGE_STEP_PX = 0.25

#: Refinement passes per side. The first takes the line from the contour's quantised
#: position to the edge; the second re-centres the profiles on it.
MARK_EDGE_ITERATIONS = 2

#: A refined edge crossing further than this from the fitted line (or three times the
#: line's scatter, if larger) is an outlier -- a glare bite, a speck -- and is refitted
#: without.
MARK_EDGE_OUTLIER_PX = 0.75

#: A quadrilateral whose refined sides scatter about their lines by more than this
#: (rms, in pixels), or this share of its side if larger, is not a square: a disc's
#: outline also fits four lines, but its scatter grows with its size (0.35 px for a
#: 10 px radius, 1 px for 20 px), where a square's stays at the noise floor. A disc
#: under ~10 px radius cannot be told from a square this way.
MARK_MAX_SIDE_SCATTER_PX = 0.25
MARK_MAX_SIDE_SCATTER_SHARE = 0.01

#: The smallest square considered at all, in pixels on a side. Lower than any mark's
#: own ``min_side_px``, because a nested mark's inner square is a third of its side and
#: must be found for the mark to be.
MARK_MIN_QUAD_SIDE_PX = 5.0

#: The local-mean window is kept at least this many times the largest mark looked for
#: (``max_side_share``): a mark wider than the window raises its own threshold and is
#: hollowed by its own ink.
MARK_WINDOW_OVER_MAX_SIDE = 1.2

#: A square in a hole less than this many times its own area is the inner square of a
#: nested mark (a bullseye's hole is 4x its inner square, a QR finder's 2.8x), not a
#: mark of its own. A sheet's outline or a form's box holds its marks in a far larger
#: hole.
MARK_NESTED_HOLE_AREA_RATIO = 9.0

#: A quadrilateral whose mean opposite-side lengths differ by more than this factor is
#: a rectangle, not a square: 1.6 is a square seen at about 51 degrees of incidence.
MARK_MAX_ASPECT = 1.6

#: A solid square whose neighbourhood out to this many sides runs off the frame, and
#: holds more than MARK_CLIP_GUARD_INK_SHARE foreground, may be the inner square of a
#: nested mark the frame cuts, and is dropped. A bullseye's outer edge is 1.06 inner
#: sides out from its inner square, a QR finder's 0.67.
MARK_CLIP_GUARD_SHARE = 1.2
MARK_CLIP_GUARD_INK_SHARE = 0.02

#: ``sigma_px`` calibration, fitted on synthetic sheets (rotations, perspective up to
#: 0.15, blur 0.7-1.5 px, noise 1-4) so that the median centre error is about sigma for
#: both kinds of mark. A nested mark's term is this share of the rms distance of its
#: squares' centres from their mean; a solid mark, with nothing to disagree with, gets
#: this floor (its side-fit scatter alone understated its error ~4x).
MARK_RING_SPREAD_SHARE = 0.5
MARK_SOLID_SIGMA_FLOOR_PX = 0.015
