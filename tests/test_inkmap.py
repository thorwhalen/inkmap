"""Tests for inkmap.

The interesting tests are the ones that would catch a *silently wrong* result: a mask
that is the right shape and density but rotated a quarter turn, a coverage map that is
plausible but biased by half a pixel, a blur estimate that is really the search
boundary. Those survive casual inspection, so they get explicit tests.

The other theme is portability across model kinds: whatever holds for a QR symbol must
hold for a raster, a polygon and a glyph, because the whole point of the architecture
is that they go through one pipeline.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

import inkmap
from inkmap import geometry, models, synth
from inkmap.types import Polarity, Region

needs_segno = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("segno") is None,
    reason="segno not installed (optional 'synth' extra)",
)
needs_pil = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("PIL") is None,
    reason="Pillow not installed (optional 'text' extra)",
)


# --------------------------------------------------------------------------- #
# Model zoo -- everything below runs against each of these
# --------------------------------------------------------------------------- #


def _raster_model():
    art = np.zeros((64, 64), dtype=bool)
    art[8:56, 8:20] = True
    art[8:20, 8:56] = True
    return models.RasterModel(art)


def _polygon_model():
    return models.PolygonModel([np.array([[2, 2], [30, 6], [10, 28]], dtype=float)])


def _bars_model():
    bars = np.zeros(95, dtype=bool)
    bars[::3] = True
    bars[7:12] = True
    return models.BarsModel(bars, height=40.0)


MODEL_FACTORIES = {
    "matrix": synth.qr_model,
    "raster": _raster_model,
    "polygon": _polygon_model,
    "bars": _bars_model,
}


@pytest.fixture(scope="module")
def qr_scene() -> synth.Scene:
    return synth.render(pixels_per_unit=10.0, rng=0)


@pytest.fixture(scope="module")
def hard_scene() -> synth.Scene:
    return synth.render(
        pixels_per_unit=10.0, perspective=0.05, blur=1.3, noise=4.0, gradient=0.3, rng=3
    )


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #


def test_find_returns_inkmap(qr_scene):
    ink = inkmap.find(qr_scene.image)
    assert ink is not None
    assert ink.coverage.shape == qr_scene.image.shape[:2]
    assert ink.coverage.dtype == np.float32
    assert 0.0 <= ink.coverage.min() and ink.coverage.max() <= 1.0


def test_foreground_one_liner(qr_scene):
    cov = inkmap.foreground(qr_scene.image)
    assert cov.shape == qr_scene.image.shape[:2]
    assert cov.max() > 0.5


def test_foreground_on_blank_image_is_zeros_not_error():
    """The one-liner must be mappable over a directory without try/except."""
    blank = np.full((200, 200), 255, dtype=np.uint8)
    cov = inkmap.foreground(blank)
    assert cov.shape == (200, 200)
    assert not cov.any()


def test_find_returns_none_when_absent():
    assert inkmap.find(np.full((200, 200), 255, dtype=np.uint8)) is None


def test_inkmap_is_array_like(qr_scene):
    ink = inkmap.find(qr_scene.image)
    assert np.asarray(ink).shape == ink.coverage.shape


def test_model_without_quad_is_an_error(qr_scene):
    with pytest.raises(ValueError, match="quad"):
        inkmap.find(qr_scene.image, model=synth.qr_model())


# --------------------------------------------------------------------------- #
# Portability across model kinds -- the point of the architecture
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", sorted(MODEL_FACTORIES))
def test_any_model_yields_accurate_coverage(kind):
    model = MODEL_FACTORIES[kind]()
    scene = synth.render(
        model,
        pixels_per_unit=8.0,
        size=(700, 900),
        perspective=0.02,
        blur=1.0,
        noise=2,
        rng=5,
    )
    ink = inkmap.find(scene.image, model=model, quad=scene.quad)
    assert ink is not None
    mae = float(np.abs(ink.coverage - scene.coverage).mean())
    assert mae < 0.01, f"{kind}: coverage MAE {mae:.4f}"


@pytest.mark.parametrize("kind", sorted(MODEL_FACTORIES))
def test_any_model_reports_a_feature_size(kind):
    model = MODEL_FACTORIES[kind]()
    assert model.feature_size > 0
    assert np.isfinite(model.feature_size)


@pytest.mark.parametrize("kind", sorted(MODEL_FACTORIES))
def test_any_model_renders(kind):
    raster = models.render_model(MODEL_FACTORIES[kind](), 4.0)
    assert raster.ndim == 2
    assert 0.0 <= raster.min() and raster.max() <= 1.0
    assert raster.max() > 0.5, "model rendered empty"


def test_duck_typed_model_needs_no_base_class():
    """A model is a protocol, not an inheritance requirement."""

    class Disc:
        extent = (20.0, 20.0)
        feature_size = 10.0

        def occupancy(self, u, v):
            return (u - 10.0) ** 2 + (v - 10.0) ** 2 < 81.0

    model = Disc()
    scene = synth.render(model, pixels_per_unit=10.0, size=400, rng=1)
    ink = inkmap.find(scene.image, model=model, quad=scene.quad)
    assert float(np.abs(ink.coverage - scene.coverage).mean()) < 0.01


# --------------------------------------------------------------------------- #
# QR specifics
# --------------------------------------------------------------------------- #


def test_module_matrix_is_exact(qr_scene):
    ink = inkmap.find(qr_scene.image)
    assert np.array_equal(ink.model.cells, qr_scene.model.cells)


@needs_segno
@pytest.mark.parametrize("payload_len", [1, 30, 200, 800])
def test_module_count_inferred_across_versions(payload_len):
    model = synth.qr_model("q" * payload_len)
    scene = synth.render(model, pixels_per_unit=8.0, size=1200, rng=1)
    ink = inkmap.find(scene.image)
    assert ink is not None
    assert np.array_equal(ink.model.cells, model.cells)


@pytest.mark.parametrize("rotation", [0, 45, 90, 135, 180, 225, 270, 315])
def test_rotation_does_not_scramble_the_model(rotation):
    """The regression this package exists to avoid.

    Re-sorting locator corners into image order (by coordinate sum/difference) looks
    harmless and passes at 0 degrees, but past 45 degrees it permutes them relative to
    the model's own frame -- rotating the model and producing a mask of the right size
    and density in the wrong places.
    """
    scene = synth.render(pixels_per_unit=10.0, rotation=rotation, size=900, rng=2)
    ink = inkmap.find(scene.image)
    assert ink is not None, f"no detection at {rotation} degrees"
    truth = scene.coverage > 0.5
    got = ink.coverage > 0.5
    iou = (truth & got).sum() / max((truth | got).sum(), 1)
    assert iou > 0.95, f"IoU {iou:.3f} at {rotation} degrees -- model is misaligned"


@needs_segno
def test_micro_qr_is_not_mistaken_for_qr():
    """Micro QR uses different module counts; fitting it as a QR silently produces a
    wrong grid. It must be ignored, not mis-fitted."""
    segno = pytest.importorskip("segno")
    qr = segno.make("A", error="m")
    if not qr.is_micro:
        pytest.skip("segno did not produce a Micro QR")
    mat = np.array([[bool(v) for v in row] for row in qr.matrix], dtype=bool)
    n, ppm, border = mat.shape[0], 10, 4
    off = border * ppm
    canvas = np.full(((n + 2 * border) * ppm,) * 2, 255, np.uint8)
    canvas[off : off + n * ppm, off : off + n * ppm] = np.kron(
        (~mat).astype(np.uint8) * 255, np.ones((ppm, ppm), np.uint8)
    )
    from inkmap.locate.qr import locate_qr_zxing

    assert locate_qr_zxing(cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR), canvas) == []


def test_multiple_marks_are_all_found():
    a = synth.render(pixels_per_unit=8.0, size=400, rng=0)
    b = synth.render(pixels_per_unit=8.0, size=400, rng=1)
    assert len(inkmap.find_all(np.hstack([a.image, b.image]))) >= 2


# --------------------------------------------------------------------------- #
# Coverage accuracy
# --------------------------------------------------------------------------- #


def test_coverage_matches_ground_truth(hard_scene):
    ink = inkmap.find(hard_scene.image)
    mae = float(np.abs(ink.coverage - hard_scene.coverage).mean())
    assert mae < 0.02, f"coverage MAE {mae:.4f}"


def test_coverage_is_continuous_not_binary():
    """Partial pixels must actually exist -- a boolean mask dressed as float is the
    failure mode this design exists to avoid."""
    scene = synth.render(pixels_per_unit=9.3, perspective=0.04, rng=7)
    ink = inkmap.find(scene.image)
    partial = ((ink.coverage > 0.02) & (ink.coverage < 0.98)).sum()
    assert partial > 100, "no partial-coverage pixels produced"


def test_supersampling_converges():
    """If a finer rate changes the answer much, the default is quantisation-limited."""
    scene = synth.render(pixels_per_unit=9.7, perspective=0.03, rng=11)
    ink = inkmap.find(scene.image, samples=4)
    fine = inkmap.coverage_map(
        ink.model, ink.placement.transform, scene.image.shape[:2], samples=16
    )
    assert float(np.abs(ink.coverage - fine).mean()) < 0.01


def test_scene_ground_truth_is_self_consistent():
    """Ground truth must equal modelled coverage under the true transform, or the
    validation set validates the wrong thing."""
    scene = synth.render(pixels_per_unit=9.0, perspective=0.05, rng=12)
    recomputed = inkmap.coverage_map(
        scene.model, scene.transform, scene.image.shape[:2], samples=8
    )
    assert np.allclose(recomputed, scene.coverage)


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #


def test_refinement_improves_corner_accuracy(hard_scene):
    """Refinement must beat the raw locator corners, or it should not be the default."""
    gray = hard_scene.image
    located = inkmap.locate(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), gray)
    assert located, "no mark located"
    placement = located[0]

    def rms(transform):
        a = geometry.transform_to_quad(transform, placement.model)
        b = geometry.transform_to_quad(hard_scene.transform, hard_scene.model)
        return float(np.sqrt(((a - b) ** 2).sum(axis=1).mean()))

    refined, score = geometry.refine_transform(
        gray, placement.model, placement.transform
    )
    assert rms(refined) < rms(placement.transform)
    assert rms(refined) < 1.0
    assert score > 0.8


def test_margin_is_outside_the_mark(qr_scene):
    ink = inkmap.find(qr_scene.image)
    assert (ink.region == Region.MARGIN).any()
    assert not ((ink.region == Region.MARGIN) & ink.inside_mask()).any()


def test_place_accepts_an_explicit_quad():
    model = _raster_model()
    scene = synth.render(model, pixels_per_unit=6.0, size=600, rng=2)
    placement = inkmap.place(model, scene.quad)
    assert placement.locator == "manual"
    maps = inkmap.analyze(scene.image, [placement])
    assert float(np.abs(maps[0].coverage - scene.coverage).mean()) < 0.01


# --------------------------------------------------------------------------- #
# Photometry
# --------------------------------------------------------------------------- #


def test_measurement_mask_is_strict_subset_of_foreground(hard_scene):
    ink = inkmap.find(hard_scene.image)
    mask = inkmap.measurement_mask(ink)
    assert mask.any()
    assert (mask & ~ink.foreground_mask()).sum() == 0
    assert mask.sum() < ink.foreground_mask().sum(), "erosion removed nothing"


def test_weight_is_never_greater_than_coverage(hard_scene):
    ink = inkmap.find(hard_scene.image)
    assert (ink.weight <= ink.coverage + 1e-6).all()


def test_foreground_and_background_masks_are_disjoint(hard_scene):
    ink = inkmap.find(hard_scene.image)
    assert not (ink.foreground_mask() & ink.background_mask()).any()


def test_srgb_linearisation():
    x = np.array([0, 10, 55, 128, 200, 255], dtype=np.uint8)
    lin = inkmap.srgb_to_linear(x)
    assert lin[0] == pytest.approx(0.0, abs=1e-6)
    assert lin[-1] == pytest.approx(1.0, abs=1e-6)
    assert np.all(np.diff(lin) > 0)
    assert lin[3] < 0.25, "mid-grey is far from 0.5 in linear light"


def test_measure_reports_foreground_darker_than_background(hard_scene):
    ink = inkmap.find(hard_scene.image)
    result = inkmap.measure(hard_scene.image, ink)
    assert result.n_foreground > 0 and result.n_background > 0
    assert result.contrast < 0


def test_measure_rejects_a_mismatched_frame(hard_scene):
    ink = inkmap.find(hard_scene.image)
    with pytest.raises(ValueError, match="register"):
        inkmap.measure(np.zeros((10, 10), dtype=np.uint8), ink)


def test_measurability_rejects_unresolvable_images():
    scene = synth.render(pixels_per_unit=5.0, blur=1.5, noise=2, size=600, rng=4)
    ink = inkmap.find(scene.image)
    assert ink is not None, "scene should still be detectable -- only unmeasurable"
    verdict = inkmap.measurability(ink)
    assert not verdict.ok
    assert verdict.resolution_ratio < 6.0


def test_measurability_accepts_a_good_image():
    scene = synth.render(pixels_per_unit=14.0, blur=0.8, size=900, rng=6)
    assert inkmap.measurability(inkmap.find(scene.image)).ok


def test_measurability_uses_features_not_units():
    """A raster model's unit is far smaller than its stroke; judging resolution per
    unit would call every image unmeasurable."""
    model = _raster_model()
    scene = synth.render(model, pixels_per_unit=2.0, size=400, blur=0.8, rng=9)
    ink = inkmap.find(scene.image, model=model, quad=scene.quad)
    assert ink.placement.pixels_per_feature > ink.placement.pixels_per_unit
    assert inkmap.measurability(ink).ok


def test_illumination_field_flattens_a_gradient():
    from inkmap.photometry import illumination_field

    scene = synth.render(pixels_per_unit=12.0, gradient=0.45, size=800, rng=8)
    ink = inkmap.find(scene.image)
    field = illumination_field(scene.image.astype(np.float32), ink)
    mask = inkmap.measurement_mask(ink, kind="background")
    before = scene.image.astype(np.float32)
    assert (before / np.maximum(field, 1e-6))[mask].std() < before[mask].std()


# --------------------------------------------------------------------------- #
# Polarity
# --------------------------------------------------------------------------- #


def test_polarity_inversion_swaps_the_classes(qr_scene):
    """Inverted marks must be expressible without any caller reinterpreting a mask.

    Compared on *measurement* masks: a pixel bisected exactly by an edge has coverage
    0.5 under both polarities, and both call it foreground -- correctly, since it is
    genuinely half foreground either way. Those pixels are excluded from measurement
    precisely because they are ambiguous.
    """
    normal = inkmap.find(qr_scene.image, polarity=Polarity.FOREGROUND_IS_DARK)
    inverted = inkmap.find(qr_scene.image, polarity=Polarity.FOREGROUND_IS_LIGHT)

    a = inkmap.measurement_mask(normal)
    b = inkmap.measurement_mask(inverted)
    assert a.any() and b.any()
    assert not (a & b).any()
    assert (b & normal.background_mask()).sum() > 0.9 * b.sum()


# --------------------------------------------------------------------------- #
# Locators
# --------------------------------------------------------------------------- #


def test_locators_registry_is_extensible():
    assert set(inkmap.LOCATORS) >= {
        "qr_zxing",
        "qr_aruco",
        "qr_opencv",
        "barcode_zxing",
    }
    calls = []

    def custom(bgr, gray):
        calls.append(True)
        return []

    scene = synth.render(rng=0)
    inkmap.locate(
        cv2.cvtColor(scene.image, cv2.COLOR_GRAY2BGR), scene.image, locators=[custom]
    )
    assert calls


def test_a_failing_locator_does_not_break_the_cascade(qr_scene):
    def broken(bgr, gray):
        raise RuntimeError("boom")

    assert inkmap.find(qr_scene.image, locators=[broken, "qr_zxing"]) is not None


# --------------------------------------------------------------------------- #
# Coarse-to-fine locating
# --------------------------------------------------------------------------- #


def _qr_cells(text: str) -> np.ndarray:
    """A QR module matrix for ``text`` from OpenCV's encoder (no segno needed)."""
    image = cv2.QRCodeEncoder.create().encode(text)
    dark = image < 128
    rows, cols = np.flatnonzero(dark.any(axis=1)), np.flatnonzero(dark.any(axis=0))
    return dark[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]


