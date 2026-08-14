"""Evaluate inkmap on real photographs, with objective pass/fail criteria.

The hard part of validating a coverage map on real images is that no per-pixel ground
truth exists. This script gets around that with checks that are objective even without
it:

**Round-trip decode.** Sample the model through inkmap's *own* fitted transform, render
the sampled model back to a clean image, and decode that. If the transform is off by
more than roughly half a unit, the sampled model is wrong and either fails to decode or
decodes to something else. The decoder is an independent oracle: it was not involved in
fitting the geometry, and it has error correction, so it does not accept near-misses.

**Independent-model agreement.** For QR, OpenCV's ``straight_qrcode`` rectifies the
symbol by its own route. Comparing it module-for-module against inkmap's sampled matrix
cross-checks two independent geometry estimates.

**Class separation.** Foreground and background must actually differ in the image. A
mask that is rotated or half a unit off still looks plausible but mixes the classes, and
the separation collapses. This is the check that catches silent misalignment.

Nothing here rewards inkmap for agreeing with itself: every criterion is anchored to
either a decoder or the raw pixels.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

import inkmap
from inkmap import geometry, models

warnings.filterwarnings("ignore")

MAX_SIDE = 1600


@dataclass
class MarkResult:
    """One located mark, with every objective check we can run on it."""

    image: str
    kind: str
    locator: str
    payload: str | None = None
    pixels_per_feature: float = 0.0
    blur_sigma: float = float("nan")
    measurable: bool = False
    round_trip: bool | None = None
    """Did the model sampled through our transform decode back to the same payload?"""
    module_agreement: float | None = None
    """Fraction of cells matching OpenCV's independent rectification (QR only)."""
    binarization_iou: float | None = None
    """IoU against an independent Sauvola binarisation -- corroboration, not truth."""
    separation: float = float("nan")
    """Mean grey level of background minus foreground, over measured pixels."""
    n_foreground: int = 0
    n_background: int = 0
    notes: list[str] = field(default_factory=list)


def load(path: Path) -> np.ndarray | None:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    if max(image.shape[:2]) > MAX_SIDE:
        scale = MAX_SIDE / max(image.shape[:2])
        image = cv2.resize(
            image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
        )
    return image


# --------------------------------------------------------------------------- #
# Round-trip: re-render the fitted model and ask a decoder what it says
# --------------------------------------------------------------------------- #


def render_clean(model, scale: int = 8, quiet: int = 4) -> np.ndarray:
    """Render a model as a clean, generously quiet-zoned image a decoder will accept."""
    raster = models.render_model(model, scale, supersample=1)
    image = ((1.0 - (raster > 0.5)) * 255).astype(np.uint8)
    pad = quiet * scale
    return cv2.copyMakeBorder(image, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)


def decode_text(image: np.ndarray) -> str | None:
    try:
        import zxingcpp
    except ImportError:
        return None
    try:
        results = zxingcpp.read_barcodes(image)
    except Exception:
        return None
    return results[0].text if results else None


def round_trip(gray: np.ndarray, ink) -> tuple[bool | None, str | None]:
    """Sample the model through our transform, re-render, decode. Compare to payload."""
    placement = ink.placement
    if placement.payload is None:
        return None, None

    model = _resample_model(gray, placement)
    if model is None:
        return None, None
    text = decode_text(render_clean(model))
    return (text == placement.payload), text


def _resample_model(gray: np.ndarray, placement):
    """Re-read the model's cells/bars from the image using the fitted transform.

    Deliberately re-samples rather than reusing the model the locator produced: the
    point is to test the *transform*, so the model must be derived from it.
    """
    model = placement.model
    if isinstance(model, models.MatrixModel):
        from inkmap.locate.qr import sample_matrix

        cells = sample_matrix(gray, placement.transform, model.n_rows)
        return models.MatrixModel(cells)
    if isinstance(model, models.BarsModel):
        n = model.bars.size
        # Sample at bar centres, averaged over the middle of the bar height.
        us = (np.arange(n) + 0.5)[:, None]
        vs = np.linspace(0.3, 0.7, 9)[None, :] * model.height
        pts = np.stack(
            [np.repeat(us, vs.size, 1).ravel(), np.tile(vs, (n, 1)).ravel()], axis=1
        ).astype(np.float32)
        img_pts = cv2.perspectiveTransform(
            pts.reshape(-1, 1, 2), placement.transform
        ).reshape(n, vs.size, 2)
        h, w = gray.shape[:2]
        xs = np.clip(np.round(img_pts[..., 0]).astype(int), 0, w - 1)
        ys = np.clip(np.round(img_pts[..., 1]).astype(int), 0, h - 1)
        values = gray[ys, xs].mean(axis=1)
        lo, hi = np.percentile(values, [2, 98])
        return models.BarsModel(values < (lo + hi) / 2.0, height=model.height)
    return None


