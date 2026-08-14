"""Per-pixel foreground coverage: the 0..1 value, and which one you want.

Three different 0..1 quantities get conflated by "how foreground is this pixel". They
answer different questions, and mixing them produces numbers that mean nothing:

**Coverage** (:func:`coverage_map`, :func:`observed_coverage`) is *physical*: the
fraction of the pixel's area lying under foreground. ISO 12647-2:2013 3.1 calls this
**area coverage**. A pixel straddling a mark's edge genuinely is 0.37 foreground. The
same quantity is the matting **alpha** (identical, for opaque marks), the
remote-sensing **fractional abundance** of an endmember in a **mixed pixel**, and the
medical-imaging **partial volume fraction**.

**Confidence** (:func:`confidence`) is *epistemic*: how sure we are of the label. This
is what the user's "probability that the pixel is foreground" means when the underlying
reality is genuinely binary. A pixel deep inside a mark has coverage 1.0 and confidence
1.0; one in a blown-out highlight may have modelled coverage 1.0 and confidence near 0.

**Weight** (:func:`measurement_weight`) is *operational*: how safe the pixel is to
measure, given that blur spreads signal across boundaries. It is the only one that
should gate a physical measurement.

Two routes to coverage
----------------------
*Modelled* (:func:`coverage_map`): the shape is known, so back-project a supersampled
grid of each pixel through the transform and ask the model. Exact up to the
supersampling rate, immune to lighting, and the right default. It answers "where should
the foreground be".

*Observed* (:func:`observed_coverage`): normalise the photograph between a background
endpoint and a solid-foreground endpoint. This is the Murray-Davies inversion, and it
answers "where is the foreground actually" -- so it is the one that can see a printing
defect. It returns an *apparent* (optical) coverage, inflated relative to geometric
coverage by lateral light scattering in the substrate (the Yule-Nielsen effect), which
is why the two routes disagree.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import config, geometry
from .models import Model
from .types import Placement, Polarity, Region

__all__ = [
    "coverage_map",
    "observed_coverage",
    "confidence",
    "measurement_weight",
    "region_map",
    "estimate_blur_sigma",
]


# --------------------------------------------------------------------------- #
# Modelled coverage
# --------------------------------------------------------------------------- #


def coverage_map(
    model: Model,
    transform: np.ndarray,
    image_shape: tuple[int, int],
    *,
    samples: int = config.SUPERSAMPLES,
) -> np.ndarray:
    """Area fraction of each pixel covered by the model's foreground, in ``[0, 1]``.

    Each pixel is probed at ``samples**2`` sub-positions on a regular grid at sub-pixel
    centres; each probe is back-projected into model coordinates and passed to
    :meth:`Model.occupancy`. The mean is the covered area fraction -- ordinary
    supersampled area coverage, the same quantity a renderer's anti-aliasing computes.

    Values are quantised to ``1/samples**2``, so ``samples`` sets the accuracy floor.
    Only the model's bounding box is evaluated, so a mark occupying 2% of a 12 MP photo
    costs 2% of the work.
    """
    h, w = image_shape
    out = np.zeros((h, w), dtype=np.float32)

    x0, y0, x1, y1 = bounding_box(model, transform, image_shape)
    if x1 <= x0 or y1 <= y0:
        return out

    inv = np.linalg.inv(np.asarray(transform, dtype=np.float64))
    # Pixel-centre convention: integer coordinate x is the CENTRE of a pixel spanning
    # [x-0.5, x+0.5). Sampling [x, x+1) instead offsets the whole map half a pixel.
    offsets = (np.arange(samples) + 0.5) / samples - 0.5
    ys, xs = np.mgrid[y0:y1, x0:x1]
    xs = xs.astype(np.float64).ravel()
    ys = ys.astype(np.float64).ravel()

    dxs, dys = np.meshgrid(offsets, offsets)
    px = xs[None, :] + dxs.ravel()[:, None]
    py = ys[None, :] + dys.ravel()[:, None]

    denom = inv[2, 0] * px + inv[2, 1] * py + inv[2, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = (inv[0, 0] * px + inv[0, 1] * py + inv[0, 2]) / denom
        v = (inv[1, 0] * px + inv[1, 1] * py + inv[1, 2]) / denom

    hits = np.asarray(model.occupancy(u, v), dtype=np.float32)
    out[y0:y1, x0:x1] = hits.mean(axis=0).reshape(y1 - y0, x1 - x0)
    return out


def bounding_box(
    model: Model, transform: np.ndarray, image_shape: tuple[int, int]
) -> tuple[int, int, int, int]:
    """Pixel bounding box ``(x0, y0, x1, y1)`` of the model, clipped to the image."""
    h, w = image_shape
    corners = geometry.transform_to_quad(transform, model)
    x0 = max(0, int(np.floor(corners[:, 0].min())))
    x1 = min(w, int(np.ceil(corners[:, 0].max())) + 1)
    y0 = max(0, int(np.floor(corners[:, 1].min())))
    y1 = min(h, int(np.ceil(corners[:, 1].max())) + 1)
    return x0, y0, x1, y1


def region_map(
    placement: Placement,
    coverage: np.ndarray,
    *,
    threshold: float = 0.5,
    margin_units: float = config.MARGIN_UNITS,
) -> np.ndarray:
    """Four-way :class:`Region` label array from a coverage map and a placement."""
    h, w = coverage.shape[:2]
    out = np.full((h, w), Region.OUTSIDE, dtype=np.uint8)

    if margin_units:
        _fill(
            out,
            geometry.margin_quad(
                placement.transform, placement.model, units=margin_units
            ),
            Region.MARGIN,
        )
    _fill(
        out,
        geometry.transform_to_quad(placement.transform, placement.model),
        Region.BACKGROUND,
    )

    inside = out == Region.BACKGROUND
    out[inside & (coverage >= threshold)] = Region.FOREGROUND
    return out


def _fill(target: np.ndarray, quad: np.ndarray, value: int) -> None:
    pts = np.round(quad).astype(np.int32).reshape(-1, 1, 2)
    cv2.fillPoly(target, [pts], color=int(value))


# --------------------------------------------------------------------------- #
# Observed coverage
# --------------------------------------------------------------------------- #


def observed_coverage(
    gray: np.ndarray,
    placement: Placement,
    *,
    polarity: Polarity = Polarity.FOREGROUND_IS_DARK,
    yule_nielsen_n: float = 1.0,
    percentile: float = 5.0,
) -> np.ndarray:
    """Apparent coverage read from the photograph itself (Murray-Davies).

    Endmember values are estimated from the mark's own pixels -- its background region
    gives the substrate endpoint, its foreground core the solid endpoint -- so no
    external calibration target is needed. Percentiles rather than extremes, so a
    specular highlight cannot define an endpoint.

    ``yule_nielsen_n`` > 1 compensates for lateral light scattering in the substrate,
    which otherwise inflates apparent coverage above geometric coverage. n = 1 is plain
    Murray-Davies; the right value is substrate- and wavelength-specific and should be
    fitted, not guessed.

    The result is *apparent*, not geometric, coverage. Do not silently substitute it
    for :func:`coverage_map`.
    """
    fore_ref, back_ref = _endmembers(gray, placement, polarity, percentile)
    if abs(fore_ref - back_ref) < 1e-6:
        return np.zeros(gray.shape[:2], dtype=np.float32)

    x = gray.astype(np.float32)
    if yule_nielsen_n != 1.0:
        inv_n = 1.0 / yule_nielsen_n
        x = np.power(np.clip(x, 1e-6, None), inv_n)
        fore_ref = float(np.power(max(fore_ref, 1e-6), inv_n))
        back_ref = float(np.power(max(back_ref, 1e-6), inv_n))

    return np.clip((x - back_ref) / (fore_ref - back_ref), 0.0, 1.0).astype(np.float32)


def _endmembers(
    gray: np.ndarray, placement: Placement, polarity: Polarity, percentile: float
) -> tuple[float, float]:
    """``(foreground_level, background_level)`` estimated from the mark's own pixels."""
    ideal = coverage_map(
        placement.model, placement.transform, gray.shape[:2], samples=4
    )
    inside = _inside(placement, gray.shape[:2])
    core = ideal >= 1.0 - config.PURE_COVERAGE_TOL
    clear = (ideal <= config.PURE_COVERAGE_TOL) & inside
    if not core.any() or not clear.any():
        return float(gray.min()), float(gray.max())

    dark = float(np.percentile(gray[core], 100 - percentile))
    light = float(np.percentile(gray[clear], percentile))
    if polarity is Polarity.FOREGROUND_IS_DARK:
        return dark, light
    return light, dark