def _qr_page(*, pixels_per_unit, shape=(700, 1400), n=4, seed=0, **degradation):
    """A page with ``n`` distinct QR codes in a row, mildly rotated and in perspective."""
    rng = np.random.default_rng(seed)
    height, width = shape
    page = np.full(shape, 255, dtype=np.uint8)
    for i in range(n):
        model = models.MatrixModel(_qr_cells(f"inkmap-page-{i:02d}-xxxxxx"))
        tile = int(model.extent[0] * pixels_per_unit * 1.6)
        scene = synth.render(
            model,
            size=tile,
            pixels_per_unit=pixels_per_unit,
            perspective=0.03,
            rotation=rng.uniform(-8, 8),
            rng=rng,
        )
        x0 = int((i + 0.5) * width / n - tile / 2)
        y0 = int(height / 2 - tile / 2)
        window = page[y0 : y0 + tile, x0 : x0 + tile]
        np.minimum(window, scene.image, out=window)
    return synth.degrade(page.astype(np.float32), rng=rng, **degradation)


def _nearest(placement, others):
    centre = placement.quad.mean(axis=0)
    return min(
        others, key=lambda o: float(np.linalg.norm(o.quad.mean(axis=0) - centre))
    )


@pytest.fixture(scope="module")
def qr_page() -> np.ndarray:
    """10 px/module: 5 px after halving, clear of ``MIN_COARSE_PIXELS_PER_FEATURE``,
    so these codes stay on the coarse path (no retry)."""
    return _qr_page(pixels_per_unit=10.0, shape=(600, 1800), blur=0.6, noise=2.0)


