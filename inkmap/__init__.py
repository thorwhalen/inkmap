"""inkmap -- per-pixel foreground coverage for photographed marks.

Given a photograph of a printed mark and a *model* of its shape, say for every pixel
how much of it is foreground (the mark) and how much is background (the substrate) --
as a continuous fraction, not a boolean.

The model is the seam. QR symbols, barcodes, printed letters and arbitrary artwork all
go through one pipeline, because all a model has to do is answer "is this point, in my
own coordinate system, foreground?"::

    import inkmap
    from inkmap import models

    inkmap.find(photo)                                        # auto-detect QR/barcode
    inkmap.find(photo, model=models.text_model("ABC"), quad=q)  # a printed word
    inkmap.find(photo, model=models.RasterModel(art), quad=q)   # anything you can draw

The simplest call::

    coverage = inkmap.foreground(photo)   # (H, W) float32 in [0, 1]

With geometry::

    ink = inkmap.find(photo)              # an InkMap, or None
    ink.placement.quad                    # (4, 2) corners -- a quadrilateral, not a
                                          # rectangle: perspective is expected
    ink.coverage                          # (H, W) float32 area coverage
    ink.region                            # OUTSIDE / MARGIN / BACKGROUND / FOREGROUND
    ink.weight                            # (H, W) float32 safe-to-measure weighting

Measuring::

    mask = inkmap.measurement_mask(ink)   # pure pixels, eroded clear of edges
    result = inkmap.measure(photo, ink)
    result.contrast                       # foreground minus background, linearised
    result.measurability.ok               # False if the image cannot support this

Terminology
-----------
The two classes are **foreground** and **background**, never dark and light: dark/light
describe appearance, and appearance inverts (white-on-black print, reflectance-reversed
symbols, inverted imaging), so an appearance name would mean the mark in one image and
the substrate in the next. :class:`Polarity` carries that mapping explicitly. The
continuous value is **coverage**, after ISO 12647-2:2013 3.1 *area coverage*. See
``docs/terminology.md``.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import config, coverage as _coverage, geometry, models, photometry
from .coverage import confidence, coverage_map, measurement_weight, observed_coverage
from .locate import LOCATORS, locate, place, validated_scale
from .models import Model
from .photometry import (
    Measurability,
    Measurement,
    measurability,
    measure,
    measurement_mask,
    srgb_to_linear,
)
from .types import InkMap, Placement, Polarity, Region


def _version() -> str:
    """Read the installed version, so it cannot drift from pyproject.toml."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("inkmap")
    except PackageNotFoundError:  # running from a source tree, not installed
        return "0.0.0.dev0"


__version__ = _version()

__all__ = [
    # facade
    "foreground",
    "find",
    "find_all",
    "place",
    # types
    "InkMap",
    "Placement",
    "Region",
    "Polarity",
    "Model",
    "Measurement",
    "Measurability",
    # measurement
    "measure",
    "measurement_mask",
    "measurability",
    "srgb_to_linear",
    # pieces
    "coverage_map",
    "observed_coverage",
    "confidence",
    "measurement_weight",
    "locate",
    "LOCATORS",
    "models",
    "geometry",
    "photometry",
    "config",
]


