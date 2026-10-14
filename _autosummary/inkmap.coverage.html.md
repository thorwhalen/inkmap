# inkmap.coverage

Per-pixel foreground coverage: the 0..1 value, and which one you want.

Three different 0..1 quantities get conflated by “how foreground is this pixel”. They
answer different questions, and mixing them produces numbers that mean nothing:

**Coverage** ([`coverage_map()`](#inkmap.coverage.coverage_map), [`observed_coverage()`](#inkmap.coverage.observed_coverage)) is *physical*: the
fraction of the pixel’s area lying under foreground. ISO 12647-2:2013 3.1 calls this
**area coverage**. A pixel straddling a mark’s edge genuinely is 0.37 foreground. The
same quantity is the matting **alpha** (identical, for opaque marks), the
remote-sensing **fractional abundance** of an endmember in a **mixed pixel**, and the
medical-imaging **partial volume fraction**.

**Confidence** ([`confidence()`](#inkmap.coverage.confidence)) is *epistemic*: how sure we are of the label. This
is what the user’s “probability that the pixel is foreground” means when the underlying
reality is genuinely binary. A pixel deep inside a mark has coverage 1.0 and confidence
1.0; one in a blown-out highlight may have modelled coverage 1.0 and confidence near 0.

**Weight** ([`measurement_weight()`](#inkmap.coverage.measurement_weight)) is *operational*: how safe the pixel is to
measure, given that blur spreads signal across boundaries. It is the only one that
should gate a physical measurement.

## Two routes to coverage

*Modelled* ([`coverage_map()`](#inkmap.coverage.coverage_map)): the shape is known, so back-project a supersampled
grid of each pixel through the transform and ask the model. Exact up to the
supersampling rate, immune to lighting, and the right default. It answers “where should
the foreground be”.

*Observed* ([`observed_coverage()`](#inkmap.coverage.observed_coverage)): normalise the photograph between a background
endpoint and a solid-foreground endpoint. This is the Murray-Davies inversion, and it
answers “where is the foreground actually” – so it is the one that can see a printing
defect. It returns an *apparent* (optical) coverage, inflated relative to geometric
coverage by lateral light scattering in the substrate (the Yule-Nielsen effect), which
is why the two routes disagree.

### Functions

| [`coverage_map`](#inkmap.coverage.coverage_map)(model, transform, image_shape, \*)   | Area fraction of each pixel covered by the model's foreground, in `[0, 1]`.   |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`observed_coverage`](#inkmap.coverage.observed_coverage)(gray, placement, \*[, ...])     | Apparent coverage read from the photograph itself (Murray-Davies).            |
| [`confidence`](#inkmap.coverage.confidence)(gray, placement, coverage, \*[, ...])  | How much to trust the coverage value at each pixel, in `[0, 1]`.              |
| [`measurement_weight`](#inkmap.coverage.measurement_weight)(coverage, \*[, ...])           | Blur-aware weight in `[0, 1]`: how safe each pixel is to *measure*.           |
| [`region_map`](#inkmap.coverage.region_map)(placement, coverage, \*[, ...])        | Four-way `Region` label array from a coverage map and a placement.            |
| [`estimate_blur_sigma`](#inkmap.coverage.estimate_blur_sigma)(gray, placement)              | Estimate imaging blur sigma, in pixels, from the mark's own edges.            |

### inkmap.coverage.confidence(gray, placement, coverage, , polarity=Polarity.FOREGROUND_IS_DARK)

How much to trust the coverage value at each pixel, in `[0, 1]`.

Distinct from coverage. Three things erode it, combined multiplicatively:

* **Model/image disagreement** – where the observed value contradicts the modelled
  coverage, one of them is wrong. This is what catches foreground that failed to
  print, a torn label, or a mis-fitted transform.
* **Clipping** – saturated or crushed pixels carry no photometric information.
* **Edge proximity** – mixed pixels are inherently less certain, and their value
  depends on sub-pixel geometry known only to ~0.5 px.

* **Return type:**
  `ndarray`

### inkmap.coverage.coverage_map(model, transform, image_shape, , samples=8)

Area fraction of each pixel covered by the model’s foreground, in `[0, 1]`.

Each pixel is probed at `samples**2` sub-positions on a regular grid at sub-pixel
centres; each probe is back-projected into model coordinates and passed to
`Model.occupancy()`. The mean is the covered area fraction – ordinary
supersampled area coverage, the same quantity a renderer’s anti-aliasing computes.

Values are quantised to `1/samples**2`, so `samples` sets the accuracy floor.
Only the model’s bounding box is evaluated, so a mark occupying 2% of a 12 MP photo
costs 2% of the work.

* **Return type:**
  `ndarray`

### inkmap.coverage.estimate_blur_sigma(gray, placement)

Estimate imaging blur sigma, in pixels, from the mark’s own edges.

Sizing the measurement margin needs this. Estimated by finding the sigma whose
blurred ideal coverage best matches the photograph.

Returns `nan` when the minimum lands at the top of the search range: that is the
search running out of room, not a measurement – the modelled shape and the
photograph do not correspond – and reporting the boundary value would silently size
the measurement margin from noise.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### inkmap.coverage.measurement_weight(coverage, , blur_sigma=None, radius=None, inside=None, kind='foreground', sigmas=2.0)

Blur-aware weight in `[0, 1]`: how safe each pixel is to *measure*.

Coverage says a pixel lies entirely under foreground. That is necessary but not
sufficient: the point spread function leaks neighbouring signal into interior
pixels, and that contamination has a different footprint from partial area
coverage – so no coverage-based weighting removes it. The fix is spatial: require
a pixel’s whole neighbourhood to be foreground, out to the radius the blur reaches.

Implemented as grayscale morphological erosion of the coverage map, which is exactly
“the minimum coverage within radius r” – continuous rather than a hard mask, so a
pixel one step from an edge is down-weighted rather than trusted or discarded.

Give either `radius` (pixels, wins if both are given) or `blur_sigma`, from
which the radius is `sigmas * blur_sigma`.

* **Return type:**
  `ndarray`

### inkmap.coverage.observed_coverage(gray, placement, , polarity=Polarity.FOREGROUND_IS_DARK, yule_nielsen_n=1.0, percentile=5.0)

Apparent coverage read from the photograph itself (Murray-Davies).

Endmember values are estimated from the mark’s own pixels – its background region
gives the substrate endpoint, its foreground core the solid endpoint – so no
external calibration target is needed. Percentiles rather than extremes, so a
specular highlight cannot define an endpoint.

`yule_nielsen_n` > 1 compensates for lateral light scattering in the substrate,
which otherwise inflates apparent coverage above geometric coverage. n = 1 is plain
Murray-Davies; the right value is substrate- and wavelength-specific and should be
fitted, not guessed.

The result is *apparent*, not geometric, coverage. Do not silently substitute it
for [`coverage_map()`](#inkmap.coverage.coverage_map).

* **Return type:**
  `ndarray`

### inkmap.coverage.region_map(placement, coverage, , threshold=0.5, margin_units=4.0)

Four-way `Region` label array from a coverage map and a placement.

* **Return type:**
  `ndarray`