def _within_mark_difference(ink, reference) -> float:
    """Mean |coverage difference| over the pixels either mark covers -- not the whole
    frame, whose blank background would dilute a wrong model into a tiny mean."""
    inside = (ink.coverage > 0) | (reference.coverage > 0)
    return float(np.abs(ink.coverage - reference.coverage)[inside].mean())


def _assert_coarse_matches_full(page, *, scale=0.5, **kwargs):
    """``find_all`` with ``locate_scale`` gives the full-resolution models and
    within-mark coverage; returns the coarse results for further checks."""
    full = inkmap.find_all(page, **kwargs)
    coarse = inkmap.find_all(page, locate_scale=scale, **kwargs)
    assert len(full) == len(coarse) > 0
    for ink in coarse:
        reference = min(
            full,
            key=lambda m: float(
                np.linalg.norm(m.placement.quad.mean(0) - ink.placement.quad.mean(0))
            ),
        )
        assert ink.placement.refined
        a, b = ink.placement.model, reference.placement.model
        for attr in ("cells", "bars"):
            if hasattr(a, attr):
                assert np.array_equal(getattr(a, attr), getattr(b, attr)), attr
        assert np.abs(ink.placement.quad - reference.placement.quad).max() < 0.1
        assert _within_mark_difference(ink, reference) < 1e-3
    return coarse


