"""Locating QR symbols: a cascade of interchangeable strategies.

Measured on 189 real photographs from Wikimedia Commons (varied angle, lighting,
substrate, print quality):

===================  ==================
locator              images detected
===================  ==================
zxing-cpp            74%
OpenCV Aruco-based   68%
OpenCV classic       43%
**union**            **80%**
===================  ==================

So OpenCV alone forfeits about 37 points of recall. All three are permissively licensed
(Apache-2.0) and ship as wheels. Deliberately *not* used: ``qrdet``/``qreader``, whose
MIT metadata is misleading -- they depend on ``ultralytics``, which is AGPL-3.0.

Getting the module matrix
-------------------------
Decoding gives the payload, but the payload does **not** determine the module pattern:
error-correction level and mask pattern are encoder choices not recoverable from the
text, so re-encoding the payload can yield a differently-sized, differently-masked
matrix. It is a silent-wrong-answer path and is not used here. The pattern is read from
the image instead: OpenCV's ``straight_qrcode`` is a bit-exact sample, and where that
is unavailable the grid is sampled directly.
"""

from __future__ import annotations

import cv2
import numpy as np

from .. import geometry
from ..models import MatrixModel
from ..types import Placement

__all__ = ["locate_qr_opencv", "locate_qr_aruco", "locate_qr_zxing", "sample_matrix"]


def _matrix_from_straight(straight: np.ndarray | None) -> np.ndarray | None:
    """OpenCV's rectified ``straight_qrcode`` -> N x N bool, True = dark module."""
    if straight is None or straight.size == 0:
        return None
    if straight.ndim == 3:
        straight = cv2.cvtColor(straight, cv2.COLOR_BGR2GRAY)
    if straight.shape[0] != straight.shape[1]:
        return None
    n = straight.shape[0]
    if n > 177:  # larger than QR version 40 -> upsampled; reduce to modules
        side = _module_side_for(n)
        if side is None:
            return None
        straight = cv2.resize(straight, (side, side), interpolation=cv2.INTER_AREA)
    return straight < 128


def _module_side_for(pixels: int) -> int | None:
    for version in range(1, 41):
        side = 4 * version + 17
        if pixels % side == 0:
            return side
    return None


def sample_matrix(
    gray: np.ndarray, transform: np.ndarray, n: int, *, window: int = 3
) -> np.ndarray:
    """Read the module matrix off the image at the grid intersections.

    ISO/IEC 18004's reference decode algorithm samples a small area centred on each
    grid intersection and thresholds. Used when no decoder handed us a matrix -- notably
    when the print is too faint to decode, which is exactly the case that must still
    work.
    """
    values = _sample_cells(gray, transform, n, window=window)
    return values < _global_threshold(values)


def _sample_cells(
    gray: np.ndarray, transform: np.ndarray, n: int, *, window: int = 3
) -> np.ndarray:
    centers = geometry.cell_centers(transform, n, n)
    h, w = gray.shape[:2]
    half = window // 2
    xs = np.clip(np.round(centers[..., 0]).astype(int), half, w - 1 - half)
    ys = np.clip(np.round(centers[..., 1]).astype(int), half, h - 1 - half)
    acc = np.zeros((n, n), dtype=np.float32)
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            acc += gray[ys + dy, xs + dx]
    return acc / (window * window)


def _global_threshold(samples: np.ndarray) -> float:
    """Midpoint between brightest and darkest sampled areas.

    ISO/IEC 18004 clause 12 and ISO/IEC 15416 3.5 both define the global threshold this
    way -- ``(Rmax + Rmin) / 2`` -- rather than by Otsu. Percentiles rather than
    min/max, so one specular pixel cannot drag it.
    """
    lo = float(np.percentile(samples, 2))
    hi = float(np.percentile(samples, 98))
    return (lo + hi) / 2.0


def infer_module_count(
    gray: np.ndarray, quad: np.ndarray, *, min_scale: float = 1.5
) -> int | None:
    """Determine a QR's module count from the image, by model selection.

    Needed because the highest-recall locator (zxing-cpp) reports geometry but not the
    module matrix, and the count is *not* derivable from pixel size alone -- a 290 px
    symbol is equally consistent with version 3 at 10 px/module and version 19 at 3.1.

    Each candidate version is scored on its **timing pattern**: ISO/IEC 18004 puts a
    strictly alternating run along row 6 and column 6. Sampling that row under a wrong
    grid destroys the alternation, making it a near-binary discriminator. Ties break on
    Otsu separability of all sampled centres, which is high only when the grid lands on
    cell centres rather than straddling edges.
    """
    sides = [float(np.linalg.norm(quad[i] - quad[(i + 1) % 4])) for i in range(4)]
    span = float(np.mean(sides))
    if span < 21:
        return None

    best, best_score = None, -np.inf
    for version in range(1, 41):
        n = 4 * version + 17
        if span / n < min_scale:
            break
        model = MatrixModel(np.zeros((n, n), dtype=bool))
        transform = geometry.quad_to_transform(quad, model)
        values = _sample_cells(gray, transform, n)
        score = _timing_score(values) + 0.25 * _separability(values)
        if score > best_score:
            best, best_score = n, score
    return best


