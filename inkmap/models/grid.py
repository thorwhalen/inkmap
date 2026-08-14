"""Models whose foreground is defined on a regular grid: QR symbols and barcodes.

Both answer occupancy by indexing, so their coverage is exact up to the supersampling
rate -- there is no intermediate bitmap to quantise them twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .base import BaseModel

__all__ = ["MatrixModel", "BarsModel"]


@dataclass
class MatrixModel(BaseModel):
    """A 2-D grid of foreground/background cells -- a QR symbol's module matrix.

    ``cells[row, col]`` is ``True`` where the cell is foreground. Model space is
    ``(n_cols, n_rows)`` in cells, origin at the mark's own top-left, so cell
    ``(i, j)`` occupies ``u in [j, j+1)``, ``v in [i, i+1)``.

    Also serves Data Matrix, Aztec, and any other matrix symbology: only the cell
    grid matters here, not how it was decoded.
    """

    cells: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cells = np.asarray(self.cells, dtype=bool)
        if self.cells.ndim != 2:
            raise ValueError(f"cells must be 2-D, got shape {self.cells.shape}")

    @property
    def extent(self) -> tuple[float, float]:
        return float(self.cells.shape[1]), float(self.cells.shape[0])

    @property
    def feature_size(self) -> float:
        """One cell -- for a matrix symbology the cell *is* the smallest feature."""
        return 1.0

    @property
    def n_rows(self) -> int:
        return int(self.cells.shape[0])

    @property
    def n_cols(self) -> int:
        return int(self.cells.shape[1])

    def occupancy(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        rows, cols = self.cells.shape
        iu = np.floor(np.nan_to_num(u, nan=-1.0)).astype(np.int64)
        iv = np.floor(np.nan_to_num(v, nan=-1.0)).astype(np.int64)
        inside = (iu >= 0) & (iu < cols) & (iv >= 0) & (iv < rows)
        np.clip(iu, 0, cols - 1, out=iu)
        np.clip(iv, 0, rows - 1, out=iv)
        return np.where(inside, self.cells[iv, iu], False)


@dataclass
class BarsModel(BaseModel):
    """A 1-D run of foreground/background bars, extruded vertically -- a linear barcode.

    ``bars`` is a boolean array over the narrowest module width, ``True`` for a bar.
    Model space is ``(len(bars), height)``; ``height`` is in the same module units, so
    a 95-module EAN-13 printed twice as tall as it is wide would use ``height=190``.
    Height rarely matters for coverage (the pattern is constant along ``v``) but it
    fixes the aspect ratio for rendering and refinement.
    """

    bars: np.ndarray
    height: float = 20.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.bars = np.asarray(self.bars, dtype=bool).ravel()
        if self.bars.size == 0:
            raise ValueError("bars must be non-empty")

    @property
    def extent(self) -> tuple[float, float]:
        return float(self.bars.size), float(self.height)

    @property
    def feature_size(self) -> float:
        """One module -- the narrowest bar, which is what must be resolved."""
        return 1.0

    def occupancy(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        n = self.bars.size
        iu = np.floor(np.nan_to_num(u, nan=-1.0)).astype(np.int64)
        inside = (iu >= 0) & (iu < n) & (v >= 0) & (v < self.height)
        np.clip(iu, 0, n - 1, out=iu)
        return np.where(inside, self.bars[iu], False)