def test_locate_scale_one_is_full_resolution(qr_scene):
    """``scale=None`` and ``scale=1`` are the full-resolution path, unchanged."""
    gray = qr_scene.image
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    base = inkmap.locate(bgr, gray)
    for scale in (None, 1, 1.0):
        again = inkmap.locate(bgr, gray, scale=scale)
        assert len(again) == len(base) > 0
        for a, b in zip(again, base):
            assert np.array_equal(a.quad, b.quad)
            assert np.array_equal(a.transform, b.transform)
            assert np.array_equal(a.model.cells, b.model.cells)
            assert (a.locator, a.payload, a.metadata) == (
                b.locator,
                b.payload,
                b.metadata,
            )


def test_coarse_locate_finds_every_code_close_to_full_resolution(qr_page):
    bgr = cv2.cvtColor(qr_page, cv2.COLOR_GRAY2BGR)
    full = inkmap.locate(bgr, qr_page)
    scale = 0.5
    coarse = inkmap.locate(bgr, qr_page, scale=scale)
    assert len(full) == len(coarse) == 4
    assert {p.payload for p in coarse} == {p.payload for p in full}
    errors = []
    for placement in coarse:
        reference = _nearest(placement, full)
        assert placement.metadata["locate_scale"] == scale
        assert np.array_equal(placement.model.cells, reference.model.cells)
        offset = np.abs(placement.quad - reference.quad)
        # zxing reports integer corners, so one coarse pixel (1 / scale) of
        # quantisation plus the half-pixel corner convention is inherent per axis...
        assert offset[[0, 1, 3]].max() <= 1.0 / scale + 0.5
        # ...and the corner without a finder pattern is extrapolated, at either scale.
        assert offset[2].max() <= 2.0 / scale
        errors.append(np.linalg.norm(placement.quad - reference.quad, axis=1))
        # transform and quad stay consistent after the mapping
        implied = geometry.transform_to_quad(placement.transform, placement.model)
        assert np.abs(implied - placement.quad).max() < 1e-2
    # On average the mapped corners land within ~1.5 full-resolution px.
    assert float(np.mean(errors)) <= 1.5


