---
name: inkmap-dev-validation
description: Read before changing anything in inkmap that could move a number — geometry, coverage rasterisation, refinement, blur estimation, measurement weighting, or a locator — and before regenerating docs/methods-and-results.md or docs/validation.md. Covers the three validation tiers (synthetic ground truth, real-photograph round-trip, corpus detection), how to run each, which numbers live in which document, and the half-pixel convention failures that any of these changes can silently reintroduce. Triggers on "regenerate the benchmarks", "update the validation numbers", "the report is stale", "did that change accuracy", or any edit to coverage.py / geometry.py / models/ / locate/.
metadata:
  audience: developers
  project: inkmap
---

# Validating inkmap

Three tiers, answering three different questions. Changing anything geometric means
re-running at least tiers 1 and 2, because the failure mode here is *silent*: a wrong
mask still looks like a mask.

| Tier | Question | Ground truth | Script |
|---|---|---|---|
| 1. Synthetic | Is the coverage value *correct*? | exact, by construction | `scripts/validate.py` |
| 2. Round-trip | Is the geometry right on *real* photos? | an independent decoder | `scripts/evaluate.py` |
| 3. Corpus | Does detection survive the real world? | none (rates only) | `scripts/corpus_eval.py` |

## Tier 1 — synthetic, exact

```bash
python scripts/validate.py > /tmp/validation.md
```

No network, ~2 minutes. Produces the geometric-accuracy, coverage-MAE,
photometric-bias and blur-estimation tables in `docs/validation.md`.

**Why it can be exact:** `synth.render` builds the image *from* the coverage map —
supersample the model through a known transform, then form the image as
`255 * (1 - coverage)`. Ground truth and stimulus are the same object, so degradations
applied afterwards leave the truth correct. `test_scene_ground_truth_is_self_consistent`
guards that property; if it fails, every number in tier 1 is meaningless.

## Tier 2 — round-trip on real photographs

```bash
python scripts/evaluate.py <corpus_root> eval.json
```

`<corpus_root>` holds `qr/`, `barcode/`, `text/` subfolders of real images.

**The trick:** no per-pixel ground truth exists for real photographs, so instead sample
the model through inkmap's *own* fitted transform, re-render it clean, and hand it to a
decoder. The decoder was not involved in fitting the geometry and has error correction,
so it does not accept near-misses.

**Calibrated sensitivity** (measured, and worth re-checking if you touch sampling):
round-trip passes at ≤0.25 units of transform error and fails at ≥0.5. So it certifies
"within a quarter of a unit", not "perfect". Do not oversell it.

Also computed: independent-model agreement (our sampled QR matrix vs OpenCV's separate
rectification) and class separation (background minus foreground grey level, which
collapses if the mask is misaligned).

## Tier 3 — corpus detection rates

```bash
python scripts/corpus_eval.py
```

Fetches and caches ~189 CC-licensed Commons photographs on first run (several minutes;
Commons rate-limits and the fetcher backs off). Produces the per-locator detection table.

## What lives where

- `docs/validation.md` — the numbers, all tiers. Regenerate wholesale; do not hand-edit
  a table, or it will drift from the script that claims to produce it.
- `docs/methods-and-results.md` — the narrative: approach, algorithms, results, limits.
  The published report; also the source of the PDF.
- `README.md` — only the headline photometric-bias table and the detection rates. If you
  change those numbers, update the README too; there is no automation tying them.

Rebuild the PDF after editing the report:

```bash
python scripts/build_report.py
```

## The failure this all exists to catch

Three half-pixel conventions have to agree, and each is invisible on inspection:

1. **Pixel centre vs corner** — OpenCV's integer coordinate `x` is the *centre* of a
   pixel spanning `[x-0.5, x+0.5)`. Rasterising `[x, x+1)` offsets the whole map half a
   pixel.
2. **The ECC template raster** — a model rendered at `s` px/unit puts template pixel `t`
   over `[t/s, (t+1)/s)`, so its centre is `(t+0.5)/s`.
3. **Locator corner conventions differ** — OpenCV's QR corners are the last *contained*
   pixel index; zxing-cpp returns the continuous outer boundary.

Getting these wrong cost 50× in accuracy during development. **The diagnostic:** if
refinement error grows with the mark's rotation angle following `R(d) − d`, the residual
`d` is a coordinate-convention offset, not noise. `test_rotation_does_not_scramble_the_model`
is the regression test; it is parameterised over eight angles precisely because the bug
is invisible at 0°.

A fourth, related trap: the ECC template needs a rendered clear margin. Blurring a
template that stops at the mark's edge makes the kernel reflect interior content across
the border, inventing an edge profile the photograph does not have — ECC then shifts the
whole fit to match the artefact (~0.45 px).

## Before you claim an improvement

- Run the full test suite; `tests/test_inkmap.py` is parameterised across model kinds
  (matrix, bars, raster, polygon, glyph) on purpose — a change that helps QR and breaks
  glyphs is not an improvement.
- Re-run tier 1 and compare tables, not vibes.
- Check that `measurability` still refuses the cases it should. Making more images
  "measurable" is a regression unless the bias table improved with it.
