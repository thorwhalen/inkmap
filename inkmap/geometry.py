"""Model space <-> image space: transforms, and refining them against the photograph.

The central object is a homography mapping *model coordinates* to image pixels. Get it
right and every mask, sample and margin polygon follows exactly. Get it wrong by a
pixel and every downstream number inherits the error, while the mask still looks
plausible.

Three half-pixel conventions have to agree, and each is invisible on inspection:

1. **Pixel centre vs pixel corner.** OpenCV treats integer coordinate ``x`` as the
   *centre* of a pixel spanning ``[x-0.5, x+0.5)``. Rasterising ``[x, x+1)`` instead --
   the natural array-indexing reading -- offsets the entire coverage map by half a
   pixel.
2. **The template raster.** A model rendered at ``s`` px per unit puts template pixel
   ``t`` over ``[t/s, (t+1)/s)`` in model units, so its *centre* is ``(t+0.5)/s``.
   Omitting that half-pixel puts a fixed ~0.7 px bias into every refinement.
3. **Detector corner conventions differ.** OpenCV's QR corners are the integer index of
   the last *contained* pixel; zxing-cpp returns the continuous outer boundary. Measured
   directly, not read from docs -- hence ``inclusive_pixel_corners``.

A symptom worth recognising: if refinement error grows with the mark's rotation angle
in the pattern ``R(d) - d``, the residual ``d`` is a coordinate-convention offset, not
noise.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import config
from .models import Model, render_model

__all__ = [
    "model_quad",
    "quad_to_transform",
    "transform_to_quad",
    "pixels_per_unit",
    "refine_transform",
    "margin_quad",
    "cell_centers",
]


def model_quad(model: Model) -> np.ndarray:
    """The model's four extent corners in model coordinates, top-left first."""
    w, h = model.extent
    return np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)


def quad_to_transform(
    quad: np.ndarray,
    model: Model,
    *,
    inclusive_pixel_corners: bool = False,
) -> np.ndarray:
    """Homography mapping model coordinates onto an image quad.

    ``quad`` must be in the *model's* own corner order (its top-left first), which is
    what the locators natively produce -- do not re-sort it.

    Set ``inclusive_pixel_corners=True`` for detectors whose corners are the integer
    index of the last contained pixel rather than the continuous outer edge. The quad
    is then expanded half a pixel outward, removing a systematic one-pixel scale error
    -- which is a third of a unit at 3 px per unit.
    """
    quad = np.asarray(quad, dtype=np.float32).reshape(4, 2)
    if inclusive_pixel_corners:
        center = quad.mean(axis=0)
        span = float(np.linalg.norm(quad[2] - quad[0]))
        if span > 1e-6:
            quad = center + (quad - center) * (1.0 + 1.0 / span)
    return cv2.getPerspectiveTransform(model_quad(model), quad.astype(np.float32))


def transform_to_quad(transform: np.ndarray, model: Model) -> np.ndarray:
    """Image-space corners implied by a transform, in model order."""
    return cv2.perspectiveTransform(
        model_quad(model).reshape(-1, 1, 2), np.asarray(transform, dtype=np.float64)
    ).reshape(4, 2)


def pixels_per_unit(transform: np.ndarray, model: Model) -> float:
    """Mean image pixels per model unit implied by a transform."""
    q = transform_to_quad(transform, model)
    w, h = model.extent
    scales = []
    if w > 0:
        scales += [np.linalg.norm(q[1] - q[0]) / w, np.linalg.norm(q[2] - q[3]) / w]
    if h > 0:
        scales += [np.linalg.norm(q[3] - q[0]) / h, np.linalg.norm(q[2] - q[1]) / h]
    return float(np.mean(scales)) if scales else 0.0