def test_coarse_find_all_matches_full_resolution_coverage(qr_page):
    """Refinement pins both to the same sub-pixel geometry, so coverage agrees."""
    coarse = _assert_coarse_matches_full(qr_page)
    assert len(coarse) == 4


@pytest.mark.parametrize("pixels_per_unit", [4.0, 5.0, 6.0, 7.0])
def test_undersampled_coarse_codes_get_full_resolution_models(pixels_per_unit):
    """Below ~4 px/module after downscaling, the module count and matrix read off the
    coarse frame are wrong although the codes decode (2 px: a 25 x 25 symbol read as
    21 x 21; 2.5-3.5 px: tens of flipped modules). Those placements are re-located at
    full resolution, so the models -- and the coverage -- match full resolution."""
    page = _qr_page(pixels_per_unit=pixels_per_unit, blur=0.6, noise=2.0)
    bgr = cv2.cvtColor(page, cv2.COLOR_GRAY2BGR)
    full = inkmap.locate(bgr, page)
    coarse = inkmap.locate(bgr, page, scale=0.5)
    assert len(full) == len(coarse) == 4
    for placement in coarse:
        assert placement.metadata["locate_retry"] == "undersampled"
        assert placement.metadata["locate_scale"] == 1.0
        reference = _nearest(placement, full)
        assert np.array_equal(placement.model.cells, reference.model.cells)

    # without the retry they stay coarse, and say their model is not to be trusted
    kept = inkmap.locate(bgr, page, scale=0.5, full_res_retry=False)
    assert all(p.metadata.get("locate_undersampled") is True for p in kept)
    assert all(p.metadata["locate_scale"] == 0.5 for p in kept)


