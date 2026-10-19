# inkmap.models

Shape models: what the foreground is expected to look like.

A model is anything that can answer [`occupancy()`](inkmap.models.base.html.md#inkmap.models.base.Model.occupancy) – is
this point in the mark’s own coordinate system foreground? – plus report its
[`extent`](inkmap.models.base.html.md#inkmap.models.base.Model.extent). That is the whole contract, and it is what
lets one pipeline serve QR symbols, barcodes, printed letters and arbitrary artwork.

> from inkmap import models

> models.MatrixModel(cells)          # QR, Data Matrix, Aztec: a grid of cells
> models.BarsModel(bars)             # EAN, Code 128, …: a run of bars
> models.RasterModel(mask)           # a logo, a scan, anything you can draw
> models.PolygonModel(outlines)      # exact vector outlines, holes included
> models.GlyphModel(“ABC”)           # printed text, rendered via Pillow

Anything duck-typed to the same two members works just as well – there is no base
class to inherit and no registration step.

### Functions

| [`render_model`](#inkmap.models.render_model)(model[, scale, supersample])   | Rasterise any model to a float `[0, 1]` array at `scale` px per model unit.              |
|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| [`text_model`](#inkmap.models.text_model)(text, \*\*kwargs)                | Convenience constructor for [`GlyphModel`](#inkmap.models.GlyphModel). |

### Classes

| [`Model`](#inkmap.models.Model)(\*args, \*\*kwargs)                      | The shape of a mark, in its own coordinate system.                                |
|-------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`BaseModel`](#inkmap.models.BaseModel)()                                    | Mixin supplying `render()` and a `feature_size` estimate.                         |
| [`MatrixModel`](#inkmap.models.MatrixModel)(cells[, metadata])                 | A 2-D grid of foreground/background cells -- a QR symbol's module matrix.         |
| [`BarsModel`](#inkmap.models.BarsModel)(bars[, height, metadata])            | A 1-D run of foreground/background bars, extruded vertically -- a linear barcode. |
| [`RasterModel`](#inkmap.models.RasterModel)(mask[, metadata])                  | Foreground given as an image: a logo, a scan, a pre-rendered glyph.               |
| [`PolygonModel`](#inkmap.models.PolygonModel)(polygons[, extent_override, ...]) | Foreground as closed outlines, with holes -- the exact case.                      |
| [`GlyphModel`](#inkmap.models.GlyphModel)(text[, font_path, font_size, ...])  | A run of printed text, rendered once at high resolution.                          |

### *class* inkmap.models.BarsModel(bars, height=20.0, metadata=dict())

Bases: [`BaseModel`](inkmap.models.base.html.md#inkmap.models.base.BaseModel)

A 1-D run of foreground/background bars, extruded vertically – a linear barcode.

`bars` is a boolean array over the narrowest module width, `True` for a bar.
Model space is `(len(bars), height)`; `height` is in the same module units, so
a 95-module EAN-13 printed twice as tall as it is wide would use `height=190`.
Height rarely matters for coverage (the pattern is constant along `v`) but it
fixes the aspect ratio for rendering and refinement.

#### *property* feature_size *: [float](https://docs.python.org/3/builtins/functions.html#float)*

One module – the narrowest bar, which is what must be resolved.

### *class* inkmap.models.BaseModel

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Mixin supplying [`render()`](#inkmap.models.BaseModel.render) and a [`feature_size`](#inkmap.models.BaseModel.feature_size) estimate.

Anything with `extent` and `occupancy` gets both for free.

#### *property* feature_size *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Estimated smallest-feature size, in model units, from the rendered shape.

Taken as twice the median distance-to-edge over foreground – i.e. the typical
stroke width. The median rather than the minimum, because every shape has a few
pixels at a corner or a serif whose distance-to-edge is near zero, and letting
those set the scale would declare every image unmeasurable.

Cached: it costs a render, and the answer cannot change for an immutable model.

#### render(scale=8.0, , supersample=4)

Rasterise the model at `scale` pixels per model unit.

Returns a float array in `[0, 1]` where 1 is foreground. Anti-aliased by
supersampling, because the main consumer is template alignment against a
photograph, and a hard-edged template correlates poorly with soft real edges.

* **Return type:**
  `ndarray`

### *class* inkmap.models.GlyphModel(text, font_path=None, font_size=256, padding=8, metadata=dict())

Bases: [`BaseModel`](inkmap.models.base.html.md#inkmap.models.base.BaseModel)

A run of printed text, rendered once at high resolution.

Text is a raster problem in practice: fonts are outlines, but hinting, kerning and
anti-aliasing mean the printed shape is what the renderer produced, not the ideal
outline. So this renders through PIL at a resolution well above the photograph’s
and treats the result as a [`RasterModel`](#inkmap.models.RasterModel).

Requires Pillow, and a font file for anything but the (very coarse) PIL default –
pass `font_path`. Model space is the rendered pixel grid.

#### *property* feature_size *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Typical stroke width of the rendered text, in raster cells.

### *class* inkmap.models.MatrixModel(cells, metadata=dict())

Bases: [`BaseModel`](inkmap.models.base.html.md#inkmap.models.base.BaseModel)

A 2-D grid of foreground/background cells – a QR symbol’s module matrix.

`cells[row, col]` is `True` where the cell is foreground. Model space is
`(n_cols, n_rows)` in cells, origin at the mark’s own top-left, so cell
`(i, j)` occupies `u in [j, j+1)`, `v in [i, i+1)`.

Also serves Data Matrix, Aztec, and any other matrix symbology: only the cell
grid matters here, not how it was decoded.

#### *property* feature_size *: [float](https://docs.python.org/3/builtins/functions.html#float)*

One cell – for a matrix symbology the cell *is* the smallest feature.

### *class* inkmap.models.Model(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

The shape of a mark, in its own coordinate system.

Implement this – or just duck-type it – to teach the package a new kind of mark.
Two members are required; `render()` has a working default in
[`BaseModel`](#inkmap.models.BaseModel).

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

[`BaseModel`](#inkmap.models.BaseModel) estimates it from the rendered shape; grid models override
it with the exact value.

#### occupancy(u, v)

Foreground indicator at model coordinates `(u, v)`.

`u` and `v` are float arrays of any matching shape. Returns an array of the
same shape, boolean or float in `[0, 1]`. Points outside [`extent`](#inkmap.models.Model.extent) must
return 0 – callers rely on that to bound the mark.

Must be vectorised: it is called with millions of points.

* **Return type:**
  `ndarray`

### *class* inkmap.models.PolygonModel(polygons, extent_override=None, metadata=dict())

Bases: [`BaseModel`](inkmap.models.base.html.md#inkmap.models.base.BaseModel)

Foreground as closed outlines, with holes – the exact case.

`polygons` is a sequence of `(N, 2)` float arrays of `(u, v)` vertices. Use
the even-odd rule: a polygon inside another cuts a hole, which is what letters like
‘o’ and ‘B’ need. No resolution is involved, so coverage error is limited only by
the supersampling rate.

#### occupancy(u, v)

Even-odd crossing test, vectorised over all points and all edges.

* **Return type:**
  `ndarray`

### *class* inkmap.models.RasterModel(mask, metadata=dict())

Bases: [`BaseModel`](inkmap.models.base.html.md#inkmap.models.base.BaseModel)

Foreground given as an image: a logo, a scan, a pre-rendered glyph.

`mask` may be boolean or float in `[0, 1]`; float is respected, so an
anti-aliased source keeps its soft edges. Model space is `(width, height)` in
raster cells.

### inkmap.models.render_model(model, scale=8.0, , supersample=4)

Rasterise any model to a float `[0, 1]` array at `scale` px per model unit.

* **Return type:**
  `ndarray`

### inkmap.models.text_model(text, \*\*kwargs)

Convenience constructor for [`GlyphModel`](#inkmap.models.GlyphModel).

* **Return type:**
  [`GlyphModel`](inkmap.models.freeform.html.md#inkmap.models.freeform.GlyphModel)

### Modules

| [`base`](inkmap.models.base.html.md#module-inkmap.models.base)         | What a *model* is, and how it becomes pixels.                                  |
|-----------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`freeform`](inkmap.models.freeform.html.md#module-inkmap.models.freeform) | Models for shapes that are not on a grid: rasters, polygons, and text.         |
| [`grid`](inkmap.models.grid.html.md#module-inkmap.models.grid)         | Models whose foreground is defined on a regular grid: QR symbols and barcodes. |
