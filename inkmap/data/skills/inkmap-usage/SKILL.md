---
name: inkmap-usage
description: Use when you need per-pixel foreground/background separation of a printed mark in a photograph — a QR code, barcode, printed text, logo, or any shape you can model — or when you need to MEASURE something about the mark itself (its reflectance, density, colour, how much of it actually printed) rather than decode it. Triggers on "which pixels are the ink", "segment the QR code", "measure the printed area", "ink coverage", "foreground mask for this mark", "is this print defective", "compare two exposures of a label", "subpixel mask", "measure the barcode not read it". Covers choosing a model, the corner-order trap, which of the three 0–1 channels to use for what, and the measurability gate that stops you reporting a number biased by tens of percent.
metadata:
  audience: users
  project: inkmap
---

# Using inkmap correctly

`inkmap` answers: **for each pixel, how much of it is the printed mark?** It returns a
continuous 0–1 fraction, not a boolean, and it is built so you can make physical
measurements on the result.

```bash
pip install inkmap
```

```python
import inkmap
coverage = inkmap.foreground("photo.jpg")   # (H, W) float32 in [0, 1]
```

Read this before writing anything beyond that one-liner. Four things below are easy to
get wrong and produce **plausible, silently incorrect** results.

## 1. Is inkmap the right tool?

| You want | Use |
|---|---|
| The payload of a QR/barcode | `zxing-cpp` directly. inkmap does not decode for you. |
| A bounding box around a mark | a detector (zxing, OpenCV). inkmap is overkill. |
| **Which pixels are the mark**, sub-pixel | **inkmap** |
| **Measure** reflectance/colour/density *of the mark* | **inkmap** |
| Is the print defective / did the ink deposit | **inkmap** (`source="observed"` vs modelled) |
| Binarise a scanned document (no known shape) | a document binariser (Sauvola, DIBCO-lineage). inkmap needs a *model*. |

The last row matters: inkmap is **model-driven**. It needs to know what shape to expect.
If you have no idea what the mark looks like, this is the wrong library.

## 2. Choose a model

The model is the input, not a special case. Pick by what you know:

```python
from inkmap import models

models.MatrixModel(cells)        # QR, Data Matrix, Aztec — a grid of cells
models.BarsModel(bars)           # EAN, Code 128, ... — a run of bars
models.RasterModel(mask)         # a logo, a scan, anything you can draw
models.PolygonModel(outlines)    # exact vector outlines, holes via even-odd
models.GlyphModel("ABC")         # printed text, rendered via Pillow
```

**Auto-detected** (no model needed): QR codes and linear barcodes.

```python
ink = inkmap.find(photo)          # largest mark
inks = inkmap.find_all(photo)     # every mark; 1 image in 5 has more than one
```

**Everything else** — text, logos, engraved marks — you supply the model *and* where it
is:

```python
ink = inkmap.find(photo, model=models.text_model("EXIT"), quad=corners)
```

### Writing your own model — two members, no base class

```python
class Disc:
    extent = (20.0, 20.0)     # model space is 20 x 20 of your units
    feature_size = 10.0       # smallest feature that must be resolved (see §5)

    def occupancy(self, u, v):            # must be vectorised over arrays
        return (u - 10) ** 2 + (v - 10) ** 2 < 81

inkmap.find(photo, model=Disc(), quad=corners)
```

Return `True`/1.0 for foreground. Points outside `extent` **must** return 0.

## 3. The corner-order trap

`quad` is four `(x, y)` image points in the **model's own order**: the point
corresponding to model-space `(0, 0)` first, then clockwise.

**Do not sort the corners by image position.** Sorting by coordinate sum/difference is
a very common idiom and it works fine until the mark is rotated past 45°, at which point
it permutes the corners relative to the model — rotating the model and producing a mask
of exactly the right size and density in the wrong places. It looks correct. It is not.

If you only have an unordered quad and the mark is orientation-ambiguous, you must
resolve the orientation some other way (a decoder, a fiducial, a known feature).

## 4. Which 0–1 channel? (the most consequential choice)

```python
ink.coverage    # geometric  — fraction of the pixel's area under foreground
ink.weight      # blur-aware — how safe this pixel is to MEASURE
inkmap.confidence(gray, ink.placement, ink.coverage)   # epistemic — trust in the label
```

| Goal | Use |
|---|---|
| Report/visualise how much ink is where | `coverage` |
| Find mixed/edge pixels | `0 < coverage < 1` |
| **Aggregate a physical measurement** | **`weight`** (or `inkmap.measurement_mask`) |
| Reject glare, clipping, model disagreement | `confidence` |
| A label for display | `ink.foreground_mask()` |