def test_undersampled_coarse_qr_coverage_matches_full_resolution():
    _assert_coarse_matches_full(_qr_page(pixels_per_unit=5.0, blur=0.6, noise=2.0))


def _barcode_page(text, *, module_px, rotation=7.0, shape=(400, 1000)):
    """A zxing-encoded EAN-13, ``module_px`` px per module, rotated -- no extra deps."""
    zxingcpp = pytest.importorskip("zxingcpp")
    if not hasattr(zxingcpp, "create_barcode"):
        pytest.skip("this zxing-cpp has no barcode writer")
    symbol = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.EAN13)
    row = np.asarray(symbol.to_image(scale=1, add_quiet_zones=False))
    row = row[row.shape[0] // 2]
    strip = cv2.resize(
        np.repeat(row[None], 60, axis=0),
        None,
        fx=module_px,
        fy=1,
        interpolation=cv2.INTER_NEAREST,
    )
    page = np.full(shape, 255, dtype=np.uint8)
    y0, x0 = (shape[0] - strip.shape[0]) // 2, (shape[1] - strip.shape[1]) // 2
    page[y0 : y0 + strip.shape[0], x0 : x0 + strip.shape[1]] = strip
    turn = cv2.getRotationMatrix2D((shape[1] / 2, shape[0] / 2), rotation, 1.0)
    page = cv2.warpAffine(page, turn, shape[::-1], borderValue=255)
    return synth.degrade(page.astype(np.float32), rng=0, blur=0.6, noise=2.0)


def test_undersampled_coarse_barcode_matches_full_resolution():
    """2 px per module after halving: the bar pattern is re-read at full resolution."""
    page = _barcode_page("5901234123457", module_px=4)
    coarse = _assert_coarse_matches_full(page, locators=["barcode_zxing"])
    assert [ink.placement.metadata["locate_retry"] for ink in coarse] == [
        "undersampled"
    ]


def test_full_res_retry_recovers_a_payload_the_coarse_pass_missed():
    """A decoder that needs >= 6 px per module: it locates the coarse codes (5 px per
    module after downscaling, above the undersampling floor) but cannot decode them,
    and decodes them at full resolution."""
    from dataclasses import replace

    def needs_six_px_per_module(bgr, gray):
        return [
            p if p.pixels_per_unit >= 6.0 else replace(p, payload=None)
            for p in inkmap.LOCATORS["qr_zxing"](bgr, gray)
        ]

    page = _qr_page(pixels_per_unit=10.0, n=2, shape=(500, 1000))
    bgr = cv2.cvtColor(page, cv2.COLOR_GRAY2BGR)
    kw = dict(locators=[needs_six_px_per_module], scale=0.5)
    without = inkmap.locate(bgr, page, full_res_retry=False, **kw)
    assert len(without) == 2 and all(p.payload is None for p in without)
    assert not any(p.metadata.get("locate_undersampled") for p in without)

    retried = inkmap.locate(bgr, page, **kw)
    assert len(retried) == 2
    reference = inkmap.locate(bgr, page, locators=["qr_zxing"])
    for placement in retried:
        target = _nearest(placement, reference)
        assert placement.payload is not None and placement.payload == target.payload
        assert placement.metadata["locate_retry"] == "undecoded"
        assert placement.metadata["locate_scale"] == 1.0
        # zxing is not exactly translation-invariant: a crop can move a corner by 1 px
        assert np.abs(placement.quad - target.quad).max() <= 1.0


def test_full_res_retry_on_a_code_too_small_to_decode_coarsely():
    """Realistic case: at 1.4 px/module after downscaling, Aruco finds a code that
    nothing decodes; the full-resolution retry decodes it."""
    page = _qr_page(pixels_per_unit=2.8, shape=(500, 1000), seed=0, blur=0.6, noise=2.0)
    bgr = cv2.cvtColor(page, cv2.COLOR_GRAY2BGR)
    coarse = inkmap.locate(bgr, page, scale=0.5, full_res_retry=False)
    if all(p.payload is not None for p in coarse):
        pytest.skip(
            "this OpenCV/zxing build decodes every code coarsely; nothing to retry"
        )
    retried = inkmap.locate(bgr, page, scale=0.5)
    assert len(retried) == len(coarse)
    assert all(p.payload is not None for p in retried)
    assert any(p.metadata.get("locate_retry") for p in retried)


@pytest.mark.parametrize("scale", [0, -0.5, 1.5, float("nan"), "half"])
def test_invalid_locate_scale_is_rejected(qr_scene, scale):
    gray = qr_scene.image
    with pytest.raises(ValueError, match="scale"):
        inkmap.locate(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), gray, scale=scale)
    with pytest.raises(ValueError, match="scale"):
        inkmap.find_all(gray, locate_scale=scale)


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #


