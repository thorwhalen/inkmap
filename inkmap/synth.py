"""Synthetic scenes with exact ground truth.

Real photographs cannot validate a coverage map. Nobody can hand-label what fraction of
a pixel is foreground, and no public dataset carries per-pixel coverage ground truth for
printed marks -- the document-binarisation benchmarks (DIBCO) are binary. So the only
way to measure whether a 0..1 output is *right* is to render scenes whose true coverage
is known analytically.

The trick that makes it exact: render the image *from* the coverage map. Supersample the
model through a known transform to get true coverage, then form the clean image as
``255 * (1 - coverage)``. Ground truth and stimulus are the same object by construction,
and any degradation applied afterwards (blur, noise, gradient, glare, JPEG) leaves the
ground truth correct.

Works for any model, so a text or logo pipeline is validated the same way as a QR one.
Real photographs remain essential for *detection* rate -- see :mod:`inkmap.corpus`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from . import config
from .coverage import coverage_map
from .geometry import model_quad
from .models import MatrixModel, Model

__all__ = ["Scene", "render", "qr_model", "default_matrix", "degrade"]

_DEFAULT_MATRIX_PATH = Path(__file__).parent / "data" / "default_qr.txt"


@dataclass(frozen=True)
class Scene:
    """A synthetic image together with the truth used to make it."""

    image: np.ndarray
    """(H, W) uint8 grayscale."""

    coverage: np.ndarray
    """(H, W) float32 exact foreground area coverage."""

    transform: np.ndarray
    """(3, 3) true model -> image mapping."""

    model: Model
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def quad(self) -> np.ndarray:
        return cv2.perspectiveTransform(
            model_quad(self.model).reshape(-1, 1, 2), self.transform
        ).reshape(4, 2)


def default_matrix() -> np.ndarray:
    """The shipped QR module matrix (a real version-3 symbol), True = dark module.

    Shipped so that :func:`render` -- and therefore the test suite and every example --
    works on a bare ``pip install inkmap``, with no optional dependency.
    """
    rows = [
        line.strip()
        for line in _DEFAULT_MATRIX_PATH.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return np.array([[c == "1" for c in row] for row in rows], dtype=bool)


def qr_model(payload: str | None = None, *, error: str = "m") -> MatrixModel:
    """A QR :class:`~inkmap.models.MatrixModel`, from ``payload`` via segno.

    With no payload, uses the shipped matrix and needs no dependency. Uses
    ``segno.make_qr`` rather than ``segno.make``: the latter may return a Micro QR for
    short payloads, a different symbology with different module counts.
    """
    if payload is None:
        return MatrixModel(default_matrix(), metadata={"symbology": "QR Code"})
    try:
        import segno
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            f"generating a QR for {payload!r} needs segno -- pip install 'inkmap[synth]', "
            "or call qr_model() with no payload for the shipped one"
        ) from exc
    qr = segno.make_qr(payload, error=error)
    cells = np.array([[bool(v) for v in row] for row in qr.matrix], dtype=bool)
    return MatrixModel(cells, metadata={"symbology": "QR Code", "payload": payload})


def render(
    model: Model | None = None,
    *,
    size: int | tuple[int, int] = 800,
    pixels_per_unit: float = 10.0,
    perspective: float = 0.0,
    rotation: float = 0.0,
    blur: float = 0.0,
    noise: float = 0.0,
    gradient: float = 0.0,
    glare: float = 0.0,
    jpeg_quality: int | None = None,
    samples: int = config.SUPERSAMPLES,
    rng: np.random.Generator | int | None = None,
) -> Scene:
    """Render one synthetic photograph of ``model`` with exact ground-truth coverage.

    Degradations are applied in capture order -- geometry, then optics (blur, glare),
    then illumination, then sensor noise, then compression -- because any other order
    models a camera that does not exist. ``perspective`` jitters the four corners by
    that fraction of the mark's span; ``rotation`` is in degrees; ``gradient`` is the
    fractional illumination falloff across the frame.
    """
    rng = np.random.default_rng(rng)
    model = qr_model() if model is None else model
    height, width = (size, size) if isinstance(size, int) else size

    mw, mh = model.extent
    span_x, span_y = mw * pixels_per_unit, mh * pixels_per_unit
    ox, oy = (width - span_x) / 2.0, (height - span_y) / 2.0

    dst = np.array(
        [[ox, oy], [ox + span_x, oy], [ox + span_x, oy + span_y], [ox, oy + span_y]],
        dtype=np.float32,
    )
    if rotation:
        theta = np.deg2rad(rotation)
        c, s = np.cos(theta), np.sin(theta)
        center = np.array([width / 2.0, height / 2.0], dtype=np.float32)
        dst = (dst - center) @ np.array([[c, -s], [s, c]], dtype=np.float32).T + center
    if perspective:
        reach = perspective * max(span_x, span_y)
        dst = dst + rng.uniform(-reach, reach, (4, 2)).astype(np.float32)

    transform = cv2.getPerspectiveTransform(model_quad(model), dst.astype(np.float32))
    coverage = coverage_map(model, transform, (height, width), samples=samples)

    image = degrade(
        255.0 * (1.0 - coverage),
        blur=blur,
        noise=noise,
        gradient=gradient,
        glare=glare,
        jpeg_quality=jpeg_quality,
        rng=rng,
    )

    return Scene(
        image=image,
        coverage=coverage,
        transform=transform.astype(np.float64),
        model=model,
        params=dict(
            size=(height, width),
            pixels_per_unit=pixels_per_unit,
            perspective=perspective,
            rotation=rotation,
            blur=blur,
            noise=noise,
            gradient=gradient,
            glare=glare,
            jpeg_quality=jpeg_quality,
        ),
    )


def degrade(
    image: np.ndarray,
    *,
    blur: float = 0.0,
    noise: float = 0.0,
    gradient: float = 0.0,
    glare: float = 0.0,
    jpeg_quality: int | None = None,
    rng: np.random.Generator | int | None = None,
) -> np.ndarray:
    """Apply a capture-order degradation chain to a float image, returning uint8."""
    rng = np.random.default_rng(rng)
    x = image.astype(np.float32)
    h, w = x.shape[:2]

    if blur:
        x = cv2.GaussianBlur(x, (0, 0), blur)
    if glare:
        yy, xx = np.mgrid[0:h, 0:w]
        cx, cy = rng.uniform(0.2, 0.8, 2) * [w, h]
        radius = max(h, w) * rng.uniform(0.1, 0.25)
        x = x + glare * 255.0 * np.exp(
            -(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * radius**2))
        )
    if gradient:
        yy, xx = np.mgrid[0:h, 0:w]
        x = x * (1.0 - gradient * (xx / w * 0.6 + yy / h * 0.4))
    if noise:
        x = x + rng.normal(0.0, noise, x.shape)

    out = np.clip(x, 0, 255).astype(np.uint8)
    if jpeg_quality is not None:
        ok, buf = cv2.imencode(
            ".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
        )
        if ok:
            out = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    return out