def _inside(placement: Placement, image_shape: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(image_shape, dtype=np.uint8)
    _fill(mask, geometry.transform_to_quad(placement.transform, placement.model), 1)
    return mask.astype(bool)


# --------------------------------------------------------------------------- #
# Confidence
# --------------------------------------------------------------------------- #


def confidence(
    gray: np.ndarray,
    placement: Placement,
    coverage: np.ndarray,
    *,
    polarity: Polarity = Polarity.FOREGROUND_IS_DARK,
) -> np.ndarray:
    """How much to trust the coverage value at each pixel, in ``[0, 1]``.

    Distinct from coverage. Three things erode it, combined multiplicatively:

    * **Model/image disagreement** -- where the observed value contradicts the modelled
      coverage, one of them is wrong. This is what catches foreground that failed to
      print, a torn label, or a mis-fitted transform.
    * **Clipping** -- saturated or crushed pixels carry no photometric information.
    * **Edge proximity** -- mixed pixels are inherently less certain, and their value
      depends on sub-pixel geometry known only to ~0.5 px.
    """
    observed = observed_coverage(gray, placement, polarity=polarity)
    agreement = 1.0 - np.abs(observed - coverage)
    valid = (gray < config.SATURATION_LEVEL) & (gray > config.BLACK_CLIP_LEVEL)
    purity = np.abs(coverage - 0.5) * 2.0
    return np.clip(agreement * purity * valid.astype(np.float32), 0.0, 1.0).astype(
        np.float32
    )


# --------------------------------------------------------------------------- #
# Measurement weight
# --------------------------------------------------------------------------- #


def measurement_weight(
    coverage: np.ndarray,
    *,
    blur_sigma: float | None = None,
    radius: int | None = None,
    inside: np.ndarray | None = None,
    kind: str = "foreground",
    sigmas: float = config.EDGE_MARGIN_SIGMAS,
) -> np.ndarray:
    """Blur-aware weight in ``[0, 1]``: how safe each pixel is to *measure*.

    Coverage says a pixel lies entirely under foreground. That is necessary but not
    sufficient: the point spread function leaks neighbouring signal into interior
    pixels, and that contamination has a different footprint from partial area
    coverage -- so no coverage-based weighting removes it. The fix is spatial: require
    a pixel's whole neighbourhood to be foreground, out to the radius the blur reaches.

    Implemented as grayscale morphological erosion of the coverage map, which is exactly
    "the minimum coverage within radius r" -- continuous rather than a hard mask, so a
    pixel one step from an edge is down-weighted rather than trusted or discarded.

    Give either ``radius`` (pixels, wins if both are given) or ``blur_sigma``, from
    which the radius is ``sigmas * blur_sigma``.
    """
    if kind == "foreground":
        field = coverage
    elif kind == "background":
        field = 1.0 - coverage
        if inside is not None:
            field = np.where(inside, field, 0.0)
    else:
        raise ValueError(f"kind must be 'foreground' or 'background', got {kind!r}")

    if radius is None:
        if blur_sigma is None or not np.isfinite(blur_sigma):
            blur_sigma = config.DEFAULT_BLUR_SIGMA
        radius = int(np.ceil(sigmas * max(blur_sigma, 0.0)))
    radius = max(1, int(radius))

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1,) * 2)
    return cv2.erode(field.astype(np.float32), kernel)


