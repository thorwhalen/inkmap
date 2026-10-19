"""Tests for the plain-patch locator, on synthetic colour photographs with exact truth.

What must not happen silently: a patch mask that spills over the patch's edge, a
substrate ring that reaches the table, or an ``ok`` verdict on a region that leaked
into the paper. Each is checked against the rendered truth, not against the eye.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

import inkmap
from inkmap import synth
from inkmap.locate import PatchRegions, locate_patch

MAX_CORNER_ERROR_PX = 0.5


def _corner_error(found, truth):
    """Largest corner distance, whichever corner each list starts from.

    "Clockwise from the top-left" is a convention, and flips at 45 degrees.
    """
    return min(
        float(np.linalg.norm(np.roll(found, k, axis=0) - truth, axis=1).max())
        for k in range(4)
    )

CONDITIONS = {
    "dark, frontal": dict(patch_bgr=(40, 40, 45), blur=1.0, noise=2.0),
    "blue, perspective": dict(
        patch_bgr=(160, 90, 40), perspective=0.06, rotation=12.0, blur=1.0, noise=2.0
    ),
    "red, rotated, blurred": dict(
        patch_bgr=(50, 50, 190), rotation=-35.0, blur=1.5, noise=3.0
    ),
    "uneven light, textured table": dict(
        perspective=0.05, rotation=12.0, blur=1.0, noise=2.0, gradient=0.4,
        background_texture=15.0,
    ),
    # The hard case: lightness close to the paper's. Otsu first splits the strip from
    # the table, so this is found only by re-splitting the leaked region.
    "pale blue on white": dict(patch_bgr=(205, 215, 225), blur=1.0, noise=2.0),
    "pale, rotated": dict(patch_bgr=(200, 225, 230), rotation=-20.0, blur=1.0, noise=2.0),
}


def _inside(quad, mask, *, by=0.0):
    """Does every pixel of ``mask`` lie at least ``by`` px inside ``quad``?"""
    ys, xs = np.nonzero(mask)
    contour = np.asarray(quad, np.float32).reshape(-1, 1, 2)
    return all(
        cv2.pointPolygonTest(contour, (float(x), float(y)), True) >= by
        for x, y in zip(xs, ys)
    )


def _outside(quad, mask, *, by=0.0):
    ys, xs = np.nonzero(mask)
    contour = np.asarray(quad, np.float32).reshape(-1, 1, 2)
    return all(
        cv2.pointPolygonTest(contour, (float(x), float(y)), True) <= -by
        for x, y in zip(xs, ys)
    )


@pytest.mark.parametrize("name", list(CONDITIONS))
def test_patch_substrate_and_corners_match_the_truth(name):
    scene = synth.render_patch(rng=1, **CONDITIONS[name])
    regions = locate_patch(scene.image)
    assert regions.ok, regions.notes
    error = _corner_error(regions.quad, scene.patch_quad)
    assert error < MAX_CORNER_ERROR_PX, f"corner error {error:.3f} px"
    assert regions.patch.sum() > 0.6 * regions.region.sum()
    assert _inside(scene.patch_quad, regions.patch, by=1.0), "patch mask spills"
    assert _outside(scene.patch_quad, regions.substrate, by=1.0), "ring on the patch"
    assert _inside(scene.paper_quad, regions.substrate), "ring reaches the table"


def test_a_thin_paper_border_is_not_overshot_onto_the_table():
    """A border narrower than the ring: the ring keeps only the paper's pixels."""
    scene = synth.render_patch(
        paper_size=(42.0, 25.5), blur=1.0, noise=2.0, rng=2
    )  # ~5 px of paper round the patch, ring out to ~9 px
    regions = locate_patch(scene.image)
    assert regions.substrate.sum() > 50
    assert _inside(scene.paper_quad, regions.substrate)


def test_a_patch_indistinguishable_from_its_paper_is_refused():
    scene = synth.render_patch(patch_bgr=(226, 232, 235), blur=1.0, noise=2.0, rng=1)
    regions = locate_patch(scene.image)
    assert not regions.ok and regions.notes


