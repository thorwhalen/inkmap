"""Locating linear (1-D) barcodes.

Geometry comes from zxing-cpp, which handles EAN-13/8, UPC-A/E, Code 128, Code 39,
Code 93, ITF, Codabar and DataBar. The *bar pattern* is then read off the image rather
than re-encoded from the decoded text, for the same reason as QR: encoders make choices
(Code 128 code-set switching, check-digit placement, ITF padding) that the decoded
string does not pin down, so re-encoding can silently produce a different pattern.

Reading it from the image needs the module width -- the narrowest bar. That is
estimated from the run lengths of the thresholded profile, which is what a real decoder
does, and it is the one number that turns a picture of stripes into a model.
"""

from __future__ import annotations

import cv2
import numpy as np

from .. import geometry
from ..models import BarsModel
from ..types import Placement

__all__ = ["locate_barcode_zxing", "profile_to_bars"]

#: Linear symbologies we know how to model. Matrix symbologies are handled elsewhere.
LINEAR_FORMATS = {
    "ean13",
    "ean8",
    "upca",
    "upce",
    "code128",
    "code39",
    "code93",
    "codabar",
    "itf",
    "databar",
    "databarexpanded",
}


def _sample_profile(
    gray: np.ndarray, quad: np.ndarray, *, width: int, rows: int = 16
) -> np.ndarray:
    """Average the mark's interior into a 1-D intensity profile along its long axis.

    Averaging over the bar height is what makes this robust: a scratch or a printed
    digit crossing one scan line is diluted, whereas a single scan line would be
    corrupted by it.
    """
    dst = np.array([[0, 0], [width, 0], [width, rows], [0, rows]], dtype=np.float32)
    warp = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    strip = cv2.warpPerspective(gray, warp, (width, rows), flags=cv2.INTER_AREA)
    # Trim the top and bottom eighth: quiet-zone bleed and human-readable digits live
    # at the edges of a barcode's bounding quad.
    cut = max(1, rows // 8)
    return strip[cut:-cut].mean(axis=0)


def profile_to_bars(profile: np.ndarray) -> tuple[np.ndarray, float] | None:
    """Quantise a 1-D profile into a bar pattern.

    Returns ``(bars, module_px)`` where ``bars`` is boolean over module positions and
    ``module_px`` is the estimated narrowest-bar width in profile samples. Thresholds at
    the midpoint of the profile's range, per ISO/IEC 15416 3.5, then takes the module
    width as a low percentile of run lengths -- low rather than the minimum, because a
    single noisy sample creates a spurious one-sample run.
    """
    if profile.size < 8:
        return None
    lo, hi = float(np.percentile(profile, 2)), float(np.percentile(profile, 98))
    if hi - lo < 1e-6:
        return None
    dark = profile < (lo + hi) / 2.0

    changes = np.flatnonzero(np.diff(dark.astype(np.int8))) + 1
    edges = np.concatenate([[0], changes, [dark.size]])
    runs = np.diff(edges)
    if runs.size < 3:
        return None

    module_px = float(np.percentile(runs, 10))
    if module_px < 1.0:
        module_px = float(runs.min())
    if module_px < 1.0:
        return None

    n_modules = int(round(dark.size / module_px))
    if not 20 <= n_modules <= 2000:
        return None

    # Resample the binary profile onto the module grid, at module centres.
    centers = (np.arange(n_modules) + 0.5) * (dark.size / n_modules)
    idx = np.clip(centers.astype(int), 0, dark.size - 1)
    return dark[idx], module_px


def locate_barcode_zxing(bgr: np.ndarray, gray: np.ndarray) -> list[Placement]:
    """Locate linear barcodes with zxing-cpp and model their bar pattern."""
    try:
        import zxingcpp
    except ImportError:
        return []
    try:
        results = zxingcpp.read_barcodes(gray)
    except Exception:
        return []

    out = []
    for res in results:
        fmt = str(res.format).replace(" ", "").replace("-", "").lower()
        if fmt not in LINEAR_FORMATS:
            continue
        p = res.position
        quad = np.array(
            [
                [p.top_left.x, p.top_left.y],
                [p.top_right.x, p.top_right.y],
                [p.bottom_right.x, p.bottom_right.y],
                [p.bottom_left.x, p.bottom_left.y],
            ],
            dtype=np.float32,
        )
        if not np.all(np.isfinite(quad)):
            continue

        span = max(
            float(np.linalg.norm(quad[1] - quad[0])),
            float(np.linalg.norm(quad[2] - quad[3])),
        )
        height = max(
            float(np.linalg.norm(quad[3] - quad[0])),
            float(np.linalg.norm(quad[2] - quad[1])),
        )
        if span < 20 or height < 4:
            continue

        # Oversample the profile so the narrowest bar spans several samples.
        profile = _sample_profile(gray, quad, width=int(min(4096, max(256, span * 4))))
        found = profile_to_bars(profile)
        if found is None:
            continue
        bars, _ = found

        model = BarsModel(
            bars,
            height=max(1.0, height / (span / bars.size)),
            metadata={"symbology": str(res.format)},
        )
        transform = geometry.quad_to_transform(quad, model)
        out.append(
            Placement(
                model=model,
                transform=transform,
                quad=quad,
                locator="barcode_zxing",
                payload=getattr(res, "text", None),
            )
        )
    return out
