# inkmap.locate.patch

Locate a plain printed patch – a uniform colour rectangle – and the substrate round it.

The other locators start from something with a decoder or from a quad you supply. A
single printed colour patch on a paper strip has neither: no code, no registration
marks, an arbitrary background. To measure the patch against its own paper, a caller
needs three things, and [`locate_patch()`](#inkmap.locate.patch.locate_patch) returns them:

```default
import inkmap

regions = inkmap.locate_patch(photo)            # seeded at the frame's centre
regions = inkmap.locate_patch(photo, seed=(x, y))
regions.patch, regions.substrate, regions.ok, regions.notes
```

- `patch`: the patch’s interior, eroded clear of its blurred edge;
- `substrate`: a narrow ring of bare substrate just outside it;
- `ok` and `notes`: whether to trust them, and if not, why.

`regions.quad` is the patch’s four corners to a fraction of a pixel, and
`regions.placement` the same as a [`Placement`](inkmap.types.html.md#inkmap.types.Placement), so the rest of
inkmap (`analyze`, `measure`) works on a patch unchanged.

**How.** The patch colour is the median CIELAB colour of a small window round the
seed. Every pixel’s distance to it is split by Otsu’s threshold (clamped to a Delta E
range), and the connected region holding the seed window is kept, closed and filled.
Its sides are then fitted to the *colour* edge – the mid-level crossing of that
Delta E image – so a pale patch on white paper, whose lightness barely differs from
the paper’s, is placed as precisely as a dark one.

**Substrate.** The ring lies between two distances from the patch, scaled to the
patch’s own size, and keeps only its light, low-chroma pixels: a thin paper border is
easily overshot onto the background, which is why the ring is narrow by default. The
paper must also be lighter than the patch, and be found on at least three of its four
sides.

**The verdict** fails, with a note saying why, on a patch that is too small, cut by
the frame, without substrate on three sides, or that is not the shape and colour of a
printed patch: an outline straying from the fitted sides (a leak, a rounded corner), no
colour step across a side (a leak into shaded paper), two colours in the region or a
large blob of another one inside it (a seed near the patch’s edge or on the paper). On
a failed verdict the region is split again at a tighter threshold, which is how a pale
patch on white paper is found at all; if no split passes, the first answer is returned
with the last split’s reason appended. Text, specks or glare on the patch are left out
of `PatchRegions.patch`; ring pixels not of the paper’s colour (a neighbouring
light patch) are left out of `PatchRegions.substrate`.

**Limits.** The patch colour is one global seed colour, so strong uneven light defeats
a pale patch: with lightness falling 40% across the frame, a patch a Delta E of ~10
from its paper is mostly refused (correctly, but refused). Coloured paper is refused
too. Corners are good to about 0.3 px at blur up to 1.5 px, pale patches included
(`python scripts/validate.py patch`). A 4000 x 3000 frame takes about 1.5 s.

**On flash bursts,** seed on an unlit frame (or the median of the unlit frames): under
flash a pale patch clips to the paper’s white and the region leaks.

### Functions

| [`locate_patch`](#inkmap.locate.patch.locate_patch)(image, \*[, seed, seed_share, ...])   | The uniform patch at `seed`, and the ring of substrate just outside it.                                                       |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| [`locate_patch_centre`](#inkmap.locate.patch.locate_patch_centre)(bgr, gray)                     | A [`LOCATORS`](inkmap.locate.html.md#inkmap.locate.LOCATORS) strategy: the patch at the frame's centre. |

### Classes

| [`PatchRegions`](#inkmap.locate.patch.PatchRegions)(patch, substrate, region, quad, ok)   | A located patch: masks over the frame, its geometry, and how far to trust them.   |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|

### *class* inkmap.locate.patch.PatchRegions(patch, substrate, region, quad, ok, notes=(), seed_lab=(nan, nan, nan), threshold_delta_e=nan, area_share=0.0, rectangularity=0.0, touches_border=False, hole_share=0.0, outline_deviation_px=nan, substrate_px=0, ring_px=(0.0, 0.0))

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A located patch: masks over the frame, its geometry, and how far to trust them.

`patch` is the interior, eroded clear of the edge; `substrate` a ring of bare
substrate just outside; `region` the whole patch, uneroded. `quad` is the
patch’s corners, clockwise as seen on screen from the one nearest the image’s
top-left, to a fraction of a pixel when its sides could be fitted (`None` if no
region was found). `ok` is `not notes`.

The rest say why: `seed_lab` the patch colour, `threshold_delta_e` the split
used, `area_share` of the frame, `rectangularity` (region over fitted quad),
`outline_deviation_px` (95th percentile of the outline’s distance from the
fitted sides), `hole_share` (share of the interior not the patch’s colour),
`substrate_px`, and `ring_px` (the ring’s inner and outer distance).

#### *property* placement *: [Placement](inkmap.types.html.md#inkmap.types.Placement) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The patch and its substrate ring as a placement, or `None` without a quad.

The model is the patch as foreground inside a border of background as wide as
the substrate ring’s outer edge, in units of about one pixel. So
`inkmap.analyze()` and [`inkmap.measure()`](inkmap.html.md#inkmap.measure) treat the patch as any other
mark, and `measure` compares the patch with the substrate round it. The
placement’s `quad` is that bordered model’s, not the patch’s: the patch’s own
corners are `quad`. `measure` averages the whole border, background
and all, where `substrate` keeps only its paper-like pixels: on a thin
paper border, measure with `substrate` instead.

### inkmap.locate.patch.locate_patch(image, , seed='centre', seed_share=0.04, min_delta_e=4.0, max_delta_e=25.0, edge_margin_share=0.08, ring_share=(0.02, 0.06), min_area_share=0.01, min_rectangularity=0.85, min_substrate_px=50, min_substrate_lift=1.0, max_substrate_chroma=15.0, min_side_share=0.15, min_edge_step=3.0)

The uniform patch at `seed`, and the ring of substrate just outside it.

`image` is a path, a BGR (or BGRA) array, or a grey array, 8-bit. `seed` is
`"centre"` or an `(x, y)` pixel inside the patch; its colour is the median of a
window `seed_share` of the frame’s shorter side across. Pixels within the Otsu
split of the CIELAB distance to it, clamped to `[min_delta_e, max_delta_e]`, are
candidates, and the connected candidate region at the seed is the patch.

`edge_margin_share` erodes the interior, and `ring_share` places the
substrate ring, both as shares of the patch’s shorter side. The verdict fails, with
a note saying why, when the patch is under `min_area_share` of the frame, less
rectangular than `min_rectangularity` (area over its minimum-area rectangle’s:
where a pale patch leaked into the paper), cut by the frame’s edge, or when the
ring holds under `min_substrate_px` pixels of substrate, substrate no lighter than
the patch by `min_substrate_lift` L\*, or substrate on fewer than three sides
(`min_side_share` of that side’s ring each), or when a side of the patch has no
colour step of `min_edge_step` across it – the sign of a region that leaked into
shaded paper. A failed verdict on a leaked region is retried at a tighter
threshold.

* **Return type:**
  [`PatchRegions`](#inkmap.locate.patch.PatchRegions)

### inkmap.locate.patch.locate_patch_centre(bgr, gray)

A [`LOCATORS`](inkmap.locate.html.md#inkmap.locate.LOCATORS) strategy: the patch at the frame’s centre.

Registered as `"patch"` but not in the default cascade, so
`inkmap.find(photo, locators=["patch"])` opts in. Returns nothing unless the
verdict is `ok`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]