def test_a_pale_card_on_a_table_with_no_paper_is_refused():
    """The 'substrate' is the table, darker than the card taken for the patch."""
    scene = synth.render_patch(
        patch_bgr=(200, 205, 210), paper_bgr=(70, 80, 95), blur=1.0, noise=2.0, rng=1
    )
    regions = locate_patch(scene.image)
    assert not regions.ok
    assert any("lighter" in n or "substrate" in n for n in regions.notes)


def test_a_patch_cut_by_the_frame_is_refused():
    scene = synth.render_patch(centre=(80.0, 300.0), blur=1.0, noise=2.0, rng=1)
    regions = locate_patch(scene.image, seed=(60, 300))
    assert not regions.ok and regions.touches_border
    assert any("frame edge" in n for n in regions.notes)


def test_an_explicit_seed_finds_an_off_centre_patch():
    scene = synth.render_patch(
        size=(600, 900), centre=(560.0, 330.0), pixels_per_unit=4.0, blur=1.0,
        noise=2.0, rng=3,
    )
    assert not locate_patch(scene.image).ok  # the centre is on the table
    regions = locate_patch(scene.image, seed=(560, 330))
    assert regions.ok, regions.notes
    assert _corner_error(regions.quad, scene.patch_quad) < MAX_CORNER_ERROR_PX


def test_bad_seeds_are_errors():
    image = synth.render_patch(rng=0).image
    with pytest.raises(ValueError, match="outside"):
        locate_patch(image, seed=(5000, 10))
    with pytest.raises(ValueError, match="centre"):
        locate_patch(image, seed="middle")


def test_grey_and_path_inputs(tmp_path):
    scene = synth.render_patch(patch_bgr=(40, 40, 40), blur=1.0, noise=2.0, rng=4)
    gray = cv2.cvtColor(scene.image, cv2.COLOR_BGR2GRAY)
    assert locate_patch(gray).ok
    path = tmp_path / "strip.png"
    cv2.imwrite(str(path), scene.image)
    assert locate_patch(path).ok
    with pytest.raises(ValueError, match="8-bit"):
        locate_patch(scene.image.astype(np.float32))


def test_the_placement_measures_the_patch_against_its_substrate():
    """With the placement, analyze and measure work unchanged, patch vs substrate."""
    scene = synth.render_patch(rotation=8.0, perspective=0.03, blur=1.0, noise=2.0, rng=1)
    regions = locate_patch(scene.image)
    placement = regions.placement
    assert placement.locator == "patch"
    ink = inkmap.analyze(scene.image, [placement])[0]
    assert ink.placement.refined
    measured = inkmap.measure(scene.image, ink)
    assert measured.measurability.ok, measured.measurability.reasons
    assert measured.foreground_mean < measured.background_mean  # a darker patch


def test_the_patch_locator_is_registered_but_opt_in():
    from inkmap import config

    assert "patch" in inkmap.LOCATORS
    assert "patch" not in config.DEFAULT_LOCATORS
    scene = synth.render_patch(blur=1.0, noise=2.0, rng=1)
    assert inkmap.find(scene.image, locators=["patch"]) is not None
    blank = np.full((300, 400, 3), 200, np.uint8)
    assert inkmap.find(blank, locators=["patch"]) is None


def test_public_surface():
    import sys

    locate = sys.modules["inkmap.locate"]
    assert {"locate_patch", "PatchRegions"} <= set(locate.__all__)
    assert inkmap.locate_patch is locate_patch
    assert inkmap.PatchRegions is PatchRegions


# --------------------------------------------------------------------------- #
# Regressions from the adversarial review: each was an ok=True on a wrong region
# --------------------------------------------------------------------------- #


