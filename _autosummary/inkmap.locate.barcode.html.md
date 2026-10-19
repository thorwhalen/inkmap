# inkmap.locate.barcode

Locating linear (1-D) barcodes.

Geometry comes from zxing-cpp, which handles EAN-13/8, UPC-A/E, Code 128, Code 39,
Code 93, ITF, Codabar and DataBar. The *bar pattern* is then read off the image rather
than re-encoded from the decoded text, for the same reason as QR: encoders make choices
(Code 128 code-set switching, check-digit placement, ITF padding) that the decoded
string does not pin down, so re-encoding can silently produce a different pattern.

Reading it from the image needs the module width – the narrowest bar. That is
estimated from the run lengths of the thresholded profile, which is what a real decoder
does, and it is the one number that turns a picture of stripes into a model.

### Functions

| [`locate_barcode_zxing`](#inkmap.locate.barcode.locate_barcode_zxing)(bgr, gray)           | Locate linear barcodes with zxing-cpp and model their bar pattern.   |
|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`profile_to_bars`](#inkmap.locate.barcode.profile_to_bars)(profile, \*[, n_modules]) | Quantise a 1-D profile into a bar pattern.                           |

### inkmap.locate.barcode.locate_barcode_zxing(bgr, gray)

Locate linear barcodes with zxing-cpp and model their bar pattern.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.locate.barcode.profile_to_bars(profile, , n_modules=None)

Quantise a 1-D profile into a bar pattern.

Returns `(bars, module_px)`. Thresholds at the midpoint of the profile’s range,
per ISO/IEC 15416 3.5. `n_modules` pins the module count when the symbology fixes
it; otherwise the module width is fitted from the run lengths.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[`ndarray`, [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)
