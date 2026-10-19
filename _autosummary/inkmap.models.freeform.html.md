# inkmap.models.freeform

Models for shapes that are not on a grid: rasters, polygons, and text.

These are the escape hatches. Anything you can draw, scan, or describe as outlines
becomes a model here, and the rest of the package treats it exactly like a QR symbol.

[`PolygonModel`](#inkmap.models.freeform.PolygonModel) is the only *exact* one – a point-in-polygon test has no
resolution. [`RasterModel`](#inkmap.models.freeform.RasterModel) quantises to its own grid, so give it enough
resolution: its cells should be several times smaller than an image pixel maps to,
or the raster’s own edges become the accuracy limit rather than the photograph’s.

### Functions

| [`text_model`](#inkmap.models.freeform.text_model)(text, \*\*kwargs)   | Convenience constructor for [`GlyphModel`](#inkmap.models.freeform.GlyphModel).   |
|---------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|

### Classes

| [`RasterModel`](#inkmap.models.freeform.RasterModel)(mask[, metadata])                  | Foreground given as an image: a logo, a scan, a pre-rendered glyph.   |
|-------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`PolygonModel`](#inkmap.models.freeform.PolygonModel)(polygons[, extent_override, ...]) | Foreground as closed outlines, with holes -- the exact case.          |
| [`GlyphModel`](#inkmap.models.freeform.GlyphModel)(text[, font_path, font_size, ...])  | A run of printed text, rendered once at high resolution.              |

### *class* inkmap.models.freeform.GlyphModel(text, font_path=None, font_size=256, padding=8, metadata=dict())

Bases: [`BaseModel`](inkmap.models.base.html.md#inkmap.models.base.BaseModel)

A run of printed text, rendered once at high resolution.

Text is a raster problem in practice: fonts are outlines, but hinting, kerning and
anti-aliasing mean the printed shape is what the renderer produced, not the ideal
outline. So this renders through PIL at a resolution well above the photograph’s
and treats the result as a [`RasterModel`](#inkmap.models.freeform.RasterModel).

Requires Pillow, and a font file for anything but the (very coarse) PIL default –
pass `font_path`. Model space is the rendered pixel grid.

#### *property* feature_size *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Typical stroke width of the rendered text, in raster cells.

### *class* inkmap.models.freeform.PolygonModel(polygons, extent_override=None, metadata=dict())

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

### *class* inkmap.models.freeform.RasterModel(mask, metadata=dict())

Bases: [`BaseModel`](inkmap.models.base.html.md#inkmap.models.base.BaseModel)

Foreground given as an image: a logo, a scan, a pre-rendered glyph.

`mask` may be boolean or float in `[0, 1]`; float is respected, so an
anti-aliased source keeps its soft edges. Model space is `(width, height)` in
raster cells.

### inkmap.models.freeform.text_model(text, \*\*kwargs)

Convenience constructor for [`GlyphModel`](#inkmap.models.freeform.GlyphModel).

* **Return type:**
  [`GlyphModel`](#inkmap.models.freeform.GlyphModel)
