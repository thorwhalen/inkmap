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

__all__ = [
    "Scene",
    "render",
    "qr_model",
    "default_matrix",
    "degrade",
    "nested_square",
    "mark_sheet",
    "PatchScene",
    "render_patch",
]

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


def nested_square(side: int, rings: tuple[float, ...] = ()) -> np.ndarray:
    """A square mark as a ``(side, side)`` cell grid: foreground, then alternating rings.

    ``rings`` are the sides of the nested squares as fractions of ``side``, outermost
    first, alternating background and foreground. Each must leave an equal whole number
    of cells on both sides, or the mark would be off-centre -- that is an error.

    >>> nested_square(7, (5 / 7, 3 / 7)).astype(int)[3]
    array([1, 0, 1, 1, 1, 0, 1])
    """
    cells = np.ones((side, side), dtype=bool)
    for k, ratio in enumerate(rings):
        inner = round(side * ratio)
        offset, odd = divmod(side - inner, 2)
        if odd or abs(inner - side * ratio) > 1e-9:
            raise ValueError(
                f"a {side}-cell mark cannot hold a centred ring of {ratio} "
                f"({side * ratio} cells); choose a side that makes it whole"
            )
        cells[offset : offset + inner, offset : offset + inner] = k % 2 == 1
    return cells


def mark_sheet() -> tuple[MatrixModel, list[tuple[tuple[float, float], tuple]]]:
    """A card of square registration marks, and where each one's centre truly is.

    Three bullseyes and a solid square at the corners, as on an OMR form, and two QR
    finder patterns inside: 700 x 500 cells, marks 50 cells (42 for a finder). Render it
    with :func:`render` at about 1.2 pixels per cell for ~60 px marks. Returns
    ``(model, truth)``, ``truth`` being ``(centre_uv, rings)`` per mark in model units,
    so ``cv2.perspectiveTransform`` through a scene's transform gives the true image
    centres.
    """
    from .locate.marks import BULLSEYE_RINGS, QR_FINDER_RINGS

    cells = np.zeros((500, 700), dtype=bool)
    truth = []
    bullseye = nested_square(50, BULLSEYE_RINGS)
    finder = np.kron(nested_square(7, QR_FINDER_RINGS), np.ones((6, 6), dtype=bool))
    layout = [
        (bullseye, 30, 30, BULLSEYE_RINGS),
        (bullseye, 30, 620, BULLSEYE_RINGS),
        (bullseye, 420, 30, BULLSEYE_RINGS),
        (np.ones((50, 50), dtype=bool), 420, 620, ()),
        (finder, 200, 250, QR_FINDER_RINGS),
        (finder, 250, 400, QR_FINDER_RINGS),
    ]
    for block, row, col, rings in layout:
        rows, cols = block.shape
        cells[row : row + rows, col : col + cols] = block
        truth.append(((col + cols / 2.0, row + rows / 2.0), rings))
    return MatrixModel(cells, metadata={"target": "square registration marks"}), truth


@dataclass(frozen=True)
class PatchScene:
    """A synthetic colour photograph of a printed patch on a paper strip, and its truth."""

    image: np.ndarray
    """(H, W, 3) uint8 BGR."""

    patch_quad: np.ndarray
    """(4, 2) true image corners of the patch, clockwise from its top-left."""

    paper_quad: np.ndarray
    """(4, 2) true image corners of the paper strip, in the same order."""

    params: dict[str, Any] = field(default_factory=dict)


