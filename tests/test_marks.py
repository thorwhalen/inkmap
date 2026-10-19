"""Tests for the square registration-mark locator, on synthetic renders with exact truth.

The number that matters is the centre error, and the failure that matters is a centre
that is plausibly placed but biased: half a pixel towards the near side of a mark seen
in perspective, or quantised to the pixel grid when the mark is axis-aligned. Both
survive a glance at an overlay, so the tests measure against the known transform.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

import inkmap
from inkmap import synth
from inkmap.locate import (
    BULLSEYE_RINGS,
    QR_FINDER_RINGS,
    SquareMark,
    find_square_marks,
    quad_centre,
)
from inkmap.types import Polarity

FRAME = (900, 1200)
PIXELS_PER_CELL = 1.2
MAX_CENTRE_ERROR_PX = 0.25  # the acceptance bound, for blur <= 1.5 px


def _render_sheet(**kwargs):
    model, truth = synth.mark_sheet()
    params = dict(
        size=FRAME, pixels_per_unit=PIXELS_PER_CELL, noise=2.0, samples=4, rng=1
    )
    scene = synth.render(model, **{**params, **kwargs})
    return scene, _truth_in_frame(scene, truth)


def _truth_in_frame(scene, truth, *, margin_px=4.0):
    """Image centre and rings of each mark lying wholly inside the frame."""
    h, w = scene.image.shape
    out = []
    for (u, v), rings in truth:
        half = 25.0  # every mark on the sheet is at most 50 cells across
        square = np.float32(
            [[u - half, v - half], [u + half, v - half], [u + half, v + half], [u - half, v + half]]
        )
        corners = cv2.perspectiveTransform(square.reshape(-1, 1, 2), scene.transform)
        corners = corners.reshape(4, 2)
        if corners.min() < margin_px or (corners[:, 0] > w - margin_px).any() or (
            corners[:, 1] > h - margin_px
        ).any():
            continue
        centre = cv2.perspectiveTransform(np.float32([[[u, v]]]), scene.transform)[0, 0]
        out.append((centre.astype(float), rings))
    return out


def _kind(mark: SquareMark):
    if mark.is_solid:
        return ()
    return min((BULLSEYE_RINGS, QR_FINDER_RINGS), key=mark.ring_error)


def _match(found, truth):
    """Pair each true mark with the nearest found one; return the centre errors."""
    errors = []
    for centre, rings in truth:
        nearest = min(found, key=lambda m: np.hypot(*(np.subtract(m.centre, centre))))
        error = float(np.hypot(*np.subtract(nearest.centre, centre)))
        assert error < 2.0, f"no mark found near {centre} (nearest {error:.1f} px away)"
        assert _kind(nearest) == rings, f"mark at {centre} misclassified: {nearest.rings}"
        errors.append(error)
    return errors


@pytest.mark.parametrize(
    "perspective,rotation,blur",
    [
        (0.0, 0.0, 1.0),  # axis-aligned: where pixel quantisation does not average out
        (0.0, 0.0, 1.5),
        (0.05, 10.0, 1.5),
        (0.1, 0.0, 1.0),
        (0.1, 25.0, 1.5),
        (0.15, -20.0, 1.0),
        (0.15, 0.0, 1.5),
    ],
)
def test_centres_are_sub_pixel_at_several_perspectives(perspective, rotation, blur):
    scene, truth = _render_sheet(perspective=perspective, rotation=rotation, blur=blur)
    assert len(truth) >= 5, "test geometry left too few marks in the frame"
    found = find_square_marks(scene.image)
    errors = _match(found, truth)
    assert len(found) == len(truth), "a mark was reported that is not on the sheet"
    assert max(errors) < MAX_CENTRE_ERROR_PX, f"centre errors {np.round(errors, 3)}"


def test_ring_ratios_tell_bullseyes_from_qr_finders():
    scene, truth = _render_sheet(perspective=0.1, rotation=15.0, blur=1.0)
    found = find_square_marks(scene.image)
    bullseyes = [m for m in found if _kind(m) == BULLSEYE_RINGS]
    finders = [m for m in found if _kind(m) == QR_FINDER_RINGS]
    assert len(bullseyes) == 3 and len(finders) == 2
    for m in bullseyes:
        assert m.ring_error(BULLSEYE_RINGS) < 0.04
    for m in finders:
        assert m.ring_error(QR_FINDER_RINGS) < 0.04


def test_a_strong_illumination_gradient_does_not_move_the_centres():
    """3.5:1 across the frame: a global threshold would lose one side of the sheet."""
    scene, truth = _render_sheet(perspective=0.1, rotation=10.0, blur=1.0, gradient=0.71)
    found = find_square_marks(scene.image)
    assert len(found) == len(truth)
    assert max(_match(found, truth)) < MAX_CENTRE_ERROR_PX


def test_inverted_print_is_found_with_the_polarity_flag():
    scene, truth = _render_sheet(perspective=0.05, rotation=10.0, blur=1.0)
    inverted = 255 - scene.image
    assert find_square_marks(inverted) == [] or all(
        _kind(m) == () for m in find_square_marks(inverted)
    )
    found = find_square_marks(inverted, polarity=Polarity.FOREGROUND_IS_LIGHT)
    assert len(found) == len(truth)
    assert max(_match(found, truth)) < MAX_CENTRE_ERROR_PX


def test_qr_finder_patterns_of_a_real_symbol():
    scene = synth.render(perspective=0.1, rotation=20.0, blur=1.0, noise=2.0, rng=3)
    finders = [
        m for m in find_square_marks(scene.image) if m.ring_error(QR_FINDER_RINGS) < 0.06
    ]
    assert len(finders) == 3


def test_a_clipped_nested_mark_is_dropped_not_reported_as_solid():
    """The frame cuts a bullseye's outer square; its inner square is not a solid mark."""
    scene, truth = _render_sheet(blur=1.0)
    (cx, cy), _ = truth[0]  # the top-left bullseye, ~60 px across
    crop = scene.image[int(cy) - 22 :, int(cx) - 22 :]  # through its outer ring only
    found = find_square_marks(crop)
    shifted = (cx - (int(cx) - 22), cy - (int(cy) - 22))
    assert all(np.hypot(*np.subtract(m.centre, shifted)) > 30 for m in found)


