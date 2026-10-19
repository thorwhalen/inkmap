"""Locate a plain printed patch -- a uniform colour rectangle -- and the substrate round it.

The other locators start from something with a decoder or from a quad you supply. A
single printed colour patch on a paper strip has neither: no code, no registration
marks, an arbitrary background. To measure the patch against its own paper, a caller
needs three things, and :func:`locate_patch` returns them::

    import inkmap

    regions = inkmap.locate_patch(photo)            # seeded at the frame's centre
    regions = inkmap.locate_patch(photo, seed=(x, y))
    regions.patch, regions.substrate, regions.ok, regions.notes

- ``patch``: the patch's interior, eroded clear of its blurred edge;
- ``substrate``: a narrow ring of bare substrate just outside it;
- ``ok`` and ``notes``: whether to trust them, and if not, why.

``regions.quad`` is the patch's four corners to a fraction of a pixel, and
``regions.placement`` the same as a :class:`~inkmap.types.Placement`, so the rest of
inkmap (``analyze``, ``measure``) works on a patch unchanged.

**How.** The patch colour is the median CIELAB colour of a small window round the
seed. Every pixel's distance to it is split by Otsu's threshold (clamped to a Delta E
range), and the connected region holding the seed window is kept, closed and filled.
Its sides are then fitted to the *colour* edge -- the mid-level crossing of that
Delta E image -- so a pale patch on white paper, whose lightness barely differs from
the paper's, is placed as precisely as a dark one.

**Substrate.** The ring lies between two distances from the patch, scaled to the
patch's own size, and keeps only its light, low-chroma pixels: a thin paper border is
easily overshot onto the background, which is why the ring is narrow by default. The
paper must also be lighter than the patch, and be found on at least three of its four
sides.

**The verdict** fails, with a note saying why, on a patch that is too small, not
four-sided, cut by the frame, without substrate on three sides, or without a colour
step across every side. That last check is what catches a pale patch that leaked into
shaded paper: the leaked boundary is a threshold's iso-line through the paper, with no
edge across it. On a failed verdict the region is split again at a tighter threshold,
which is how a pale patch on white paper is found at all; if no split passes, the
first answer is returned with the last split's reason appended.

**Limits.** The patch colour is one global seed colour, so strong uneven light defeats
a pale patch: with lightness falling 40% across the frame, a patch a Delta E of ~10
from its paper is mostly refused (correctly, but refused). Corners are good to about
0.2 px for a saturated patch and 0.5 px for a pale one at blur up to 1.5 px
(``python scripts/validate.py patch``).

**On flash bursts,** seed on an unlit frame (or the median of the unlit frames): under
flash a pale patch clips to the paper's white and the region leaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Sequence

import cv2
import numpy as np

from .. import config, geometry
from ..models import PolygonModel
from ..types import Placement
from .marks import _clockwise_from_top_left, _fit_quad

__all__ = ["PatchRegions", "locate_patch", "locate_patch_centre"]


@dataclass(frozen=True, eq=False)
class PatchRegions:
    """A located patch: masks over the frame, its geometry, and how far to trust them.

    ``patch`` is the interior, eroded clear of the edge; ``substrate`` a ring of bare
    substrate just outside; ``region`` the whole patch, uneroded. ``quad`` is the
    patch's corners, clockwise as seen on screen from the one nearest the image's
    top-left, to a fraction of a pixel when its sides could be fitted (``None`` if no
    region was found). ``ok`` is ``not notes``.
    """

    patch: np.ndarray
    substrate: np.ndarray
    region: np.ndarray
    quad: np.ndarray | None
    ok: bool
    notes: tuple[str, ...] = ()
    seed_lab: tuple[float, float, float] = (float("nan"),) * 3
    threshold_delta_e: float = float("nan")
    area_share: float = 0.0
    rectangularity: float = 0.0
    touches_border: bool = False
    metrics: dict = field(default_factory=dict, repr=False)

    @property
    def placement(self) -> Placement | None:
        """The patch and its substrate ring as a placement, or ``None`` without a quad.

        The model is the patch as foreground inside a border of background as wide as
        the substrate ring's outer edge, in units of about one pixel. So
        :func:`inkmap.analyze` and :func:`inkmap.measure` treat the patch as any other
        mark, and ``measure`` compares the patch with the substrate round it. The
        placement's ``quad`` is that bordered model's, not the patch's: the patch's own
        corners are :attr:`quad`. ``measure`` averages the whole border, background
        and all, where :attr:`substrate` keeps only its paper-like pixels: on a thin
        paper border, measure with :attr:`substrate` instead.
        """
        if self.quad is None:
            return None
        quad = np.asarray(self.quad, dtype=np.float64)
        width = (
            np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])
        ) / 2
        height = (
            np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])
        ) / 2
        border = float(self.metrics.get("ring_px", (0.0, 0.0))[1])
        inset = np.array(
            [
                [border, border],
                [border + width, border],
                [border + width, border + height],
                [border, border + height],
            ]
        )
        model = PolygonModel(
            [inset],
            extent_override=(width + 2 * border, height + 2 * border),
            metadata={"shape": "patch", "border_units": border},
        )
        transform = cv2.getPerspectiveTransform(
            inset.astype(np.float32), quad.astype(np.float32)
        ).astype(np.float64)
        return Placement(
            model=model,
            transform=transform,
            quad=geometry.transform_to_quad(transform, model).astype(np.float32),
            locator="patch",
            metadata={"ok": self.ok, "notes": self.notes, "patch_quad": quad},
        )


def locate_patch(
    image,
    *,
    seed: str | Sequence[float] = "centre",
    seed_share: float = config.PATCH_SEED_SHARE,
    min_delta_e: float = config.PATCH_MIN_DELTA_E,
    max_delta_e: float = config.PATCH_MAX_DELTA_E,
    edge_margin_share: float = config.PATCH_EDGE_MARGIN_SHARE,
    ring_share: tuple[float, float] = config.PATCH_RING_SHARE,
    min_area_share: float = config.PATCH_MIN_AREA_SHARE,
    min_rectangularity: float = config.PATCH_MIN_RECTANGULARITY,
    min_substrate_px: int = config.PATCH_MIN_SUBSTRATE_PX,
    min_substrate_lift: float = config.PATCH_MIN_SUBSTRATE_LIFT,
    max_substrate_chroma: float = config.PATCH_MAX_SUBSTRATE_CHROMA,
    min_side_share: float = config.PATCH_MIN_SIDE_SHARE,
    min_edge_step: float = config.PATCH_MIN_EDGE_STEP,
) -> PatchRegions:
    """The uniform patch at ``seed``, and the ring of substrate just outside it.

    ``image`` is a path, a BGR (or BGRA) array, or a grey array, 8-bit. ``seed`` is
    ``"centre"`` or an ``(x, y)`` pixel inside the patch; its colour is the median of a
    window ``seed_share`` of the frame's shorter side across. Pixels within the Otsu
    split of the CIELAB distance to it, clamped to ``[min_delta_e, max_delta_e]``, are
    candidates, and the connected candidate region at the seed is the patch.

    ``edge_margin_share`` erodes the interior, and ``ring_share`` places the
    substrate ring, both as shares of the patch's shorter side. The verdict fails, with
    a note saying why, when the patch is under ``min_area_share`` of the frame, less
    rectangular than ``min_rectangularity`` (area over its minimum-area rectangle's:
    where a pale patch leaked into the paper), cut by the frame's edge, or when the
    ring holds under ``min_substrate_px`` pixels of substrate, substrate no lighter than
    the patch by ``min_substrate_lift`` L*, or substrate on fewer than three sides
    (``min_side_share`` of that side's ring each), or when a side of the patch has no
    colour step of ``min_edge_step`` across it -- the sign of a region that leaked into
    shaded paper. A failed verdict on a leaked region is retried at a tighter
    threshold.
    """
    from .. import _as_bgr  # the facade's image coercion; lazy, as it imports us

    bgr = _as_bgr(image)
    if bgr.dtype != np.uint8:
        raise ValueError(f"locate_patch takes an 8-bit image, got {bgr.dtype}")
    h, w = bgr.shape[:2]
    colour = bgr.astype(np.float32)
    lab = cv2.cvtColor(colour / 255.0, cv2.COLOR_BGR2Lab)
    sx, sy = _seed_point(seed, w, h)
    half = max(1, int(round(seed_share * min(h, w) / 2)))
    window = (
        slice(max(sy - half, 0), sy + half + 1),
        slice(max(sx - half, 0), sx + half + 1),
    )
    seed_lab = np.median(lab[window].reshape(-1, 3), axis=0)
    distance = np.linalg.norm(lab - seed_lab, axis=-1).astype(np.float32)
    tau = float(
        np.clip(
            _otsu(np.minimum(distance, 3 * max_delta_e).ravel()),
            min_delta_e,
            max_delta_e,
        )
    )

    def assess(region: np.ndarray, tau: float) -> PatchRegions:
        return _assess(
            region,
            lab=lab,
            seed_lab=seed_lab,
            colour=colour,
            distance=distance,
            tau=tau,
            min_delta_e=min_delta_e,
            edge_margin_share=edge_margin_share,
            ring_share=ring_share,
            min_area_share=min_area_share,
            min_rectangularity=min_rectangularity,
            min_substrate_px=min_substrate_px,
            min_substrate_lift=min_substrate_lift,
            max_substrate_chroma=max_substrate_chroma,
            min_side_share=min_side_share,
            min_edge_step=min_edge_step,
        )

    region = _seeded_region(distance, tau, window)
    if region is None:
        empty = np.zeros((h, w), dtype=bool)
        notes = ("no patch-coloured pixels at the seed",)
        return PatchRegions(
            empty, empty, empty, None, False, notes, tuple(map(float, seed_lab)), tau
        )
    first = found = assess(region, tau)
    # Otsu splits the frame's strongest contrast first, which for a pale patch on white
    # paper over a dark table is strip-versus-table: the region is then patch and paper
    # together, and the verdict fails. Only then, split the region's own distances
    # again, tighter each time: under uneven light the first re-split can still hold a
    # shaded part of the paper, and the edge check refuses it. A split that only cuts
    # noise fails its verdict too, and the first answer stands.
    for _ in range(config.PATCH_MAX_RESPLITS):
        if found.ok:
            break
        inner_tau = max(_otsu_split(distance[found.region])[0], min_delta_e)
        if inner_tau >= tau:
            break
        tau = inner_tau
        region = _seeded_region(distance, tau, window)
        if region is None:
            break
        found = assess(region, tau)
    if found.ok or found is first:
        return found
    return replace(
        first,
        notes=first.notes
        + (
            f"re-split to Delta E {found.threshold_delta_e:.1f}: {'; '.join(found.notes)}",
        ),
    )


def _assess(
    region: np.ndarray,
    *,
    lab: np.ndarray,
    seed_lab: np.ndarray,
    colour: np.ndarray,
    distance: np.ndarray,
    tau: float,
    min_delta_e: float,
    edge_margin_share: float,
    ring_share: tuple[float, float],
    min_area_share: float,
    min_rectangularity: float,
    min_substrate_px: int,
    min_substrate_lift: float,
    max_substrate_chroma: float,
    min_side_share: float,
    min_edge_step: float,
) -> PatchRegions:
    """Fill a seeded region, fit its quad, build its masks and judge them."""
    h, w = region.shape
    region = cv2.morphologyEx(
        region,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    )
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contour = max(contours, key=cv2.contourArea)
    filled = np.zeros((h, w), dtype=np.uint8)
    cv2.drawContours(filled, [contour], -1, 1, thickness=-1)
    area = float(filled.sum())
    (_, _), (rw, rh), _ = cv2.minAreaRect(contour)
    x, y, bw, bh = cv2.boundingRect(contour)
    touches = x <= 0 or y <= 0 or x + bw >= w or y + bh >= h
    short = max(min(rw, rh), 1.0)

    # Distance outwards from the thresholded outline: where to look for the colour just
    # outside the patch, before its sides are fitted.
    outside = cv2.distanceTransform(1 - filled, cv2.DIST_L2, 5)
    # The sides are fitted to the image's own values (linear in what blur mixes), the
    # step check is made in CIELAB (perceptual, so one threshold serves every colour).
    quad = _patch_quad(
        contour,
        _edge_signal(
            colour, np.median(colour[filled.astype(bool)], axis=0), None, outside
        ),
        min_contrast=config.PATCH_MIN_EDGE_CONTRAST,
    )
    signal = _edge_signal(lab, seed_lab, distance, outside)
    # Against the fitted quadrilateral, not the minimum-area rectangle: a rectangle
    # seen in perspective is a trapezoid, and would score as low as a leaked region.
    rectangularity = area / max(_polygon_area(quad), 1.0)
    steps = _side_steps(signal, quad)
    # The interior and the ring are measured from the fitted sides, not from the
    # thresholded outline, which sits wherever the threshold cuts the blurred edge.
    beyond = _beyond_sides(quad, (h, w))
    patch = beyond < -max(1.0, edge_margin_share * short)
    inner = max(2.0, ring_share[0] * short)
    outer = max(inner + 3.0, ring_share[1] * short)
    ring = (beyond > inner) & (beyond <= outer)
    substrate = np.zeros((h, w), dtype=bool)
    if ring.any():
        # Split the ring's lightness only where it holds two populations (paper and a
        # darker background), not where shading spreads the paper's own lightness.
        split, gap = _otsu_split(lab[..., 0][ring])
        if gap < config.PATCH_SUBSTRATE_SPLIT_GAP:
            split = -np.inf
        chroma = np.hypot(lab[..., 1], lab[..., 2])
        substrate_like = (lab[..., 0] > split) & (chroma < max_substrate_chroma)
        # One pixel in from the substrate's own edge: pixels straddling paper and
        # background are neither.
        substrate_like = cv2.erode(
            substrate_like.astype(np.uint8), np.ones((3, 3), np.uint8)
        )
        substrate = ring & substrate_like.astype(bool)

    notes: list[str] = []
    area_share = area / (h * w)
    if area_share < min_area_share:
        notes.append(f"patch area {area_share:.1%} of the frame < {min_area_share:.0%}")
    if rectangularity < min_rectangularity:
        notes.append(f"rectangularity {rectangularity:.2f} < {min_rectangularity}")
    if touches:
        notes.append("patch region touches the frame edge")
    if min(steps) < min_edge_step:
        # A printed patch has a colour step on every side. A side with none is a
        # threshold's iso-line through shaded paper: the region leaked.
        notes.append(
            f"no colour edge on a side (step {min(steps):.1f} < {min_edge_step:.1f})"
        )
    if not patch.any():
        notes.append("no interior left after the edge margin")
    n_substrate = int(substrate.sum())
    if n_substrate < min_substrate_px:
        notes.append(f"substrate ring {n_substrate} px < {min_substrate_px}")
    elif (
        float(np.median(lab[..., 0][substrate]))
        <= float(seed_lab[0]) + min_substrate_lift
    ):
        # Paper is the lightest thing on the strip: "substrate" no lighter than the
        # patch is the table under a pale card that was taken for the patch.
        notes.append("substrate ring is not lighter than the patch")
    else:
        sides = _sides_with_substrate(ring, substrate, quad, filled, min_side_share)
        if sides < 3:
            notes.append(f"substrate found on {sides} of 4 sides")

    return PatchRegions(
        patch=patch,
        substrate=substrate,
        region=filled.astype(bool),
        quad=quad,
        ok=not notes,
        notes=tuple(notes),
        seed_lab=tuple(map(float, seed_lab)),
        threshold_delta_e=tau,
        area_share=area_share,
        rectangularity=float(rectangularity),
        touches_border=bool(touches),
        metrics={"substrate_px": n_substrate, "ring_px": (inner, outer)},
    )


def _edge_signal(values, seed_value, fallback, outside) -> np.ndarray:
    """A grey image whose mid-level crossing is the patch's colour edge.

    Each pixel's colour ``values`` projected onto the direction from the patch's colour
    ``seed_value`` to what lies just outside it. Linear in the colour, so a blurred
    edge's mid-level is where the edge is -- unlike the Delta E distance, which noise
    lifts near zero, pushing every side outwards on a low-contrast patch. ``fallback``
    (or the distance to the seed) when there is nothing outside to aim at.
    """
    band = (outside > config.PATCH_EDGE_BAND_PX[0]) & (
        outside <= config.PATCH_EDGE_BAND_PX[1]
    )
    direction = (
        np.median(values[band], axis=0) - seed_value if band.any() else np.zeros(3)
    )
    norm = float(np.linalg.norm(direction))
    if norm < 1e-6:
        if fallback is not None:
            return fallback
        return np.linalg.norm(values - seed_value, axis=-1).astype(np.float32)
    return ((values - seed_value) @ (direction / norm)).astype(np.float32)


def locate_patch_centre(bgr: np.ndarray, gray: np.ndarray) -> list[Placement]:
    """A :data:`~inkmap.locate.LOCATORS` strategy: the patch at the frame's centre.

    Registered as ``"patch"`` but not in the default cascade, so
    ``inkmap.find(photo, locators=["patch"])`` opts in. Returns nothing unless the
    verdict is ``ok``.
    """
    regions = locate_patch(bgr)
    return [regions.placement] if regions.ok and regions.quad is not None else []


def _seed_point(seed, w: int, h: int) -> tuple[int, int]:
    if isinstance(seed, str):
        if seed not in ("centre", "center"):
            raise ValueError(f"seed must be 'centre' or an (x, y) point, got {seed!r}")
        return w // 2, h // 2
    sx, sy = (int(round(float(v))) for v in seed)
    if not (0 <= sx < w and 0 <= sy < h):
        raise ValueError(f"seed {(sx, sy)} is outside the {w} x {h} frame")
    return sx, sy


def _seeded_region(distance: np.ndarray, tau: float, window) -> np.ndarray | None:
    """The connected region under ``tau`` holding most of the seed window, or None.

    Most of the window, not the seed pixel: one noisy pixel at the seed would
    otherwise lose the whole patch.
    """
    candidate = (distance < tau).astype(np.uint8)
    _, labels = cv2.connectedComponents(candidate, connectivity=4)
    in_window = labels[window][candidate[window].astype(bool)]
    if in_window.size == 0:
        return None
    return (labels == np.bincount(in_window).argmax()).astype(np.uint8)


def _otsu_split(values: np.ndarray) -> tuple[float, float]:
    """Otsu's threshold of ``values``, and how far apart the two classes' means are."""
    if values.size < 2 or np.ptp(values) == 0:
        return float("inf"), 0.0
    tau = _otsu(values)
    below, above = values[values < tau], values[values >= tau]
    if below.size == 0 or above.size == 0:
        return tau, 0.0
    return tau, float(above.mean() - below.mean())


def _otsu(values: np.ndarray, *, bins: int = 128) -> float:
    """Otsu's threshold of a 1-D sample: the split maximising between-class variance."""
    hist, edges = np.histogram(values, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    weight = np.cumsum(hist)
    mean = np.cumsum(hist * centres)
    w0, w1 = weight[:-1], weight[-1] - weight[:-1]
    valid = (w0 > 0) & (w1 > 0)
    between = np.zeros_like(w0, dtype=float)
    m0 = mean[:-1][valid] / w0[valid]
    m1 = (mean[-1] - mean[:-1][valid]) / w1[valid]
    between[valid] = w0[valid] * w1[valid] * (m0 - m1) ** 2
    return float(centres[int(np.argmax(between))])


def _patch_quad(contour: np.ndarray, distance: np.ndarray, *, min_contrast: float):
    """The patch's corners: sides fitted to the colour edge, else the polygon's vertices.

    Falls back to the minimum-area rectangle when the outline is not four-sided.
    """
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(
        contour, config.PATCH_POLY_EPSILON_SHARE * perimeter, True
    )
    if len(approx) == 4 and cv2.isContourConvex(approx):
        fit = _fit_quad(
            contour,
            approx,
            distance,
            min_contrast=min_contrast,
            level_window=config.PATCH_EDGE_LEVEL_WINDOW,
        )
        corners = fit[0] if fit is not None else approx.reshape(4, 2).astype(float)
    else:
        corners = cv2.boxPoints(cv2.minAreaRect(contour)).astype(float)
    return _clockwise_from_top_left(corners)


def _beyond_sides(quad: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """How far each pixel centre lies outside the convex ``quad``, in pixels.

    Negative inside: minus the distance to the nearest side, exactly. Outside: the
    distance past the furthest side, which is exact off a side and squares off the
    corners (a ring built from it has square corners).
    """
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    centroid = quad.mean(axis=0)
    beyond = np.full((h, w), -np.inf, dtype=np.float32)
    for a, b in zip(quad, np.roll(quad, -1, axis=0)):
        d = b - a
        normal = np.array([-d[1], d[0]]) / max(float(np.linalg.norm(d)), 1e-9)
        if normal @ ((a + b) / 2 - centroid) < 0:
            normal = -normal
        np.maximum(
            beyond,
            (xx - a[0]) * normal[0] + (yy - a[1]) * normal[1],
            out=beyond,
        )
    return beyond


def _polygon_area(corners: np.ndarray) -> float:
    x, y = corners[:, 0], corners[:, 1]
    return float(abs(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) / 2.0)


def _side_steps(signal: np.ndarray, quad: np.ndarray) -> list[float]:
    """The colour step across each side: median signal just outside minus inside.

    Sampled at ``PATCH_EDGE_STEP_OFFSET_PX`` either side of the side's line, along its
    middle part (clear of the corners).
    """
    lo, hi = config.PATCH_EDGE_STEP_OFFSET_PX
    centroid = quad.mean(axis=0)
    steps = []
    for a, b in zip(quad, np.roll(quad, -1, axis=0)):
        d = b - a
        length = float(np.linalg.norm(d))
        if length < 1e-6:
            steps.append(0.0)
            continue
        normal = np.array([-d[1], d[0]]) / length
        if normal @ ((a + b) / 2 - centroid) < 0:
            normal = -normal  # pointing out of the patch
        t = np.linspace(0.2, 0.8, max(8, int(length * 0.6)))[:, None]
        on_line = a + t * d
        offsets = np.linspace(lo, hi, 3)

        def sample(sign):
            xy = (on_line[:, None, :] + sign * offsets[None, :, None] * normal).reshape(
                -1, 2
            )
            return cv2.remap(
                signal,
                xy[:, 0].astype(np.float32).reshape(1, -1),
                xy[:, 1].astype(np.float32).reshape(1, -1),
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )

        steps.append(float(np.median(sample(+1)) - np.median(sample(-1))))
    return steps


def _sides_with_substrate(ring, substrate, quad, filled, min_side_share) -> int:
    """On how many of the patch's four sides the ring holds enough substrate."""
    ry, rx = np.nonzero(ring)
    if quad is not None:
        # Each ring pixel belongs to the side whose line it is nearest.
        pts = np.stack([rx, ry], axis=1).astype(float)
        a, b = quad, np.roll(quad, -1, axis=0)
        d = b - a
        normals = (
            np.stack([-d[:, 1], d[:, 0]], axis=1) / np.linalg.norm(d, axis=1)[:, None]
        )
        off_line = np.einsum("pkj,kj->pk", pts[:, None, :] - a[None], normals)
        side = np.argmin(np.abs(off_line), axis=1)
    else:
        ys, xs = np.nonzero(filled)
        angle = np.arctan2(ry - ys.mean(), rx - xs.mean())
        side = ((angle + np.pi / 4) // (np.pi / 2)).astype(int) % 4
    kept = substrate[ry, rx]
    return sum(
        1
        for k in range(4)
        if (side == k).any() and kept[side == k].mean() >= min_side_share
    )
