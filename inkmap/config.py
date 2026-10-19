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

# --- Plain patches ----------------------------------------------------------- #

#: The patch colour is the median over a window this share of the frame's shorter side
#: across, round the seed. Small, so that a seed near the patch's edge still takes the
#: patch's colour, not the paper's.
PATCH_SEED_SHARE = 0.04

#: The CIELAB distance (Delta E) that splits patch from not-patch is Otsu's threshold,
#: clamped to this range: below 4 the split follows noise, above 25 a pale patch leaks
#: into white paper.
PATCH_MIN_DELTA_E = 4.0
PATCH_MAX_DELTA_E = 25.0

#: The interior is eroded clear of the patch's blurred edge by this share of its
#: shorter side.
PATCH_EDGE_MARGIN_SHARE = 0.08

#: The substrate ring runs between these shares of the patch's shorter side outside
#: it. Narrow on purpose: a thin paper border is easily overshot onto the background.
PATCH_RING_SHARE = (0.02, 0.06)

#: Verdict thresholds. A patch under this share of the frame is too small to trust.
PATCH_MIN_AREA_SHARE = 0.01
#: Area over the minimum-area rectangle's: a pale patch that leaked into the paper
#: is no longer rectangular. (A rectangle seen in perspective scores ~0.9-1.)
PATCH_MIN_RECTANGULARITY = 0.85
#: The ring must hold at least this many substrate pixels...
PATCH_MIN_SUBSTRATE_PX = 50
#: ...whose median L* exceeds the patch's by at least this much (paper is lighter)...
PATCH_MIN_SUBSTRATE_LIFT = 1.0
#: ...and which are low-chroma (C*ab under this): paper, not a coloured table.
PATCH_MAX_SUBSTRATE_CHROMA = 15.0
#: ...on at least three sides, each holding substrate in this share of its ring.
PATCH_MIN_SIDE_SHARE = 0.15

#: A patch's outline is four-sided when a polygon within this share of its perimeter
#: fits it with four vertices.
PATCH_POLY_EPSILON_SHARE = 0.02

#: How many times the patch region may be re-split by Otsu within itself, peeling off
#: the paper a pale patch was first merged with (one is usually enough).
PATCH_MAX_RESPLITS = 3

#: The patch's sides are fitted to its colour edge along the direction from the patch's
#: colour to the median colour of this band outside it (in pixels from its outline).
PATCH_EDGE_BAND_PX = (2.0, 6.0)

#: A patch must show a colour step of at least this (in Delta E along the patch-to-
#: paper direction) across every side, measured between PATCH_EDGE_STEP_OFFSET_PX
#: inside and outside it. A leaked region's boundary through shaded paper has none.
PATCH_MIN_EDGE_STEP = 3.0
PATCH_EDGE_STEP_OFFSET_PX = (2.0, 4.0)

#: The substrate ring's lightness is split (paper from a darker background) only when
#: its two Otsu classes are this many L* apart; shading alone spreads paper less.
PATCH_SUBSTRATE_SPLIT_GAP = 15.0

#: A patch side is refined against the image only where its edge steps by at least
#: this many 8-bit levels (along the patch-to-paper colour direction).
PATCH_MIN_EDGE_CONTRAST = 3.0

#: A patch side's edge level is taken per profile and smoothed over this many profiles
#: (pixels) along the side, rather than once for the whole side: uneven light moves it
#: along a long side, which on a faint edge tilts the fitted line.
PATCH_EDGE_LEVEL_WINDOW = 25

#: The thresholded outline must lie within this many pixels of the fitted sides (95th
#: percentile): a lobe leaked into shaded paper, or a rounded corner, strays further.
PATCH_MAX_OUTLINE_DEVIATION_PX = 2.0

#: Pixels of the interior that are not the patch's colour are always left out of it.
#: The verdict fails when one connected blob of them covers more than this share of
#: the interior (another patch, or the patch itself inside a region seeded on the
#: paper: 7-8% in the cases seen), or when all of them together cover more than
#: PATCH_MAX_OFF_COLOUR_SHARE (text, specks or glare obscuring the patch).
PATCH_MAX_HOLE_SHARE = 0.05
PATCH_MAX_OFF_COLOUR_SHARE = 0.25

#: Substrate pixels must be within this Delta E of the ring's median paper colour: a
#: neighbouring light-grey patch, or a white table, can pass for paper otherwise.
PATCH_SUBSTRATE_MAX_DELTA_E = 8.0

#: Interior pixels further from the seed colour than the patch's median distance plus
#: this many robust deviations (1.4826 MAD) are left out, with a pixel round them:
#: the fringe of text or glare on the patch.
PATCH_INTERIOR_MADS = 4.0

#: Two colours are distinct when their Otsu split along the principal axis is at least
#: this many pooled deviations apart. One evenly spread population -- a patch under a
#: lighting gradient -- scores about 3.5; a patch beside its paper, far more.
PATCH_TWO_COLOUR_SEPARATION = 5.0

# --- Plain patches: flattening uneven light ------------------------------------ #

#: When a patch is refused, the light over its paper may be fitted and divided out,
#: and the patch located again (``locate_patch(flatten="auto")``). The paper is
#: sampled round the refused region, out to this share of its larger side...
PATCH_FLATTEN_PAD_SHARE = 0.5
#: ...needing at least this many paper-like pixels, of which at most this many are
#: used in the fit.
PATCH_FLATTEN_MIN_PX = 200
PATCH_FLATTEN_MAX_SAMPLES = 50_000
#: The field is a polynomial of this degree in the frame coordinates: 2 follows an
#: oblique gradient and vignetting.
PATCH_FLATTEN_DEGREE = 2
#: Fitted as an upper envelope: pixels more than this many robust deviations below the
#: fit (the darker patch, specks) are dropped and the fit repeated, this many times.
PATCH_FLATTEN_ENVELOPE_SIGMAS = 2.5
PATCH_FLATTEN_ITERATIONS = 6