def render_patch(
    *,
    size: tuple[int, int] = (600, 800),
    patch_bgr: tuple[float, float, float] = (60.0, 110.0, 200.0),
    paper_bgr: tuple[float, float, float] = (232.0, 236.0, 238.0),
    background_bgr: tuple[float, float, float] = (70.0, 80.0, 95.0),
    patch_size: tuple[float, float] = (40.0, 24.0),
    paper_size: tuple[float, float] = (100.0, 32.0),
    pixels_per_unit: float = 6.0,
    centre: tuple[float, float] | None = None,
    perspective: float = 0.0,
    rotation: float = 0.0,
    blur: float = 0.0,
    noise: float = 0.0,
    gradient: float = 0.0,
    background_texture: float = 0.0,
    supersample: int = 8,
    rng: np.random.Generator | int | None = None,
) -> PatchScene:
    """Render a uniform colour patch centred on a paper strip, over a background.

    Model space is the strip's own, in units: a ``paper_size`` strip with a
    ``patch_size`` patch at its centre, mapped into the frame at ``pixels_per_unit``
    around ``centre`` (the frame's centre by default), then rotated by ``rotation``
    degrees and its corners jittered by ``perspective`` of the strip's span. Edges are
    anti-aliased by drawing at ``supersample`` times the resolution and area-averaging,
    so the true patch quad is exact to that sampling. ``background_texture`` adds
    low-frequency blotches of that many grey levels to the background (a table, a
    cloth). Degradations then apply per channel, as in :func:`degrade`.
    """
    rng = np.random.default_rng(rng)
    height, width = size
    cx, cy = (width / 2.0, height / 2.0) if centre is None else centre
    pw, ph = paper_size
    qw, qh = patch_size

    def rect(w, h):
        return np.array(
            [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]],
            dtype=np.float64,
        )

    paper_uv, patch_uv = rect(pw, ph), rect(qw, qh)
    dst = paper_uv * pixels_per_unit
    theta = np.deg2rad(rotation)
    c, s_ = np.cos(theta), np.sin(theta)
    dst = dst @ np.array([[c, -s_], [s_, c]]).T + (cx, cy)
    if perspective:
        reach = perspective * max(pw, ph) * pixels_per_unit
        dst = dst + rng.uniform(-reach, reach, (4, 2))
    transform = cv2.getPerspectiveTransform(
        paper_uv.astype(np.float32), dst.astype(np.float32)
    )

    def to_image(uv):
        return cv2.perspectiveTransform(
            uv.reshape(-1, 1, 2).astype(np.float64), transform
        ).reshape(4, 2)

    paper_quad, patch_quad = to_image(paper_uv), to_image(patch_uv)

    k = int(supersample)
    image = np.empty((height, width, 3), dtype=np.float32)
    image[:] = background_bgr
    if background_texture:
        blotches = cv2.resize(
            rng.normal(0.0, 1.0, (max(2, height // 40), max(2, width // 40))),
            (width, height),
            interpolation=cv2.INTER_CUBIC,
        )
        image += (background_texture * blotches)[..., None].astype(np.float32)

    def fill(quad, colour):
        # Blend ``colour`` in by the exact area coverage of each pixel, from centre
        # sampling k x k sub-pixels: one is inside when its centre is on the inner side
        # of all four edges. Sub-pixel j of pixel x is centred at x - 0.5 + (j + 0.5)/k.
        # (cv2.fillConvexPoly includes both boundary rows, which would widen the right
        # and bottom edges by a sub-pixel.) Only the quad's bounding box is sampled.
        lo = np.maximum(np.floor(quad.min(axis=0)).astype(int) - 1, 0)
        hi = np.minimum(
            np.ceil(quad.max(axis=0)).astype(int) + 1, (width - 1, height - 1)
        )
        if (hi < lo).any():
            return
        offsets = (np.arange(k) + 0.5) / k - 0.5
        gx = (np.arange(lo[0], hi[0] + 1)[:, None] + offsets).ravel()
        orientation = np.sign(
            np.sum(
                quad[:, 0] * np.roll(quad[:, 1], -1)
                - np.roll(quad[:, 0], -1) * quad[:, 1]
            )
        )
        colour = np.asarray(colour, np.float32)
        cols = hi[0] - lo[0] + 1
        for top in range(lo[1], hi[1] + 1, 16):  # row chunks keep memory bounded
            bottom = min(top + 16, hi[1] + 1)
            gy = (np.arange(top, bottom)[:, None] + offsets).ravel()
            inside = np.ones((gy.size, gx.size), dtype=bool)
            for (ax, ay), (bx, by) in zip(quad, np.roll(quad, -1, axis=0)):
                cross = (bx - ax) * (gy[:, None] - ay) - (by - ay) * (gx[None, :] - ax)
                inside &= orientation * cross >= 0
            coverage = inside.reshape(bottom - top, k, cols, k).mean(axis=(1, 3))
            block = image[top:bottom, lo[0] : hi[0] + 1]
            block[:] = block * (1 - coverage[..., None]) + colour * coverage[..., None]

    fill(paper_quad, paper_bgr)
    fill(patch_quad, patch_bgr)
    channels = [
        degrade(
            image[..., i],
            blur=blur,
            noise=noise,
            gradient=gradient,
            rng=int(rng.integers(1 << 31)),
        )
        for i in range(3)
    ]
    return PatchScene(
        image=np.dstack(channels),
        patch_quad=patch_quad,
        paper_quad=paper_quad,
        params=dict(
            size=size,
            patch_bgr=patch_bgr,
            paper_bgr=paper_bgr,
            pixels_per_unit=pixels_per_unit,
            perspective=perspective,
            rotation=rotation,
            blur=blur,
            noise=noise,
            gradient=gradient,
        ),
    )


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
