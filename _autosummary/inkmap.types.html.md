# inkmap.types

The data types the whole package speaks in.

Naming here is deliberate, because the obvious names are traps:

* The two classes inside a mark’s footprint are `FOREGROUND` and `BACKGROUND`,
  **not** dark and light. Dark/light describe *appearance*, and appearance inverts:
  white-on-black print, reflectance-reversed symbols (explicitly permitted by ISO/IEC
  18004 for QR), and any inverted imaging modality all swap which class is dark. A
  `dark_mask` would then silently mean foreground in one image and background in the
  next. [`Polarity`](#inkmap.types.Polarity) carries that mapping explicitly instead.
* `BACKGROUND` is scoped to *within the mark’s footprint*. The clear margin around
  the mark is `MARGIN` and everything else is `OUTSIDE`, so the ambiguity that
  makes a bare “background” dangerous – substrate inside the mark, or everything that
  is not the mark? – cannot arise.
* The continuous value is `coverage`, after ISO 12647-2:2013 3.1 *area coverage*,
  “ratio of the area covered with ink to the entire area” – the only term in any
  standard whose definition is literally the quantity computed here.

See `docs/terminology.md` for the full cross-field mapping.

### Classes

| [`InkMap`](#inkmap.types.InkMap)(coverage, region, placement[, ...])        | Per-pixel foreground coverage for one placement, plus the geometry it came from.   |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`Placement`](#inkmap.types.Placement)(model, transform, quad[, locator, ...]) | A located instance of a model: which shape, and where it sits in the image.        |
| [`Polarity`](#inkmap.types.Polarity)(\*values)                                | Which apparent-brightness state the foreground corresponds to.                     |
| [`Region`](#inkmap.types.Region)(\*values)                                  | Four-way pixel classification.                                                     |

### *class* inkmap.types.InkMap(coverage, region, placement, polarity=Polarity.FOREGROUND_IS_DARK, weight=None, blur_sigma=None, metadata=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Per-pixel foreground coverage for one placement, plus the geometry it came from.

`coverage` is *geometric* area coverage: the fraction of each pixel’s area lying
under foreground. It is not an optical/reflectance-derived coverage (which lateral
light scattering in the substrate inflates – the Murray-Davies/Yule-Nielsen
effect), and it is not a probability. See `confidence()` for that.

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
labelling; for anything photometric use [`inkmap.measurement_mask()`](inkmap.html.md#inkmap.measurement_mask)
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

(H, W) uint8 of [`Region`](#inkmap.types.Region) values.

#### weight *: ndarray | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

(H, W) float32 in [0, 1] – the blur-aware measurement weight, and the **only**
channel that should gate a physical measurement. Coverage is geometric and ignores
the point spread function; confidence is epistemic and says nothing about
partial-area contamination. See [`inkmap.coverage.measurement_weight()`](inkmap.coverage.html.md#inkmap.coverage.measurement_weight).

### *class* inkmap.types.Placement(model, transform, quad, locator='', payload=None, refined=False, score=None, metadata=dict())

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
measurement is possible – not [`pixels_per_unit`](#inkmap.types.Placement.pixels_per_unit). A model unit is not a
feature: a QR module is both, but a glyph rendered onto a 512-cell raster has
strokes tens of cells wide, so pixels-per-unit there would understate the real
resolution by that factor and declare every image unmeasurable.

#### *property* pixels_per_unit *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Image pixels per model unit.

For a QR symbol a “unit” is one module; for a barcode, one narrow bar; for a
raster model, one raster cell. Use [`pixels_per_feature`](#inkmap.types.Placement.pixels_per_feature) to reason about
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

### *class* inkmap.types.Polarity(\*values)

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

### *class* inkmap.types.Region(\*values)

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
