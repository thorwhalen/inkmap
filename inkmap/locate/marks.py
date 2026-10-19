"""Find square registration marks: solid squares and nested squares, sub-pixel.

The other locators here find marks that have a decoder. Printed targets also carry
plain registration marks -- a solid square, or a bullseye of nested squares at each
corner of a sheet, as on OMR forms -- and pose estimation needs their centres to a small
fraction of a pixel. :func:`find_square_marks` finds them::

    from inkmap.locate import BULLSEYE_RINGS, find_square_marks

    marks = find_square_marks(gray)
    bullseyes = [m for m in marks if m.ring_error(BULLSEYE_RINGS) < 0.06]
    bullseyes[0].centre, bullseyes[0].sigma_px

It knows what a square mark looks like, not which mark is which on a particular layout:
naming them, by ring ratio and by where they sit relative to each other, is the
caller's.

A **nested** mark is a foreground square holding a background square holding a
foreground square. A bullseye (rings at 0.64 and 0.32 of the side) and a QR symbol's
finder pattern (7:5:3 modules) are both of this kind, and they are told apart by their
ring ratios, which perspective barely changes. A **solid** mark is a foreground square
with nothing inside it, and reports no rings.

**Centres are projective.** The centre of a square seen in perspective is where its
image's diagonals cross, not the centroid of its pixels, which is pulled towards the
near side. Each side is fitted as a line to its contour points, the corners are the
lines' intersections, and the centre is where the diagonals cross. A threshold that
grows or shrinks the foreground moves all four sides alike and leaves that intersection
in place, which is what makes the centre robust to exposure and blur.

**Uncertainty.** Each mark carries ``sigma_px``, an estimate of how far its centre is
from the truth: the scatter of the side fits over the square root of the points per
side, combined with the disagreement between the centres of a nested mark's squares. A
nested mark's centre is the side-weighted mean of its squares' centres, which
perspective maps to one point. For a solid mark there are no rings to disagree, so the
figure understates damage that keeps the outline straight (a glare bite, heavy blur). A
mark cut by the frame's edge is dropped, never measured.

**Limits.** Each ring must be several blur widths across to survive binarisation: at
blur 1.5 px a bullseye needs roughly 40 px or more, a solid square 10 px. A mark wider
than the local-mean window (``local_window_share`` of the frame) is hollowed by its own
ink and missed. A disc under about 10 px radius fits four lines as well as a square of
its size does, so it cannot be told from one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .. import config
from ..types import Polarity

__all__ = [
    "SquareMark",
    "find_square_marks",
    "ring_ratios",
    "quad_centre",
    "BULLSEYE_RINGS",
    "QR_FINDER_RINGS",
]

#: Side of each inner square of a bullseye as a fraction of the outer: background at
#: 0.64, foreground at 0.32.
BULLSEYE_RINGS = (0.64, 0.32)

#: A QR finder pattern: 7 modules of foreground, 5 of background, 3 of foreground
#: (ISO/IEC 18004 §6.3.3).
QR_FINDER_RINGS = (5 / 7, 3 / 7)


@dataclass(frozen=True, eq=False)
class SquareMark:
    """One square mark found in an image. Coordinates are pixels, ``(x, y)``.

    ``corners`` are the outer square's, clockwise as seen on screen, starting from the
    one nearest the image's top-left. A square has no intrinsic first corner, so that
    order is a convention, not an identification. ``rings`` is the side of each nested
    square as a fraction of the outer one, outermost first (empty for a solid mark).
    ``centres`` are the outer square's centre followed by each nested square's, each
    where that square's diagonals cross; ``centre`` is their mean weighted by side,
    which for a solid mark is the outer square's own.
    """

    centre: tuple[float, float]
    corners: np.ndarray  # (4, 2)
    side_px: float
    rings: tuple[float, ...] = ()
    sigma_px: float = float("nan")
    centres: tuple[tuple[float, float], ...] = field(default=(), repr=False)

    @property
    def is_solid(self) -> bool:
        return not self.rings

    def ring_error(self, expected: tuple[float, ...]) -> float:
        """Largest difference between these ring ratios and ``expected``; inf if unlike.

        >>> SquareMark((0, 0), np.zeros((4, 2)), 10.0, rings=(0.7, 0.4)).ring_error(
        ...     QR_FINDER_RINGS
        ... )  # doctest: +ELLIPSIS
        0.028...
        >>> SquareMark((0, 0), np.zeros((4, 2)), 10.0).ring_error(BULLSEYE_RINGS)
        inf
        """
        if len(self.rings) != len(expected):
            return math.inf
        return max(abs(a - b) for a, b in zip(self.rings, expected))


def quad_centre(corners) -> tuple[float, float] | None:
    """Where the diagonals of a quadrilateral cross: the projective centre of a square.

    ``corners`` must be in cyclic order (either direction). ``None`` if degenerate.

    >>> quad_centre([(0, 0), (4, 0), (4, 2), (0, 2)])
    (2.0, 1.0)
    """
    c = np.asarray(corners, float).reshape(4, 2)
    hit = _line_intersection((c[0], c[2] - c[0]), (c[1], c[3] - c[1]))
    return None if hit is None else (float(hit[0]), float(hit[1]))


def ring_ratios(outer_area: float, inner_areas) -> tuple[float, ...]:
    """Side ratios of nested squares from their areas: ``sqrt(inner / outer)``.

    >>> ring_ratios(100.0, (64.0, 16.0))
    (0.8, 0.4)
    """
    return tuple(math.sqrt(a / outer_area) for a in inner_areas)


def find_square_marks(
    gray: np.ndarray,
    *,
    min_side_px: float = 8.0,
    max_side_share: float = 0.25,
    polarity: Polarity = Polarity.FOREGROUND_IS_DARK,
    dark_share: float = config.MARK_DARK_SHARE,
    min_contrast: float = config.MARK_MIN_CONTRAST,
    local_window_share: float = config.MARK_LOCAL_WINDOW_SHARE,
) -> list[SquareMark]:
    """Every solid or nested square mark in ``gray`` (2-D, 0-255 scale), largest first.

    A mark's outer square must be at least ``min_side_px`` on a side and at most
    ``max_side_share`` of the frame's shorter side. Nested marks report their ring
    ratios; solid marks report none. ``polarity`` says whether the marks read darker
    than the substrate (the usual case) or brighter.

    The foreground is binarised relative to the local mean brightness: a pixel is
    foreground when it is darker than ``dark_share`` of the mean over a window
    ``local_window_share`` of the frame's shorter side, and darker by at least
    ``min_contrast`` grey levels.
    """
    g = np.asarray(gray, dtype=np.float32)
    if g.ndim != 2:
        raise ValueError(
            f"find_square_marks takes a 2-D grey image, got shape {g.shape}"
        )
    if not Polarity(polarity).foreground_is_dark():
        g = 255.0 - g
    h, w = g.shape
    window = max(15, int(local_window_share * min(h, w)) | 1)
    local = cv2.blur(g, (window, window))
    foreground = (g < dark_share * local) & (local - g > min_contrast)
    contours, hierarchy, quads = _quads(
        foreground.astype(np.uint8) * 255,
        g,
        min_side_px=min(min_side_px, config.MARK_MIN_QUAD_SIDE_PX),
        min_contrast=min_contrast,
    )
    if hierarchy is None:
        return []
    max_side = max_side_share * min(h, w)

    # The inner foreground square of a nested mark is not a mark of its own. Only a
    # square whose one hole holds exactly one square is a nested mark: the dark band a
    # table or a shadow makes round a whole sheet also has the sheet as its hole, and
    # every mark on the sheet inside it. A mark-sized square hole holding one square
    # marks its child as inner too, so that a nested mark whose outer square is lost
    # (cut by the frame, bitten by glare) is dropped, not reported as a solid mark.
    nested_inner: set[int] = set()
    for i in quads:
        holes = _children(hierarchy, i)
        if len(holes) == 1:
            inner = [c for c in _children(hierarchy, holes[0]) if c in quads]
            if len(inner) == 1:
                nested_inner.add(inner[0])
        if _depth(hierarchy, i) % 2 and np.sqrt(quads[i][1]) <= max_side:
            inner = [c for c in _children(hierarchy, i) if c in quads]
            if len(inner) == 1:
                nested_inner.add(inner[0])

    marks = []
    for i, ((corners, resid, n_side), area) in quads.items():
        if i in nested_inner or _depth(hierarchy, i) % 2:
            continue  # an inner square, or (odd depth) the boundary of a hole
        side = float(np.sqrt(area))
        if not min_side_px <= side <= max_side:
            continue
        centre = quad_centre(corners)
        if centre is None:
            continue
        min_hole_area = config.MARK_MIN_HOLE_AREA_SHARE * cv2.contourArea(contours[i])
        holes = [
            c
            for c in _children(hierarchy, i)
            if cv2.contourArea(contours[c]) > min_hole_area
        ]
        rings: tuple[float, ...] = ()
        centres = [centre]
        if holes:
            if len(holes) != 1 or holes[0] not in quads:
                continue  # several holes, or a hole that is not a square: not a mark
            hole = holes[0]
            (hole_corners, _, _), hole_area = quads[hole]
            inner = [c for c in _children(hierarchy, hole) if c in quads]
            if len(inner) != 1:
                continue
            (inner_corners, _, _), inner_area = quads[inner[0]]
            rings = ring_ratios(area, (hole_area, inner_area))
            centres += [quad_centre(hole_corners), quad_centre(inner_corners)]
            if None in centres:
                continue
        # Concentric squares share one centre, and so do their images under any
        # homography: each square's diagonals estimate the same point. Weigh each by
        # its side, which is how many edge points went into its corners.
        points = np.array(centres)
        weights = np.array((1.0, *rings))
        best = weights @ points / weights.sum()
        spread = float(np.max(np.linalg.norm(points - best, axis=1)))
        marks.append(
            SquareMark(
                centre=(float(best[0]), float(best[1])),
                corners=_clockwise_from_top_left(corners),
                side_px=side,
                rings=rings,
                sigma_px=math.hypot(resid / math.sqrt(max(n_side, 1)), spread),
                centres=tuple(centres),
            )
        )
    marks.sort(key=lambda m: -m.side_px)
    return marks


def _line_intersection(l1, l2):
    """Intersection of two lines given as ``(point, direction)``; None if parallel."""
    (p, d), (q, e) = l1, l2
    a = np.array([[d[0], -e[0]], [d[1], -e[1]]], dtype=float)
    if abs(np.linalg.det(a)) < 1e-12:
        return None
    s, _ = np.linalg.solve(a, np.asarray(q, float) - np.asarray(p, float))
    return np.asarray(p, float) + s * np.asarray(d, float)


def _clockwise_from_top_left(corners: np.ndarray) -> np.ndarray:
    """Reorder cyclic corners clockwise on screen (y down), nearest the origin first."""
    c = np.asarray(corners, float).reshape(4, 2)
    x, y = c[:, 0], c[:, 1]
    if float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) < 0:
        c = c[::-1]
    return np.roll(c, -int(np.argmin(c.sum(axis=1))), axis=0)


def _fit_quad(
    contour: np.ndarray, approx: np.ndarray, gray: np.ndarray, *, min_contrast
):
    """Refine a four-vertex polygon into four sub-pixel side lines and their corners.

    Each side is first fitted to its contour points, leaving out the ends near the
    corners, then refined against the grey image by :func:`_refine_side`. Returns
    ``(corners, residual_px, min_points_per_side)``, or ``None`` when a side has too
    few points to fit or two fitted sides are parallel.
    """
    pts = contour.reshape(-1, 2).astype(float)
    verts = approx.reshape(4, 2).astype(float)
    # Index of the contour point nearest each vertex, in contour order.
    idx = [int(np.argmin(((pts - v) ** 2).sum(axis=1))) for v in verts]
    n = len(pts)
    lines, residuals, counts = [], [], []
    for k in range(4):
        a, b = idx[k], idx[(k + 1) % 4]
        side = pts[[(a + j) % n for j in range((b - a) % n + 1)]]
        trim = int(round(config.MARK_CORNER_TRIM_SHARE * len(side)))
        if len(side) - 2 * trim >= 3:
            side = side[trim : len(side) - trim]
        if len(side) < 3:
            return None
        line = _fit_line(side)
        half = min(
            config.MARK_EDGE_PROFILE_PX, config.MARK_EDGE_PROFILE_SHARE * len(side)
        )
        for _ in range(config.MARK_EDGE_ITERATIONS):
            refined = _refine_side(gray, line, half=half, min_contrast=min_contrast)
            if refined is None:
                break
            line = refined
        centre, direction, _, _, resid, count = line
        residuals.append(resid)
        counts.append(count)
        lines.append((centre, direction))
    corners = []
    for k in range(4):
        hit = _line_intersection(lines[k - 1], lines[k])
        if hit is None:
            return None
        corners.append(hit)
    resid = float(np.sqrt(np.mean(np.square(residuals))))
    return np.array(corners), resid, min(counts)


def _fit_line(points: np.ndarray):
    """Total-least-squares line through ``points``.

    Returns ``(centre, direction, s0, s1, rms_residual, n)``, where ``[s0, s1]`` is the
    span the points cover along ``direction`` from ``centre``.
    """
    centre = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - centre)
    direction, normal = vt[0], vt[1]
    along = (points - centre) @ direction
    resid = float(np.sqrt(np.mean(((points - centre) @ normal) ** 2)))
    return centre, direction, float(along.min()), float(along.max()), resid, len(points)


def _refine_side(gray: np.ndarray, line, *, half: float, min_contrast: float):
    """Move a side's line onto the grey image's mid-level edge, to a fraction of a pixel.

    A line fitted to contour pixels inherits their quantisation: on an edge that runs
    nearly along the pixel grid the error does not average out, and reaches half a
    pixel. So sample the grey profile across the line, one profile per pixel along it,
    find where each crosses the level midway between the two sides, and refit the line
    to those crossings. The midway level is unbiased for a blurred step, whatever the
    blur, and the profile is short enough not to reach a neighbouring edge.

    Returns the refined line as :func:`_fit_line` does, or ``None`` when the edge has
    too little contrast or too few crossings to refine.
    """
    centre, direction, s0, s1, _, _ = line
    normal = np.array([-direction[1], direction[0]])
    s = np.arange(s0, s1 + 1e-9, 1.0)
    t = np.arange(-half, half + 1e-9, config.MARK_EDGE_STEP_PX)
    if len(s) < 3 or len(t) < 3:
        return None
    xy = (
        centre[None, None, :]
        + s[:, None, None] * direction[None, None, :]
        + t[None, :, None] * normal[None, None, :]
    ).astype(np.float32)
    profiles = cv2.remap(
        gray,
        np.ascontiguousarray(xy[..., 0]),
        np.ascontiguousarray(xy[..., 1]),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    one_side, other_side = np.median(profiles[:, 0]), np.median(profiles[:, -1])
    if abs(other_side - one_side) < min_contrast:
        return None
    d = profiles - 0.5 * (one_side + other_side)
    a, b = d[:, :-1], d[:, 1:]
    crosses = (np.sign(a) != np.sign(b)) & (a != b)
    with np.errstate(divide="ignore", invalid="ignore"):
        at = t[:-1] + (a / (a - b)) * (t[1] - t[0])
    # The crossing nearest the current line, per profile.
    nearest = np.where(crosses, np.abs(at), np.inf)
    j = np.argmin(nearest, axis=1)
    rows = np.flatnonzero(np.isfinite(nearest[np.arange(len(s)), j]))
    if len(rows) < 3:
        return None
    offsets = at[rows, j[rows]]
    points = centre + s[rows, None] * direction + offsets[:, None] * normal
    refined = _fit_line(points)
    # Leave out the crossings a glare bite or a speck pulled off the line, and refit.
    rc, rd, *_ = refined
    off_line = np.abs((points - rc) @ np.array([-rd[1], rd[0]]))
    keep = off_line <= max(config.MARK_EDGE_OUTLIER_PX, 3.0 * refined[4])
    if 3 <= keep.sum() < len(points):
        refined = _fit_line(points[keep])
    return refined


def _quads(
    binary: np.ndarray, gray: np.ndarray, *, min_side_px: float, min_contrast: float
):
    """Every contour of ``binary`` that is a plausible convex quadrilateral.

    Returns ``(contours, hierarchy, quads)``, where ``quads`` maps a contour's index to
    ``(fit, area)``, ``fit`` is :func:`_fit_quad`'s result, and ``area`` is that of the
    fitted quadrilateral (not of the binary contour, which the threshold grows or
    shrinks).
    """
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    if hierarchy is None:
        return contours, None, {}
    hierarchy = hierarchy[0]
    height, width = binary.shape
    border = config.MARK_BORDER_PX
    max_ratio = config.MARK_MAX_SIDE_RATIO
    quads = {}
    for i, contour in enumerate(contours):
        xy = contour.reshape(-1, 2)
        if (
            xy[:, 0].min() < border
            or xy[:, 1].min() < border
            or xy[:, 0].max() >= width - border
            or xy[:, 1].max() >= height - border
        ):
            continue
        if cv2.contourArea(contour) < 0.5 * min_side_px**2:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(
            contour, config.MARK_POLY_EPSILON_SHARE * perimeter, True
        )
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        v = approx.reshape(4, 2).astype(float)
        sides = np.linalg.norm(np.roll(v, -1, axis=0) - v, axis=1)
        if sides.min() < 0.7 * min_side_px:
            continue
        if max(sides[0], sides[2]) / max(min(sides[0], sides[2]), 1e-9) > max_ratio:
            continue
        if max(sides[1], sides[3]) / max(min(sides[1], sides[3]), 1e-9) > max_ratio:
            continue
        fit = _fit_quad(contour, approx, gray, min_contrast=min_contrast)
        if fit is None:
            continue
        area = _polygon_area(fit[0])
        # Straight sides: a disc's outline also fits four lines, but its scatter about
        # them grows with its size, where a square's stays at the noise floor.
        if fit[1] > max(
            config.MARK_MAX_SIDE_SCATTER_PX,
            config.MARK_MAX_SIDE_SCATTER_SHARE * np.sqrt(area),
        ):
            continue
        quads[i] = (fit, area)
    return contours, hierarchy, quads


def _polygon_area(corners: np.ndarray) -> float:
    """Area of a simple polygon from its vertices in cyclic order (shoelace)."""
    x, y = corners[:, 0], corners[:, 1]
    return float(abs(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) / 2.0)


def _children(hierarchy: np.ndarray, i: int) -> list[int]:
    """Indices of contour ``i``'s direct children in an OpenCV ``RETR_TREE`` hierarchy."""
    out, child = [], hierarchy[i][2]
    while child != -1:
        out.append(int(child))
        child = hierarchy[child][0]
    return out


def _depth(hierarchy: np.ndarray, i: int) -> int:
    """How many contours enclose contour ``i``: even for foreground, odd for a hole."""
    depth, parent = 0, hierarchy[i][3]
    while parent != -1:
        depth += 1
        parent = hierarchy[parent][3]
    return depth
