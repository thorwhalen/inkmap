"""Evaluate inkmap on real photographs of printed text.

Text is the hardest of the three mark types to validate, and the reason is worth stating
plainly: **inkmap's modelled path needs the right font.** A QR module grid is fully
determined once you know the module matrix, and a barcode's bars likewise. A glyph is
not: 'A' in Helvetica and 'A' in Times are different shapes, and if the model renders
the wrong one, the coverage map is wrong no matter how good the geometry is.

So this script measures two things separately:

1. **Geometry** -- can inkmap place a glyph model where the word actually is? Measured by
   how much the placed model overlaps an independent binarisation of the same region.
2. **Shape fidelity** -- how much of the residual error is the font, not the placement?
   Measured by comparing the glyph model against a ``RasterModel`` built from the image
   itself, which has the true shape by construction and isolates the font's contribution.

Tesseract supplies the word and its box. It is an independent oracle for *what* and
*where*; inkmap is not involved in producing either.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

import inkmap
from inkmap import models

warnings.filterwarnings("ignore")

MAX_SIDE = 1600
MIN_WORD_HEIGHT = 28  # px; below this a word cannot support a measurement anyway
MIN_CONFIDENCE = 80.0


@dataclass
class WordResult:
    image: str
    text: str
    confidence: float
    box: tuple[int, int, int, int]
    pixels_per_feature: float = 0.0
    glyph_iou: float | None = None
    """Placed glyph model vs an independent Sauvola binarisation."""
    raster_iou: float | None = None
    """Image-derived raster model vs the same binarisation -- the geometry-only ceiling."""
    separation: float = float("nan")
    measurable: bool = False
    notes: list[str] = field(default_factory=list)


def _load(path: Path):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    if max(image.shape[:2]) > MAX_SIDE:
        s = MAX_SIDE / max(image.shape[:2])
        image = cv2.resize(image, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return image


def find_words(bgr: np.ndarray):
    """Tesseract word boxes: an independent answer to *what* and *where*."""
    import pytesseract

    data = pytesseract.image_to_data(bgr, output_type=pytesseract.Output.DICT)
    out = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if not text or not text.isalnum() or conf < MIN_CONFIDENCE:
            continue
        h = int(data["height"][i])
        if h < MIN_WORD_HEIGHT:
            continue
        out.append(
            (
                text,
                conf,
                (
                    int(data["left"][i]),
                    int(data["top"][i]),
                    int(data["width"][i]),
                    h,
                ),
            )
        )
    return out


def _sauvola(gray: np.ndarray, inside: np.ndarray, scale: float) -> np.ndarray:
    from skimage.filters import threshold_sauvola

    window = max(15, int(scale * 4) | 1)
    return (gray < threshold_sauvola(gray, window_size=window, k=0.2)) & inside


def _iou(a: np.ndarray, b: np.ndarray) -> float | None:
    union = (a | b).sum()
    return float((a & b).sum() / union) if union else None


def evaluate_word(bgr, gray, text, conf, box) -> WordResult:
    x, y, w, h = box
    quad = np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
    result = WordResult(image="", text=text, confidence=conf, box=box)

    # 1. The glyph model: what inkmap would use if you told it the word.
    try:
        glyph = models.text_model(text, font_size=192)
    except Exception as exc:
        result.notes.append(f"glyph render failed: {exc}")
        return result

    ink = inkmap.find(bgr, model=glyph, quad=quad)
    if ink is None:
        result.notes.append("placement failed")
        return result
    result.pixels_per_feature = float(ink.placement.pixels_per_feature)
    verdict = inkmap.measurability(ink)
    result.measurable = bool(verdict.ok)
    result.notes.extend(verdict.reasons)

    inside = ink.inside_mask()
    if inside.sum() < 200:
        result.notes.append("region too small")
        return result
    reference = _sauvola(gray, inside, ink.placement.pixels_per_feature)
    result.glyph_iou = _iou(ink.foreground_mask() & inside, reference)

    fore = inkmap.measurement_mask(ink, kind="foreground")
    back = inkmap.measurement_mask(ink, kind="background")
    if fore.any() and back.any():
        result.separation = float(gray[back].mean() - gray[fore].mean())

    # 2. The geometry-only ceiling: a raster model taken from the image itself has the
    #    true shape, so whatever it scores is what placement alone can achieve. The gap
    #    between this and glyph_iou is the font's contribution.
    crop = gray[y : y + h, x : x + w]
    if crop.size > 100:
        from skimage.filters import threshold_sauvola

        window = max(15, int(max(3, h // 8)) | 1)
        mask = crop < threshold_sauvola(crop, window_size=window, k=0.2)
        raster = models.RasterModel(mask.astype(np.float32))
        rink = inkmap.find(bgr, model=raster, quad=quad, refine=False)
        if rink is not None:
            rinside = rink.inside_mask()
            result.raster_iou = _iou(
                rink.foreground_mask() & rinside, _sauvola(gray, rinside, 4.0)
            )
    return result


def main(folder: Path, out: Path, limit: int | None = None) -> None:
    paths = sorted(
        p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".png", ".jpeg"}
    )
    if limit:
        paths = paths[:limit]

    results: list[WordResult] = []
    for path in paths:
        bgr = _load(path)
        if bgr is None:
            continue
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        try:
            words = find_words(bgr)
        except Exception:
            continue
        for text, conf, box in words[:6]:  # cap per image so one poster cannot dominate
            r = evaluate_word(bgr, gray, text, conf, box)
            r.image = path.name
            results.append(r)

    glyph = [r.glyph_iou for r in results if r.glyph_iou is not None]
    raster = [r.raster_iou for r in results if r.raster_iou is not None]
    sep = [r.separation for r in results if np.isfinite(r.separation)]
    summary = {
        "kind": "text",
        "images": len(paths),
        "words_evaluated": len(results),
        "glyph_iou_median": float(np.median(glyph)) if glyph else None,
        "raster_iou_median": float(np.median(raster)) if raster else None,
        "separation_median": float(np.median(sep)) if sep else None,
        "separation_positive_rate": float(np.mean([s > 0 for s in sep]))
        if sep
        else None,
        "measurable_rate": float(np.mean([r.measurable for r in results]))
        if results
        else 0.0,
    }
    out.write_text(
        json.dumps(
            {"summary": summary, "words": [asdict(r) for r in results]}, indent=1
        )
    )
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    import sys

    main(
        Path(sys.argv[1]),
        Path(sys.argv[2] if len(sys.argv) > 2 else "eval_text.json"),
        int(sys.argv[3]) if len(sys.argv) > 3 else None,
    )
