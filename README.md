# inkmap

Per-pixel foreground coverage for photographed marks.

Given a photo of a printed mark and a **model** of its shape, say — for every pixel —
how much of it is foreground (the mark) and how much is background (the substrate). Not
a boolean mask: a continuous 0–1 area fraction, accurate enough to measure on.

```bash
pip install inkmap
```

```python
import inkmap

coverage = inkmap.foreground("photo.jpg")   # (H, W) float32 in [0, 1]
```

## The idea

Decoding a QR code is a solved problem. Reading text is a solved problem. **Measuring**
the mark itself is not: if you need to know the reflectance, density, or colour of the
printed material — as opposed to what it says — you need to know exactly which pixels
are mark, which are substrate, and which are neither.

The shape is the input, not a special case. A model answers one question — *is this
point, in my own coordinate system, foreground?* — and everything else (locating,
sub-pixel refinement, rasterising, measuring) is written against that one question. So
QR symbols, barcodes, printed letters and arbitrary artwork all go through one pipeline.

```python
from inkmap import models

inkmap.find(photo)                                        # auto-detect QR / barcode
inkmap.find(photo, model=models.text_model("ABC"), quad=q)  # printed text
inkmap.find(photo, model=models.RasterModel(logo), quad=q)  # anything you can draw
inkmap.find(photo, model=models.PolygonModel(outlines), quad=q)   # exact vector shape
```

Writing your own is two members and no base class:

```python
class Disc:
    extent = (20.0, 20.0)      # model space is 20 x 20 units
    feature_size = 10.0        # smallest feature that must be resolved

    def occupancy(self, u, v):                    # vectorised
        return (u - 10) ** 2 + (v - 10) ** 2 < 81

inkmap.find(photo, model=Disc(), quad=corners)
```

## What you get back

```python
ink = inkmap.find("photo.jpg")        # an InkMap, or None

ink.placement.quad                    # (4, 2) corners — a quadrilateral, not a
                                      # rectangle; perspective is expected
ink.placement.transform               # (3, 3) model space -> image pixels
ink.placement.pixels_per_feature      # the resolution figure that governs everything

ink.coverage                          # (H, W) float32 — foreground area fraction
ink.region                            # OUTSIDE / MARGIN / BACKGROUND / FOREGROUND
ink.weight                            # (H, W) float32 — safe-to-measure weighting
```

Then measure:

```python
result = inkmap.measure("photo.jpg", ink)

result.foreground_mean                # sRGB-linearised mean over safe pixels
result.background_mean
result.contrast
result.measurability.ok               # False if this image can't support it
```

`measure` accepts any frame registered to the one you located in, so geometry can be
established once on the sharpest image and reused across exposures, channels or
modalities.

## The three 0–1 channels

Conflating these is the fastest route to a wrong measurement:

| | what it is | use it for |
|---|---|---|
| `coverage` | **geometric** — fraction of the pixel's area under foreground | reporting, print QC, finding mixed pixels |
| `weight` | **blur-aware** — coverage eroded by how far the PSF actually reaches | **the only channel that should gate a measurement** |
| `confidence` | **epistemic** — how much to trust the label here | quality gating, artefact rejection |

If the underlying reality is binary, "probability this pixel is foreground" is
`confidence`. If it isn't — a pixel genuinely straddling an edge — the degree of
membership is `coverage`. They are different numbers and both are worth having.

Measured on synthetic scenes with exact ground truth, recovering a foreground-only
signal at 6 px per feature:

| pixel selection | no blur | σ=1 | σ=2 | σ=3 |
|---|---|---|---|---|
| `coverage > 0.5` (what a threshold gives you) | −3.3% | −12.2% | −23.3% | −32.4% |
| `coverage == 1.0` (geometrically pure) | −0.0% | −8.0% | −19.9% | −30.1% |
| **`weight`** (PSF-eroded) | **+0.0%** | **−0.2%** | **−0.6%** | **−1.5%** |

Geometric purity is *not* sufficient: blur drags background signal into pixels entirely
under foreground, and that contamination has a different footprint from partial
coverage — so no coverage-based weighting removes it. Only spatial erosion does. See
[docs/validation.md](docs/validation.md).

## Terminology

The classes are **foreground** and **background**, never dark/light — appearance
inverts (white-on-black print, reflectance-reversed symbols, inverted imaging), so an
appearance-based name would mean the mark in one image and the substrate in the next.
`Polarity` carries that mapping explicitly:

```python
from inkmap import Polarity
inkmap.find(photo, polarity=Polarity.FOREGROUND_IS_LIGHT)
```

The continuous value is **coverage**, after ISO 12647-2 *area coverage*. Full
cross-field mapping to ISO/IEC 18004, 15415, DIBCO, printing, matting, remote sensing
and medical-imaging vocabulary: [docs/terminology.md](docs/terminology.md).

## How it works

```
photograph ──► locate ──► recover model ──► refine transform ──► rasterise ──► erode
```