def binarization_iou(gray: np.ndarray, ink) -> float | None:
    """IoU between the modelled foreground and an independent local binarisation.

    Sauvola knows nothing about the model, so agreement is genuine evidence that the
    model landed where the ink is. It is *not* ground truth -- Sauvola has its own
    errors, and it places its boundary in the middle of the blurred edge, which is
    precisely what inkmap avoids -- so treat this as a corroboration score, not an
    accuracy figure. A misaligned model collapses it; a well-aligned one lands around
    0.7-0.9 depending on how well the model matches the real shape.
    """
    inside = ink.inside_mask()
    if inside.sum() < 200:
        return None
    try:
        from skimage.filters import threshold_sauvola
    except ImportError:
        return None

    window = max(15, int(ink.placement.pixels_per_feature * 4) | 1)
    thresh = threshold_sauvola(gray, window_size=window, k=0.2)
    dark = (gray < thresh) & inside

    if ink.polarity == inkmap.Polarity.FOREGROUND_IS_LIGHT:
        dark = (~dark) & inside
    model_fg = ink.foreground_mask() & inside
    union = (dark | model_fg).sum()
    return float((dark & model_fg).sum() / union) if union else None


def module_agreement(bgr: np.ndarray, ink) -> float | None:
    """Compare our sampled QR matrix against OpenCV's independent rectification."""
    model = ink.placement.model
    if not isinstance(model, models.MatrixModel):
        return None
    try:
        ok, _, _, straight = cv2.QRCodeDetector().detectAndDecodeMulti(bgr)
    except cv2.error:
        return None
    if not ok or straight is None or len(straight) == 0:
        return None
    for candidate in straight:
        if candidate is None or candidate.size == 0:
            continue
        other = candidate < 128
        if other.shape == model.cells.shape:
            return float((other == model.cells).mean())
    return None


# --------------------------------------------------------------------------- #
# Per-image evaluation
# --------------------------------------------------------------------------- #


def evaluate_image(path: Path, kind: str, *, locators=None) -> list[MarkResult]:
    bgr = load(path)
    if bgr is None:
        return []
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    kwargs = {} if locators is None else {"locators": list(locators)}
    try:
        maps = inkmap.find_all(bgr, **kwargs)
    except Exception as exc:
        return [
            MarkResult(path.name, kind, "error", notes=[f"{type(exc).__name__}: {exc}"])
        ]

    out = []
    for ink in maps:
        verdict = inkmap.measurability(ink)
        fore = inkmap.measurement_mask(ink, kind="foreground")
        back = inkmap.measurement_mask(ink, kind="background")
        separation = (
            float(gray[back].mean() - gray[fore].mean())
            if fore.any() and back.any()
            else float("nan")
        )
        ok, decoded = round_trip(gray, ink)
        out.append(
            MarkResult(
                image=path.name,
                kind=kind,
                locator=ink.placement.locator,
                payload=ink.placement.payload,
                pixels_per_feature=float(ink.placement.pixels_per_feature),
                blur_sigma=float(ink.blur_sigma)
                if ink.blur_sigma is not None
                else float("nan"),
                measurable=bool(verdict.ok),
                round_trip=ok,
                module_agreement=module_agreement(bgr, ink),
                binarization_iou=binarization_iou(gray, ink),
                separation=separation,
                n_foreground=int(fore.sum()),
                n_background=int(back.sum()),
                notes=list(verdict.reasons),
            )
        )
    return out


def summarise(results: list[MarkResult], kind: str, n_images: int) -> dict[str, Any]:
    rows = [r for r in results if r.kind == kind and r.locator != "error"]
    imgs = {r.image for r in rows}
    rt = [r.round_trip for r in rows if r.round_trip is not None]
    ma = [r.module_agreement for r in rows if r.module_agreement is not None]
    sep = [r.separation for r in rows if np.isfinite(r.separation)]
    biou = [r.binarization_iou for r in rows if r.binarization_iou is not None]
    ppf = [r.pixels_per_feature for r in rows if r.pixels_per_feature > 0]
    return {
        "kind": kind,
        "images": n_images,
        "images_with_mark": len(imgs),
        "detection_rate": len(imgs) / n_images if n_images else 0.0,
        "marks": len(rows),
        "round_trip_n": len(rt),
        "round_trip_rate": float(np.mean(rt)) if rt else None,
        "module_agreement_median": float(np.median(ma)) if ma else None,
        "separation_median": float(np.median(sep)) if sep else None,
        "binarization_iou_median": float(np.median(biou)) if biou else None,
        "separation_positive_rate": float(np.mean([s > 0 for s in sep]))
        if sep
        else None,
        "pixels_per_feature_median": float(np.median(ppf)) if ppf else None,
        "measurable_rate": float(np.mean([r.measurable for r in rows]))
        if rows
        else 0.0,
    }


def main(root: Path, out: Path) -> None:
    sets = {
        "qr": root / "qr",
        "barcode": root / "barcode",
        "text": root / "text",
    }
    results: list[MarkResult] = []
    summaries = []
    for kind, folder in sets.items():
        if not folder.exists():
            print(f"  (no {kind} folder at {folder})")
            continue
        paths = sorted(
            p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".png", ".jpeg"}
        )
        locators = None
        if kind == "barcode":
            locators = ["barcode_zxing"]
        elif kind == "qr":
            locators = ["qr_zxing", "qr_aruco", "qr_opencv"]
        for path in paths:
            results.extend(evaluate_image(path, kind, locators=locators))
        summaries.append(summarise(results, kind, len(paths)))
        print(f"  {kind}: {len(paths)} images done")

    out.write_text(
        json.dumps(
            {"summaries": summaries, "marks": [asdict(r) for r in results]}, indent=1
        )
    )
    print(f"\nwrote {out}")
    for s in summaries:
        print(json.dumps(s))


if __name__ == "__main__":
    import sys

    main(Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "eval.json"))