def _as_bgr(image) -> np.ndarray:
    """Accept a path, a grayscale array, or a BGR/BGRA array; return BGR uint8."""
    if not isinstance(image, np.ndarray):
        img = cv2.imread(str(image), cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(f"could not read image: {image}")
        return img
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def analyze(
    image,
    placements,
    *,
    polarity: Polarity = Polarity.FOREGROUND_IS_DARK,
    samples: int = config.SUPERSAMPLES,
    source: str = "modelled",
    refine: bool = True,
    estimate_blur: bool = True,
    margin_units: float = config.MARGIN_UNITS,
) -> list[InkMap]:
    """Turn located placements into ink maps. The half of the pipeline after locating.

    Separated from :func:`find_all` so that a placement obtained any other way -- from
    :func:`place`, from your own detector, from a previous run -- gets exactly the same
    treatment.
    """
    bgr = _as_bgr(image)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    out: list[InkMap] = []
    for placement in placements:
        if refine:
            placement = _refine(gray, placement)
        cov = _coverage_for(
            gray, placement, source=source, samples=samples, polarity=polarity
        )
        sigma = (
            _coverage.estimate_blur_sigma(gray, placement) if estimate_blur else None
        )
        out.append(
            InkMap(
                coverage=cov,
                region=_coverage.region_map(placement, cov, margin_units=margin_units),
                placement=placement,
                polarity=polarity,
                weight=_coverage.measurement_weight(
                    cov,
                    blur_sigma=sigma
                    if sigma is not None
                    else config.DEFAULT_BLUR_SIGMA,
                    kind="foreground",
                ),
                blur_sigma=sigma,
            )
        )
    return out


def find_all(
    image,
    *,
    model: Model | None = None,
    quad=None,
    locators=config.DEFAULT_LOCATORS,
    locate_scale: float | None = None,
    **kwargs,
) -> list[InkMap]:
    """Find every mark in ``image`` and compute its foreground coverage.

    With ``model`` and ``quad``, skips detection entirely and analyses that one
    placement -- the path for marks no detector knows about. With neither, runs the
    locator cascade (QR and linear barcodes out of the box).

    ``refine`` (default on) aligns the rendered model to the photograph, pinning the
    transform to sub-pixel accuracy; it is far more accurate than locator corners alone
    and costs a few milliseconds.

    ``source`` picks where coverage comes from: ``"modelled"`` (default) computes it
    from the model -- exact and lighting-independent, answering "where should the
    foreground be". ``"observed"`` reads it from the photograph, answering "where is
    the foreground actually", and so is the one that can see a printing defect.

    ``locate_scale`` (e.g. ``0.5``) locates on a downscaled copy of the frame and maps
    the placements back -- several times faster on large photographs, with refinement
    restoring sub-pixel geometry. Codes need about 4 px per module *after* downscaling
    (``config.MIN_COARSE_PIXELS_PER_FEATURE``); those below are re-located at full
    resolution. ``None`` (default) locates at full resolution. See
    :func:`inkmap.locate` (its ``scale``). Ignored when ``model``/``quad`` are given.
    """
    locate_scale = validated_scale(locate_scale)
    if model is not None:
        if quad is None:
            raise ValueError(
                "pass quad= alongside model= (four image points, model's corner order); "
                "use inkmap.place() directly if you want the Placement itself"
            )
        placements = [place(model, quad)]
    elif quad is not None:
        raise ValueError("quad= needs model=")
    else:
        bgr = _as_bgr(image)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        placements = locate(bgr, gray, locators=locators, scale=locate_scale)

    return analyze(image, placements, **kwargs)


def find(image, **kwargs) -> InkMap | None:
    """The largest mark in ``image``, or ``None``. See :func:`find_all`."""
    maps = find_all(image, **kwargs)
    if not maps:
        return None
    return max(maps, key=lambda m: cv2.contourArea(m.placement.quad.astype(np.float32)))


def foreground(image, **kwargs) -> np.ndarray:
    """Foreground coverage of the largest mark, ``(H, W) float32`` in ``[0, 1]``.

    All-zero if nothing is found -- the one-liner never raises on a miss, so it can be
    mapped over a directory. Use :func:`find` to tell "no mark" from "a mark with no
    foreground".
    """
    ink = find(image, **kwargs)
    if ink is None:
        return np.zeros(_as_bgr(image).shape[:2], dtype=np.float32)
    return ink.coverage


def _refine(gray: np.ndarray, placement: Placement) -> Placement:
    """Sub-pixel-refine a placement's transform, keeping the original on failure."""
    from dataclasses import replace

    transform, score = geometry.refine_transform(
        gray, placement.model, placement.transform
    )
    return replace(
        placement,
        transform=transform,
        quad=geometry.transform_to_quad(transform, placement.model).astype(np.float32),
        refined=bool(np.isfinite(score) and score >= config.ECC_MIN_CORRELATION),
        score=None if not np.isfinite(score) else float(score),
    )


def _coverage_for(
    gray: np.ndarray,
    placement: Placement,
    *,
    source: str,
    samples: int,
    polarity: Polarity,
) -> np.ndarray:
    if source == "modelled":
        cov = coverage_map(
            placement.model, placement.transform, gray.shape[:2], samples=samples
        )
        if polarity is Polarity.FOREGROUND_IS_LIGHT:
            inside = _coverage._inside(placement, gray.shape[:2])
            cov = np.where(inside, 1.0 - cov, 0.0).astype(np.float32)
        return cov
    if source == "observed":
        return observed_coverage(gray, placement, polarity=polarity)
    raise ValueError(f"source must be 'modelled' or 'observed', got {source!r}")