1. **Locate** — a cascade of `zxing-cpp`, OpenCV's Aruco-based QR detector and OpenCV's
   classic detector, plus linear barcodes. On 189 real photographs: zxing 74%, aruco
   68%, OpenCV 43%, **union 80%**. For marks nothing can auto-detect, `inkmap.place()`
   takes the corners from you.
2. **Recover the model** — from a bit-exact rectification where a decoder offers one,
   otherwise sampled from the image. *Never* by re-encoding a decoded payload:
   error-correction level, mask pattern and code-set choices are not recoverable from
   the text, so re-encoding can silently produce a different pattern.
3. **Refine** — align the rendered model to the photograph with ECC. Four locator
   corners are four observations; the model has thousands. Takes corner error from
   ~1 px to **0.02–0.03 px** (4–53× depending on conditions).
4. **Rasterise** — supersample each pixel, back-project through the transform, ask the
   model `occupancy(u, v)`. Exact up to the supersampling rate, and independent of
   lighting. Coverage MAE against exact ground truth is **0.0000–0.0005**.
5. **Erode to a weight** — by ~2× the estimated blur σ, because geometric purity is not
   enough (see the table above).

Decoding is optional throughout. A mark whose material barely deposited will not
decode, and that is exactly the case that must still work.

Sub-pixel geometry turns out to hinge on **three half-pixel conventions agreeing** —
pixel-centre vs pixel-corner rasterisation, the template raster, and the fact that
different locators disagree about what a "corner" is. Getting them wrong cost 50× in
accuracy during development, and none of it is visible on inspection: the mask still
looks like a mask. The diagnostic, if you ever chase this: *if the error grows with the
mark's rotation angle following `R(d) − d`, the residual `d` is a convention offset, not
noise.*

## How well it works

Validated three ways, because no single way is sufficient — synthetic scenes (exact
ground truth by construction), real photographs (round-trip through an independent
decoder), and DIBCO (hand-labelled per-pixel ink truth).

| | detection | round-trip geometry | round-trip when *measurable* |
|---|---|---|---|
| **QR** (189 real photos) | 80% | 77% | **96%** |
| **Barcode** (56 real photos) | 95% | 48% | **89%** |
| **Text** (86 real words) | — (no locator; you supply the quad) | — | see below |

The conditional matters: **when inkmap judges an image measurable, an independent decoder
confirms the geometry 96% of the time.** Failures concentrate where the library already
says not to trust it.

On **real ink with hand-labelled ground truth** (DIBCO), eroding a *perfect* mask by one
pixel shifts the measured foreground mean by **17% of the foreground/background
contrast** — so the contamination argument is not an artefact of synthetic data.

**Text is the honest weak spot.** Placement works (IoU 0.76 with an image-derived shape)
but a glyph model with the wrong font does not (IoU 0.17). Measured directly: with the
correct font IoU is 0.997–1.000; with a wrong one, 0.46–0.80. For text, pass the actual
font or take the shape from the image.

📄 **[Methods and results](docs/methods-and-results.md)** ([PDF](docs/methods-and-results.pdf))
— the full write-up: approach, algorithms, every number, the datasets, the limits, and a
barcode defect the evaluation caught and forced a fix for (round-trip 5% → 48%).

## Large photographs: locate coarse, refine fine

Locating is a large share of the cost on big frames and scales with pixel count, so `find_all(photo, locate_scale=0.5)` (or `locate(bgr, gray, scale=0.5)`) runs the detectors on an `INTER_AREA`-downscaled copy and maps the placements back to full resolution; refinement then pins them to sub-pixel accuracy as usual, so coverage maps match the full-resolution ones. On a 4000 x 3000 photograph of a page with 8 QR codes, locating took 1,129 ms at full resolution, 288 ms at 0.5 and 152 ms at 0.35, with all 8 codes found and decoded (on a slower 2-core server, a synthetic page of the same size: 11.6 s, 2.5 s and 1.1 s).

Use it when your codes are large in the frame: a code's modules should still span about 4 px after downscaling (`config.MIN_COARSE_PIXELS_PER_FEATURE`), i.e. 8 px at full resolution for 0.5 and about 11.5 px for 0.35. Below that the module count and pattern read off the small frame go wrong even though the code still decodes (at 2 px a 25 x 25 QR reads as 21 x 21), and refinement cannot repair a wrong model. So, with `full_res_retry=True` (the default), any coarse placement under that floor, or found but not decoded, is re-located on a full-resolution crop around it (`metadata["locate_retry"]` says why). The crops are small, but if every code needs one the speedup is gone, so pick the scale from your smallest code. With `full_res_retry=False`, placements under the floor are kept and marked `metadata["locate_undersampled"] = True`; do not trust their model. Custom locators run on the downscaled frame and must return coordinates in the frame they are given. A code the coarse pass misses entirely is not recovered, so lower the downscaling instead. The default, `None`, locates at full resolution exactly as before.