@needs_pil
def test_glyph_model_covers_printed_text():
    model = models.text_model("INK", font_size=200)
    scene = synth.render(
        model, pixels_per_unit=1.5, size=(600, 1400), blur=1.0, noise=2, rng=4
    )
    ink = inkmap.find(scene.image, model=model, quad=scene.quad)
    assert float(np.abs(ink.coverage - scene.coverage).mean()) < 0.01
    assert inkmap.measurability(ink).ok


# --------------------------------------------------------------------------- #
# Synth
# --------------------------------------------------------------------------- #


def test_render_is_deterministic_given_a_seed():
    a = synth.render(perspective=0.05, noise=5, rng=42)
    b = synth.render(perspective=0.05, noise=5, rng=42)
    assert np.array_equal(a.image, b.image)


# --------------------------------------------------------------------------- #
# Barcode model recovery -- regression for a bug found on real photographs
# --------------------------------------------------------------------------- #

needs_pybarcode = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("barcode") is None,
    reason="python-barcode not installed",
)


def _render_barcode(symbology: str, data: str):
    import io

    import barcode
    from barcode.writer import ImageWriter
    from PIL import Image

    buf = io.BytesIO()
    barcode.get(symbology, data, writer=ImageWriter()).write(
        buf,
        options={
            "module_width": 0.4,
            "module_height": 12.0,
            "quiet_zone": 6.0,
            "write_text": False,
            "dpi": 300,
        },
    )
    return np.array(Image.open(buf).convert("L"))


