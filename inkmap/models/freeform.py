"""Models for shapes that are not on a grid: rasters, polygons, and text.

These are the escape hatches. Anything you can draw, scan, or describe as outlines
becomes a model here, and the rest of the package treats it exactly like a QR symbol.

:class:`PolygonModel` is the only *exact* one -- a point-in-polygon test has no
resolution. :class:`RasterModel` quantises to its own grid, so give it enough
resolution: its cells should be several times smaller than an image pixel maps to,
or the raster's own edges become the accuracy limit rather than the photograph's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from .base import BaseModel

__all__ = ["RasterModel", "PolygonModel", "GlyphModel", "text_model"]


@dataclass
class RasterModel(BaseModel):
    """Foreground given as an image: a logo, a scan, a pre-rendered glyph.

    ``mask`` may be boolean or float in ``[0, 1]``; float is respected, so an
    anti-aliased source keeps its soft edges. Model space is ``(width, height)`` in
    raster cells.
    """

    mask: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        mask = np.asarray(self.mask)
        if mask.ndim == 3:
            mask = mask.mean(axis=2)
        if mask.ndim != 2:
            raise ValueError(f"mask must be 2-D, got shape {mask.shape}")
        if mask.dtype == bool:
            self.mask = mask.astype(np.float32)
        else:
            mask = mask.astype(np.float32)
            hi = float(mask.max())
            self.mask = mask / hi if hi > 1.0 else mask

    @property
    def extent(self) -> tuple[float, float]:
        return float(self.mask.shape[1]), float(self.mask.shape[0])

    def occupancy(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        rows, cols = self.mask.shape
        iu = np.floor(np.nan_to_num(u, nan=-1.0)).astype(np.int64)
        iv = np.floor(np.nan_to_num(v, nan=-1.0)).astype(np.int64)
        inside = (iu >= 0) & (iu < cols) & (iv >= 0) & (iv < rows)
        np.clip(iu, 0, cols - 1, out=iu)
        np.clip(iv, 0, rows - 1, out=iv)
        return np.where(inside, self.mask[iv, iu], 0.0)


@dataclass
class PolygonModel(BaseModel):
    """Foreground as closed outlines, with holes -- the exact case.

    ``polygons`` is a sequence of ``(N, 2)`` float arrays of ``(u, v)`` vertices. Use
    the even-odd rule: a polygon inside another cuts a hole, which is what letters like
    'o' and 'B' need. No resolution is involved, so coverage error is limited only by
    the supersampling rate.
    """

    polygons: Sequence[np.ndarray]
    extent_override: tuple[float, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.polygons = [
            np.asarray(p, dtype=np.float64).reshape(-1, 2) for p in self.polygons
        ]
        if not self.polygons:
            raise ValueError("need at least one polygon")

    @property
    def extent(self) -> tuple[float, float]:
        if self.extent_override is not None:
            return self.extent_override
        allpts = np.vstack(self.polygons)
        return float(allpts[:, 0].max()), float(allpts[:, 1].max())

    def occupancy(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Even-odd crossing test, vectorised over all points and all edges."""
        shape = np.shape(u)
        pu = np.asarray(u, dtype=np.float64).ravel()
        pv = np.asarray(v, dtype=np.float64).ravel()
        inside = np.zeros(pu.shape, dtype=bool)

        for poly in self.polygons:
            x0, y0 = poly[:, 0], poly[:, 1]
            x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
            for a0, b0, a1, b1 in zip(x0, y0, x1, y1):
                if b0 == b1:
                    continue
                crosses = (b0 > pv) != (b1 > pv)
                if not crosses.any():
                    continue
                t = (pv - b0) / (b1 - b0)
                xint = a0 + t * (a1 - a0)
                inside ^= crosses & (pu < xint)
        return inside.reshape(shape)


@dataclass
class GlyphModel(BaseModel):
    """A run of printed text, rendered once at high resolution.

    Text is a raster problem in practice: fonts are outlines, but hinting, kerning and
    anti-aliasing mean the printed shape is what the renderer produced, not the ideal
    outline. So this renders through PIL at a resolution well above the photograph's
    and treats the result as a :class:`RasterModel`.

    Requires Pillow, and a font file for anything but the (very coarse) PIL default --
    pass ``font_path``. Model space is the rendered pixel grid.
    """

    text: str
    font_path: str | None = None
    font_size: int = 256
    padding: int = 8
    metadata: dict[str, Any] = field(default_factory=dict)
    _raster: RasterModel | None = field(default=None, repr=False, init=False)

    def __post_init__(self) -> None:
        self._raster = RasterModel(self._render_text())

    def _render_text(self) -> np.ndarray:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "GlyphModel needs Pillow -- pip install 'inkmap[text]'"
            ) from exc

        if self.font_path:
            font = ImageFont.truetype(self.font_path, self.font_size)
        else:
            try:
                font = ImageFont.load_default(size=self.font_size)
            except TypeError:  # Pillow < 9.2 has no size argument
                font = ImageFont.load_default()

        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        left, top, right, bottom = probe.textbbox((0, 0), self.text, font=font)
        w = max(1, right - left) + 2 * self.padding
        h = max(1, bottom - top) + 2 * self.padding

        image = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(image)
        draw.text(
            (self.padding - left, self.padding - top), self.text, fill=255, font=font
        )
        return np.asarray(image, dtype=np.float32) / 255.0

    @property
    def extent(self) -> tuple[float, float]:
        return self._raster.extent

    @property
    def feature_size(self) -> float:
        """Typical stroke width of the rendered text, in raster cells."""
        return self._raster.feature_size

    def occupancy(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        return self._raster.occupancy(u, v)


def text_model(text: str, **kwargs: Any) -> GlyphModel:
    """Convenience constructor for :class:`GlyphModel`."""
    return GlyphModel(text=text, **kwargs)
