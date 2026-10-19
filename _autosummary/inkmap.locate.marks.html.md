# inkmap.locate.marks

Find square registration marks: solid squares and nested squares, sub-pixel.

The other locators here find marks that have a decoder. Printed targets also carry
plain registration marks – a solid square, or a bullseye of nested squares at each
corner of a sheet, as on OMR forms – and pose estimation needs their centres to a small
fraction of a pixel. [`find_square_marks()`](#inkmap.locate.marks.find_square_marks) finds them:

```default
from inkmap.locate import BULLSEYE_RINGS, find_square_marks

marks = find_square_marks(gray)
bullseyes = [m for m in marks if m.ring_error(BULLSEYE_RINGS) < 0.06]
bullseyes[0].centre, bullseyes[0].sigma_px
```

It knows what a square mark looks like, not which mark is which on a particular layout:
naming them, by ring ratio and by where they sit relative to each other, is the
caller’s.

A **nested** mark is a foreground square holding a background square holding a
foreground square. A bullseye (rings at 0.64 and 0.32 of the side) and a QR symbol’s
finder pattern (7:5:3 modules) are both of this kind, and they are told apart by their
ring ratios, which perspective barely changes. A **solid** mark is a foreground square
with nothing inside it, and reports no rings.

**Centres are projective.** The centre of a square seen in perspective is where its
image’s diagonals cross, not the centroid of its pixels, which is pulled towards the
near side. Each side is fitted as a line to its contour points, the corners are the
lines’ intersections, and the centre is where the diagonals cross. The sides are
placed on the grey image’s mid-level edge, not on the binarised outline, so the
threshold does not move them: one that grew the foreground would move all four sides
out alike, which leaves the diagonals’ crossing in place for a square seen head-on but
not for one in strong perspective. The mid-level edge is exact for a linear sensor
response; a gamma-encoded image moves a blurred edge a little (a worst centre error of
0.16 px was measured at strong perspective and blur 2 px with gamma 1/2.2).

**Uncertainty.** Each mark carries `sigma_px`, an estimate of how far its centre is
from the truth: the scatter of the side fits over the square root of the points per
side, combined, for a nested mark, with the disagreement between its squares’ centres
(its centre is their side-weighted mean, since perspective maps them to one point),
and for a solid mark, which has nothing to disagree with, with a fixed floor for the
biases the fit cannot see. Both are calibrated on synthetic sheets so that the median
centre error is about `sigma_px`; the tail is heavier than a Gaussian’s (one mark in
twenty is off by 3-6 sigma), so weigh marks by it, but do not gate on it. A mark cut by
the frame’s edge is dropped, never measured.

**Limits.** Each ring must be several blur widths across to survive binarisation: at
blur 1.5 px a bullseye needs roughly 40 px or more, a solid square 10 px. Marks over
`max_side_share` of the frame (10% by default) are not looked for; raising it widens
the local-mean window with it, which tolerates uneven lighting less well. A disc under
about 10 px radius fits four lines as well as a square of its size does, so it cannot
be told from one. Anything square is a candidate, so a QR symbol’s clusters of data
modules come back as small solid marks.

### Module Attributes

| [`BULLSEYE_RINGS`](#inkmap.locate.marks.BULLSEYE_RINGS)   | background at 0.64, foreground at 0.32.                                           |
|-------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`QR_FINDER_RINGS`](#inkmap.locate.marks.QR_FINDER_RINGS)  | 7 modules of foreground, 5 of background, 3 of foreground (ISO/IEC 18004 §6.3.3). |

### Functions

| [`find_square_marks`](#inkmap.locate.marks.find_square_marks)(gray, \*[, min_side_px, ...])   | Every solid or nested square mark in `gray` (2-D, 0-255 scale), largest first.   |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`ring_ratios`](#inkmap.locate.marks.ring_ratios)(outer_area, inner_areas)              | Side ratios of nested squares from their areas: `sqrt(inner / outer)`.           |
| [`quad_centre`](#inkmap.locate.marks.quad_centre)(corners)                              | Where the diagonals of a quadrilateral cross: the projective centre of a square. |

### Classes

| [`SquareMark`](#inkmap.locate.marks.SquareMark)(centre, corners, side_px[, ...])   | One square mark found in an image.   |
|------------------------------------------------------------------------------------------------|--------------------------------------|

### inkmap.locate.marks.BULLSEYE_RINGS *= (0.64, 0.32)*

background at
0.64, foreground at 0.32.

* **Type:**
  Side of each inner square of a bullseye as a fraction of the outer

### inkmap.locate.marks.QR_FINDER_RINGS *= (0.7142857142857143, 0.42857142857142855)*

7 modules of foreground, 5 of background, 3 of foreground
(ISO/IEC 18004 §6.3.3).

* **Type:**
  A QR finder pattern

### *class* inkmap.locate.marks.SquareMark(centre, corners, side_px, rings=(), sigma_px=nan, centres=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One square mark found in an image. Coordinates are pixels, `(x, y)`.

`corners` are the outer square’s, clockwise as seen on screen, starting from the
one nearest the image’s top-left. A square has no intrinsic first corner, so that
order is a convention, not an identification. `rings` is the side of each nested
square as a fraction of the outer one, outermost first (empty for a solid mark).
`centres` are the outer square’s centre followed by each nested square’s, each
where that square’s diagonals cross; `centre` is their mean weighted by side,
which for a solid mark is the outer square’s own.

#### ring_error(expected)

Largest difference between these ring ratios and `expected`; inf if unlike.

```pycon
>>> SquareMark((0, 0), np.zeros((4, 2)), 10.0, rings=(0.7, 0.4)).ring_error(
...     QR_FINDER_RINGS
... )
0.028...
>>> SquareMark((0, 0), np.zeros((4, 2)), 10.0).ring_error(BULLSEYE_RINGS)
inf
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### inkmap.locate.marks.find_square_marks(gray, , min_side_px=8.0, max_side_share=0.1, polarity=Polarity.FOREGROUND_IS_DARK, dark_share=0.72, min_contrast=6.0, local_window_share=0.12)

Every solid or nested square mark in `gray` (2-D, 0-255 scale), largest first.

A mark’s outer square must be at least `min_side_px` on a side and at most
`max_side_share` of the frame’s shorter side. Nested marks report their ring
ratios; solid marks report none. `polarity` says whether the marks read darker
than the substrate (the usual case) or brighter.

The foreground is binarised relative to the local mean brightness: a pixel is
foreground when it is darker than `dark_share` of the mean over a window
`local_window_share` of the frame’s shorter side, and darker by at least
`min_contrast` grey levels. The window is widened to stay wider than the largest
mark looked for, since a mark wider than it is hollowed by its own ink.

Anything square is a candidate: a QR symbol’s clusters of data modules and some
printed glyphs come back as solid marks too. Telling the registration marks from
them, by size, ring ratio and layout, is the caller’s.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`SquareMark`](#inkmap.locate.marks.SquareMark)]

### inkmap.locate.marks.quad_centre(corners)

Where the diagonals of a quadrilateral cross: the projective centre of a square.

`corners` must be in cyclic order (either direction). `None` if degenerate.

```pycon
>>> quad_centre([(0, 0), (4, 0), (4, 2), (0, 2)])
(2.0, 1.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### inkmap.locate.marks.ring_ratios(outer_area, inner_areas)

Side ratios of nested squares from their areas: `sqrt(inner / outer)`.

```pycon
>>> ring_ratios(100.0, (64.0, 16.0))
(0.8, 0.4)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]
