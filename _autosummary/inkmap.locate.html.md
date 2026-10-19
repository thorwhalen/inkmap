# inkmap.locate

Locators: finding where a model sits in an image.

A locator is a plain function `(bgr, gray) -> list[Placement]`, so registering your
own needs no subclassing:

> from inkmap import locate

> locate.LOCATORS[“mine”] = my_locator
> inkmap.find_all(photo, locators=[“mine”, “qr_zxing”])

For the many cases where the mark cannot be auto-detected – a letter, a logo, a shape
with no decoder in the world – [`place()`](#inkmap.locate.place) is the universal entry point: you supply
the model and where its corners are, and the rest of the package proceeds identically.
That is the seam that makes this work for “anything the user provides a model for”.

Plain registration marks – solid squares and nested-square bullseyes, which carry no
code to decode – are found by [`find_square_marks()`](#inkmap.locate.find_square_marks), which returns their
projective sub-pixel centres rather than placements of a model. A plain printed
patch – a uniform colour rectangle, no code – and the ring of substrate round it are
found by [`locate_patch()`](#inkmap.locate.locate_patch), seeded at a point inside it.

### Module Attributes

| [`LOCATORS`](#inkmap.locate.LOCATORS)   | `LOCATORS["mine"] = my_locator`.   |
|-------------------------------------------------------------|------------------------------------|

### Functions

| [`locate`](#inkmap.locate.locate)(bgr, gray, \*[, locators, first_hit, ...])   | Run locator strategies and merge their results, de-duplicating by position.                            |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| [`place`](#inkmap.locate.place)(model, quad, \*[, ...])                       | Place a model at a known quadrilateral -- the universal escape hatch.                                  |
| [`validated_scale`](#inkmap.locate.validated_scale)(scale)                              | Check a locate scale; `None` means full resolution (and so does `1`).                                  |
| [`locate_qr_opencv`](#inkmap.locate.locate_qr_opencv)(bgr, gray)                         | OpenCV's classic `QRCodeDetector`.                                                                     |
| [`locate_qr_aruco`](#inkmap.locate.locate_qr_aruco)(bgr, gray)                          | OpenCV's `QRCodeDetectorAruco` -- finds the finder patterns as Aruco-like markers.                     |
| [`locate_qr_zxing`](#inkmap.locate.locate_qr_zxing)(bgr, gray)                          | zxing-cpp.                                                                                             |
| [`locate_barcode_zxing`](#inkmap.locate.locate_barcode_zxing)(bgr, gray)                     | Locate linear barcodes with zxing-cpp and model their bar pattern.                                     |
| [`find_square_marks`](#inkmap.locate.find_square_marks)(gray, \*[, min_side_px, ...])     | Every solid or nested square mark in `gray` (2-D, 0-255 scale), largest first.                         |
| [`quad_centre`](#inkmap.locate.quad_centre)(corners)                                | Where the diagonals of a quadrilateral cross: the projective centre of a square.                       |
| [`ring_ratios`](#inkmap.locate.ring_ratios)(outer_area, inner_areas)                | Side ratios of nested squares from their areas: `sqrt(inner / outer)`.                                 |
| [`locate_patch`](#inkmap.locate.locate_patch)(image, \*[, seed, seed_share, ...])    | The uniform patch at `seed`, and the ring of substrate just outside it.                                |
| [`locate_patch_centre`](#inkmap.locate.locate_patch_centre)(bgr, gray)                      | A [`LOCATORS`](#inkmap.locate.LOCATORS) strategy: the patch at the frame's centre. |

### Classes

| [`SquareMark`](#inkmap.locate.SquareMark)(centre, corners, side_px[, ...])      | One square mark found in an image.                                              |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`PatchRegions`](#inkmap.locate.PatchRegions)(patch, substrate, region, quad, ok) | A located patch: masks over the frame, its geometry, and how far to trust them. |

### inkmap.locate.LOCATORS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[[ndarray, ndarray], [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[Placement](inkmap.types.html.md#inkmap.types.Placement)]]]* *= {'barcode_zxing': <function locate_barcode_zxing>, 'patch': <function locate_patch_centre>, 'qr_aruco': <function locate_qr_aruco>, 'qr_opencv': <function locate_qr_opencv>, 'qr_zxing': <function locate_qr_zxing>}*

`LOCATORS["mine"] = my_locator`.

* **Type:**
  Registry of locator strategies. Add your own

### *class* inkmap.locate.PatchRegions(patch, substrate, region, quad, ok, notes=(), seed_lab=(nan, nan, nan), threshold_delta_e=nan, area_share=0.0, rectangularity=0.0, touches_border=False, hole_share=0.0, outline_deviation_px=nan, substrate_px=0, ring_px=(0.0, 0.0))

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A located patch: masks over the frame, its geometry, and how far to trust them.

`patch` is the interior, eroded clear of the edge; `substrate` a ring of bare
substrate just outside; `region` the whole patch, uneroded. `quad` is the
patch’s corners, clockwise as seen on screen from the one nearest the image’s
top-left, to a fraction of a pixel when its sides could be fitted (`None` if no
region was found). `ok` is `not notes`.

The rest say why: `seed_lab` the patch colour, `threshold_delta_e` the split
used, `area_share` of the frame, `rectangularity` (region over fitted quad),
`outline_deviation_px` (95th percentile of the outline’s distance from the
fitted sides), `hole_share` (share of the interior not the patch’s colour),
`substrate_px`, and `ring_px` (the ring’s inner and outer distance).

#### *property* placement *: [Placement](inkmap.types.html.md#inkmap.types.Placement) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The patch and its substrate ring as a placement, or `None` without a quad.

The model is the patch as foreground inside a border of background as wide as
the substrate ring’s outer edge, in units of about one pixel. So
`inkmap.analyze()` and [`inkmap.measure()`](inkmap.html.md#inkmap.measure) treat the patch as any other
mark, and `measure` compares the patch with the substrate round it. The
placement’s `quad` is that bordered model’s, not the patch’s: the patch’s own
corners are `quad`. `measure` averages the whole border, background
and all, where `substrate` keeps only its paper-like pixels: on a thin
paper border, measure with `substrate` instead.

### *class* inkmap.locate.SquareMark(centre, corners, side_px, rings=(), sigma_px=nan, centres=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One square mark found in an image. Coordinates are pixels, `(x, y)`.

`corners` are the outer square’s, clockwise as seen on screen, starting from the
one nearest the image’s top-left. A square has no intrinsic first corner, so that
order is a convention, not an identification. `rings` is the side of each nested
square as a fraction of the outer one, outermost first (empty for a solid mark).
`centres` are the outer square’s centre followed by each nested square’s, each
where that square’s diagonals cross; `centre` is their mean weighted by side,
which for a solid mark is the outer square’s own.

#### ring_error(expected)

Largest difference between these ring ratios and `expected`; inf if unlike.

```pycon
>>> SquareMark((0, 0), np.zeros((4, 2)), 10.0, rings=(0.7, 0.4)).ring_error(
...     QR_FINDER_RINGS
... )
0.028...
>>> SquareMark((0, 0), np.zeros((4, 2)), 10.0).ring_error(BULLSEYE_RINGS)
inf
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### inkmap.locate.find_square_marks(gray, , min_side_px=8.0, max_side_share=0.1, polarity=Polarity.FOREGROUND_IS_DARK, dark_share=0.72, min_contrast=6.0, local_window_share=0.12)

Every solid or nested square mark in `gray` (2-D, 0-255 scale), largest first.

A mark’s outer square must be at least `min_side_px` on a side and at most
`max_side_share` of the frame’s shorter side. Nested marks report their ring
ratios; solid marks report none. `polarity` says whether the marks read darker
than the substrate (the usual case) or brighter.

The foreground is binarised relative to the local mean brightness: a pixel is
foreground when it is darker than `dark_share` of the mean over a window
`local_window_share` of the frame’s shorter side, and darker by at least
`min_contrast` grey levels. The window is widened to stay wider than the largest
mark looked for, since a mark wider than it is hollowed by its own ink.

Anything square is a candidate: a QR symbol’s clusters of data modules and some
printed glyphs come back as solid marks too. Telling the registration marks from
them, by size, ring ratio and layout, is the caller’s.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`SquareMark`](inkmap.locate.marks.html.md#inkmap.locate.marks.SquareMark)]

### inkmap.locate.locate(bgr, gray, , locators=('qr_zxing', 'qr_aruco', 'qr_opencv', 'barcode_zxing'), first_hit=False, scale=None, full_res_retry=True)

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

### inkmap.locate.locate_barcode_zxing(bgr, gray)

Locate linear barcodes with zxing-cpp and model their bar pattern.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.locate.locate_patch(image, , seed='centre', seed_share=0.04, min_delta_e=4.0, max_delta_e=25.0, edge_margin_share=0.08, ring_share=(0.02, 0.06), min_area_share=0.01, min_rectangularity=0.85, min_substrate_px=50, min_substrate_lift=1.0, max_substrate_chroma=15.0, min_side_share=0.15, min_edge_step=3.0)

The uniform patch at `seed`, and the ring of substrate just outside it.

`image` is a path, a BGR (or BGRA) array, or a grey array, 8-bit. `seed` is
`"centre"` or an `(x, y)` pixel inside the patch; its colour is the median of a
window `seed_share` of the frame’s shorter side across. Pixels within the Otsu
split of the CIELAB distance to it, clamped to `[min_delta_e, max_delta_e]`, are
candidates, and the connected candidate region at the seed is the patch.

`edge_margin_share` erodes the interior, and `ring_share` places the
substrate ring, both as shares of the patch’s shorter side. The verdict fails, with
a note saying why, when the patch is under `min_area_share` of the frame, less
rectangular than `min_rectangularity` (area over its minimum-area rectangle’s:
where a pale patch leaked into the paper), cut by the frame’s edge, or when the
ring holds under `min_substrate_px` pixels of substrate, substrate no lighter than
the patch by `min_substrate_lift` L\*, or substrate on fewer than three sides
(`min_side_share` of that side’s ring each), or when a side of the patch has no
colour step of `min_edge_step` across it – the sign of a region that leaked into
shaded paper. A failed verdict on a leaked region is retried at a tighter
threshold.

* **Return type:**
  [`PatchRegions`](inkmap.locate.patch.html.md#inkmap.locate.patch.PatchRegions)

### inkmap.locate.locate_patch_centre(bgr, gray)

A [`LOCATORS`](#inkmap.locate.LOCATORS) strategy: the patch at the frame’s centre.

Registered as `"patch"` but not in the default cascade, so
`inkmap.find(photo, locators=["patch"])` opts in. Returns nothing unless the
verdict is `ok`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.locate.locate_qr_aruco(bgr, gray)

OpenCV’s `QRCodeDetectorAruco` – finds the finder patterns as Aruco-like
markers. Notably more robust than the classic detector on real photographs.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.locate.locate_qr_opencv(bgr, gray)

OpenCV’s classic `QRCodeDetector`. Corners are inclusive pixel indices.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.locate.locate_qr_zxing(bgr, gray)

zxing-cpp. Highest recall of the three, and its corners are the continuous outer
boundary (spanning exactly `N * scale`), not inclusive pixel indices.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.locate.place(model, quad, , inclusive_pixel_corners=False, locator='manual', \*\*metadata)

Place a model at a known quadrilateral – the universal escape hatch.

`quad` is four `(x, y)` image points in the *model’s* own corner order: the
point corresponding to model-space `(0, 0)` first, then clockwise. Order matters
and is not inferred: sorting corners by image position silently mislabels them once
the mark is rotated past 45 degrees.

Use this for anything without a decoder – printed letters, logos, engraved marks –
or when you already know where the mark is and only want the coverage machinery.

* **Return type:**
  [`Placement`](inkmap.types.html.md#inkmap.types.Placement)

### inkmap.locate.quad_centre(corners)

Where the diagonals of a quadrilateral cross: the projective centre of a square.

`corners` must be in cyclic order (either direction). `None` if degenerate.

```pycon
>>> quad_centre([(0, 0), (4, 0), (4, 2), (0, 2)])
(2.0, 1.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### inkmap.locate.ring_ratios(outer_area, inner_areas)

Side ratios of nested squares from their areas: `sqrt(inner / outer)`.

```pycon
>>> ring_ratios(100.0, (64.0, 16.0))
(0.8, 0.4)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### inkmap.locate.validated_scale(scale)

Check a locate scale; `None` means full resolution (and so does `1`).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### Modules

| [`barcode`](inkmap.locate.barcode.html.md#module-inkmap.locate.barcode)   | Locating linear (1-D) barcodes.                                                           |
|-----------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| [`marks`](inkmap.locate.marks.html.md#module-inkmap.locate.marks)       | Find square registration marks: solid squares and nested squares, sub-pixel.              |
| [`patch`](inkmap.locate.patch.html.md#module-inkmap.locate.patch)       | Locate a plain printed patch -- a uniform colour rectangle -- and the substrate round it. |
| [`qr`](inkmap.locate.qr.html.md#module-inkmap.locate.qr)             | Locating QR symbols: a cascade of interchangeable strategies.                             |
