# inkmap.photometry

Turning masks into measurements that are actually valid.

Everything here exists because a per-pixel mask is necessary but nowhere near
sufficient for measuring anything *about* the mark – its reflectance, its density, its
colour, how much of it actually printed. The failure modes are silent: they do not
raise, they return a plausible number wrong by tens of percent.

Measured on synthetic scenes with exact ground truth (see `docs/validation.md`), the
bias in recovering a foreground-only signal at 6 px per model unit:

| pixel selection   | blur=0   | sigma=1 px   | sigma=2 px   | sigma=3 px   |
|-------------------|----------|--------------|--------------|--------------|
| coverage > 0.5    | -3.3%    | -12.2%       | -23.3%       | -32.4%       |
| coverage == 1.0   | -0.0%    | -8.0%        | -19.9%       | -30.1%       |
| weight (2 sigma)  | +0.0%    | -0.2%        | -0.6%        | -1.5%        |

Two lessons. Geometric purity is necessary but *not* sufficient – a pixel entirely
under foreground still reads 30% low, because the point spread function drags
background signal into it, and that contamination has a different footprint from
partial area coverage. Only spatial erosion removes it, which is what the weight
channel is.

And erosion stops working once the blur is wide relative to a model unit: there are no
uncontaminated pixels left. That is the classic partial-volume result, and it is why
[`measurability()`](#inkmap.photometry.measurability) exists – better to say the measurement is not possible than to
return a confidently wrong number.

### Functions

| [`srgb_to_linear`](#inkmap.photometry.srgb_to_linear)(image)                              | Undo the sRGB transfer function, returning float in `[0, 1]`.                  |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`measurement_mask`](#inkmap.photometry.measurement_mask)(ink_map, \*[, kind, purity, ...]) | Pixels safe to measure: geometrically pure, then eroded clear of edges.        |
| [`measurement_margin`](#inkmap.photometry.measurement_margin)(blur_sigma, \*[, sigmas])       | Erosion radius in pixels for a given blur sigma.                               |
| [`measurability`](#inkmap.photometry.measurability)(ink_map, \*[, min_pixels])           | Judge whether a foreground/background measurement can be trusted here.         |
| [`measure`](#inkmap.photometry.measure)(image, ink_map, \*[, linearize, ...])      | Aggregate `image` over the safe foreground and background pixels of `ink_map`. |
| [`illumination_field`](#inkmap.photometry.illumination_field)(image, ink_map, \*[, degree])   | Fit a smooth illumination field across the mark from its background pixels.    |

### Classes

| [`Measurability`](#inkmap.photometry.Measurability)(ok, pixels_per_feature, ...[, ...])   | Whether a trustworthy measurement is possible on this image at all.           |
|------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`Measurement`](#inkmap.photometry.Measurement)(foreground_mean, foreground_std, ...)   | Aggregated signal over foreground and background, with its validity attached. |

### *class* inkmap.photometry.Measurability(ok, pixels_per_feature, blur_sigma, resolution_ratio, n_foreground_pixels, n_background_pixels, reasons=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Whether a trustworthy measurement is possible on this image at all.

#### resolution_ratio *: [float](https://docs.python.org/3/builtins/functions.html#float)*

`pixels_per_feature / blur_sigma`. Below ~6 the blur is wide relative to the
mark’s smallest feature and no erosion leaves uncontaminated pixels.

### *class* inkmap.photometry.Measurement(foreground_mean, foreground_std, foreground_median, background_mean, background_std, background_median, n_foreground, n_background, measurability=None, metadata=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Aggregated signal over foreground and background, with its validity attached.

`measurability` is carried along deliberately: a caller that ignores it has to do
so explicitly.

#### *property* contrast *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Foreground minus background.

#### *property* ratio *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Foreground over background; `nan` when the background reads zero.

#### *property* snr *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Contrast over the pooled standard deviation.

### inkmap.photometry.illumination_field(image, ink_map, , degree=1)

Fit a smooth illumination field across the mark from its background pixels.

The background within the mark samples the illumination across the whole mark, so
the scene calibrates itself – no flat-field frame required. A first-order (planar)
fit handles the usual oblique-lighting gradient; degree 2 handles vignetting
curvature at the cost of being able to absorb real signal.

Returns a field normalised to mean 1.0 over the mark; divide by it to flatten.

* **Return type:**
  `ndarray`

### inkmap.photometry.measurability(ink_map, , min_pixels=50)

Judge whether a foreground/background measurement can be trusted here.

Returning a number quietly biased by 30% is worse than refusing, so this is checked
up front and attached to every [`Measurement`](#inkmap.photometry.Measurement).

* **Return type:**
  [`Measurability`](#inkmap.photometry.Measurability)

### inkmap.photometry.measure(image, ink_map, , linearize=True, flatten=False, margin=None, robust=True)

Aggregate `image` over the safe foreground and background pixels of `ink_map`.

`image` need not be the one the mark was located in: any frame registered to it
works, which is the usual way to measure a different exposure, channel or modality
using geometry established once on the sharpest frame.

`linearize` undoes sRGB encoding first – leave it on for anything from a normal
camera pipeline, off for already-linear data. `flatten` divides out a fitted
illumination field. `robust` reports medians alongside means; on real photographs
they diverge exactly where something is wrong, which makes the pair a free
diagnostic.

* **Return type:**
  [`Measurement`](#inkmap.photometry.Measurement)

### inkmap.photometry.measurement_margin(blur_sigma, , sigmas=2.0)

Erosion radius in pixels for a given blur sigma. At least 1 px.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### inkmap.photometry.measurement_mask(ink_map, , kind='foreground', purity=0.999, margin=None)

Pixels safe to measure: geometrically pure, then eroded clear of edges.

`kind` selects `"foreground"` or `"background"`. `purity` is the coverage
threshold for “pure”; the default demands essentially total coverage, which is the
point – a partially covered pixel biases the mean toward the other class.

This is the mask to use for a measurement. `InkMap.foreground_mask()` is for
display and for anything that only needs a label.

* **Return type:**
  `ndarray`

### inkmap.photometry.srgb_to_linear(image)

Undo the sRGB transfer function, returning float in `[0, 1]`.

Averaging pixel values without this is a real error, not a nicety: sRGB values are
perceptually encoded, so the mean of encoded values is not the encoded mean
intensity. Any difference between two exposures compounds it. Apply before any
arithmetic that claims to be about light.

The piecewise IEC 61966-2-1 curve, not the 2.2 power approximation.

* **Return type:**
  `ndarray`