def test_a_seed_near_the_patch_edge_still_takes_the_patch_colour():
    """A seed window straddling the edge took the paper's colour: the strip came back."""
    scene = synth.render_patch(
        patch_bgr=(205, 215, 225), background_bgr=(245, 245, 245), blur=1.0,
        noise=2.0, rng=0,
    )  # the patch spans x 280..520
    regions = locate_patch(scene.image, seed=(515, 300))
    assert regions.ok, regions.notes
    assert _corner_error(regions.quad, scene.patch_quad) < MAX_CORNER_ERROR_PX


def test_a_region_holding_another_colour_is_refused():
    """Seeded on the paper of a strip lying on a white page: the strip is no patch."""
    scene = synth.render_patch(
        patch_bgr=(205, 215, 225), background_bgr=(250, 250, 250), blur=1.0,
        noise=2.0, rng=0,
    )
    regions = locate_patch(scene.image, seed=(200, 300))  # on the strip, off the patch
    assert not regions.ok
    assert any("another colour" in n or "two colours" in n for n in regions.notes)


def test_a_neighbouring_light_patch_is_not_substrate():
    """A colour bar: a light-grey patch butting onto the measured one."""
    scene = synth.render_patch(rotation=0.0, blur=1.0, noise=2.0, rng=1)
    image = scene.image.copy()
    image[228:373, 521:600] = 195  # x 520..600 on the paper strip, beside the patch
    image = cv2.GaussianBlur(image, (0, 0), 1.0)
    regions = locate_patch(image)
    assert regions.ok, regions.notes
    neighbour = np.zeros(image.shape[:2], bool)
    neighbour[226:375, 519:602] = True
    assert (regions.substrate & neighbour).sum() < 0.01 * regions.substrate.sum()


def test_text_on_the_patch_is_left_out_of_the_interior():
    scene = synth.render_patch(rotation=0.0, rng=1)
    image = scene.image.copy()
    ink = np.zeros(image.shape[:2], np.uint8)
    cv2.putText(ink, "C-42", (330, 320), cv2.FONT_HERSHEY_SIMPLEX, 1.6, 1, 3)
    image[ink.astype(bool)] = 20
    image = cv2.GaussianBlur(image, (0, 0), 1.0)
    regions = locate_patch(image)
    assert regions.ok, regions.notes
    text = cv2.dilate(ink, np.ones((3, 3), np.uint8)).astype(bool)
    assert not (regions.patch & text).any()


def _card(draw):
    """A strip of paper on a table, with ``draw(image)`` painting the patch."""
    image = np.full((600, 800, 3), (70, 80, 95), np.uint8)
    image[150:450, 100:700] = (232, 236, 238)
    draw(image)
    return cv2.GaussianBlur(image, (0, 0), 1.0)


def _rounded(radius):
    def draw(image, colour=(160, 90, 40), box=(280, 240, 520, 360)):
        x0, y0, x1, y1 = box
        cv2.rectangle(image, (x0 + radius, y0), (x1 - radius, y1), colour, -1)
        cv2.rectangle(image, (x0, y0 + radius), (x1, y1 - radius), colour, -1)
        for cx in (x0 + radius, x1 - radius):
            for cy in (y0 + radius, y1 - radius):
                cv2.circle(image, (cx, cy), radius, colour, -1)

    return draw


@pytest.mark.parametrize(
    "draw",
    [
        lambda im: cv2.ellipse(im, (400, 300), (120, 72), 0, 0, 360, (160, 90, 40), -1),
        _rounded(25),
    ],
    ids=["ellipse", "rounded r=25"],
)
def test_non_rectangular_patches_are_refused(draw):
    regions = locate_patch(_card(draw))
    assert not regions.ok
    assert any("strays" in n or "rectangularity" in n for n in regions.notes)


def test_slightly_rounded_corners_are_still_a_patch():
    assert locate_patch(_card(_rounded(6))).ok


def test_non_finite_and_malformed_seeds_are_errors():
    image = synth.render_patch(rng=0).image
    for seed in [(np.nan, 10), (10, 20, 30)]:
        with pytest.raises(ValueError, match="finite"):
            locate_patch(image, seed=seed)
