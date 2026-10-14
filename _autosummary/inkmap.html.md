# inkmap

inkmap – per-pixel foreground coverage for photographed marks.

Given a photograph of a printed mark and a *model* of its shape, say for every pixel
how much of it is foreground (the mark) and how much is background (the substrate) –
as a continuous fraction, not a boolean.

The model is the seam. QR symbols, barcodes, printed letters and arbitrary artwork all
go through one pipeline, because all a model has to do is answer “is this point, in my
own coordinate system, foreground?”:

```default
import inkmap
from inkmap import models

inkmap.find(photo)                                        # auto-detect QR/barcode
inkmap.find(photo, model=models.text_model("ABC"), quad=q)  # a printed word
inkmap.find(photo, model=models.RasterModel(art), quad=q)   # anything you can draw
```

The simplest call:

```default
coverage = inkmap.foreground(photo)   # (H, W) float32 in [0, 1]
```

With geometry:

```default
ink = inkmap.find(photo)              # an InkMap, or None
ink.placement.quad                    # (4, 2) corners -- a quadrilateral, not a
                                      # rectangle: perspective is expected
ink.coverage                          # (H, W) float32 area coverage
ink.region                            # OUTSIDE / MARGIN / BACKGROUND / FOREGROUND
ink.weight                            # (H, W) float32 safe-to-measure weighting
```

Measuring:

```default
mask = inkmap.measurement_mask(ink)   # pure pixels, eroded clear of edges
result = inkmap.measure(photo, ink)
result.contrast                       # foreground minus background, linearised
result.measurability.ok               # False if the image cannot support this
```

## Terminology

