# Terminology

inkmap has to talk to audiences that use different words for the same things: barcode
people (ISO/IEC 18004, 15415), print people (ISO 12647), document-analysis people
(DIBCO), and anyone making a physical measurement. This table is the mapping. The short
version: **foreground / background** for the classes, **coverage** for the 0–1 value.

## The mapping

| inkmap name | ISO/IEC 18004 (QR) | ISO/IEC 15415 (verification) | Printing | Document analysis (DIBCO) | Matting | Remote sensing | Medical imaging |
|---|---|---|---|---|---|---|---|
| `Region.FOREGROUND` | dark module\* | dark module | printed area | foreground ("object ink pixels") | foreground | endmember of interest | — |
| `Region.BACKGROUND` | light module\* | light module, substrate | substrate, paper | background | background | substrate endmember | — |
| `Region.MARGIN` | quiet zone | quiet zone | — | margin | — | — | — |
| `Region.OUTSIDE` | — | — | — | — | — | — | — |
| `coverage` | — | — | **area coverage** (ISO 12647-2 §3.1) | — | alpha, opacity | fractional abundance | partial volume fraction |
| partial pixel | — | — | — | — | unknown region | mixed pixel | partial volume effect |
| `weight` | — | — | — | — | — | — | (what PVC corrects) |
| `feature_size` | module | module | — | stroke width | — | GSD | ~2× FWHM rule |
| edge spread | — | **print growth** (PG) | dot gain / TVI† | — | — | — | spill-over |

\* ISO/IEC 18004 defines dark/light as statements about *apparent reflectance*, and
includes an explicit reflectance-reversal clause. See below.

† Dot gain / TVI is halftone vocabulary. A QR module or a letter stroke is a solid
fill, not a screen, so ISO/IEC 15415's **print growth** is the right term for a 2-D
mark.

## Why these names

### Why not `dark` / `light`

They are the correct normative words — for the *symbol*. They are the wrong words for
the *pixels being measured*, because they describe appearance, and appearance inverts:
white-on-black print, reflectance-reversed symbols (which ISO/IEC 18004 explicitly
permits), engraved or embossed marks lit obliquely, and any inverted imaging modality
all swap which class is dark.

A `dark_mask` would then silently mean the mark in one image and the substrate in the
next. So inkmap keeps `dark`/`light` strictly at the symbology layer (`MatrixModel`
cells are `True` for a dark module, per the spec) and bridges to physical classes with
an explicit polarity:

```python
inkmap.find(photo, polarity=Polarity.FOREGROUND_IS_DARK)   # normal print
inkmap.find(photo, polarity=Polarity.FOREGROUND_IS_LIGHT)  # inverted
```

### Why `background` is safe here but dangerous elsewhere

`foreground`/`background` is the DIBCO standard, and the natural vocabulary for a
shape-agnostic package. The usual objection is that "background" is ambiguous —
substrate *inside* the mark, or everything that is not the mark?

inkmap removes the ambiguity by splitting the outside into two named regions:
`BACKGROUND` is scoped to within the mark's footprint, `MARGIN` is the specified clear
surround, and `OUTSIDE` is everything else. Each is a decided statement about location,
so no single word has to carry both meanings.

`substrate` also appears in the docs as a synonym for the material under the mark; it
is the term of art in the barcode standards themselves (ISO/IEC 15415 "Substrate
characteristics"; ISO/IEC 15416 §7, and §3.12 defines *show-through* as a property of
the substrate).

### Why `coverage`

ISO 12647-2:2013 §3.1 defines **area coverage** as "ratio of the area covered with ink
to the entire area". That is literally the quantity computed, and the only term in any
standard whose definition matches. Two caveats, documented rather than glossed:

- ISO 12647 defines area coverage per *ink zone*, not per pixel. Applying it per pixel
  is a defensible extension, but it is an extension.