def refine_transform(
    gray: np.ndarray,
    model: Model,
    transform: np.ndarray,
    *,
    iterations: int = config.ECC_ITERATIONS,
    eps: float = config.ECC_EPS,
    blur_frac: float = config.ECC_TEMPLATE_BLUR_FRAC,
    min_correlation: float = config.ECC_MIN_CORRELATION,
    margin_units: float = config.TEMPLATE_MARGIN_UNITS,
) -> tuple[np.ndarray, float]:
    """Refine a model->image transform by ECC-aligning the rendered model.

    Four detector corners are four observations; the model's whole shape is thousands.
    Aligning the rendered pattern therefore pins the 8-DoF homography far more tightly
    -- measured at 0.02-0.03 px corner RMS versus ~1 px from detector corners.

    Returns ``(transform, correlation)``, falling back to the input unchanged when the
    optimiser fails or the correlation lands below ``min_correlation`` -- a refinement
    that did not converge is worse than none.

    Two details do most of the work. The template is rendered at the *observed* scale;
    rendering at a fixed small scale aliases the comparison and makes the result
    measurably worse than no refinement at all. And the template carries a clear margin,
    because blurring a template that stops at the mark's edge makes the kernel reflect
    interior content back across the border, inventing an edge profile the photograph
    does not have -- ECC then shifts the whole fit to match the artefact.
    """
    scale = float(
        np.clip(
            round(pixels_per_unit(transform, model)),
            config.ECC_MIN_SCALE,
            config.ECC_MAX_SCALE,
        )
    )
    template = render_model(model, scale, supersample=2)
    if blur_frac:
        template = cv2.GaussianBlur(template, (0, 0), max(scale * blur_frac, 0.6))

    pad = int(round(margin_units * scale))
    if pad:
        template = cv2.copyMakeBorder(
            template, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0.0
        )

    # Foreground renders as 1; photographs of normal-polarity marks are dark there.
    template = 1.0 - template

    # ECC's warp maps template pixels -> image pixels; ours maps model units -> image.
    # Fold in the render scale, the margin offset (template pixel 0 is model unit
    # -pad/scale) and the half-pixel centre convention, then take them back out.
    offset = 0.5 / scale - pad / scale
    to_model = np.array(
        [[1.0 / scale, 0.0, offset], [0.0, 1.0 / scale, offset], [0.0, 0.0, 1.0]]
    )
    warp = (np.asarray(transform, dtype=np.float64) @ to_model).astype(np.float32)
    warp /= warp[2, 2]

    try:
        correlation, warp = cv2.findTransformECC(
            _zscore(template),
            _zscore(gray),
            warp,
            cv2.MOTION_HOMOGRAPHY,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, iterations, eps),
            None,
            5,
        )
    except cv2.error:
        return np.asarray(transform, dtype=np.float64), float("nan")

    if not np.isfinite(correlation) or correlation < min_correlation:
        return np.asarray(transform, dtype=np.float64), float(correlation)

    refined = warp.astype(np.float64) @ np.linalg.inv(to_model)
    return refined / refined[2, 2], float(correlation)


def _zscore(image: np.ndarray) -> np.ndarray:
    """Zero-mean unit-variance float32. ECC is contrast-invariant but conditions better
    on normalised input, and this makes template and image commensurate."""
    x = image.astype(np.float32)
    return (x - x.mean()) / (x.std() + 1e-6)


def margin_quad(
    transform: np.ndarray, model: Model, *, units: float = config.MARGIN_UNITS
) -> np.ndarray:
    """Image-space quad of the model plus a clear margin of ``units`` model units.

    ISO/IEC 18004 mandates a 4-module quiet zone for QR; linear symbologies specify
    light margins; printed text has its own whitespace. The margin is guaranteed
    background, which makes it a reference region that -- unlike background *inside*
    the mark -- carries no risk of spread from adjacent foreground.
    """
    w, h = model.extent
    m = float(units)
    outer = np.array(
        [[-m, -m], [w + m, -m], [w + m, h + m], [-m, h + m]], dtype=np.float32
    )
    return cv2.perspectiveTransform(
        outer.reshape(-1, 1, 2), np.asarray(transform, dtype=np.float64)
    ).reshape(4, 2)


def cell_centers(transform: np.ndarray, n_cols: int, n_rows: int) -> np.ndarray:
    """``(n_rows, n_cols, 2)`` image coordinates of unit-cell centres.

    Meaningful for grid models. ISO/IEC 18004's reference decode algorithm samples a
    small area at each grid intersection -- deliberately avoiding edges rather than
    modelling them -- and this is where to do the same.
    """
    uu, vv = np.meshgrid(np.arange(n_cols) + 0.5, np.arange(n_rows) + 0.5)
    pts = np.stack([uu.ravel(), vv.ravel()], axis=1).astype(np.float32)
    return cv2.perspectiveTransform(
        pts.reshape(-1, 1, 2), np.asarray(transform, dtype=np.float64)
    ).reshape(n_rows, n_cols, 2)