def _timing_score(values: np.ndarray) -> float:
    n = values.shape[0]
    if n < 21:
        return 0.0
    dark = values < _global_threshold(values)
    interior = slice(8, n - 8)
    expected = np.arange(8, n - 8) % 2 == 0
    row, col = dark[6, interior], dark[interior, 6]
    if row.size == 0:
        return 0.0
    return float((row == expected).mean() + (col == expected).mean()) / 2.0


def _separability(values: np.ndarray) -> float:
    x = values.ravel()
    total = float(x.var())
    if total < 1e-9:
        return 0.0
    threshold = _global_threshold(values)
    a, b = x[x < threshold], x[x >= threshold]
    if a.size == 0 or b.size == 0:
        return 0.0
    wa, wb = a.size / x.size, b.size / x.size
    return float(np.clip(wa * wb * (a.mean() - b.mean()) ** 2 / total, 0.0, 1.0))


def _placement(
    gray: np.ndarray,
    quad: np.ndarray,
    *,
    cells: np.ndarray | None,
    payload: str | None,
    locator: str,
    inclusive_pixel_corners: bool,
) -> Placement | None:
    quad = np.asarray(quad, dtype=np.float32).reshape(4, 2)
    if not np.all(np.isfinite(quad)):
        return None

    if cells is None:
        n = infer_module_count(gray, quad)
        if n is None:
            return None
        probe = MatrixModel(np.zeros((n, n), dtype=bool))
        transform = geometry.quad_to_transform(
            quad, probe, inclusive_pixel_corners=inclusive_pixel_corners
        )
        cells = sample_matrix(gray, transform, n)

    model = MatrixModel(cells, metadata={"symbology": "QR Code"})
    transform = geometry.quad_to_transform(
        quad, model, inclusive_pixel_corners=inclusive_pixel_corners
    )
    return Placement(
        model=model,
        transform=transform,
        quad=quad,
        locator=locator,
        payload=payload or None,
    )


def _from_opencv(detector, bgr, gray, name: str) -> list[Placement]:
    try:
        ok, decoded, points, straight = detector.detectAndDecodeMulti(bgr)
    except cv2.error:
        return []
    if not ok or points is None:
        return []
    out, straights = [], list(straight) if straight is not None else []
    for i, quad in enumerate(np.asarray(points).reshape(-1, 4, 2)):
        placement = _placement(
            gray,
            quad,
            cells=_matrix_from_straight(straights[i] if i < len(straights) else None),
            payload=decoded[i] if decoded is not None and i < len(decoded) else None,
            locator=name,
            inclusive_pixel_corners=True,
        )
        if placement is not None:
            out.append(placement)
    return out


def locate_qr_opencv(bgr: np.ndarray, gray: np.ndarray) -> list[Placement]:
    """OpenCV's classic ``QRCodeDetector``. Corners are inclusive pixel indices."""
    return _from_opencv(cv2.QRCodeDetector(), bgr, gray, "qr_opencv")


def locate_qr_aruco(bgr: np.ndarray, gray: np.ndarray) -> list[Placement]:
    """OpenCV's ``QRCodeDetectorAruco`` -- finds the finder patterns as Aruco-like
    markers. Notably more robust than the classic detector on real photographs."""
    if not hasattr(cv2, "QRCodeDetectorAruco"):
        return []
    return _from_opencv(cv2.QRCodeDetectorAruco(), bgr, gray, "qr_aruco")


def locate_qr_zxing(bgr: np.ndarray, gray: np.ndarray) -> list[Placement]:
    """zxing-cpp. Highest recall of the three, and its corners are the continuous outer
    boundary (spanning exactly ``N * scale``), not inclusive pixel indices."""
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
        # Exact match: "Micro QR Code" and "rMQR Code" also contain "QR" but use
        # different module counts, so a substring test silently mis-fits them.
        if str(res.format).replace(" ", "").lower() != "qrcode":
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
        placement = _placement(
            gray,
            quad,
            cells=None,
            payload=getattr(res, "text", None),
            locator="qr_zxing",
            inclusive_pixel_corners=False,
        )
        if placement is not None:
            out.append(placement)
    return out
