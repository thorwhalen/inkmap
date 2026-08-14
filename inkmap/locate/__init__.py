"""Locators: finding where a model sits in an image.

A locator is a plain function ``(bgr, gray) -> list[Placement]``, so registering your
own needs no subclassing:

    from inkmap import locate

    locate.LOCATORS["mine"] = my_locator
    inkmap.find_all(photo, locators=["mine", "qr_zxing"])

For the many cases where the mark cannot be auto-detected -- a letter, a logo, a shape
with no decoder in the world -- :func:`place` is the universal entry point: you supply
the model and where its corners are, and the rest of the package proceeds identically.
That is the seam that makes this work for "anything the user provides a model for".
"""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

import numpy as np

from .. import config, geometry
from ..models import Model
from ..types import Placement
from .barcode import locate_barcode_zxing
from .qr import locate_qr_aruco, locate_qr_opencv, locate_qr_zxing

Locator = Callable[[np.ndarray, np.ndarray], list[Placement]]

__all__ = [
    "LOCATORS",
    "Locator",
    "locate",
    "place",
    "locate_qr_opencv",
    "locate_qr_aruco",
    "locate_qr_zxing",
    "locate_barcode_zxing",
]

#: Registry of locator strategies. Add your own: ``LOCATORS["mine"] = my_locator``.
LOCATORS: dict[str, Locator] = {
    "qr_zxing": locate_qr_zxing,
    "qr_aruco": locate_qr_aruco,
    "qr_opencv": locate_qr_opencv,
    "barcode_zxing": locate_barcode_zxing,
}


def place(
    model: Model,
    quad,
    *,
    inclusive_pixel_corners: bool = False,
    locator: str = "manual",
    **metadata,
) -> Placement:
    """Place a model at a known quadrilateral -- the universal escape hatch.

    ``quad`` is four ``(x, y)`` image points in the *model's* own corner order: the
    point corresponding to model-space ``(0, 0)`` first, then clockwise. Order matters
    and is not inferred: sorting corners by image position silently mislabels them once
    the mark is rotated past 45 degrees.

    Use this for anything without a decoder -- printed letters, logos, engraved marks --
    or when you already know where the mark is and only want the coverage machinery.
    """
    quad = np.asarray(quad, dtype=np.float32).reshape(4, 2)
    return Placement(
        model=model,
        transform=geometry.quad_to_transform(
            quad, model, inclusive_pixel_corners=inclusive_pixel_corners
        ),
        quad=quad,
        locator=locator,
        metadata=dict(metadata),
    )


def locate(
    bgr: np.ndarray,
    gray: np.ndarray,
    *,
    locators: Sequence[str | Locator] = config.DEFAULT_LOCATORS,
    first_hit: bool = False,
) -> list[Placement]:
    """Run locator strategies and merge their results, de-duplicating by position.

    Strategies are tried in order. With ``first_hit=True`` the cascade stops at the
    first strategy that finds anything -- cheaper, and usually right when you know there
    is one mark. Otherwise every strategy runs and results merge, which is what earns
    the recall when an image holds several marks that no single detector finds all of.
    """
    found: list[Placement] = []
    for spec in locators:
        fn = LOCATORS[spec] if isinstance(spec, str) else spec
        try:
            placements = fn(bgr, gray)
        except Exception:
            continue
        for placement in placements:
            if not _duplicate(placement, found):
                found.append(placement)
        if first_hit and found:
            break
    return found


def _duplicate(candidate: Placement, existing: Iterable[Placement]) -> bool:
    """Two placements are the same mark if their centres are within half a span."""
    c = candidate.quad.mean(axis=0)
    span = float(np.linalg.norm(candidate.quad[2] - candidate.quad[0]))
    return any(
        float(np.linalg.norm(other.quad.mean(axis=0) - c)) < span * 0.5
        for other in existing
    )
