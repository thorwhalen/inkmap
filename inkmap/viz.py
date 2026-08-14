"""Visual overlays, for checking that a result is actually right.

Coverage maps are the kind of output that looks plausible when it is subtly wrong -- a
half-unit offset or a quarter-turn rotation of the model both produce a mask of the
right shape, size and density. Looking at it is the cheapest way to catch that class of
error, so this is a first-class part of the workflow rather than a nicety.

Only needs OpenCV and numpy; nothing here imports matplotlib.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import geometry
from .models import BarsModel, MatrixModel
from .types import InkMap, Region

__all__ = ["overlay", "panel", "colorize_coverage", "colorize_regions", "REGION_COLORS"]

#: BGR colours per region. Foreground warm, background cool, margin neutral.
REGION_COLORS: dict[int, tuple[int, int, int]] = {
    Region.OUTSIDE: (0, 0, 0),
    Region.MARGIN: (90, 90, 90),
    Region.BACKGROUND: (200, 140, 60),
    Region.FOREGROUND: (60, 90, 230),
}


def _as_bgr(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image.copy()


def colorize_regions(region: np.ndarray) -> np.ndarray:
    """(H, W) region labels -> BGR image."""
    out = np.zeros((*region.shape, 3), dtype=np.uint8)
    for value, color in REGION_COLORS.items():
        out[region == value] = color
    return out


def colorize_coverage(coverage: np.ndarray) -> np.ndarray:
    """(H, W) float coverage -> BGR heatmap. Partial coverage is what to look at."""
    scaled = np.clip(coverage * 255.0, 0, 255).astype(np.uint8)
    return cv2.applyColorMap(scaled, cv2.COLORMAP_INFERNO)


def overlay(
    image: np.ndarray,
    ink_map: InkMap,
    *,
    alpha: float = 0.45,
    draw_quad: bool = True,
    draw_grid: bool = False,
) -> np.ndarray:
    """Blend the region map over the original image.

    ``draw_grid`` overlays the fitted model grid, which is the fastest way to see a
    mis-fitted transform: if the lines do not sit on the mark's own boundaries, every
    downstream number is wrong no matter how clean the mask looks.
    """
    base = _as_bgr(image)
    tint = colorize_regions(ink_map.region)
    mask = (ink_map.region != Region.OUTSIDE)[..., None]
    out = np.where(mask, cv2.addWeighted(base, 1 - alpha, tint, alpha, 0), base)

    if draw_quad:
        pts = np.round(ink_map.placement.quad).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], True, (0, 255, 255), 2, cv2.LINE_AA)
    if draw_grid:
        _draw_grid(out, ink_map)
    return out


def _draw_grid(canvas: np.ndarray, ink_map: InkMap) -> None:
    """Draw the model's natural grid, where it has one, else its extent box."""
    model = ink_map.model
    transform = ink_map.placement.transform
    width, height = model.extent

    if isinstance(model, MatrixModel):
        us = np.arange(0, model.n_cols + 1, max(1, model.n_cols // 25))
        vs = np.arange(0, model.n_rows + 1, max(1, model.n_rows // 25))
    elif isinstance(model, BarsModel):
        us = np.arange(0, width + 1, max(1, int(width) // 40))
        vs = np.array([0.0, height])
    else:  # freeform: just the extent box, plus a centre cross
        us = np.array([0.0, width / 2, width])
        vs = np.array([0.0, height / 2, height])

    for u in us:
        _line(canvas, transform, (u, 0.0), (u, height))
    for v in vs:
        _line(canvas, transform, (0.0, v), (width, v))


def _line(canvas: np.ndarray, transform: np.ndarray, a, b) -> None:
    seg = cv2.perspectiveTransform(
        np.float32([a, b]).reshape(-1, 1, 2), np.asarray(transform, dtype=np.float64)
    ).reshape(2, 2)
    if not np.all(np.isfinite(seg)):
        return
    cv2.line(
        canvas,
        tuple(np.round(seg[0]).astype(int)),
        tuple(np.round(seg[1]).astype(int)),
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )


def panel(image: np.ndarray, ink_map: InkMap, *, crop: bool = True) -> np.ndarray:
    """Four-pane contact sheet: original | overlay | coverage | measurement weight.

    The last two panes are the ones worth studying. Coverage should show a thin soft
    fringe along every foreground boundary; weight should show that fringe eaten away,
    leaving only interiors. If weight is empty, the image cannot support a measurement.
    """
    base = _as_bgr(image)
    panes = [
        base,
        overlay(image, ink_map),
        colorize_coverage(ink_map.coverage),
        colorize_coverage(
            ink_map.weight if ink_map.weight is not None else ink_map.coverage
        ),
    ]
    if crop:
        x, y, w, h = _crop_box(ink_map, base.shape[:2])
        panes = [p[y : y + h, x : x + w] for p in panes]
    height = max(p.shape[0] for p in panes)
    panes = [
        cv2.copyMakeBorder(
            p, 0, height - p.shape[0], 0, 8, cv2.BORDER_CONSTANT, value=(20, 20, 20)
        )
        for p in panes
    ]
    return np.hstack(panes)


def _crop_box(
    ink_map: InkMap, shape: tuple[int, int], *, pad: float = 0.25
) -> tuple[int, int, int, int]:
    """Bounding box around the mark with a proportional margin."""
    h, w = shape
    quad = ink_map.placement.quad
    x0, y0 = quad.min(axis=0)
    x1, y1 = quad.max(axis=0)
    mx, my = (x1 - x0) * pad, (y1 - y0) * pad
    x0 = int(max(0, x0 - mx))
    y0 = int(max(0, y0 - my))
    x1 = int(min(w, x1 + mx))
    y1 = int(min(h, y1 + my))
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)
