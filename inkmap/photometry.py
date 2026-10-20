"""Turning masks into measurements that are actually valid.

Everything here exists because a per-pixel mask is necessary but nowhere near
sufficient for measuring anything *about* the mark -- its reflectance, its density, its
colour, how much of it actually printed. The failure modes are silent: they do not
raise, they return a plausible number wrong by tens of percent.

Measured on synthetic scenes with exact ground truth (see ``docs/validation.md``), the
bias in recovering a foreground-only signal at 6 px per model unit:

=====================  ========  ==========  ==========  ==========
pixel selection        blur=0    sigma=1 px  sigma=2 px  sigma=3 px
=====================  ========  ==========  ==========  ==========
coverage > 0.5           -3.3%     -12.2%      -23.3%      -32.4%
coverage == 1.0          -0.0%      -8.0%      -19.9%      -30.1%
weight (2 sigma)         +0.0%      -0.2%       -0.6%       -1.5%
=====================  ========  ==========  ==========  ==========

Two lessons. Geometric purity is necessary but *not* sufficient -- a pixel entirely
under foreground still reads 30% low, because the point spread function drags
background signal into it, and that contamination has a different footprint from
partial area coverage. Only spatial erosion removes it, which is what the weight
channel is.

And erosion stops working once the blur is wide relative to a model unit: there are no
uncontaminated pixels left. That is the classic partial-volume result, and it is why
:func:`measurability` exists -- better to say the measurement is not possible than to
return a confidently wrong number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from . import config
from .types import InkMap

__all__ = [
    "srgb_to_linear",
    "measurement_mask",
    "measurement_margin",
    "measurability",
    "Measurability",
    "Measurement",
    "measure",
    "illumination_field",
]


def srgb_to_linear(image: np.ndarray) -> np.ndarray:
    """Undo the sRGB transfer function, returning float in ``[0, 1]``.

    Averaging pixel values without this is a real error, not a nicety: sRGB values are
    perceptually encoded, so the mean of encoded values is not the encoded mean
    intensity. Any difference between two exposures compounds it. Apply before any
    arithmetic that claims to be about light.

    The piecewise IEC 61966-2-1 curve, not the 2.2 power approximation.
    """
    x = image.astype(np.float32)
    if x.max() > 1.0:
        x = x / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(
        np.float32
    )


def measurement_margin(
    blur_sigma: float, *, sigmas: float = config.EDGE_MARGIN_SIGMAS
) -> int:
    """Erosion radius in pixels for a given blur sigma. At least 1 px."""
    return max(1, int(np.ceil(sigmas * max(blur_sigma, 0.0))))


def measurement_mask(
    ink_map: InkMap,
    *,
    kind: str = "foreground",
    purity: float = 1.0 - config.PURE_COVERAGE_TOL,
    margin: int | None = None,
) -> np.ndarray:
    """Pixels safe to measure: geometrically pure, then eroded clear of edges.

    ``kind`` selects ``"foreground"`` or ``"background"``. ``purity`` is the coverage
    threshold for "pure"; the default demands essentially total coverage, which is the
    point -- a partially covered pixel biases the mean toward the other class.

    This is the mask to use for a measurement. :meth:`InkMap.foreground_mask` is for
    display and for anything that only needs a label.
    """
    from .coverage import measurement_weight

    if kind not in ("foreground", "background"):
        raise ValueError(f"kind must be 'foreground' or 'background', got {kind!r}")

    # The foreground weight is precomputed by `find`; reuse unless a custom margin
    # means it was built at the wrong radius.
    if kind == "foreground" and margin is None and ink_map.weight is not None:
        return ink_map.weight >= purity

    sigma = ink_map.blur_sigma
    if sigma is None or not np.isfinite(sigma):
        sigma = config.DEFAULT_BLUR_SIGMA

    weight = measurement_weight(
        ink_map.coverage,
        blur_sigma=sigma,
        radius=margin,
        inside=ink_map.inside_mask(),
        kind=kind,
    )
    return weight >= purity


@dataclass(frozen=True)
class Measurability:
    """Whether a trustworthy measurement is possible on this image at all."""

    ok: bool
    pixels_per_feature: float
    blur_sigma: float
    resolution_ratio: float
    """``pixels_per_feature / blur_sigma``. Below ~6 the blur is wide relative to the
    mark's smallest feature and no erosion leaves uncontaminated pixels."""
    n_foreground_pixels: int
    n_background_pixels: int
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.ok


def measurability(ink_map: InkMap, *, min_pixels: int = 50) -> Measurability:
    """Judge whether a foreground/background measurement can be trusted here.

    Returning a number quietly biased by 30% is worse than refusing, so this is checked
    up front and attached to every :class:`Measurement`.
    """
    sigma = ink_map.blur_sigma
    if sigma is None or not np.isfinite(sigma):
        sigma = config.DEFAULT_BLUR_SIGMA
    scale = ink_map.placement.pixels_per_feature
    ratio = scale / max(sigma, 1e-6)

    n_fore = int(measurement_mask(ink_map, kind="foreground").sum())
    n_back = int(measurement_mask(ink_map, kind="background").sum())

    reasons: list[str] = []
    if ratio < config.MIN_SCALE_OVER_SIGMA:
        reasons.append(
            f"blur is wide relative to the smallest feature (px/feature {scale:.1f} / sigma "
            f"{sigma:.2f} = {ratio:.1f}, want >= {config.MIN_SCALE_OVER_SIGMA}); "
            "edge contamination cannot be eroded away"
        )
    if n_fore < min_pixels:
        reasons.append(
            f"only {n_fore} pure foreground pixels survive erosion (want >= {min_pixels})"
        )
    if n_back < min_pixels:
        reasons.append(
            f"only {n_back} pure background pixels survive erosion (want >= {min_pixels})"
        )

    return Measurability(
        ok=not reasons,
        pixels_per_feature=scale,
        blur_sigma=sigma,
        resolution_ratio=ratio,
        n_foreground_pixels=n_fore,
        n_background_pixels=n_back,
        reasons=tuple(reasons),
    )