**Never aggregate a measurement over `coverage` or `foreground_mask`.** Geometric purity
is necessary but not sufficient: optical blur drags background signal into pixels that
are entirely under foreground, and that contamination has a *different footprint* from
partial area coverage, so no coverage-weighting removes it. Measured bias at 6 px per
feature:

| selection | no blur | σ=1 | σ=2 | σ=3 |
|---|---|---|---|---|
| `coverage > 0.5` | −3.3% | −12.2% | −23.3% | −32.4% |
| `coverage == 1.0` | −0.0% | −8.0% | −19.9% | −30.1% |
| **`weight`** | +0.0% | **−0.2%** | **−0.6%** | **−1.5%** |

If someone asks "why is my measured ink reflectance too high/low", this table is almost
always the answer.

## 5. Gate on measurability — do not skip this

```python
result = inkmap.measure(photo, ink)
if not result.measurability.ok:
    print(result.measurability.reasons)   # say so; do not report the number
else:
    print(result.contrast)
```

Below roughly **6 pixels per feature per unit of blur σ**, the blur is wide relative to
the mark's smallest feature, erosion leaves nothing uncontaminated, and the mean is
biased by tens of percent. inkmap refuses instead of guessing. On a corpus of real web
photographs of QR codes, **about half** failed this gate — that is the honest answer for
low-resolution images, not a defect.

`pixels_per_feature`, not `pixels_per_unit`, is the number that matters: a QR module is
both, but a glyph raster cell is far smaller than a stroke.

## 6. Polarity — never assume dark = mark

```python
from inkmap import Polarity
inkmap.find(photo, polarity=Polarity.FOREGROUND_IS_LIGHT)   # white-on-black, inverted imaging
```

Classes are **foreground/background**, never dark/light, because appearance inverts. If
you are comparing two frames where the mark's apparent brightness flips between them,
establish geometry on the frame where the mark reads normally and reuse it.

## 7. Recipes

**Measure the mark against its own substrate** (the substrate inside the mark samples
the same illumination, so the scene calibrates itself):

```python
ink = inkmap.find(photo)
r = inkmap.measure(photo, ink, flatten=True)   # flatten fits an illumination field
r.foreground_mean, r.background_mean, r.contrast
```

**Compare two frames** (different exposure, channel, or modality). Locate once on the
sharpest/most legible frame, then measure both — `measure` accepts any frame registered
to it:

```python
ink = inkmap.find(sharp_frame)
a = inkmap.measure(frame_a, ink)
b = inkmap.measure(frame_b, ink)
```

Register the frames first if they are separate captures; sub-pixel misalignment puts an
edge into the difference.

**Detect a print defect** — modelled coverage says where the mark *should* be, observed
coverage says where it *is*; their disagreement is the defect:

```python
modelled = inkmap.find(photo)
observed = inkmap.find(photo, source="observed")
defect = modelled.coverage - observed.coverage
```

**Check your result visually** — do this at least once per new setup:

```python
from inkmap import viz
import cv2
cv2.imwrite("check.png", viz.panel(photo, ink))          # original|overlay|coverage|weight
cv2.imwrite("grid.png", viz.overlay(photo, ink, draw_grid=True))
```

In `grid.png` the grid lines must sit on the mark's own boundaries. If they are offset by
half a unit, everything downstream is wrong while still looking fine.

## 8. Pitfalls, condensed

- **Do not re-encode a decoded payload to get the model.** EC level, mask pattern and
  code-set choices are not recoverable from the text, so re-encoding can silently
  produce a different pattern. inkmap reads the model from the image; you should too.
- **Do not average sRGB values.** `measure` linearises by default (`linearize=True`);
  turn it off only for already-linear data.
- **Micro QR and rMQR are ignored**, not fitted — different module counts.
- **`find` returns `None`** when nothing is found; `foreground()` returns zeros. Check.
- **Non-planar substrates** (bottles, wrinkled labels) degrade toward the edges: one
  homography assumes a plane.
- **Screened/halftoned print**: modelled coverage reports the *nominal* geometry. If the
  ink is a halftone screen rather than solid, use `source="observed"`.

## Where to look next

- `docs/terminology.md` — the cross-field vocabulary map (ISO/IEC 18004, 15415, ISO
  12647-2 *area coverage*, DIBCO, matting, remote sensing, medical imaging).
- `docs/methods-and-results.md` — how it works and how well, with measured numbers.
- `inkmap.config` — every tunable, as documented constants.
