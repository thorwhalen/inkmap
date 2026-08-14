"""Validate the erosion claim on REAL ink, against REAL per-pixel ground truth.

DIBCO (Document Image Binarization Contest, 2009-2019) is the only public dataset with
exact per-pixel ink/background ground truth. It is documents, not marks, so inkmap's
*modelled* path does not apply -- there is no shape to model. What it does uniquely
allow is testing the claim the whole measurement design rests on:

    A geometrically correct foreground mask is still not safe to measure on, because
    the imaging blur drags background signal into pixels that are entirely ink. Only
    spatial erosion removes it.

Everything else in this repository tests that on synthetic scenes, where the blur is
one we applied ourselves. Here the ink is real, the optics are real, the degradation is
real, and the mask is somebody else's hand-labelled ground truth -- inkmap plays no
part in producing it. If the claim is an artefact of the synthetic generator, this is
where it falls apart.

Method: take the GT foreground, erode it by r pixels, and measure the mean grey level.
If boundary pixels were uncontaminated, the mean would not move. The amount it moves is
the contamination a naive mask carries.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import cv2
import numpy as np

warnings.filterwarnings("ignore")

RADII = (0, 1, 2, 3, 4)
IMAGE_EXT = {".bmp", ".png", ".tif", ".tiff", ".jpg", ".jpeg"}


def pair_up(root: Path) -> list[tuple[Path, Path]]:
    """Match each source image to its ground-truth mask by stem and shape.

    DIBCO's directory naming is inconsistent across eleven editions, so pairing is done
    by resolution + stem rather than by trusting any folder convention.
    """
    by_stem: dict[str, list[Path]] = {}
    for path in root.rglob("*"):
        if path.suffix.lower() not in IMAGE_EXT:
            continue
        stem = path.stem.lower()
        for suffix in ("_gt", "-gt", "_estgt", "_skelgt", "_gt_gray"):
            stem = stem.replace(suffix, "")
        by_stem.setdefault(stem, []).append(path)

    pairs = []
    for stem, paths in by_stem.items():
        gts = [
            p for p in paths if "gt" in p.stem.lower() and "skel" not in p.stem.lower()
        ]
        srcs = [p for p in paths if p not in gts]
        if not gts or not srcs:
            continue
        for src in srcs:
            img = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            for gt in gts:
                mask = cv2.imread(str(gt), cv2.IMREAD_GRAYSCALE)
                if mask is None or mask.shape != img.shape:
                    continue
                if len(np.unique(mask)) > 2:
                    continue
                pairs.append((src, gt))
                break
            break
    return sorted(pairs)


def measure_pair(src: Path, gt: Path) -> dict | None:
    image = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    mask = cv2.imread(str(gt), cv2.IMREAD_GRAYSCALE)
    if image is None or mask is None or image.shape != mask.shape:
        return None

    # DIBCO GT: ink is 0 (black), background 255.
    foreground = mask < 128
    background = ~foreground
    if foreground.sum() < 500 or background.sum() < 500:
        return None

    values = image.astype(np.float32)
    background_mean = float(values[background].mean())

    row: dict = {
        "image": src.name,
        "ink_fraction": float(foreground.mean()),
        "background_mean": background_mean,
        "foreground_mean": {},
        "kept_fraction": {},
    }
    for r in RADII:
        if r == 0:
            eroded = foreground
        else:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2)
            eroded = cv2.erode(foreground.astype(np.uint8), k).astype(bool)
        if eroded.sum() < 100:
            break
        row["foreground_mean"][str(r)] = float(values[eroded].mean())
        row["kept_fraction"][str(r)] = float(eroded.sum() / foreground.sum())
    return row if row["foreground_mean"] else None


def main(root: Path, out: Path) -> None:
    pairs = pair_up(root)
    print(f"paired {len(pairs)} image/ground-truth files")

    rows = [r for r in (measure_pair(s, g) for s, g in pairs) if r]
    print(f"measured {len(rows)}\n")

    print("Contamination of a geometrically correct mask, on real ink (DIBCO).")
    print("Foreground mean grey at each erosion radius; the shift from r=0 is the")
    print("contamination that boundary pixels carry.\n")
    print(
        f"{'erosion r':>10} {'fg mean':>9} {'shift vs r=0':>14} {'as % of contrast':>18} {'pixels kept':>12}"
    )

    base = np.median([r["foreground_mean"]["0"] for r in rows])
    contrast = np.median(
        [r["background_mean"] - r["foreground_mean"]["0"] for r in rows]
    )
    summary = []
    for radius in RADII:
        key = str(radius)
        vals = [r["foreground_mean"][key] for r in rows if key in r["foreground_mean"]]
        kept = [r["kept_fraction"][key] for r in rows if key in r["kept_fraction"]]
        if not vals:
            continue
        median = float(np.median(vals))
        shift = median - base
        summary.append(
            {
                "radius": radius,
                "foreground_mean": median,
                "shift": shift,
                "shift_pct_of_contrast": 100.0 * shift / contrast if contrast else None,
                "kept_fraction": float(np.median(kept)),
                "n": len(vals),
            }
        )
        print(
            f"{radius:>10} {median:>9.1f} {shift:>14.1f} "
            f"{100.0 * shift / contrast:>17.1f}% {np.median(kept):>11.1%}"
        )

    print(
        f"\nmedian background mean: {np.median([r['background_mean'] for r in rows]):.1f}"
    )
    print(f"median foreground/background contrast at r=0: {contrast:.1f} grey levels")
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    import sys

    main(Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "dibco.json"))
