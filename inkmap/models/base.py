"""What a *model* is, and how it becomes pixels.

A model answers one question: **given a point in the mark's own coordinate system, is
that point foreground?** Everything else in this package -- locating, refining,
rasterising, measuring -- is written against that one question, which is why the same
machinery serves QR symbols, barcodes, printed letters and any shape a user supplies.

Model space
-----------
Each model defines its own natural units and its own extent. A QR symbol is ``N x N``
modules; a Code 128 barcode is ``n x 1`` modules wide by one unit tall; a glyph is
whatever its em-box says. Nothing outside this module needs to know which -- the
:class:`~inkmap.types.Placement` carries a homography from model space to image pixels,
and that is the only bridge required.

Why ``occupancy`` and not "give me a bitmap"
--------------------------------------------
Coverage is computed by supersampling each image pixel's footprint back into model
space. If a model can answer occupancy *analytically* -- and a QR module grid or a
barcode can -- the result is exact, limited only by the supersampling rate. Forcing
every model through a bitmap would quantise it twice: once rendering, once sampling.
Models that genuinely are rasters (a scanned logo, a rendered glyph) implement
occupancy as a lookup and lose nothing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

__all__ = ["Model", "BaseModel", "render_model"]


@runtime_checkable
class Model(Protocol):
    """The shape of a mark, in its own coordinate system.

    Implement this -- or just duck-type it -- to teach the package a new kind of mark.
    Two members are required; :meth:`render` has a working default in
    :class:`BaseModel`.
    """

    @property
    def extent(self) -> tuple[float, float]:
        """``(width, height)`` of model space, in the model's natural units."""
        ...

    @property
    def feature_size(self) -> float:
        """Size of the smallest feature that must be resolved, in model units.

        A model unit is not a feature. A QR module *is* the smallest feature, so its
        feature size is 1. But a glyph rendered onto a 512-cell raster has strokes tens
        of cells wide, and a model unit there is far smaller than anything that must be
        resolved. Whether an image can support a measurement depends on pixels per
        *feature*, not pixels per unit, so this is what makes that judgement portable
        across model kinds.

        :class:`BaseModel` estimates it from the rendered shape; grid models override
        it with the exact value.
        """
        ...

    def occupancy(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Foreground indicator at model coordinates ``(u, v)``.

        ``u`` and ``v`` are float arrays of any matching shape. Returns an array of the
        same shape, boolean or float in ``[0, 1]``. Points outside :attr:`extent` must
        return 0 -- callers rely on that to bound the mark.

        Must be vectorised: it is called with millions of points.
        """
        ...


class BaseModel:
    """Mixin supplying :meth:`render` and a :attr:`feature_size` estimate.

    Anything with ``extent`` and ``occupancy`` gets both for free.
    """

    extent: tuple[float, float]

    def occupancy(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    @property
    def feature_size(self) -> float:
        """Estimated smallest-feature size, in model units, from the rendered shape.

        Taken as twice the median distance-to-edge over foreground -- i.e. the typical
        stroke width. The median rather than the minimum, because every shape has a few
        pixels at a corner or a serif whose distance-to-edge is near zero, and letting
        those set the scale would declare every image unmeasurable.

        Cached: it costs a render, and the answer cannot change for an immutable model.
        """
        cached = getattr(self, "_feature_size", None)
        if cached is None:
            cached = estimate_feature_size(self)
            object.__setattr__(self, "_feature_size", cached)
        return cached

    def render(self, scale: float = 8.0, *, supersample: int = 4) -> np.ndarray:
        """Rasterise the model at ``scale`` pixels per model unit.

        Returns a float array in ``[0, 1]`` where 1 is foreground. Anti-aliased by
        supersampling, because the main consumer is template alignment against a
        photograph, and a hard-edged template correlates poorly with soft real edges.
        """
        return render_model(self, scale, supersample=supersample)


def estimate_feature_size(model: Model, *, target_px: int = 256) -> float:
    """Estimate a model's smallest-feature size, in model units, by rendering it.

    Renders at a resolution independent of the model's own units (so the answer does
    not depend on how finely the model happens to be discretised), then takes twice the
    median distance-to-edge over foreground as the typical stroke width.
    """
    import cv2

    width, height = model.extent
    if width <= 0 or height <= 0:
        return 1.0
    scale = target_px / max(width, height)
    raster = render_model(model, scale, supersample=1)
    binary = (raster > 0.5).astype(np.uint8)
    if not binary.any():
        return 1.0

    distances = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    interior = distances[binary.astype(bool)]
    if interior.size == 0:
        return 1.0
    stroke_px = 2.0 * float(np.median(interior))
    return max(stroke_px / scale, 1e-6)


def render_model(
    model: Model, scale: float = 8.0, *, supersample: int = 4
) -> np.ndarray:
    """Rasterise any model to a float ``[0, 1]`` array at ``scale`` px per model unit."""
    width, height = model.extent
    w = max(1, int(round(width * scale)))
    h = max(1, int(round(height * scale)))

    offsets = (np.arange(supersample) + 0.5) / supersample
    du, dv = np.meshgrid(offsets, offsets)
    du = du.ravel()[:, None]
    dv = dv.ravel()[:, None]

    cols = np.arange(w, dtype=np.float64)
    rows = np.arange(h, dtype=np.float64)
    uu, vv = np.meshgrid(cols, rows)
    u = uu.ravel()[None, :] + du  # (S2, npx)
    v = vv.ravel()[None, :] + dv
    u = u / scale
    v = v / scale

    hits = np.asarray(model.occupancy(u, v), dtype=np.float64)
    return hits.mean(axis=0).reshape(h, w).astype(np.float32)
