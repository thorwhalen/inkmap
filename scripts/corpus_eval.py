"""Evaluate inkmap on the real-photograph corpus. Reproduces the tables in docs/validation.md.

Run ``python scripts/corpus_eval.py``. Fetches and caches the corpus on first run
(a few minutes; Commons rate-limits).
"""

from __future__ import annotations

import time
import warnings

import cv2
import numpy as np

import inkmap
from inkmap import data

warnings.filterwarnings("ignore")
MAX_SIDE = 1600  # downscale huge originals; a 4000 px billboard adds nothing but time


def _load(path):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    if max(image.shape[:2]) > MAX_SIDE:
        scale = MAX_SIDE / max(image.shape[:2])
        image = cv2.resize(
            image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
        )
    return image


def per_locator(images: list) -> None:
    print("\n## Detection rate per locator\n")
    print("| locator | images with a detection |")
    print("|---|---|")
    counts = {name: 0 for name in inkmap.LOCATORS}
    union = 0
    for image in images:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hit = False
        for name, fn in inkmap.LOCATORS.items():
            try:
                found = bool(fn(image, gray))
            except Exception:
                found = False
            counts[name] += found
            hit |= found
        union += hit
    n = len(images)
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"| {name} | {count / n * 100:.0f}% |")
    print(f"| **cascade (union)** | **{union / n * 100:.0f}%** |")


def end_to_end(images: list) -> None:
    print("\n## End to end\n")
    found = symbols = refined = measurable = 0
    times: list[float] = []
    seps: list[float] = []
    for image in images:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        start = time.perf_counter()
        try:
            maps = inkmap.find_all(image)
        except Exception:
            continue
        times.append(time.perf_counter() - start)
        if maps:
            found += 1
        for ink in maps:
            symbols += 1
            refined += ink.placement.refined
            measurable += inkmap.measurability(ink).ok
            mi = inkmap.measurement_mask(ink, kind="foreground")
            ms = inkmap.measurement_mask(ink, kind="background")
            if mi.sum() >= 40 and ms.sum() >= 40:
                seps.append(float(gray[ms].mean()) - float(gray[mi].mean()))

    n = len(images)
    print("| metric | value |")
    print("|---|---|")
    print(f"| images with >=1 mark | {found} / {n} ({found / n * 100:.0f}%) |")
    print(f"| marks found | {symbols} |")
    print(
        f"| refinement converged | {refined} / {symbols} ({refined / max(symbols, 1) * 100:.0f}%) |"
    )
    print(
        f"| judged measurable | {measurable} / {symbols} ({measurable / max(symbols, 1) * 100:.0f}%) |"
    )
    print(f"| median runtime | {np.median(times) * 1000:.0f} ms |")

    if seps:
        arr = np.array(seps)
        print("\n## Polarity check (ink must read darker than substrate)\n")
        print("| metric | value |")
        print("|---|---|")
        print(f"| symbols measured | {len(arr)} |")
        print(
            f"| correct polarity | {(arr > 0).sum()} / {len(arr)} ({(arr > 0).mean() * 100:.0f}%) |"
        )
        print(
            f"| separation > 50 levels | {(arr > 50).sum()} / {len(arr)} ({(arr > 50).mean() * 100:.0f}%) |"
        )
        print(f"| median separation | {np.median(arr):.0f} grey levels |")


if __name__ == "__main__":
    paths = data.fetch()
    print(f"corpus: {len(paths)} cached images")
    images = [img for img in (_load(p) for p in paths) if img is not None]
    per_locator(images)
    end_to_end(images)
