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

from dataclasses import replace
from typing import Callable, Iterable, Sequence

import cv2
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
    "validated_scale",
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
    scale: float | None = None,
    full_res_retry: bool = True,
) -> list[Placement]:
    """Run locator strategies and merge their results, de-duplicating by position.

    Strategies are tried in order. With ``first_hit=True`` the cascade stops at the
    first strategy that finds anything -- cheaper, and usually right when you know there
    is one mark. Otherwise every strategy runs and results merge, which is what earns
    the recall when an image holds several marks that no single detector finds all of.

    **Coarse-to-fine.** ``scale`` (``0 < scale <= 1``) runs the cascade on a copy of the
    frame downscaled by that factor (``cv2.INTER_AREA``), then maps every placement back
    to full-resolution pixels. Locating costs roughly in proportion to pixel count, so
    on a 4000 x 3000 photograph 0.5 is about 4x faster and 0.35 about 7x. ``None`` (the
    default) or ``1`` locate at full resolution, exactly as without the argument.

    Every locator -- a registered name or your own callable -- is handed the
    *downscaled* ``bgr`` and ``gray`` (and, on a retry, a full-resolution crop), and
    must return placements in the coordinates of the frame it was given; mapping them
    back to the full frame is done here. A locator that bakes in absolute pixel sizes
    or positions will misbehave under ``scale``.

    The mapping is one affine ``A`` (small -> full pixels), in the pixel-centre
    convention ``cv2.resize`` uses, ``x_full = (x_small + 0.5) / scale - 0.5``, applied
    to both ``quad`` and ``transform`` (``A @ transform``). Locator name and payload are
    kept; ``metadata["locate_scale"]`` records the scale used. Corner conventions differ
    by locator (OpenCV's are inclusive pixel indices, zxing's are the continuous outer
    boundary), so a locator's own half-pixel bias is magnified by ``1 / scale`` on the
    way up -- a pixel or so at 0.5. That does not matter downstream when
    :func:`inkmap.analyze` refines (its default), which pins the transform to sub-pixel
    accuracy at full resolution anyway.

    **The model is the fragile part, not the geometry.** Locators read the model off
    the frame they are given -- a QR's module count and module matrix, a barcode's bar
    pattern -- and refinement cannot repair a wrong model, it only fits its geometry.
    Below about ``config.MIN_COARSE_PIXELS_PER_FEATURE`` (4) pixels per module in the
    downscaled frame those reads go wrong while the code still decodes: a 25 x 25 QR
    read as 21 x 21, or tens of flipped modules. So, with ``full_res_retry`` (default
    on; only meaningful with ``scale < 1``), a coarse placement is re-located on a
    padded full-resolution crop around it when either its ``payload`` is ``None`` (found
    but not decoded -- typically a small, far-away code) or its pixels per feature in
    the downscaled frame are under that floor. The full-resolution result replaces it
    (``metadata["locate_retry"]`` names the reason, ``"undecoded"`` or
    ``"undersampled"``, and ``locate_scale`` becomes 1.0). Crops are small, so this
    costs little; pick ``scale`` so your codes clear the floor (at 0.5, 8 px per module
    at full resolution) and it never triggers. A coarse placement under the floor that
    is kept anyway -- ``full_res_retry=False``, or the crop found nothing -- carries
    ``metadata["locate_undersampled"] = True``: treat its model as unreliable. A mark
    the coarse pass misses entirely is not recovered: lower the downscaling instead.
    """
    scale = validated_scale(scale)
    if scale is None:
        return _locate_at(bgr, gray, locators=locators, first_hit=first_hit)

    height, width = gray.shape[:2]
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    small_bgr = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
    small_gray = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
    up = _upscaling(size[0] / width, size[1] / height)

    coarse = _locate_at(small_bgr, small_gray, locators=locators, first_hit=first_hit)
    out = []
    for small in coarse:
        reason = _retry_reason(small)
        placement = _mapped(small, up, locate_scale=scale)
        retried = None
        if reason is not None and full_res_retry:
            retried = _retry_at_full_resolution(
                placement, bgr, gray, locators=locators, first_hit=first_hit
            )
        if retried is not None:
            placement = replace(
                retried, metadata={**retried.metadata, "locate_retry": reason}
            )
        elif reason == "undersampled":
            placement = replace(
                placement, metadata={**placement.metadata, "locate_undersampled": True}
            )
        out.append(placement)
    return out