## Registration marks

Printed targets often carry plain marks with no code to decode: a solid square, or nested-square bullseyes at the corners of a sheet, as on OMR forms. `find_square_marks` finds them and returns each one's projective centre to a small fraction of a pixel, which is what pose estimation needs:

```python
from inkmap.locate import BULLSEYE_RINGS, find_square_marks

marks = find_square_marks(gray)                 # largest first
for m in marks:
    m.centre, m.sigma_px                        # sub-pixel centre, its typical error
    m.corners                                   # (4, 2), clockwise from the top-left
    m.rings                                     # () for a solid square
bullseyes = [m for m in marks if m.ring_error(BULLSEYE_RINGS) < 0.06]
```

Nested marks are told apart by their ring ratios (bullseye 0.64/0.32, QR finder 5/7 and 3/7), which perspective barely changes. Anything square is a candidate (a QR symbol's data modules too), so which mark is which on your layout stays with you; marks over 10% of the frame need `max_side_share=`. On synthetic sheets at up to 15% corner perspective and blur ≤ 2 px, the worst centre error is 0.13 px ([validation](docs/validation.md#square-registration-marks)).

## Plain patches

A single printed colour patch on a paper strip has no code and no marks to locate it by. `locate_patch` finds it from a seed point and returns the three things a measurement of the patch against its own paper needs: its interior, clear of the edge; a narrow ring of bare substrate round it; and a verdict on whether to trust them.

```python
regions = inkmap.locate_patch(photo)              # seeded at the frame's centre
regions = inkmap.locate_patch(photo, seed=(x, y))
regions.patch, regions.substrate                  # boolean masks over the frame
regions.ok, regions.notes                         # the verdict, and why not
regions.quad                                      # (4, 2) sub-pixel corners

ink = inkmap.analyze(photo, [regions.placement])[0]   # or: find(photo, locators=["patch"])
inkmap.measure(photo, ink)                        # patch vs the substrate round it
```

The patch is grown from the seed's CIELAB colour and its sides fitted to the colour edge, so a pale patch on white paper is placed as well as a dark one. Uneven light is divided out when it would otherwise defeat a pale patch. The verdict refuses a patch that leaked into the paper, is cut by the frame, or has no paper round it; see [validation](docs/validation.md#plain-patches). On flash bursts, seed on an unlit frame: under flash a pale patch clips to white.

## Extending it

```python
inkmap.LOCATORS["mine"] = my_locator          # (bgr, gray) -> list[Placement]
inkmap.find(photo, locators=["mine", "qr_zxing"])
```

Tunable defaults live in `inkmap.config` — supersampling, ECC parameters, erosion
margin, saturation levels — as documented constants rather than inline magic numbers.

## Skills for AI agents

If you drive inkmap from an agent, the shipped skill
[`inkmap-usage`](inkmap/data/skills/inkmap-usage/SKILL.md) is the short version of
everything that is easy to get wrong: choosing a model, the corner-order trap, which of
the three 0–1 channels to use for what, and gating on measurability. Install it with
[`skill`](https://github.com/thorwhalen/skill), or just read it.

## Test data

384 real photographs of marks in the wild — 189 QR, 56 barcodes, 139 printed text —
(CC0 / public domain / CC BY / CC BY-SA), fetched on demand and cached:

```python
from inkmap import corpus

corpus.kinds()                        # {'qr': 189, 'barcode': 56, 'text': 139}
paths = corpus.fetch(kind="barcode")
print(corpus.attribution_text())      # attribution is required for CC BY / CC BY-SA
```

Synthetic scenes with **exact** ground-truth coverage — the only way to validate a 0–1
output, since no photograph comes with per-pixel truth:

```python
from inkmap import synth

scene = synth.render(my_model, perspective=0.05, blur=1.2, glare=0.3, jpeg_quality=80)
scene.image      # the degraded photograph
scene.coverage   # exact ground truth, by construction
```

## Looking at results

Coverage maps look plausible when subtly wrong, so check them:

```python
from inkmap import viz
import cv2

# original | overlay | coverage | weight
cv2.imwrite("check.png", viz.panel(photo, ink))
cv2.imwrite("grid.png", viz.overlay(photo, ink, draw_grid=True))
```

## Install notes

Hard dependencies are `numpy`, `opencv-python-headless` and `zxing-cpp` — all
permissively licensed (BSD / Apache-2.0), all pure wheels, no system libraries.

If you already have `opencv-python` or `opencv-contrib-python`, install with
`--no-deps` and keep yours: all four `opencv-*` distributions provide the same `cv2`
and conflict when more than one is installed.

`segno` is needed only to build a QR for an arbitrary payload (`inkmap[synth]`);
Pillow only for `GlyphModel` (`inkmap[text]`).

Deliberately **not** used: `qrdet` / `qreader`, which are MIT on the tin but depend on
`ultralytics`, which is AGPL-3.0.

## License

MIT
