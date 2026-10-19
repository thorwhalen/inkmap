# inkmap.locate.qr

Locating QR symbols: a cascade of interchangeable strategies.

Measured on 189 real photographs from Wikimedia Commons (varied angle, lighting,
substrate, print quality):

| locator            | images detected   |
|--------------------|-------------------|
| zxing-cpp          | 74%               |
| OpenCV Aruco-based | 68%               |
| OpenCV classic     | 43%               |
| **union**          | **80%**           |

So OpenCV alone forfeits about 37 points of recall. All three are permissively licensed
(Apache-2.0) and ship as wheels. Deliberately *not* used: `qrdet`/`qreader`, whose
MIT metadata is misleading – they depend on `ultralytics`, which is AGPL-3.0.

## Getting the module matrix

Decoding gives the payload, but the payload does **not** determine the module pattern:
error-correction level and mask pattern are encoder choices not recoverable from the
text, so re-encoding the payload can yield a differently-sized, differently-masked
matrix. It is a silent-wrong-answer path and is not used here. The pattern is read from
the image instead: OpenCV’s `straight_qrcode` is a bit-exact sample, and where that
is unavailable the grid is sampled directly.

### Functions

| [`locate_qr_opencv`](#inkmap.locate.qr.locate_qr_opencv)(bgr, gray)                     | OpenCV's classic `QRCodeDetector`.                                                 |
|--------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`locate_qr_aruco`](#inkmap.locate.qr.locate_qr_aruco)(bgr, gray)                      | OpenCV's `QRCodeDetectorAruco` -- finds the finder patterns as Aruco-like markers. |
| [`locate_qr_zxing`](#inkmap.locate.qr.locate_qr_zxing)(bgr, gray)                      | zxing-cpp.                                                                         |
| [`sample_matrix`](#inkmap.locate.qr.sample_matrix)(gray, transform, n, \*[, window]) | Read the module matrix off the image at the grid intersections.                    |

### inkmap.locate.qr.locate_qr_aruco(bgr, gray)

OpenCV’s `QRCodeDetectorAruco` – finds the finder patterns as Aruco-like
markers. Notably more robust than the classic detector on real photographs.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.locate.qr.locate_qr_opencv(bgr, gray)

OpenCV’s classic `QRCodeDetector`. Corners are inclusive pixel indices.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.locate.qr.locate_qr_zxing(bgr, gray)

zxing-cpp. Highest recall of the three, and its corners are the continuous outer
boundary (spanning exactly `N * scale`), not inclusive pixel indices.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Placement`](inkmap.types.html.md#inkmap.types.Placement)]

### inkmap.locate.qr.sample_matrix(gray, transform, n, , window=3)

Read the module matrix off the image at the grid intersections.

ISO/IEC 18004’s reference decode algorithm samples a small area centred on each
grid intersection and thresholds. Used when no decoder handed us a matrix – notably
when the print is too faint to decode, which is exactly the case that must still
work.

* **Return type:**
  `ndarray`