- inkmap's `coverage` is **geometric**, not optical. A reflectance-derived coverage is
  inflated by lateral light scattering in the substrate (the Yule–Nielsen effect); that
  variant is `observed_coverage` and is called *apparent* coverage throughout.

### Why not `trimap`

The shape is identical — a few classes over an image — and the temptation is real. But
a matting trimap's third class is **unknown/undecided**, whereas every inkmap region is
a decided statement about location. Anyone who knows matting would be misled.

### Why not `alpha`

For opaque marks, `coverage` and matting `alpha` are numerically identical. But `alpha`
collides with absorptivity and significance level for a physics audience, and carries
compositing connotations for a CV audience. `coverage` is unambiguous to both; the
equivalence is documented so people who think in matting terms can find it.

### `cell` vs `module` vs `unit`

For QR the grid unit is a **module**; "cell" is Data Matrix / ISO/IEC 29158 vocabulary.
inkmap generalises across symbologies, so the neutral word in the API is **unit** (of
model space), with `MatrixModel` documenting that its unit is a module.

### `feature_size`, and why resolution is measured in features

A model unit is not a feature. A QR module is both. But a glyph rendered onto a
512-cell raster has strokes tens of cells wide, so "pixels per unit" there understates
the real resolution by that factor. Every judgement about whether an image can support
a measurement uses `pixels_per_feature = pixels_per_unit × model.feature_size`, which
is portable across model kinds. Grid models report an exact 1.0; freeform models
estimate it as twice the median distance-to-edge — the typical stroke width.

The medical-imaging analogue is the rule that objects smaller than roughly twice the
system FWHM have their intensity systematically underestimated.

## The three 0–1 channels

| Channel | What it is | Use it for |
|---|---|---|
| `coverage` | **Geometric** fraction of the pixel's area under foreground. Deterministic; essentially noise-free. | Reporting, print-growth QC, identifying mixed pixels |
| `weight` | **Blur-aware** measurement selector — coverage eroded by the distance the point spread function actually reaches. | **The only channel that should gate a physical measurement** |
| `confidence` | **Epistemic**: how much to trust the label here, given clipping, glare and model/image disagreement. | Quality gating, artefact rejection |

If the underlying reality is binary — a pixel is either mark or substrate and we are
merely unsure which — then "probability of foreground" is `confidence`. If reality is
genuinely not binary, because the pixel straddles an edge, then the degree of membership
is `coverage`. Both are real, and neither substitutes for the other: a pixel can be
exactly half foreground (coverage 0.5) and we can be completely certain of that
(confidence 1.0).

Crucially, **`coverage` is not sufficient to weight a measurement**. Coverage is
geometry; the point spread function leaks background signal into pixels that are
geometrically pure foreground. Those two effects have different footprints, so no
coverage-based weighting removes the contamination. Only spatial erosion does — which
is what `weight` is. See [validation.md](validation.md) for the measured bias.

## Standards cited

Clause numbers moved between editions (ISO/IEC 18004 renumbered substantially between
2015 and 2024), so citations carry an edition year.

- **ISO/IEC 18004** — QR Code symbology. Dark/light modules, quiet zone (4 modules),
  function patterns, the reference decode algorithm (global threshold at the midpoint of
  max and min reflectance; sample a 3×3 pixel area at each grid intersection).
- **ISO/IEC 15415** — 2-D symbol print quality. Reflectance, Rmax/Rmin, symbol contrast,
  modulation, grid non-uniformity, fixed pattern damage, print growth. Substrate
  characteristics.
- **ISO/IEC 15416** — linear symbol print quality. Bar/space = dark/light *element*;
  substrate, show-through.
- **ISO/IEC 19762** — the harmonised AIDC vocabulary the above defer to.
- **ISO 12647-2:2013** — area coverage (§3.1), tone value (§3.4).
- **ISO 20654:2017** — SCTV; the "apparent" vs geometric coverage distinction.
- **IEC 61966-2-1** — sRGB transfer function, used by `srgb_to_linear`.
