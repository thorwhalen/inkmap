# inkmap.models.base

What a *model* is, and how it becomes pixels.

A model answers one question: \*\*given a point in the mark’s own coordinate system, is
that point foreground?\*\* Everything else in this package – locating, refining,
rasterising, measuring – is written against that one question, which is why the same
machinery serves QR symbols, barcodes, printed letters and any shape a user supplies.

## Model space

Each model defines its own natural units and its own extent. A QR symbol is `N x N`
modules; a Code 128 barcode is `n x 1` modules wide by one unit tall; a glyph is
whatever its em-box says. Nothing outside this module needs to know which – the
[`Placement`](inkmap.types.html.md#inkmap.types.Placement) carries a homography from model space to image pixels,
and that is the only bridge required.

## Why `occupancy` and not “give me a bitmap”

Coverage is computed by supersampling each image pixel’s footprint back into model
space. If a model can answer occupancy *analytically* – and a QR module grid or a
barcode can – the result is exact, limited only by the supersampling rate. Forcing
every model through a bitmap would quantise it twice: once rendering, once sampling.
Models that genuinely are rasters (a scanned logo, a rendered glyph) implement
occupancy as a lookup and lose nothing.

### Functions

| [`render_model`](#inkmap.models.base.render_model)(model[, scale, supersample])   | Rasterise any model to a float `[0, 1]` array at `scale` px per model unit.   |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|

### Classes

| [`Model`](#inkmap.models.base.Model)(\*args, \*\*kwargs)   | The shape of a mark, in its own coordinate system.        |
|------------------------------------------------------------------------------|-----------------------------------------------------------|
| [`BaseModel`](#inkmap.models.base.BaseModel)()                 | Mixin supplying `render()` and a `feature_size` estimate. |

### *class* inkmap.models.base.BaseModel

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Mixin supplying [`render()`](#inkmap.models.base.BaseModel.render) and a [`feature_size`](#inkmap.models.base.BaseModel.feature_size) estimate.

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

### *class* inkmap.models.base.Model(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

The shape of a mark, in its own coordinate system.

Implement this – or just duck-type it – to teach the package a new kind of mark.
Two members are required; `render()` has a working default in
[`BaseModel`](#inkmap.models.base.BaseModel).

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

[`BaseModel`](#inkmap.models.base.BaseModel) estimates it from the rendered shape; grid models override
it with the exact value.

#### occupancy(u, v)

Foreground indicator at model coordinates `(u, v)`.

`u` and `v` are float arrays of any matching shape. Returns an array of the
same shape, boolean or float in `[0, 1]`. Points outside [`extent`](#inkmap.models.base.Model.extent) must
return 0 – callers rely on that to bound the mark.

Must be vectorised: it is called with millions of points.

* **Return type:**
  `ndarray`

### inkmap.models.base.render_model(model, scale=8.0, , supersample=4)

Rasterise any model to a float `[0, 1]` array at `scale` px per model unit.

* **Return type:**
  `ndarray`
