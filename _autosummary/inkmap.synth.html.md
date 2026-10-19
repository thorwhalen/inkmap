# inkmap.synth

Synthetic scenes with exact ground truth.

Real photographs cannot validate a coverage map. Nobody can hand-label what fraction of
a pixel is foreground, and no public dataset carries per-pixel coverage ground truth for
printed marks – the document-binarisation benchmarks (DIBCO) are binary. So the only
way to measure whether a 0..1 output is *right* is to render scenes whose true coverage
is known analytically.

The trick that makes it exact: render the image *from* the coverage map. Supersample the
model through a known transform to get true coverage, then form the clean image as
`255 * (1 - coverage)`. Ground truth and stimulus are the same object by construction,
and any degradation applied afterwards (blur, noise, gradient, glare, JPEG) leaves the
ground truth correct.

Works for any model, so a text or logo pipeline is validated the same way as a QR one.
Real photographs remain essential for *detection* rate – see [`inkmap.corpus`](inkmap.corpus.html.md#module-inkmap.corpus).

### Functions

| [`render`](#inkmap.synth.render)([model, size, pixels_per_unit, ...])      | Render one synthetic photograph of `model` with exact ground-truth coverage.                                           |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| [`qr_model`](#inkmap.synth.qr_model)([payload, error])                       | A QR [`MatrixModel`](inkmap.models.html.md#inkmap.models.MatrixModel), from `payload` via segno. |
| [`default_matrix`](#inkmap.synth.default_matrix)()                                 | The shipped QR module matrix (a real version-3 symbol), True = dark module.                                            |
| [`degrade`](#inkmap.synth.degrade)(image, \*[, blur, noise, gradient, ...]) | Apply a capture-order degradation chain to a float image, returning uint8.                                             |
| [`nested_square`](#inkmap.synth.nested_square)(side[, rings])                     | A square mark as a `(side, side)` cell grid: foreground, then alternating rings.                                       |
| [`mark_sheet`](#inkmap.synth.mark_sheet)()                                     | A card of square registration marks, and where each one's centre truly is.                                             |

### Classes

| [`Scene`](#inkmap.synth.Scene)(image, coverage, transform, model[, ...])   | A synthetic image together with the truth used to make it.   |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------------|

### *class* inkmap.synth.Scene(image, coverage, transform, model, params=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A synthetic image together with the truth used to make it.

#### coverage *: ndarray*

(H, W) float32 exact foreground area coverage.

#### image *: ndarray*

(H, W) uint8 grayscale.

#### transform *: ndarray*

(3, 3) true model -> image mapping.

### inkmap.synth.default_matrix()

The shipped QR module matrix (a real version-3 symbol), True = dark module.

Shipped so that [`render()`](#inkmap.synth.render) – and therefore the test suite and every example –
works on a bare `pip install inkmap`, with no optional dependency.

* **Return type:**
  `ndarray`

### inkmap.synth.degrade(image, , blur=0.0, noise=0.0, gradient=0.0, glare=0.0, jpeg_quality=None, rng=None)

Apply a capture-order degradation chain to a float image, returning uint8.

* **Return type:**
  `ndarray`

### inkmap.synth.mark_sheet()

A card of square registration marks, and where each one’s centre truly is.

Three bullseyes and a solid square at the corners, as on an OMR form, and two QR
finder patterns inside: 700 x 500 cells, marks 50 cells (42 for a finder). Render it
with [`render()`](#inkmap.synth.render) at about 1.2 pixels per cell for ~60 px marks. Returns
`(model, truth)`, `truth` being `(centre_uv, rings)` per mark in model units,
so `cv2.perspectiveTransform` through a scene’s transform gives the true image
centres.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`MatrixModel`](inkmap.models.grid.html.md#inkmap.models.grid.MatrixModel), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)]]]

### inkmap.synth.nested_square(side, rings=())

A square mark as a `(side, side)` cell grid: foreground, then alternating rings.

`rings` are the sides of the nested squares as fractions of `side`, outermost
first, alternating background and foreground. Each must leave an equal whole number
of cells on both sides, or the mark would be off-centre – that is an error.

```pycon
>>> nested_square(7, (5 / 7, 3 / 7)).astype(int)[3]
array([1, 0, 1, 1, 1, 0, 1])
```

* **Return type:**
  `ndarray`

### inkmap.synth.qr_model(payload=None, , error='m')

A QR [`MatrixModel`](inkmap.models.html.md#inkmap.models.MatrixModel), from `payload` via segno.

With no payload, uses the shipped matrix and needs no dependency. Uses
`segno.make_qr` rather than `segno.make`: the latter may return a Micro QR for
short payloads, a different symbology with different module counts.

* **Return type:**
  [`MatrixModel`](inkmap.models.grid.html.md#inkmap.models.grid.MatrixModel)

### inkmap.synth.render(model=None, , size=800, pixels_per_unit=10.0, perspective=0.0, rotation=0.0, blur=0.0, noise=0.0, gradient=0.0, glare=0.0, jpeg_quality=None, samples=8, rng=None)

Render one synthetic photograph of `model` with exact ground-truth coverage.

Degradations are applied in capture order – geometry, then optics (blur, glare),
then illumination, then sensor noise, then compression – because any other order
models a camera that does not exist. `perspective` jitters the four corners by
that fraction of the mark’s span; `rotation` is in degrees; `gradient` is the
fractional illumination falloff across the frame.

* **Return type:**
  [`Scene`](#inkmap.synth.Scene)
