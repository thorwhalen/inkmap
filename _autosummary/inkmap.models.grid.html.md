# inkmap.models.grid

Models whose foreground is defined on a regular grid: QR symbols and barcodes.

Both answer occupancy by indexing, so their coverage is exact up to the supersampling
rate – there is no intermediate bitmap to quantise them twice.

### Classes

| [`MatrixModel`](#inkmap.models.grid.MatrixModel)(cells[, metadata])      | A 2-D grid of foreground/background cells -- a QR symbol's module matrix.         |
|--------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`BarsModel`](#inkmap.models.grid.BarsModel)(bars[, height, metadata]) | A 1-D run of foreground/background bars, extruded vertically -- a linear barcode. |

### *class* inkmap.models.grid.BarsModel(bars, height=20.0, metadata=dict())

Bases: [`BaseModel`](inkmap.models.base.html.md#inkmap.models.base.BaseModel)

A 1-D run of foreground/background bars, extruded vertically – a linear barcode.

`bars` is a boolean array over the narrowest module width, `True` for a bar.
Model space is `(len(bars), height)`; `height` is in the same module units, so
a 95-module EAN-13 printed twice as tall as it is wide would use `height=190`.
Height rarely matters for coverage (the pattern is constant along `v`) but it
fixes the aspect ratio for rendering and refinement.

#### *property* feature_size *: [float](https://docs.python.org/3/builtins/functions.html#float)*

One module – the narrowest bar, which is what must be resolved.

### *class* inkmap.models.grid.MatrixModel(cells, metadata=dict())

Bases: [`BaseModel`](inkmap.models.base.html.md#inkmap.models.base.BaseModel)

A 2-D grid of foreground/background cells – a QR symbol’s module matrix.

`cells[row, col]` is `True` where the cell is foreground. Model space is
`(n_cols, n_rows)` in cells, origin at the mark’s own top-left, so cell
`(i, j)` occupies `u in [j, j+1)`, `v in [i, i+1)`.

Also serves Data Matrix, Aztec, and any other matrix symbology: only the cell
grid matters here, not how it was decoded.

#### *property* feature_size *: [float](https://docs.python.org/3/builtins/functions.html#float)*

One cell – for a matrix symbology the cell *is* the smallest feature.