def illumination_field(
    image: np.ndarray, ink_map: InkMap, *, degree: int = 1
) -> np.ndarray:
    """Fit a smooth illumination field across the mark from its background pixels.

    The background within the mark samples the illumination across the whole mark, so
    the scene calibrates itself -- no flat-field frame required. A first-order (planar)
    fit handles the usual oblique-lighting gradient; degree 2 handles vignetting
    curvature at the cost of being able to absorb real signal.

    Returns a field normalised to mean 1.0 over the mark; divide by it to flatten.
    """
    mask = measurement_mask(ink_map, kind="background")
    if mask.sum() < 12:
        return np.ones(image.shape[:2], dtype=np.float32)

    h, w = image.shape[:2]
    field = smooth_field(image, mask, degree=degree)

    inside = ink_map.inside_mask()
    scale = float(field[inside].mean()) if inside.any() else float(field.mean())
    if abs(scale) < 1e-9:
        return np.ones((h, w), dtype=np.float32)
    return (field / scale).astype(np.float32)


def smooth_field(image: np.ndarray, mask: np.ndarray, *, degree: int = 1) -> np.ndarray:
    """A 2-D polynomial of ``degree`` fitted to ``image`` over the pixels of ``mask``.

    ``image`` is one channel or several (fitted each on its own); the field covers the
    whole frame, in the image's own units, so dividing by it, normalised to the level
    wanted, flattens the illumination that the masked pixels sample.
    """
    h, w = image.shape[:2]
    ys, xs = np.nonzero(mask)
    values = image[ys, xs].astype(np.float64)
    basis = _poly_basis(xs / w, ys / h, degree)
    coeffs, *_ = np.linalg.lstsq(basis, values, rcond=None)
    yy, xx = np.mgrid[0:h, 0:w]
    field = _poly_basis((xx / w).ravel(), (yy / h).ravel(), degree) @ coeffs
    return field.reshape(image.shape[:2] + values.shape[1:])


def _poly_basis(x: np.ndarray, y: np.ndarray, degree: int) -> np.ndarray:
    """Design matrix of 2-D monomials up to ``degree``."""
    cols = [np.ones_like(x)]
    for total in range(1, degree + 1):
        for i in range(total + 1):
            cols.append((x ** (total - i)) * (y**i))
    return np.stack(cols, axis=1)


@dataclass(frozen=True)
class Measurement:
    """Aggregated signal over foreground and background, with its validity attached.

    ``measurability`` is carried along deliberately: a caller that ignores it has to do
    so explicitly.
    """

    foreground_mean: float
    foreground_std: float
    foreground_median: float
    background_mean: float
    background_std: float
    background_median: float
    n_foreground: int
    n_background: int
    measurability: Measurability | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def contrast(self) -> float:
        """Foreground minus background."""
        return self.foreground_mean - self.background_mean

    @property
    def ratio(self) -> float:
        """Foreground over background; ``nan`` when the background reads zero."""
        return (
            self.foreground_mean / self.background_mean
            if self.background_mean
            else float("nan")
        )

    @property
    def snr(self) -> float:
        """Contrast over the pooled standard deviation."""
        pooled = float(np.hypot(self.foreground_std, self.background_std))
        return float(self.contrast / pooled) if pooled else float("inf")


def measure(
    image: np.ndarray,
    ink_map: InkMap,
    *,
    linearize: bool = True,
    flatten: bool = False,
    margin: int | None = None,
    robust: bool = True,
) -> Measurement:
    """Aggregate ``image`` over the safe foreground and background pixels of ``ink_map``.

    ``image`` need not be the one the mark was located in: any frame registered to it
    works, which is the usual way to measure a different exposure, channel or modality
    using geometry established once on the sharpest frame.

    ``linearize`` undoes sRGB encoding first -- leave it on for anything from a normal
    camera pipeline, off for already-linear data. ``flatten`` divides out a fitted
    illumination field. ``robust`` reports medians alongside means; on real photographs
    they diverge exactly where something is wrong, which makes the pair a free
    diagnostic.
    """
    data = image
    if data.ndim == 3:
        data = cv2.cvtColor(data, cv2.COLOR_BGR2GRAY)
    if data.shape[:2] != ink_map.coverage.shape[:2]:
        raise ValueError(
            f"image shape {data.shape[:2]} does not match the ink map "
            f"{ink_map.coverage.shape[:2]}; register the frames first"
        )

    values = srgb_to_linear(data) if linearize else data.astype(np.float32)
    if flatten:
        values = values / np.maximum(illumination_field(values, ink_map), 1e-6)

    fore = measurement_mask(ink_map, kind="foreground", margin=margin)
    back = measurement_mask(ink_map, kind="background", margin=margin)

    def stats(mask: np.ndarray) -> tuple[float, float, float, int]:
        if not mask.any():
            return float("nan"), float("nan"), float("nan"), 0
        vals = values[mask]
        median = float(np.median(vals)) if robust else float("nan")
        return float(vals.mean()), float(vals.std()), median, int(vals.size)

    fm, fs, fmed, fn = stats(fore)
    bm, bs, bmed, bn = stats(back)

    return Measurement(
        foreground_mean=fm,
        foreground_std=fs,
        foreground_median=fmed,
        background_mean=bm,
        background_std=bs,
        background_median=bmed,
        n_foreground=fn,
        n_background=bn,
        measurability=measurability(ink_map),
        metadata={"linearized": linearize, "flattened": flatten},
    )
