"""Shape models: what the foreground is expected to look like.

A model is anything that can answer :meth:`~inkmap.models.base.Model.occupancy` -- is
this point in the mark's own coordinate system foreground? -- plus report its
:attr:`~inkmap.models.base.Model.extent`. That is the whole contract, and it is what
lets one pipeline serve QR symbols, barcodes, printed letters and arbitrary artwork.

    from inkmap import models

    models.MatrixModel(cells)          # QR, Data Matrix, Aztec: a grid of cells
    models.BarsModel(bars)             # EAN, Code 128, ...: a run of bars
    models.RasterModel(mask)           # a logo, a scan, anything you can draw
    models.PolygonModel(outlines)      # exact vector outlines, holes included
    models.GlyphModel("ABC")           # printed text, rendered via Pillow

Anything duck-typed to the same two members works just as well -- there is no base
class to inherit and no registration step.
"""

from .base import BaseModel, Model, render_model
from .freeform import GlyphModel, PolygonModel, RasterModel, text_model
from .grid import BarsModel, MatrixModel

__all__ = [
    "Model",
    "BaseModel",
    "render_model",
    "MatrixModel",
    "BarsModel",
    "RasterModel",
    "PolygonModel",
    "GlyphModel",
    "text_model",
]