The two classes are **foreground** and **background**, never dark and light: dark/light
describe appearance, and appearance inverts (white-on-black print, reflectance-reversed
symbols, inverted imaging), so an appearance name would mean the mark in one image and
the substrate in the next. [`Polarity`](#inkmap.Polarity) carries that mapping explicitly. The
continuous value is **coverage**, after ISO 12647-2:2013 3.1 *area coverage*. See
`docs/terminology.md`.

### Functions

| [`foreground`](#inkmap.foreground)(image, \*\*kwargs)                      | Foreground coverage of the largest mark, `(H, W) float32` in `[0, 1]`.         |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`find`](#inkmap.find)(image, \*\*kwargs)                            | The largest mark in `image`, or `None`.                                        |
| [`find_all`](#inkmap.find_all)(image, \*[, model, quad, locators, ...])  | Find every mark in `image` and compute its foreground coverage.                |
| [`place`](#inkmap.place)(model, quad, \*[, ...])                      | Place a model at a known quadrilateral -- the universal escape hatch.          |
| [`measure`](#inkmap.measure)(image, ink_map, \*[, linearize, ...])      | Aggregate `image` over the safe foreground and background pixels of `ink_map`. |
| [`measurement_mask`](#inkmap.measurement_mask)(ink_map, \*[, kind, purity, ...]) | Pixels safe to measure: geometrically pure, then eroded clear of edges.        |
| [`measurability`](#inkmap.measurability)(ink_map, \*[, min_pixels])           | Judge whether a foreground/background measurement can be trusted here.         |
| [`srgb_to_linear`](#inkmap.srgb_to_linear)(image)                              | Undo the sRGB transfer function, returning float in `[0, 1]`.                  |
| [`coverage_map`](#inkmap.coverage_map)(model, transform, image_shape, \*)    | Area fraction of each pixel covered by the model's foreground, in `[0, 1]`.    |
| [`observed_coverage`](#inkmap.observed_coverage)(gray, placement, \*[, ...])      | Apparent coverage read from the photograph itself (Murray-Davies).             |
| [`confidence`](#inkmap.confidence)(gray, placement, coverage, \*[, ...])   | How much to trust the coverage value at each pixel, in `[0, 1]`.               |
| [`measurement_weight`](#inkmap.measurement_weight)(coverage, \*[, ...])            | Blur-aware weight in `[0, 1]`: how safe each pixel is to *measure*.            |
| [`locate`](#inkmap.locate)(bgr, gray, \*[, locators, first_hit, ...])  | Run locator strategies and merge their results, de-duplicating by position.    |

### Classes

| [`InkMap`](#inkmap.InkMap)(coverage, region, placement[, ...])        | Per-pixel foreground coverage for one placement, plus the geometry it came from.   |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`Placement`](#inkmap.Placement)(model, transform, quad[, locator, ...]) | A located instance of a model: which shape, and where it sits in the image.        |
| [`Region`](#inkmap.Region)(\*values)                                  | Four-way pixel classification.                                                     |
| [`Polarity`](#inkmap.Polarity)(\*values)                                | Which apparent-brightness state the foreground corresponds to.                     |
| [`Model`](#inkmap.Model)(\*args, \*\*kwargs)                         | The shape of a mark, in its own coordinate system.                                 |
| [`Measurement`](#inkmap.Measurement)(foreground_mean, foreground_std, ...) | Aggregated signal over foreground and background, with its validity attached.      |
| [`Measurability`](#inkmap.Measurability)(ok, pixels_per_feature, ...[, ...]) | Whether a trustworthy measurement is possible on this image at all.                |

### *class* inkmap.InkMap(coverage, region, placement, polarity=Polarity.FOREGROUND_IS_DARK, weight=None, blur_sigma=None, metadata=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Per-pixel foreground coverage for one placement, plus the geometry it came from.

`coverage` is *geometric* area coverage: the fraction of each pixel’s area lying
under foreground. It is not an optical/reflectance-derived coverage (which lateral
light scattering in the substrate inflates – the Murray-Davies/Yule-Nielsen
effect), and it is not a probability. See [`confidence()`](#inkmap.confidence) for that.

#### background_mask(, threshold=0.5)

Bare-substrate pixels within the mark’s footprint (not the margin).

* **Return type:**
  `ndarray`

#### blur_sigma *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

Estimated image blur (px). `nan` means estimation failed – typically because
the modelled shape and the photograph do not correspond.

#### coverage *: ndarray*

(H, W) float32 in [0, 1]. Zero outside the mark.

#### foreground_mask(, threshold=0.5)

Boolean foreground mask by thresholding coverage. Fine for display and
labelling; for anything photometric use [`inkmap.measurement_mask()`](#inkmap.measurement_mask)
instead, which accounts for blur.

* **Return type:**
  `ndarray`

#### inside_mask(, margin=False)

Every pixel within the mark’s footprint. With `margin=True`, include the
clear surround as well.

* **Return type:**
  `ndarray`

#### margin_mask()

The clear surround – an alternative reference region.

* **Return type:**
  `ndarray`

#### region *: ndarray*

(H, W) uint8 of [`Region`](#inkmap.Region) values.

#### weight *: ndarray | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

(H, W) float32 in [0, 1] – the blur-aware measurement weight, and the **only**
channel that should gate a physical measurement. Coverage is geometric and ignores
the point spread function; confidence is epistemic and says nothing about
partial-area contamination. See [`inkmap.coverage.measurement_weight()`](inkmap.coverage.html.md#inkmap.coverage.measurement_weight).

### *class* inkmap.Measurability(ok, pixels_per_feature, blur_sigma, resolution_ratio, n_foreground_pixels, n_background_pixels, reasons=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Whether a trustworthy measurement is possible on this image at all.

#### resolution_ratio *: [float](https://docs.python.org/3/builtins/functions.html#float)*

`pixels_per_feature / blur_sigma`. Below ~6 the blur is wide relative to the
mark’s smallest feature and no erosion leaves uncontaminated pixels.

### *class* inkmap.Measurement(foreground_mean, foreground_std, foreground_median, background_mean, background_std, background_median, n_foreground, n_background, measurability=None, metadata=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Aggregated signal over foreground and background, with its validity attached.

`measurability` is carried along deliberately: a caller that ignores it has to do
so explicitly.

#### *property* contrast *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Foreground minus background.

#### *property* ratio *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Foreground over background; `nan` when the background reads zero.

#### *property* snr *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Contrast over the pooled standard deviation.

### *class* inkmap.Model(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

The shape of a mark, in its own coordinate system.

Implement this – or just duck-type it – to teach the package a new kind of mark.
Two members are required; `render()` has a working default in
`BaseModel`.

#### *property* extent *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]*

`(width, height)` of model space, in the model’s natural units.

#### *property* feature_size *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Size of the smallest feature that must be resolved, in model units.

A model unit is not a feature. A QR module *is* the smallest feature, so its
feature size is 1. But a glyph rendered onto a 512-cell raster has strokes tens
of cells wide, and a model unit there is far smaller than anything that must be
resolved. Whether an image can support a measurement depends on pixels per
*feature*, not pixels per unit, so this is what makes that judgement portable
across model kinds.

`BaseModel` estimates it from the rendered shape; grid models override
it with the exact value.

#### occupancy(u, v)

Foreground indicator at model coordinates `(u, v)`.

`u` and `v` are float arrays of any matching shape. Returns an array of the
same shape, boolean or float in `[0, 1]`. Points outside [`extent`](#inkmap.Model.extent) must
return 0 – callers rely on that to bound the mark.

Must be vectorised: it is called with millions of points.

* **Return type:**
  `ndarray`

### *class* inkmap.Placement(model, transform, quad, locator='', payload=None, refined=False, score=None, metadata=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A located instance of a model: which shape, and where it sits in the image.

`transform` is the bridge the whole package is built on – a 3x3 homography from
*model space* (the model’s own units, origin at its top-left) to image pixels. The
quad is just its image under that transform, kept for convenience.

#### locator *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

Which locator strategy produced this.

#### payload *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

Decoded content, when the locator happened to decode something. Never required:
decoding is not the point, and a barely-deposited mark may locate but not decode.

#### *property* pixels_per_feature *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Image pixels across the model’s smallest feature.

**This** is the resolution figure that governs whether a trustworthy
measurement is possible – not [`pixels_per_unit`](#inkmap.Placement.pixels_per_unit). A model unit is not a
feature: a QR module is both, but a glyph rendered onto a 512-cell raster has
strokes tens of cells wide, so pixels-per-unit there would understate the real
resolution by that factor and declare every image unmeasurable.

#### *property* pixels_per_unit *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Image pixels per model unit.

For a QR symbol a “unit” is one module; for a barcode, one narrow bar; for a
raster model, one raster cell. Use [`pixels_per_feature`](#inkmap.Placement.pixels_per_feature) to reason about
whether the image resolves the mark.

#### quad *: ndarray*

(4, 2) float32 image-space corners of the model’s extent, in the *model’s* own
order (its top-left first), not re-sorted into image order. Re-sorting by
coordinate sum/difference – a common idiom – silently mislabels corners once the
mark is rotated past 45 degrees, which rotates the model and corrupts every derived
mask while leaving it looking plausible.

#### score *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

Alignment score from refinement, if it ran. A proxy for geometric fit quality.

#### transform *: ndarray*

(3, 3) float64, model coordinates -> image pixels.

#### *property* units_per_pixel *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Model units spanned by one image pixel, averaged over the two axes.

### *class* inkmap.Polarity(\*values)

Bases: [`IntEnum`](https://docs.python.org/3/library/enum.html#enum.IntEnum)

Which apparent-brightness state the foreground corresponds to.

Carried explicitly so that no appearance word ever has to stand in for a physical
class. Flipping this is the supported way to handle inverted print and inverted
imaging, rather than inverting masks at the call site.

#### FOREGROUND_IS_DARK *= 0*

ink absorbs, so the mark reads darker than the substrate.

* **Type:**
  The usual case

#### FOREGROUND_IS_LIGHT *= 1*

the mark reads brighter than the substrate.

* **Type:**
  Reversed

### *class* inkmap.Region(\*values)

Bases: [`IntEnum`](https://docs.python.org/3/library/enum.html#enum.IntEnum)

Four-way pixel classification.

Not a matting *trimap*: a trimap’s third class is “unknown/undecided”, whereas
every class here is a decided statement about location.

#### BACKGROUND *= 2*

Bare substrate within the mark’s footprint.

#### FOREGROUND *= 3*

The mark itself – printed ink, toner, engraving, whatever laid it down.

#### MARGIN *= 1*

The clear surround a mark is specified to have – a QR quiet zone, a barcode
light margin, the whitespace around a glyph. Guaranteed background, contiguous, and
free of edge effects from neighbouring foreground, which often makes it a better
reference region than the background *inside* the mark.

#### OUTSIDE *= 0*

Outside the mark and its margin.

### inkmap.confidence(gray, placement, coverage, , polarity=Polarity.FOREGROUND_IS_DARK)

How much to trust the coverage value at each pixel, in `[0, 1]`.

Distinct from coverage. Three things erode it, combined multiplicatively:

* **Model/image disagreement** – where the observed value contradicts the modelled
  coverage, one of them is wrong. This is what catches foreground that failed to
  print, a torn label, or a mis-fitted transform.
* **Clipping** – saturated or crushed pixels carry no photometric information.
* **Edge proximity** – mixed pixels are inherently less certain, and their value
  depends on sub-pixel geometry known only to ~0.5 px.

* **Return type:**
  `ndarray`

### inkmap.coverage_map(model, transform, image_shape, , samples=8)

Area fraction of each pixel covered by the model’s foreground, in `[0, 1]`.

Each pixel is probed at `samples**2` sub-positions on a regular grid at sub-pixel
centres; each probe is back-projected into model coordinates and passed to
[`Model.occupancy()`](#inkmap.Model.occupancy). The mean is the covered area fraction – ordinary
supersampled area coverage, the same quantity a renderer’s anti-aliasing computes.

Values are quantised to `1/samples**2`, so `samples` sets the accuracy floor.
Only the model’s bounding box is evaluated, so a mark occupying 2% of a 12 MP photo
costs 2% of the work.

* **Return type:**
  `ndarray`

### inkmap.find(image, \*\*kwargs)

The largest mark in `image`, or `None`. See [`find_all()`](#inkmap.find_all).

* **Return type:**
  [`InkMap`](inkmap.types.html.md#inkmap.types.InkMap) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### inkmap.find_all(image, , model=None, quad=None, locators=('qr_zxing', 'qr_aruco', 'qr_opencv', 'barcode_zxing'), locate_scale=None, \*\*kwargs)

Find every mark in `image` and compute its foreground coverage.

With `model` and `quad`, skips detection entirely and analyses that one
placement – the path for marks no detector knows about. With neither, runs the
locator cascade (QR and linear barcodes out of the box).

`refine` (default on) aligns the rendered model to the photograph, pinning the
transform to sub-pixel accuracy; it is far more accurate than locator corners alone
and costs a few milliseconds.

`source` picks where coverage comes from: `"modelled"` (default) computes it
from the model – exact and lighting-independent, answering “where should the
foreground be”. `"observed"` reads it from the photograph, answering “where is
the foreground actually”, and so is the one that can see a printing defect.

`locate_scale` (e.g. `0.5`) locates on a downscaled copy of the frame and maps
the placements back – several times faster on large photographs, with refinement
restoring sub-pixel geometry. Codes need about 4 px per module *after* downscaling
(`config.MIN_COARSE_PIXELS_PER_FEATURE`); those below are re-located at full
resolution. `None` (default) locates at full resolution. See
[`inkmap.locate()`](#inkmap.locate) (its `scale`). Ignored when `model`/`quad` are given.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`InkMap`](inkmap.types.html.md#inkmap.types.InkMap)]

### inkmap.foreground(image, \*\*kwargs)

Foreground coverage of the largest mark, `(H, W) float32` in `[0, 1]`.

All-zero if nothing is found – the one-liner never raises on a miss, so it can be
mapped over a directory. Use [`find()`](#inkmap.find) to tell “no mark” from “a mark with no
foreground”.

* **Return type:**
  `ndarray`

### inkmap.locate(bgr, gray, , locators=('qr_zxing', 'qr_aruco', 'qr_opencv', 'barcode_zxing'), first_hit=False, scale=None, full_res_retry=True)

Run locator strategies and merge their results, de-duplicating by position.

Strategies are tried in order. With `first_hit=True` the cascade stops at the
first strategy that finds anything – cheaper, and usually right when you know there
is one mark. Otherwise every strategy runs and results merge, which is what earns
the recall when an image holds several marks that no single detector finds all of.

**Coarse-to-fine.** `scale` (`0 < scale <= 1`) runs the cascade on a copy of the
frame downscaled by that factor (`cv2.INTER_AREA`), then maps every placement back
to full-resolution pixels. Locating costs roughly in proportion to pixel count, so
on a 4000 x 3000 photograph 0.5 is about 4x faster and 0.35 about 7x. `None` (the
default) or `1` locate at full resolution, exactly as without the argument.

Every locator – a registered name or your own callable – is handed the
*downscaled* `bgr` and `gray` (and, on a retry, a full-resolution crop), and
must return placements in the coordinates of the frame it was given; mapping them
back to the full frame is done here. A locator that bakes in absolute pixel sizes
or positions will misbehave under `scale`.

The mapping is one affine `A` (small -> full pixels), in the pixel-centre
convention `cv2.resize` uses, `x_full = (x_small + 0.5) / scale - 0.5`, applied
to both `quad` and `transform` (`A @ transform`). Locator name and payload are
kept; `metadata["locate_scale"]` records the scale used. Corner conventions differ
by locator (OpenCV’s are inclusive pixel indices, zxing’s are the continuous outer
boundary), so a locator’s own half-pixel bias is magnified by `1 / scale` on the
way up – a pixel or so at 0.5. That does not matter downstream when
`inkmap.analyze()` refines (its default), which pins the transform to sub-pixel
accuracy at full resolution anyway.

**The model is the fragile part, not the geometry.** Locators read the model off
the frame they are given – a QR’s module count and module matrix, a barcode’s bar
pattern – and refinement cannot repair a wrong model, it only fits its geometry.
Below about `config.MIN_COARSE_PIXELS_PER_FEATURE` (4) pixels per module in the
downscaled frame those reads go wrong while the code still decodes: a 25 x 25 QR
read as 21 x 21, or tens of flipped modules. So, with `full_res_retry` (default
on; only meaningful with `scale < 1`), a coarse placement is re-located on a
padded full-resolution crop around it when either its `payload` is `None` (found
but not decoded – typically a small, far-away code) or its pixels per feature in
the downscaled frame are under that floor. The full-resolution result replaces it
(`metadata["locate_retry"]` names the reason, `"undecoded"` or
`"undersampled"`, and `locate_scale` becomes 1.0). Crops are small, so this
costs little; pick `scale` so your codes clear the floor (at 0.5, 8 px per module
at full resolution) and it never triggers. A coarse placement under the floor that
is kept anyway – `full_res_retry=False`, or the crop found nothing – carries
`metadata["locate_undersampled"] = True`: treat its model as unreliable. A mark
the coarse pass misses entirely is not recovered: lower the downscaling instead.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.measurability(ink_map, , min_pixels=50)

Judge whether a foreground/background measurement can be trusted here.

Returning a number quietly biased by 30% is worse than refusing, so this is checked
up front and attached to every [`Measurement`](#inkmap.Measurement).

* **Return type:**
  [`Measurability`](inkmap.photometry.html.md#inkmap.photometry.Measurability)

### inkmap.measure(image, ink_map, , linearize=True, flatten=False, margin=None, robust=True)

Aggregate `image` over the safe foreground and background pixels of `ink_map`.

`image` need not be the one the mark was located in: any frame registered to it
works, which is the usual way to measure a different exposure, channel or modality
using geometry established once on the sharpest frame.

`linearize` undoes sRGB encoding first – leave it on for anything from a normal
camera pipeline, off for already-linear data. `flatten` divides out a fitted
illumination field. `robust` reports medians alongside means; on real photographs
they diverge exactly where something is wrong, which makes the pair a free
diagnostic.

* **Return type:**
  [`Measurement`](inkmap.photometry.html.md#inkmap.photometry.Measurement)

### inkmap.measurement_mask(ink_map, , kind='foreground', purity=0.999, margin=None)

Pixels safe to measure: geometrically pure, then eroded clear of edges.

`kind` selects `"foreground"` or `"background"`. `purity` is the coverage
threshold for “pure”; the default demands essentially total coverage, which is the
point – a partially covered pixel biases the mean toward the other class.

This is the mask to use for a measurement. [`InkMap.foreground_mask()`](#inkmap.InkMap.foreground_mask) is for
display and for anything that only needs a label.

* **Return type:**
  `ndarray`

### inkmap.measurement_weight(coverage, , blur_sigma=None, radius=None, inside=None, kind='foreground', sigmas=2.0)

Blur-aware weight in `[0, 1]`: how safe each pixel is to *measure*.

Coverage says a pixel lies entirely under foreground. That is necessary but not
sufficient: the point spread function leaks neighbouring signal into interior
pixels, and that contamination has a different footprint from partial area
coverage – so no coverage-based weighting removes it. The fix is spatial: require
a pixel’s whole neighbourhood to be foreground, out to the radius the blur reaches.

Implemented as grayscale morphological erosion of the coverage map, which is exactly
“the minimum coverage within radius r” – continuous rather than a hard mask, so a
pixel one step from an edge is down-weighted rather than trusted or discarded.

Give either `radius` (pixels, wins if both are given) or `blur_sigma`, from
which the radius is `sigmas * blur_sigma`.

* **Return type:**
  `ndarray`

### inkmap.observed_coverage(gray, placement, , polarity=Polarity.FOREGROUND_IS_DARK, yule_nielsen_n=1.0, percentile=5.0)

Apparent coverage read from the photograph itself (Murray-Davies).

Endmember values are estimated from the mark’s own pixels – its background region
gives the substrate endpoint, its foreground core the solid endpoint – so no
external calibration target is needed. Percentiles rather than extremes, so a
specular highlight cannot define an endpoint.

`yule_nielsen_n` > 1 compensates for lateral light scattering in the substrate,
which otherwise inflates apparent coverage above geometric coverage. n = 1 is plain
Murray-Davies; the right value is substrate- and wavelength-specific and should be
fitted, not guessed.

The result is *apparent*, not geometric, coverage. Do not silently substitute it
for [`coverage_map()`](#inkmap.coverage_map).

* **Return type:**
  `ndarray`

### inkmap.place(model, quad, , inclusive_pixel_corners=False, locator='manual', \*\*metadata)

Place a model at a known quadrilateral – the universal escape hatch.

`quad` is four `(x, y)` image points in the *model’s* own corner order: the
point corresponding to model-space `(0, 0)` first, then clockwise. Order matters
and is not inferred: sorting corners by image position silently mislabels them once
the mark is rotated past 45 degrees.

Use this for anything without a decoder – printed letters, logos, engraved marks –
or when you already know where the mark is and only want the coverage machinery.

* **Return type:**
  [`Placement`](inkmap.types.html.md#inkmap.types.Placement)

### inkmap.srgb_to_linear(image)

Undo the sRGB transfer function, returning float in `[0, 1]`.

Averaging pixel values without this is a real error, not a nicety: sRGB values are
perceptually encoded, so the mean of encoded values is not the encoded mean
intensity. Any difference between two exposures compounds it. Apply before any
arithmetic that claims to be about light.

The piecewise IEC 61966-2-1 curve, not the 2.2 power approximation.

* **Return type:**
  `ndarray`

### Modules

| [`models`](inkmap.models.html.md#module-inkmap.models)         | Shape models: what the foreground is expected to look like.                                  |
|--------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| [`geometry`](inkmap.geometry.html.md#module-inkmap.geometry)     | Model space <-> image space: transforms, and refining them against the photograph.           |
| [`photometry`](inkmap.photometry.html.md#module-inkmap.photometry) | Turning masks into measurements that are actually valid.                                     |
| [`config`](inkmap.config.html.md#module-inkmap.config)         | Tunable defaults, in one place.                                                              |
| [`corpus`](inkmap.corpus.html.md#module-inkmap.corpus)         | The real-photograph test corpus: 384 photographed marks in the wild, from Wikimedia Commons. |
| [`coverage`](inkmap.coverage.html.md#module-inkmap.coverage)     | Per-pixel foreground coverage: the 0..1 value, and which one you want.                       |
| [`synth`](inkmap.synth.html.md#module-inkmap.synth)           | Synthetic scenes with exact ground truth.                                                    |
| [`types`](inkmap.types.html.md#module-inkmap.types)           | The data types the whole package speaks in.                                                  |
| [`viz`](inkmap.viz.html.md#module-inkmap.viz)               | Visual overlays, for checking that a result is actually right.                               |
