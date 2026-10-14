# inkmap.geometry

Model space <-> image space: transforms, and refining them against the photograph.

The central object is a homography mapping *model coordinates* to image pixels. Get it
right and every mask, sample and margin polygon follows exactly. Get it wrong by a
pixel and every downstream number inherits the error, while the mask still looks
plausible.

Three half-pixel conventions have to agree, and each is invisible on inspection:

1. **Pixel centre vs pixel corner.** OpenCV treats integer coordinate `x` as the
   *centre* of a pixel spanning `[x-0.5, x+0.5)`. Rasterising `[x, x+1)` instead –
   the natural array-indexing reading – offsets the entire coverage map by half a
   pixel.
2. **The template raster.** A model rendered at `s` px per unit puts template pixel
   `t` over `[t/s, (t+1)/s)` in model units, so its *centre* is `(t+0.5)/s`.
   Omitting that half-pixel puts a fixed ~0.7 px bias into every refinement.
3. **Detector corner conventions differ.** OpenCV’s QR corners are the integer index of
   the last *contained* pixel; zxing-cpp returns the continuous outer boundary. Measured
   directly, not read from docs – hence `inclusive_pixel_corners`.

A symptom worth recognising: if refinement error grows with the mark’s rotation angle
in the pattern `R(d) - d`, the residual `d` is a coordinate-convention offset, not
noise.

### Functions

| [`model_quad`](#inkmap.geometry.model_quad)(model)                            | The model's four extent corners in model coordinates, top-left first.     |
|-----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`quad_to_transform`](#inkmap.geometry.quad_to_transform)(quad, model, \*[, ...])    | Homography mapping model coordinates onto an image quad.                  |
| [`transform_to_quad`](#inkmap.geometry.transform_to_quad)(transform, model)          | Image-space corners implied by a transform, in model order.               |
| [`pixels_per_unit`](#inkmap.geometry.pixels_per_unit)(transform, model)            | Mean image pixels per model unit implied by a transform.                  |
| [`refine_transform`](#inkmap.geometry.refine_transform)(gray, model, transform, \*) | Refine a model->image transform by ECC-aligning the rendered model.       |
| [`margin_quad`](#inkmap.geometry.margin_quad)(transform, model, \*[, units])   | Image-space quad of the model plus a clear margin of `units` model units. |
| [`cell_centers`](#inkmap.geometry.cell_centers)(transform, n_cols, n_rows)      | `(n_rows, n_cols, 2)` image coordinates of unit-cell centres.             |

### inkmap.geometry.cell_centers(transform, n_cols, n_rows)

`(n_rows, n_cols, 2)` image coordinates of unit-cell centres.

Meaningful for grid models. ISO/IEC 18004’s reference decode algorithm samples a
small area at each grid intersection – deliberately avoiding edges rather than
modelling them – and this is where to do the same.

* **Return type:**
  `ndarray`

### inkmap.geometry.margin_quad(transform, model, , units=4.0)

Image-space quad of the model plus a clear margin of `units` model units.

ISO/IEC 18004 mandates a 4-module quiet zone for QR; linear symbologies specify
light margins; printed text has its own whitespace. The margin is guaranteed
background, which makes it a reference region that – unlike background *inside*
the mark – carries no risk of spread from adjacent foreground.

* **Return type:**
  `ndarray`

### inkmap.geometry.model_quad(model)

The model’s four extent corners in model coordinates, top-left first.

* **Return type:**
  `ndarray`

### inkmap.geometry.pixels_per_unit(transform, model)

Mean image pixels per model unit implied by a transform.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### inkmap.geometry.quad_to_transform(quad, model, , inclusive_pixel_corners=False)

Homography mapping model coordinates onto an image quad.

`quad` must be in the *model’s* own corner order (its top-left first), which is
what the locators natively produce – do not re-sort it.

Set `inclusive_pixel_corners=True` for detectors whose corners are the integer
index of the last contained pixel rather than the continuous outer edge. The quad
is then expanded half a pixel outward, removing a systematic one-pixel scale error
– which is a third of a unit at 3 px per unit.

* **Return type:**
  `ndarray`

### inkmap.geometry.refine_transform(gray, model, transform, , iterations=200, eps=1e-07, blur_frac=0.25, min_correlation=0.5, margin_units=2.0)

Refine a model->image transform by ECC-aligning the rendered model.

Four detector corners are four observations; the model’s whole shape is thousands.
Aligning the rendered pattern therefore pins the 8-DoF homography far more tightly
– measured at 0.02-0.03 px corner RMS versus ~1 px from detector corners.

Returns `(transform, correlation)`, falling back to the input unchanged when the
optimiser fails or the correlation lands below `min_correlation` – a refinement
that did not converge is worse than none.

Two details do most of the work. The template is rendered at the *observed* scale;
rendering at a fixed small scale aliases the comparison and makes the result
measurably worse than no refinement at all. And the template carries a clear margin,
because blurring a template that stops at the mark’s edge makes the kernel reflect
interior content back across the border, inventing an edge profile the photograph
does not have – ECC then shifts the whole fit to match the artefact.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[`ndarray`, [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### inkmap.geometry.transform_to_quad(transform, model)

Image-space corners implied by a transform, in model order.

* **Return type:**
  `ndarray`
