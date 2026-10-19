# inkmap.config

Tunable defaults, in one place.

Every number the algorithms depend on lives here rather than inline, so behaviour can
be adjusted without editing logic and the meaning of each constant is documented
exactly once. Functions take these as keyword-only defaults; nothing reads the module
at call time, so overriding one is a call-site concern, not global mutable state.

### Module Attributes

| [`SUPERSAMPLES`](#inkmap.config.SUPERSAMPLES)                   | Sub-samples per pixel per axis when computing area coverage.                                                                                                                                                                                                                                                                                                                            |
|---------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`ECC_TEMPLATE_BLUR_FRAC`](#inkmap.config.ECC_TEMPLATE_BLUR_FRAC)         | Gaussian smoothing of the ECC template, as a fraction of one model unit's rendered size.                                                                                                                                                                                                                                                                                                |
| [`ECC_MIN_CORRELATION`](#inkmap.config.ECC_MIN_CORRELATION)            | Minimum ECC correlation for a refinement to be accepted.                                                                                                                                                                                                                                                                                                                                |
| [`ECC_MIN_SCALE`](#inkmap.config.ECC_MIN_SCALE)                  | The template is rendered at the observed pixels-per-unit, clamped here.                                                                                                                                                                                                                                                                                                                 |
| [`TEMPLATE_MARGIN_UNITS`](#inkmap.config.TEMPLATE_MARGIN_UNITS)          | Clear margin rendered around the ECC template, in model units.                                                                                                                                                                                                                                                                                                                          |
| [`MARGIN_UNITS`](#inkmap.config.MARGIN_UNITS)                   | Default clear margin around a mark, in model units, labelled Region.MARGIN.                                                                                                                                                                                                                                                                                                             |
| [`PURE_COVERAGE_TOL`](#inkmap.config.PURE_COVERAGE_TOL)              | Coverage within this of 1.0 (or 0.0) counts as pure.                                                                                                                                                                                                                                                                                                                                    |
| [`EDGE_MARGIN_SIGMAS`](#inkmap.config.EDGE_MARGIN_SIGMAS)             | Default erosion of the pure-foreground mask, in multiples of the estimated blur sigma.                                                                                                                                                                                                                                                                                                  |
| [`DEFAULT_BLUR_SIGMA`](#inkmap.config.DEFAULT_BLUR_SIGMA)             | Fallback blur sigma (px) when it cannot be estimated from the image.                                                                                                                                                                                                                                                                                                                    |
| [`MIN_SCALE_OVER_SIGMA`](#inkmap.config.MIN_SCALE_OVER_SIGMA)           | Below this ratio of pixels-per-unit to blur sigma, no erosion can recover an uncontaminated measurement -- the blur is wide relative to a unit and every pixel is mixed.                                                                                                                                                                                                                |
| [`SATURATION_LEVEL`](#inkmap.config.SATURATION_LEVEL)               | Pixels at or above this 8-bit level are treated as clipped and excluded.                                                                                                                                                                                                                                                                                                                |
| [`BLACK_CLIP_LEVEL`](#inkmap.config.BLACK_CLIP_LEVEL)               | Pixels at or below this level are treated as crushed black and excluded.                                                                                                                                                                                                                                                                                                                |
| [`DEFAULT_LOCATORS`](#inkmap.config.DEFAULT_LOCATORS)               | Locator strategies tried by default, in order.                                                                                                                                                                                                                                                                                                                                          |
| [`LOCATE_RETRY_PADDING`](#inkmap.config.LOCATE_RETRY_PADDING)           | a coarse placement that was not decoded, or is under `MIN_COARSE_PIXELS_PER_FEATURE`, is retried on a full-resolution crop around it, padded on each side by this fraction of the placement's larger bounding-box side.                                                                                                                                                                 |
| [`MIN_COARSE_PIXELS_PER_FEATURE`](#inkmap.config.MIN_COARSE_PIXELS_PER_FEATURE)  | below this many image pixels per model feature (a QR module, a barcode's narrowest bar) *in the downscaled frame*, the model a locator reads off that frame is unreliable even when the code decodes -- with modules at 2 px a 25 x 25 QR is read as 21 x 21, at 2.5-3.5 px tens of its 625 modules flip, and only from 4 px are they all right (synthetic pages, `locate(scale=0.5)`). |
| [`MARK_DARK_SHARE`](#inkmap.config.MARK_DARK_SHARE)                | A pixel is foreground when it is darker than this share of the local mean brightness.                                                                                                                                                                                                                                                                                                   |
| [`MARK_MIN_CONTRAST`](#inkmap.config.MARK_MIN_CONTRAST)              | ...and darker than the local mean by at least this many grey levels (of 255).                                                                                                                                                                                                                                                                                                           |
| [`MARK_LOCAL_WINDOW_SHARE`](#inkmap.config.MARK_LOCAL_WINDOW_SHARE)        | wider than any mark, so a mark's own ink does not raise the threshold inside it.                                                                                                                                                                                                                                                                                                        |
| [`MARK_BORDER_PX`](#inkmap.config.MARK_BORDER_PX)                 | A contour within this many pixels of the frame's edge is cut by it.                                                                                                                                                                                                                                                                                                                     |
| [`MARK_POLY_EPSILON_SHARE`](#inkmap.config.MARK_POLY_EPSILON_SHARE)        | A contour is a quadrilateral when a polygon within this share of its perimeter fits it with four vertices (`cv2.approxPolyDP`'s epsilon).                                                                                                                                                                                                                                               |
| [`MARK_MAX_SIDE_RATIO`](#inkmap.config.MARK_MAX_SIDE_RATIO)            | A quadrilateral whose opposite sides differ by more than this factor is not a square seen at any plausible incidence.                                                                                                                                                                                                                                                                   |
| [`MARK_MIN_HOLE_AREA_SHARE`](#inkmap.config.MARK_MIN_HOLE_AREA_SHARE)       | the square is solid.                                                                                                                                                                                                                                                                                                                                                                    |
| [`MARK_CORNER_TRIM_SHARE`](#inkmap.config.MARK_CORNER_TRIM_SHARE)         | Contour points within this share of a side's length from either corner are left out of that side's line fit: the corner is where binarisation rounds the outline.                                                                                                                                                                                                                       |
| [`MARK_EDGE_PROFILE_PX`](#inkmap.config.MARK_EDGE_PROFILE_PX)           | Each side's line is refined against the grey image along profiles this many pixels either side of it (and no more than MARK_EDGE_PROFILE_SHARE of the side's length), long enough to bracket a blurred edge, short enough not to reach a ring's next edge.                                                                                                                              |
| [`MARK_EDGE_STEP_PX`](#inkmap.config.MARK_EDGE_STEP_PX)              | Spacing of the samples along each edge profile, in pixels.                                                                                                                                                                                                                                                                                                                              |
| [`MARK_EDGE_ITERATIONS`](#inkmap.config.MARK_EDGE_ITERATIONS)           | Refinement passes per side.                                                                                                                                                                                                                                                                                                                                                             |
| [`MARK_EDGE_OUTLIER_PX`](#inkmap.config.MARK_EDGE_OUTLIER_PX)           | A refined edge crossing further than this from the fitted line (or three times the line's scatter, if larger) is an outlier -- a glare bite, a speck -- and is refitted without.                                                                                                                                                                                                        |
| [`MARK_MAX_SIDE_SCATTER_PX`](#inkmap.config.MARK_MAX_SIDE_SCATTER_PX)       | A quadrilateral whose refined sides scatter about their lines by more than this (rms, in pixels), or this share of its side if larger, is not a square: a disc's outline also fits four lines, but its scatter grows with its size (0.35 px for a 10 px radius, 1 px for 20 px), where a square's stays at the noise floor.                                                             |
| [`MARK_MIN_QUAD_SIDE_PX`](#inkmap.config.MARK_MIN_QUAD_SIDE_PX)          | The smallest square considered at all, in pixels on a side.                                                                                                                                                                                                                                                                                                                             |
| [`MARK_WINDOW_OVER_MAX_SIDE`](#inkmap.config.MARK_WINDOW_OVER_MAX_SIDE)      | The local-mean window is kept at least this many times the largest mark looked for (`max_side_share`): a mark wider than the window raises its own threshold and is hollowed by its own ink.                                                                                                                                                                                            |
| [`MARK_NESTED_HOLE_AREA_RATIO`](#inkmap.config.MARK_NESTED_HOLE_AREA_RATIO)    | A square in a hole less than this many times its own area is the inner square of a nested mark (a bullseye's hole is 4x its inner square, a QR finder's 2.8x), not a mark of its own.                                                                                                                                                                                                   |
| [`MARK_MAX_ASPECT`](#inkmap.config.MARK_MAX_ASPECT)                | A quadrilateral whose mean opposite-side lengths differ by more than this factor is a rectangle, not a square: 1.6 is a square seen at about 51 degrees of incidence.                                                                                                                                                                                                                   |
| [`MARK_CLIP_GUARD_SHARE`](#inkmap.config.MARK_CLIP_GUARD_SHARE)          | A solid square whose neighbourhood out to this many sides runs off the frame, and holds more than MARK_CLIP_GUARD_INK_SHARE foreground, may be the inner square of a nested mark the frame cuts, and is dropped.                                                                                                                                                                        |
| [`MARK_RING_SPREAD_SHARE`](#inkmap.config.MARK_RING_SPREAD_SHARE)         | `sigma_px` calibration, fitted on synthetic sheets (rotations, perspective up to 0.15, blur 0.7-1.5 px, noise 1-4) so that the median centre error is about sigma for both kinds of mark.                                                                                                                                                                                               |
| [`PATCH_SEED_SHARE`](#inkmap.config.PATCH_SEED_SHARE)               | The patch colour is the median over a window this share of the frame's shorter side across, round the seed.                                                                                                                                                                                                                                                                             |
| [`PATCH_MIN_DELTA_E`](#inkmap.config.PATCH_MIN_DELTA_E)              | The CIELAB distance (Delta E) that splits patch from not-patch is Otsu's threshold, clamped to this range: below 4 the split follows noise, above 25 a pale patch leaks into white paper.                                                                                                                                                                                               |
| [`PATCH_EDGE_MARGIN_SHARE`](#inkmap.config.PATCH_EDGE_MARGIN_SHARE)        | The interior is eroded clear of the patch's blurred edge by this share of its shorter side.                                                                                                                                                                                                                                                                                             |
| [`PATCH_RING_SHARE`](#inkmap.config.PATCH_RING_SHARE)               | The substrate ring runs between these shares of the patch's shorter side outside it.                                                                                                                                                                                                                                                                                                    |
| [`PATCH_MIN_AREA_SHARE`](#inkmap.config.PATCH_MIN_AREA_SHARE)           | Verdict thresholds.                                                                                                                                                                                                                                                                                                                                                                     |
| [`PATCH_MIN_RECTANGULARITY`](#inkmap.config.PATCH_MIN_RECTANGULARITY)       | a pale patch that leaked into the paper is no longer rectangular.                                                                                                                                                                                                                                                                                                                       |
| [`PATCH_MIN_SUBSTRATE_PX`](#inkmap.config.PATCH_MIN_SUBSTRATE_PX)         | The ring must hold at least this many substrate pixels...                                                                                                                                                                                                                                                                                                                               |
| [`PATCH_MIN_SUBSTRATE_LIFT`](#inkmap.config.PATCH_MIN_SUBSTRATE_LIFT)       | ...whose median L\* exceeds the patch's by at least this much (paper is lighter)...                                                                                                                                                                                                                                                                                                     |
| [`PATCH_MAX_SUBSTRATE_CHROMA`](#inkmap.config.PATCH_MAX_SUBSTRATE_CHROMA)     | paper, not a coloured table.                                                                                                                                                                                                                                                                                                                                                            |
| [`PATCH_MIN_SIDE_SHARE`](#inkmap.config.PATCH_MIN_SIDE_SHARE)           | ...on at least three sides, each holding substrate in this share of its ring.                                                                                                                                                                                                                                                                                                           |
| [`PATCH_POLY_EPSILON_SHARE`](#inkmap.config.PATCH_POLY_EPSILON_SHARE)       | A patch's outline is four-sided when a polygon within this share of its perimeter fits it with four vertices.                                                                                                                                                                                                                                                                           |
| [`PATCH_MAX_RESPLITS`](#inkmap.config.PATCH_MAX_RESPLITS)             | How many times the patch region may be re-split by Otsu within itself, peeling off the paper a pale patch was first merged with (one is usually enough).                                                                                                                                                                                                                                |
| [`PATCH_EDGE_BAND_PX`](#inkmap.config.PATCH_EDGE_BAND_PX)             | The patch's sides are fitted to its colour edge along the direction from the patch's colour to the median colour of this band outside it (in pixels from its outline).                                                                                                                                                                                                                  |
| [`PATCH_MIN_EDGE_STEP`](#inkmap.config.PATCH_MIN_EDGE_STEP)            | A patch must show a colour step of at least this (in Delta E along the patch-to- paper direction) across every side, measured between PATCH_EDGE_STEP_OFFSET_PX inside and outside it.                                                                                                                                                                                                  |
| [`PATCH_SUBSTRATE_SPLIT_GAP`](#inkmap.config.PATCH_SUBSTRATE_SPLIT_GAP)      | The substrate ring's lightness is split (paper from a darker background) only when its two Otsu classes are this many L\* apart; shading alone spreads paper less.                                                                                                                                                                                                                      |
| [`PATCH_MIN_EDGE_CONTRAST`](#inkmap.config.PATCH_MIN_EDGE_CONTRAST)        | A patch side is refined against the image only where its edge steps by at least this many 8-bit levels (along the patch-to-paper colour direction).                                                                                                                                                                                                                                     |
| [`PATCH_EDGE_LEVEL_WINDOW`](#inkmap.config.PATCH_EDGE_LEVEL_WINDOW)        | A patch side's edge level is taken per profile and smoothed over this many profiles (pixels) along the side, rather than once for the whole side: uneven light moves it along a long side, which on a faint edge tilts the fitted line.                                                                                                                                                 |
| [`PATCH_MAX_OUTLINE_DEVIATION_PX`](#inkmap.config.PATCH_MAX_OUTLINE_DEVIATION_PX) | The thresholded outline must lie within this many pixels of the fitted sides (95th percentile): a lobe leaked into shaded paper, or a rounded corner, strays further.                                                                                                                                                                                                                   |
| [`PATCH_MAX_HOLE_SHARE`](#inkmap.config.PATCH_MAX_HOLE_SHARE)           | Pixels of the interior that are not the patch's colour are always left out of it.                                                                                                                                                                                                                                                                                                       |
| [`PATCH_SUBSTRATE_MAX_DELTA_E`](#inkmap.config.PATCH_SUBSTRATE_MAX_DELTA_E)    | a neighbouring light-grey patch, or a white table, can pass for paper otherwise.                                                                                                                                                                                                                                                                                                        |
| [`PATCH_INTERIOR_MADS`](#inkmap.config.PATCH_INTERIOR_MADS)            | Interior pixels further from the seed colour than the patch's median distance plus this many robust deviations (1.4826 MAD) are left out, with a pixel round them: the fringe of text or glare on the patch.                                                                                                                                                                            |
| [`PATCH_TWO_COLOUR_SEPARATION`](#inkmap.config.PATCH_TWO_COLOUR_SEPARATION)    | Two colours are distinct when their Otsu split along the principal axis is at least this many pooled deviations apart.                                                                                                                                                                                                                                                                  |

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

### inkmap.config.MARK_BORDER_PX *= 2*

A contour within this many pixels of the frame’s edge is cut by it. Its shape is not
the mark’s, and a clipped mark’s centre is wrong by a share of its side, so it is
dropped rather than measured.

### inkmap.config.MARK_CLIP_GUARD_SHARE *= 1.2*

A solid square whose neighbourhood out to this many sides runs off the frame, and
holds more than MARK_CLIP_GUARD_INK_SHARE foreground, may be the inner square of a
nested mark the frame cuts, and is dropped. A bullseye’s outer edge is 1.06 inner
sides out from its inner square, a QR finder’s 0.67.

### inkmap.config.MARK_CORNER_TRIM_SHARE *= 0.15*

Contour points within this share of a side’s length from either corner are left out
of that side’s line fit: the corner is where binarisation rounds the outline.

### inkmap.config.MARK_DARK_SHARE *= 0.72*

A pixel is foreground when it is darker than this share of the local mean
brightness. Relative rather than absolute, so that an unevenly lit sheet (3.5:1 from
one side to the other) and a dim frame are binarised alike.

### inkmap.config.MARK_EDGE_ITERATIONS *= 2*

Refinement passes per side. The first takes the line from the contour’s quantised
position to the edge; the second re-centres the profiles on it.

### inkmap.config.MARK_EDGE_OUTLIER_PX *= 0.75*

A refined edge crossing further than this from the fitted line (or three times the
line’s scatter, if larger) is an outlier – a glare bite, a speck – and is refitted
without.

### inkmap.config.MARK_EDGE_PROFILE_PX *= 2.5*

Each side’s line is refined against the grey image along profiles this many pixels
either side of it (and no more than MARK_EDGE_PROFILE_SHARE of the side’s length),
long enough to bracket a blurred edge, short enough not to reach a ring’s next edge.

### inkmap.config.MARK_EDGE_STEP_PX *= 0.25*

Spacing of the samples along each edge profile, in pixels.

### inkmap.config.MARK_LOCAL_WINDOW_SHARE *= 0.12*

wider
than any mark, so a mark’s own ink does not raise the threshold inside it.

* **Type:**
  The local mean is taken over a window this share of the frame’s shorter side

### inkmap.config.MARK_MAX_ASPECT *= 1.6*

A quadrilateral whose mean opposite-side lengths differ by more than this factor is
a rectangle, not a square: 1.6 is a square seen at about 51 degrees of incidence.

### inkmap.config.MARK_MAX_SIDE_RATIO *= 2.5*

A quadrilateral whose opposite sides differ by more than this factor is not a square
seen at any plausible incidence.

### inkmap.config.MARK_MAX_SIDE_SCATTER_PX *= 0.25*

A quadrilateral whose refined sides scatter about their lines by more than this
(rms, in pixels), or this share of its side if larger, is not a square: a disc’s
outline also fits four lines, but its scatter grows with its size (0.35 px for a
10 px radius, 1 px for 20 px), where a square’s stays at the noise floor. A disc
under ~10 px radius cannot be told from a square this way.

### inkmap.config.MARK_MIN_CONTRAST *= 6.0*

…and darker than the local mean by at least this many grey levels (of 255).
Without a floor, sensor noise on a near-black table is “darker than 72% of the local
mean” everywhere, and the contour search drowns in blobs.

### inkmap.config.MARK_MIN_HOLE_AREA_SHARE *= 0.02*

the square is solid.

* **Type:**
  A hole smaller than this share of its square’s area is noise

### inkmap.config.MARK_MIN_QUAD_SIDE_PX *= 5.0*

The smallest square considered at all, in pixels on a side. Lower than any mark’s
own `min_side_px`, because a nested mark’s inner square is a third of its side and
must be found for the mark to be.

### inkmap.config.MARK_NESTED_HOLE_AREA_RATIO *= 9.0*

A square in a hole less than this many times its own area is the inner square of a
nested mark (a bullseye’s hole is 4x its inner square, a QR finder’s 2.8x), not a
mark of its own. A sheet’s outline or a form’s box holds its marks in a far larger
hole.

### inkmap.config.MARK_POLY_EPSILON_SHARE *= 0.04*

A contour is a quadrilateral when a polygon within this share of its perimeter fits
it with four vertices (`cv2.approxPolyDP`’s epsilon).

### inkmap.config.MARK_RING_SPREAD_SHARE *= 0.5*

`sigma_px` calibration, fitted on synthetic sheets (rotations, perspective up to
0.15, blur 0.7-1.5 px, noise 1-4) so that the median centre error is about sigma for
both kinds of mark. A nested mark’s term is this share of the rms distance of its
squares’ centres from their mean; a solid mark, with nothing to disagree with, gets
this floor (its side-fit scatter alone understated its error ~4x).

### inkmap.config.MARK_WINDOW_OVER_MAX_SIDE *= 1.2*

The local-mean window is kept at least this many times the largest mark looked for
(`max_side_share`): a mark wider than the window raises its own threshold and is
hollowed by its own ink.

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

### inkmap.config.PATCH_EDGE_BAND_PX *= (2.0, 6.0)*

The patch’s sides are fitted to its colour edge along the direction from the patch’s
colour to the median colour of this band outside it (in pixels from its outline).

### inkmap.config.PATCH_EDGE_LEVEL_WINDOW *= 25*

A patch side’s edge level is taken per profile and smoothed over this many profiles
(pixels) along the side, rather than once for the whole side: uneven light moves it
along a long side, which on a faint edge tilts the fitted line.

### inkmap.config.PATCH_EDGE_MARGIN_SHARE *= 0.08*

The interior is eroded clear of the patch’s blurred edge by this share of its
shorter side.

### inkmap.config.PATCH_INTERIOR_MADS *= 4.0*

Interior pixels further from the seed colour than the patch’s median distance plus
this many robust deviations (1.4826 MAD) are left out, with a pixel round them:
the fringe of text or glare on the patch.

### inkmap.config.PATCH_MAX_HOLE_SHARE *= 0.05*

Pixels of the interior that are not the patch’s colour are always left out of it.
The verdict fails when one connected blob of them covers more than this share of
the interior (another patch, or the patch itself inside a region seeded on the
paper: 7-8% in the cases seen), or when all of them together cover more than
PATCH_MAX_OFF_COLOUR_SHARE (text, specks or glare obscuring the patch).

### inkmap.config.PATCH_MAX_OUTLINE_DEVIATION_PX *= 2.0*

The thresholded outline must lie within this many pixels of the fitted sides (95th
percentile): a lobe leaked into shaded paper, or a rounded corner, strays further.

### inkmap.config.PATCH_MAX_RESPLITS *= 3*

How many times the patch region may be re-split by Otsu within itself, peeling off
the paper a pale patch was first merged with (one is usually enough).

### inkmap.config.PATCH_MAX_SUBSTRATE_CHROMA *= 15.0*

paper, not a coloured table.

* **Type:**
  …and which are low-chroma (C\*ab under this)

### inkmap.config.PATCH_MIN_AREA_SHARE *= 0.01*

Verdict thresholds. A patch under this share of the frame is too small to trust.

### inkmap.config.PATCH_MIN_DELTA_E *= 4.0*

The CIELAB distance (Delta E) that splits patch from not-patch is Otsu’s threshold,
clamped to this range: below 4 the split follows noise, above 25 a pale patch leaks
into white paper.

### inkmap.config.PATCH_MIN_EDGE_CONTRAST *= 3.0*

A patch side is refined against the image only where its edge steps by at least
this many 8-bit levels (along the patch-to-paper colour direction).

### inkmap.config.PATCH_MIN_EDGE_STEP *= 3.0*

A patch must show a colour step of at least this (in Delta E along the patch-to-
paper direction) across every side, measured between PATCH_EDGE_STEP_OFFSET_PX
inside and outside it. A leaked region’s boundary through shaded paper has none.

### inkmap.config.PATCH_MIN_RECTANGULARITY *= 0.85*

a pale patch that leaked into the paper
is no longer rectangular. (A rectangle seen in perspective scores ~0.9-1.)

* **Type:**
  Area over the minimum-area rectangle’s

### inkmap.config.PATCH_MIN_SIDE_SHARE *= 0.15*

…on at least three sides, each holding substrate in this share of its ring.

### inkmap.config.PATCH_MIN_SUBSTRATE_LIFT *= 1.0*

…whose median L\* exceeds the patch’s by at least this much (paper is lighter)…

### inkmap.config.PATCH_MIN_SUBSTRATE_PX *= 50*

The ring must hold at least this many substrate pixels…

### inkmap.config.PATCH_POLY_EPSILON_SHARE *= 0.02*

A patch’s outline is four-sided when a polygon within this share of its perimeter
fits it with four vertices.

### inkmap.config.PATCH_RING_SHARE *= (0.02, 0.06)*

The substrate ring runs between these shares of the patch’s shorter side outside
it. Narrow on purpose: a thin paper border is easily overshot onto the background.

### inkmap.config.PATCH_SEED_SHARE *= 0.04*

The patch colour is the median over a window this share of the frame’s shorter side
across, round the seed. Small, so that a seed near the patch’s edge still takes the
patch’s colour, not the paper’s.

### inkmap.config.PATCH_SUBSTRATE_MAX_DELTA_E *= 8.0*

a
neighbouring light-grey patch, or a white table, can pass for paper otherwise.

* **Type:**
  Substrate pixels must be within this Delta E of the ring’s median paper colour

### inkmap.config.PATCH_SUBSTRATE_SPLIT_GAP *= 15.0*

The substrate ring’s lightness is split (paper from a darker background) only when
its two Otsu classes are this many L\* apart; shading alone spreads paper less.

### inkmap.config.PATCH_TWO_COLOUR_SEPARATION *= 5.0*

Two colours are distinct when their Otsu split along the principal axis is at least
this many pooled deviations apart. One evenly spread population – a patch under a
lighting gradient – scores about 3.5; a patch beside its paper, far more.

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
