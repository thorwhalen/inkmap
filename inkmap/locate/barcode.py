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


#: Symbologies whose total module count is fixed by the specification. Using the spec
#: beats estimating: a module-width estimate that is 10% low inflates the module count
#: by 10%, and every bar after the first is then placed wrong.
FIXED_MODULE_COUNTS = {
    "ean13": 95,
    "upca": 95,
    "ean8": 67,
    "upce": 51,
}


def _fit_module_width(runs: np.ndarray, span: float) -> float | None:
    """Find the module width that best explains the run lengths as integer multiples.

    Every run in a linear barcode is a whole number of modules wide, so the correct
    width is the one that makes ``run / width`` closest to integers across all runs.
    Minimising that residual is far more robust than reading a percentile of the run
    lengths: one noisy sample creates a spurious short run and drags a percentile down,
    and a width that is 10% low inflates the module count by 10%.
    """
    if runs.size < 3:
        return None
    seed = float(np.percentile(runs, 10))
    if seed < 1.0:
        seed = float(runs.min())
    if seed < 0.8:
        return None

    candidates = np.linspace(seed * 0.6, seed * 2.2, 400)
    best, best_cost = None, np.inf
    for width in candidates:
        if width < 0.5:
            continue
        quotient = runs / width
        # Ignore quotients that round to zero: those are noise, not modules.
        keep = quotient > 0.5
        if keep.sum() < 3:
            continue
        residual = quotient[keep] - np.round(quotient[keep])
        total = span / width
        cost = float(np.mean(residual**2)) + (total - round(total)) ** 2 / max(total, 1)
        if cost < best_cost:
            best, best_cost = float(width), cost
    return best


def profile_to_bars(
    profile: np.ndarray, *, n_modules: int | None = None
) -> tuple[np.ndarray, float] | None:
    """Quantise a 1-D profile into a bar pattern.

    Returns ``(bars, module_px)``. Thresholds at the midpoint of the profile's range,
    per ISO/IEC 15416 3.5. ``n_modules`` pins the module count when the symbology fixes
    it; otherwise the module width is fitted from the run lengths.
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

    if n_modules is None:
        module_px = _fit_module_width(runs.astype(float), float(dark.size))
        if module_px is None:
            return None
        n_modules = int(round(dark.size / module_px))
        if not 20 <= n_modules <= 2000:
            return None
    else:
        module_px = dark.size / n_modules

    # Sample at module centres.
    centers = (np.arange(n_modules) + 0.5) * (dark.size / n_modules)
    idx = np.clip(centers.astype(int), 0, dark.size - 1)
    return dark[idx], float(module_px)


def _decodes_to(bars: np.ndarray, payload: str) -> bool:
    """Render a bar pattern cleanly and check a decoder reads the expected payload."""
    try:
        import zxingcpp
    except ImportError:
        return False
    scale, quiet = 4, 12
    strip = np.repeat(~bars, scale)[None, :].astype(np.uint8) * 255
    image = np.repeat(strip, 60, axis=0)
    image = cv2.copyMakeBorder(
        image, 20, 20, quiet * scale, quiet * scale, cv2.BORDER_CONSTANT, value=255
    )
    try:
        return any(r.text == payload for r in zxingcpp.read_barcodes(image))
    except Exception:
        return False


def recover_bars(
    profile: np.ndarray, *, n_modules: int | None = None, payload: str | None = None
) -> np.ndarray | None:
    """Recover the bar pattern from a profile, verifying it against the payload.

    Variable-length symbologies (Code 128, Code 39, ITF) do not pin the module count, so
    it has to be fitted -- and a fit that is one module out places every bar after the
    first incorrectly while still looking like a barcode. Since the decoder already told
    us the payload, the recovered pattern can be *checked*: render it and see whether it
    decodes back. If not, try neighbouring module counts.

    This is not circular. The payload came from the decoder reading the photograph; the
    pattern is being reconstructed from our own geometry. Agreement means the geometry
    is right, and disagreement is a genuine failure signal rather than a guess.
    """
    first = profile_to_bars(profile, n_modules=n_modules)
    if first is None:
        return None
    bars, _ = first
    if payload is None or n_modules is not None or _decodes_to(bars, payload):
        return bars

    base = bars.size
    for delta in (1, -1, 2, -2, 3, -3):
        candidate = profile_to_bars(profile, n_modules=base + delta)
        if candidate is None:
            continue
        if _decodes_to(candidate[0], payload):
            return candidate[0]
    return bars


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
        bars = recover_bars(
            profile,
            n_modules=FIXED_MODULE_COUNTS.get(fmt),
            payload=getattr(res, "text", None),
        )
        if bars is None:
            continue

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
