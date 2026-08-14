"""Reproduce every number in docs/validation.md.

Run: ``python scripts/validate.py``. Synthetic scenes only, so it needs no network
and no cached corpus; the real-photograph figures come from ``scripts/corpus_eval.py``.
"""

from __future__ import annotations

import numpy as np

import inkmap
from inkmap import geometry, synth
from inkmap.coverage import measurement_weight

TRIALS = 12


def _corner_rms(estimated: np.ndarray, truth: np.ndarray, model) -> float:
    a = geometry.transform_to_quad(estimated, model)
    b = geometry.transform_to_quad(truth, model)
    return float(np.sqrt(((a - b) ** 2).sum(axis=1).mean()))


def geometry_accuracy() -> None:
    print("\n## Geometric accuracy: detector corners vs model-based refinement")
    print("\n| condition | detector corners (px RMS) | refined (px RMS) | gain |")
    print("|---|---|---|---|")
    conditions = [
        ("clean, frontal", dict()),
        ("mild perspective", dict(perspective=0.03, blur=0.8, noise=2, gradient=0.1)),
        ("strong perspective", dict(perspective=0.08, blur=1.5, noise=4, gradient=0.2)),
        (
            "defocused (sigma 3)",
            dict(perspective=0.03, blur=3.0, noise=3, gradient=0.2),
        ),
        ("noisy + gradient", dict(perspective=0.05, blur=1.2, noise=12, gradient=0.4)),
        ("glare + jpeg", dict(perspective=0.04, blur=1.0, glare=0.3, jpeg_quality=70)),
    ]
    for name, kw in conditions:
        raw, ref = [], []
        for t in range(TRIALS):
            scene = synth.render(pixels_per_unit=10.0, size=900, rng=t, **kw)
            import cv2

            bgr = cv2.cvtColor(scene.image, cv2.COLOR_GRAY2BGR)
            located = inkmap.locate(bgr, scene.image)
            if not located:
                continue
            placement = located[0]
            refined, _ = geometry.refine_transform(
                scene.image, placement.model, placement.transform
            )
            model = placement.model
            raw.append(_corner_rms(placement.transform, scene.transform, model))
            ref.append(_corner_rms(refined, scene.transform, model))
        if not raw:
            print(f"| {name} | not detected | | |")
            continue
        r, f = np.median(raw), np.median(ref)
        print(f"| {name} | {r:.2f} | {f:.2f} | {r / max(f, 1e-9):.0f}x |")


def coverage_accuracy() -> None:
    print("\n## Coverage accuracy vs exact ground truth (MAE)")
    print("\n| condition | overall MAE | MAE on mixed pixels |")
    print("|---|---|---|")
    conditions = [
        ("clean", dict()),
        ("mild perspective", dict(perspective=0.03, blur=0.8, noise=2)),
        ("strong perspective", dict(perspective=0.08, blur=1.5, noise=4, gradient=0.2)),
        ("glare + jpeg", dict(perspective=0.04, blur=1.0, glare=0.3, jpeg_quality=70)),
    ]
    for name, kw in conditions:
        overall, mixed = [], []
        for t in range(TRIALS):
            scene = synth.render(pixels_per_unit=9.7, size=900, rng=t, **kw)
            ink = inkmap.find(scene.image)
            if ink is None:
                continue
            err = np.abs(ink.coverage - scene.coverage)
            edge = (scene.coverage > 0.02) & (scene.coverage < 0.98)
            overall.append(float(err.mean()))
            if edge.any():
                mixed.append(float(err[edge].mean()))
        if overall:
            print(f"| {name} | {np.median(overall):.4f} | {np.median(mixed):.3f} |")


def photometric_bias() -> None:
    print("\n## Photometric bias: which pixels you measure")
    print(
        "\nRecovering a foreground-only signal (true value 100) from a frame "
        "blurred by the camera PSF. Bias in %, median of "
        f"{TRIALS} scenes.\n"
    )
    print("| px/feature | PSF sigma | coverage>0.5 | coverage==1 | weight (2 sigma) |")
    print("|---|---|---|---|---|")
    import cv2

    signal = 100.0
    for ppm, size in ((12.0, 700), (6.0, 400)):
        for psf in (0.0, 1.0, 2.0, 3.0):
            rows: dict[str, list[float]] = {"c05": [], "c1": [], "w": []}
            for t in range(TRIALS):
                scene = synth.render(
                    pixels_per_unit=ppm,
                    size=size,
                    perspective=0.05,
                    blur=1.2,
                    noise=3,
                    gradient=0.2,
                    rng=200 + t,
                )
                truth = scene.coverage * signal
                if psf:
                    truth = cv2.GaussianBlur(truth, (0, 0), psf)
                ink = inkmap.find(scene.image)
                if ink is None:
                    continue
                weight = measurement_weight(
                    ink.coverage, blur_sigma=psf if psf else 0.5, kind="foreground"
                )
                for key, mask in (
                    ("c05", ink.coverage > 0.5),
                    ("c1", ink.coverage >= 0.999),
                    ("w", weight >= 0.999),
                ):
                    if mask.any():
                        rows[key].append((truth[mask].mean() - signal) / signal * 100)
            fmt = lambda k: f"{np.median(rows[k]):+.2f}%" if rows[k] else "n/a"  # noqa: E731
            print(
                f"| {ppm:.0f} | {psf:.1f} | {fmt('c05')} | {fmt('c1')} | {fmt('w')} |"
            )


def blur_estimation() -> None:
    print("\n## Blur estimation")
    print("\n| true sigma | estimated (median) |")
    print("|---|---|")
    for true_sigma in (0.5, 1.0, 1.5, 2.0, 3.0):
        got = []
        for t in range(TRIALS):
            scene = synth.render(
                pixels_per_unit=12.0, size=800, blur=true_sigma, noise=2, rng=t
            )
            ink = inkmap.find(scene.image)
            if (
                ink is not None
                and ink.blur_sigma is not None
                and np.isfinite(ink.blur_sigma)
            ):
                got.append(ink.blur_sigma)
        print(
            f"| {true_sigma:.1f} | {np.median(got):.2f} |"
            if got
            else f"| {true_sigma:.1f} | n/a |"
        )


if __name__ == "__main__":
    geometry_accuracy()
    coverage_accuracy()
    photometric_bias()
    blur_estimation()