@needs_pil
@needs_pybarcode
@pytest.mark.parametrize(
    "symbology,data,expected_modules",
    [
        ("ean13", "5901234123457", 95),
        ("ean8", "96385074", 67),
        ("upca", "036000291452", 95),
    ],
)
def test_fixed_width_symbologies_recover_the_spec_module_count(
    symbology, data, expected_modules
):
    """The count is fixed by the specification, so estimating it is a needless risk.

    Regression: a percentile-based module-width estimate returned 105 modules for a
    95-module EAN-13. Every bar after the first was then placed wrong, while the mask
    still looked like a barcode -- real-photograph round-trip decode was 5%.
    """
    image = _render_barcode(symbology, data)
    ink = inkmap.find(
        cv2.cvtColor(image, cv2.COLOR_GRAY2BGR), locators=["barcode_zxing"]
    )
    assert ink is not None, f"{symbology} not located"
    assert ink.model.bars.size == expected_modules


@needs_pil
@needs_pybarcode
@pytest.mark.parametrize("data", ["INKMAP-TEST", "0123456789"])
def test_variable_width_symbology_is_verified_against_the_payload(data):
    """Code 128 has no fixed module count, so the fit is checked by re-decoding."""
    from inkmap.locate.barcode import _decodes_to

    image = _render_barcode("code128", data)
    ink = inkmap.find(
        cv2.cvtColor(image, cv2.COLOR_GRAY2BGR), locators=["barcode_zxing"]
    )
    assert ink is not None
    assert _decodes_to(ink.model.bars, data), (
        "recovered bars do not decode to the payload"
    )


def test_locate_is_the_package_and_callable_as_the_cascade():
    """inkmap.locate is the locator package, and calling it runs the cascade.

    Regression (#5): the facade re-exported the locate() function over the package,
    so ``inkmap.locate.LOCATORS``, ``from inkmap import locate; locate.LOCATORS``
    (the package docstring's own example) and ``import inkmap.locate.marks as m``
    all failed.
    """
    import importlib
    import inspect
    import types

    from inkmap import locate

    assert isinstance(inkmap.locate, types.ModuleType)
    assert locate is inkmap.locate is importlib.import_module("inkmap.locate")
    assert locate.LOCATORS is inkmap.LOCATORS
    assert inkmap.locate.find_square_marks is inkmap.find_square_marks
    import inkmap.locate.marks as marks  # noqa: F401

    assert "scale" in inspect.signature(inkmap.locate).parameters
    import pickle

    assert pickle.loads(pickle.dumps(inkmap.locate)) is inkmap.locate  # process pools
    scene = synth.render(rng=0)
    bgr = cv2.cvtColor(scene.image, cv2.COLOR_GRAY2BGR)
    assert len(inkmap.locate(bgr, scene.image)) == len(locate.locate(bgr, scene.image)) > 0
