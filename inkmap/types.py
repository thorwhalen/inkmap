"""The data types the whole package speaks in.

Naming here is deliberate, because the obvious names are traps:

* The two classes inside a mark's footprint are ``FOREGROUND`` and ``BACKGROUND``,
  **not** dark and light. Dark/light describe *appearance*, and appearance inverts:
  white-on-black print, reflectance-reversed symbols (explicitly permitted by ISO/IEC
  18004 for QR), and any inverted imaging modality all swap which class is dark. A
  ``dark_mask`` would then silently mean foreground in one image and background in the
  next. :class:`Polarity` carries that mapping explicitly instead.
* ``BACKGROUND`` is scoped to *within the mark's footprint*. The clear margin around
  the mark is ``MARGIN`` and everything else is ``OUTSIDE``, so the ambiguity that
  makes a bare "background" dangerous -- substrate inside the mark, or everything that
  is not the mark? -- cannot arise.
* The continuous value is ``coverage``, after ISO 12647-2:2013 3.1 *area coverage*,
  "ratio of the area covered with ink to the entire area" -- the only term in any
  standard whose definition is literally the quantity computed here.

See ``docs/terminology.md`` for the full cross-field mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import numpy as np

from .models import Model


class Region(IntEnum):
    """Four-way pixel classification.

    Not a matting *trimap*: a trimap's third class is "unknown/undecided", whereas
    every class here is a decided statement about location.
    """

    OUTSIDE = 0
    """Outside the mark and its margin."""

    MARGIN = 1
    """The clear surround a mark is specified to have -- a QR quiet zone, a barcode
    light margin, the whitespace around a glyph. Guaranteed background, contiguous, and
    free of edge effects from neighbouring foreground, which often makes it a better
    reference region than the background *inside* the mark."""

    BACKGROUND = 2
    """Bare substrate within the mark's footprint."""

    FOREGROUND = 3
    """The mark itself -- printed ink, toner, engraving, whatever laid it down."""


class Polarity(IntEnum):
    """Which apparent-brightness state the foreground corresponds to.

    Carried explicitly so that no appearance word ever has to stand in for a physical
    class. Flipping this is the supported way to handle inverted print and inverted
    imaging, rather than inverting masks at the call site.
    """

    FOREGROUND_IS_DARK = 0
    """The usual case: ink absorbs, so the mark reads darker than the substrate."""

    FOREGROUND_IS_LIGHT = 1
    """Reversed: the mark reads brighter than the substrate."""

    def foreground_is_dark(self) -> bool:
        return self is Polarity.FOREGROUND_IS_DARK


@dataclass(frozen=True)
class Placement:
    """A located instance of a model: which shape, and where it sits in the image.

    ``transform`` is the bridge the whole package is built on -- a 3x3 homography from
    *model space* (the model's own units, origin at its top-left) to image pixels. The
    quad is just its image under that transform, kept for convenience.
    """

    model: Model
    transform: np.ndarray
    """(3, 3) float64, model coordinates -> image pixels."""

    quad: np.ndarray
    """(4, 2) float32 image-space corners of the model's extent, in the *model's* own
    order (its top-left first), not re-sorted into image order. Re-sorting by
    coordinate sum/difference -- a common idiom -- silently mislabels corners once the
    mark is rotated past 45 degrees, which rotates the model and corrupts every derived
    mask while leaving it looking plausible."""

    locator: str = ""
    """Which locator strategy produced this."""

    payload: str | None = None
    """Decoded content, when the locator happened to decode something. Never required:
    decoding is not the point, and a barely-deposited mark may locate but not decode."""

    refined: bool = False
    score: float | None = None
    """Alignment score from refinement, if it ran. A proxy for geometric fit quality."""

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def units_per_pixel(self) -> float:
        """Model units spanned by one image pixel, averaged over the two axes."""
        return 1.0 / max(self.pixels_per_unit, 1e-12)

    @property
    def pixels_per_feature(self) -> float:
        """Image pixels across the model's smallest feature.

        **This** is the resolution figure that governs whether a trustworthy
        measurement is possible -- not :attr:`pixels_per_unit`. A model unit is not a
        feature: a QR module is both, but a glyph rendered onto a 512-cell raster has
        strokes tens of cells wide, so pixels-per-unit there would understate the real
        resolution by that factor and declare every image unmeasurable.
        """
        return self.pixels_per_unit * float(getattr(self.model, "feature_size", 1.0))

    @property
    def pixels_per_unit(self) -> float:
        """Image pixels per model unit.

        For a QR symbol a "unit" is one module; for a barcode, one narrow bar; for a
        raster model, one raster cell. Use :attr:`pixels_per_feature` to reason about
        whether the image resolves the mark.
        """
        width, height = self.model.extent
        q = self.quad
        top = float(np.linalg.norm(q[1] - q[0]))
        bottom = float(np.linalg.norm(q[2] - q[3]))
        left = float(np.linalg.norm(q[3] - q[0]))
        right = float(np.linalg.norm(q[2] - q[1]))
        scales = []
        if width > 0:
            scales += [top / width, bottom / width]
        if height > 0:
            scales += [left / height, right / height]
        return float(np.mean(scales)) if scales else 0.0


@dataclass
class InkMap:
    """Per-pixel foreground coverage for one placement, plus the geometry it came from.

    ``coverage`` is *geometric* area coverage: the fraction of each pixel's area lying
    under foreground. It is not an optical/reflectance-derived coverage (which lateral
    light scattering in the substrate inflates -- the Murray-Davies/Yule-Nielsen
    effect), and it is not a probability. See :meth:`confidence` for that.
    """

    coverage: np.ndarray
    """(H, W) float32 in [0, 1]. Zero outside the mark."""

    region: np.ndarray
    """(H, W) uint8 of :class:`Region` values."""

    placement: Placement
    polarity: Polarity = Polarity.FOREGROUND_IS_DARK

    weight: np.ndarray | None = None
    """(H, W) float32 in [0, 1] -- the blur-aware measurement weight, and the **only**
    channel that should gate a physical measurement. Coverage is geometric and ignores
    the point spread function; confidence is epistemic and says nothing about
    partial-area contamination. See :func:`inkmap.coverage.measurement_weight`."""

    blur_sigma: float | None = None
    """Estimated image blur (px). ``nan`` means estimation failed -- typically because
    the modelled shape and the photograph do not correspond."""

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def model(self) -> Model:
        return self.placement.model

    # -- masks --------------------------------------------------------------- #

    def foreground_mask(self, *, threshold: float = 0.5) -> np.ndarray:
        """Boolean foreground mask by thresholding coverage. Fine for display and
        labelling; for anything photometric use :func:`inkmap.measurement_mask`
        instead, which accounts for blur."""
        return self.coverage >= threshold

    def background_mask(self, *, threshold: float = 0.5) -> np.ndarray:
        """Bare-substrate pixels within the mark's footprint (not the margin)."""
        return (self.region == Region.BACKGROUND) & (self.coverage < threshold)

    def inside_mask(self, *, margin: bool = False) -> np.ndarray:
        """Every pixel within the mark's footprint. With ``margin=True``, include the
        clear surround as well."""
        inside = (self.region == Region.FOREGROUND) | (self.region == Region.BACKGROUND)
        if margin:
            inside |= self.region == Region.MARGIN
        return inside

    def margin_mask(self) -> np.ndarray:
        """The clear surround -- an alternative reference region."""
        return self.region == Region.MARGIN

    def __array__(self, dtype=None):
        """``np.asarray(ink_map)`` gives the coverage map -- usually what you want."""
        return self.coverage.astype(dtype) if dtype else self.coverage