def test_discs_are_not_squares():
    yy, xx = np.mgrid[0:600, 0:800]
    image = np.full((600, 800), 240.0)
    for cx, cy, r in [(400, 150, 12), (600, 300, 20), (200, 400, 35)]:
        image[(xx - cx) ** 2 + (yy - cy) ** 2 < r * r] = 30.0
    image = synth.degrade(image, blur=1.2, noise=2.0, rng=0)
    assert find_square_marks(image) == []


def test_corners_are_clockwise_from_the_top_left():
    scene, _ = _render_sheet(rotation=30.0, blur=1.0)
    for mark in find_square_marks(scene.image):
        c = mark.corners
        x, y = c[:, 0], c[:, 1]
        assert np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) > 0  # clockwise, y down
        assert np.argmin(c.sum(axis=1)) == 0
        if mark.is_solid:
            assert np.allclose(quad_centre(c), mark.centre)
        else:  # the mean of its squares' centres, all within a fraction of a pixel
            assert np.hypot(*np.subtract(quad_centre(c), mark.centre)) < 0.5


def test_sigma_is_reported_and_of_the_right_order():
    scene, truth = _render_sheet(perspective=0.1, rotation=10.0, blur=1.5)
    found = find_square_marks(scene.image)
    assert all(np.isfinite(m.sigma_px) and 0 <= m.sigma_px < 1.0 for m in found)
    assert all(len(m.centres) == 1 + len(m.rings) for m in found)


def test_size_bounds_are_respected():
    scene, truth = _render_sheet(blur=1.0)
    assert find_square_marks(scene.image, min_side_px=70) == []
    assert find_square_marks(scene.image, max_side_share=0.01) == []
    # The bound is on the outer square: a nested mark's inner square (a third of its
    # side) is below it, and must still be found for the mark to be.
    found = find_square_marks(scene.image, min_side_px=40)
    assert sorted(_kind(m) for m in found) == sorted(rings for _, rings in truth)


def test_small_bullseyes_are_found_at_the_default_minimum():
    """A 24 px bullseye (inner square 7.7 px) is found with the default bounds."""
    scene, truth = _render_sheet(pixels_per_unit=0.48, blur=0.7, size=(480, 640))
    found = find_square_marks(scene.image)
    bullseyes = [m for m in found if _kind(m) == BULLSEYE_RINGS]
    assert len(bullseyes) == 3


def test_rejects_a_colour_image():
    with pytest.raises(ValueError, match="2-D"):
        find_square_marks(np.zeros((10, 10, 3), np.uint8))


def test_blank_and_tiny_frames_yield_nothing():
    assert find_square_marks(np.full((200, 300), 200, np.uint8)) == []
    assert find_square_marks(np.zeros((5, 5), np.uint8)) == []


def test_nested_square_refuses_an_off_centre_ring():
    with pytest.raises(ValueError, match="cannot hold"):
        synth.nested_square(25, BULLSEYE_RINGS)


def test_public_surface():
    import sys

    locate = sys.modules["inkmap.locate"]  # the attribute is the locate() function
    for name in ["find_square_marks", "SquareMark", "BULLSEYE_RINGS", "QR_FINDER_RINGS"]:
        assert name in locate.__all__
    assert inkmap.find_square_marks is find_square_marks
    assert inkmap.SquareMark is SquareMark
    assert QR_FINDER_RINGS == (5 / 7, 3 / 7)