def _retry_reason(
    small: Placement,
    *,
    min_pixels_per_feature: float = config.MIN_COARSE_PIXELS_PER_FEATURE,
) -> str | None:
    """Why a coarse placement (in downscaled pixels) should be re-located, if at all.

    Undersampling is checked before decoding because it is the silent failure: an
    undecoded code is visibly incomplete, an undersampled one decodes fine and carries
    a wrong model.
    """
    if small.pixels_per_feature < min_pixels_per_feature:
        return "undersampled"
    if small.payload is None:
        return "undecoded"
    return None


def validated_scale(scale: float | None) -> float | None:
    """Check a locate scale; ``None`` means full resolution (and so does ``1``)."""
    if scale is None:
        return None
    try:
        value = float(scale)
    except (TypeError, ValueError):
        raise ValueError(
            f"scale must be a number in (0, 1] or None, got {scale!r}"
        ) from None
    if not 0.0 < value <= 1.0:  # also rejects nan
        raise ValueError(
            f"scale must be in (0, 1] -- the downscaling factor for a coarse locate, "
            f"e.g. 0.5 -- or None for full resolution; got {scale!r}"
        )
    return None if value == 1.0 else value


def _locate_at(bgr, gray, *, locators, first_hit) -> list[Placement]:
    """The cascade itself, at whatever resolution it is handed."""
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


def _upscaling(sx: float, sy: float) -> np.ndarray:
    """Affine from downscaled to full-resolution pixels, pixel-centre convention.

    ``cv2.resize`` aligns pixel centres: small pixel ``i`` covers full-resolution
    ``[i / s, (i + 1) / s)`` in edge coordinates, so its centre ``i`` maps to
    ``(i + 0.5) / s - 0.5``.
    """
    return np.array(
        [
            [1.0 / sx, 0.0, 0.5 / sx - 0.5],
            [0.0, 1.0 / sy, 0.5 / sy - 0.5],
            [0.0, 0.0, 1.0],
        ]
    )


def _mapped(placement: Placement, affine: np.ndarray, **metadata) -> Placement:
    """``placement`` carried through an image-space affine (both quad and transform)."""
    transform = affine @ np.asarray(placement.transform, dtype=np.float64)
    transform = transform / transform[2, 2]
    quad = (
        np.asarray(placement.quad, dtype=np.float64) @ affine[:2, :2].T + affine[:2, 2]
    )
    return replace(
        placement,
        transform=transform,
        quad=quad.astype(np.float32),
        metadata={**placement.metadata, **metadata},
    )


def _retry_at_full_resolution(
    placement: Placement,
    bgr: np.ndarray,
    gray: np.ndarray,
    *,
    locators,
    first_hit: bool,
    padding: float = config.LOCATE_RETRY_PADDING,
) -> Placement | None:
    """Re-locate a coarse placement on a full-resolution crop around it.

    Returns the full-resolution placement of the same mark (preferring a decoded one),
    in full-image coordinates, or ``None`` if the crop yields nothing there.
    """
    height, width = gray.shape[:2]
    lo, hi = placement.quad.min(axis=0), placement.quad.max(axis=0)
    pad = padding * float(max(hi - lo))
    x0, y0 = (max(0, int(np.floor(v - pad))) for v in lo)
    x1 = min(width, int(np.ceil(hi[0] + pad)) + 1)
    y1 = min(height, int(np.ceil(hi[1] + pad)) + 1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None

    found = _locate_at(
        np.ascontiguousarray(bgr[y0:y1, x0:x1]),
        np.ascontiguousarray(gray[y0:y1, x0:x1]),
        locators=locators,
        first_hit=first_hit,
    )
    shift = np.array([[1.0, 0.0, x0], [0.0, 1.0, y0], [0.0, 0.0, 1.0]])
    same_mark = [
        candidate
        for candidate in (_mapped(p, shift, locate_scale=1.0) for p in found)
        if _duplicate(candidate, [placement])
    ]
    if not same_mark:
        return None
    centre = placement.quad.mean(axis=0)
    return min(
        same_mark,
        key=lambda c: (
            c.payload is None,
            float(np.linalg.norm(c.quad.mean(axis=0) - centre)),
        ),
    )


def _duplicate(candidate: Placement, existing: Iterable[Placement]) -> bool:
    """Two placements are the same mark if their centres are within half a span."""
    c = candidate.quad.mean(axis=0)
    span = float(np.linalg.norm(candidate.quad[2] - candidate.quad[0]))
    return any(
        float(np.linalg.norm(other.quad.mean(axis=0) - c)) < span * 0.5
        for other in existing
    )