# --------------------------------------------------------------------------- #
# Blur estimation
# --------------------------------------------------------------------------- #


def estimate_blur_sigma(gray: np.ndarray, placement: Placement) -> float:
    """Estimate imaging blur sigma, in pixels, from the mark's own edges.

    Sizing the measurement margin needs this. Estimated by finding the sigma whose
    blurred ideal coverage best matches the photograph.

    Returns ``nan`` when the minimum lands at the top of the search range: that is the
    search running out of room, not a measurement -- the modelled shape and the
    photograph do not correspond -- and reporting the boundary value would silently size
    the measurement margin from noise.
    """
    ideal = coverage_map(
        placement.model, placement.transform, gray.shape[:2], samples=4
    )
    x0, y0, x1, y1 = bounding_box(placement.model, placement.transform, gray.shape[:2])
    if x1 - x0 < 16 or y1 - y0 < 16:
        return config.DEFAULT_BLUR_SIGMA

    ideal_c = ideal[y0:y1, x0:x1]
    obs = gray[y0:y1, x0:x1].astype(np.float32)
    lo, hi = np.percentile(obs, [5, 95])
    if hi - lo < 1e-6:
        return config.DEFAULT_BLUR_SIGMA
    obs_n = np.clip((hi - obs) / (hi - lo), 0.0, 1.0)

    scale = placement.pixels_per_feature
    grid = np.linspace(0.3, max(1.0, scale * 0.8), 16)
    errs = [
        float(np.mean((cv2.GaussianBlur(ideal_c, (0, 0), s) - obs_n) ** 2))
        for s in grid
    ]
    best = int(np.argmin(errs))
    if best == len(grid) - 1:
        return float("nan")
    return float(grid[best])
