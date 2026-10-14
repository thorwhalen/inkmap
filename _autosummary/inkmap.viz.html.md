# inkmap.viz

Visual overlays, for checking that a result is actually right.

Coverage maps are the kind of output that looks plausible when it is subtly wrong – a
half-unit offset or a quarter-turn rotation of the model both produce a mask of the
right shape, size and density. Looking at it is the cheapest way to catch that class of
error, so this is a first-class part of the workflow rather than a nicety.

Only needs OpenCV and numpy; nothing here imports matplotlib.

### Module Attributes

| [`REGION_COLORS`](#inkmap.viz.REGION_COLORS)   | BGR colours per region.   |
|------------------------------------------------------------------|---------------------------|

### Functions

| [`overlay`](#inkmap.viz.overlay)(image, ink_map, \*[, alpha, ...])   | Blend the region map over the original image.                                |
|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`panel`](#inkmap.viz.panel)(image, ink_map, \*[, crop])           | Four-pane contact sheet: original | overlay | coverage | measurement weight. |
| [`colorize_coverage`](#inkmap.viz.colorize_coverage)(coverage)                 | (H, W) float coverage -> BGR heatmap.                                        |
| [`colorize_regions`](#inkmap.viz.colorize_regions)(region)                    | (H, W) region labels -> BGR image.                                           |

### inkmap.viz.REGION_COLORS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[int](https://docs.python.org/3/builtins/functions.html#int), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)]]* *= {Region.OUTSIDE: (0, 0, 0), Region.MARGIN: (90, 90, 90), Region.BACKGROUND: (200, 140, 60), Region.FOREGROUND: (60, 90, 230)}*

BGR colours per region. Foreground warm, background cool, margin neutral.

### inkmap.viz.colorize_coverage(coverage)

(H, W) float coverage -> BGR heatmap. Partial coverage is what to look at.

* **Return type:**
  `ndarray`

### inkmap.viz.colorize_regions(region)

(H, W) region labels -> BGR image.

* **Return type:**
  `ndarray`

### inkmap.viz.overlay(image, ink_map, , alpha=0.45, draw_quad=True, draw_grid=False)

Blend the region map over the original image.

`draw_grid` overlays the fitted model grid, which is the fastest way to see a
mis-fitted transform: if the lines do not sit on the mark’s own boundaries, every
downstream number is wrong no matter how clean the mask looks.

* **Return type:**
  `ndarray`

### inkmap.viz.panel(image, ink_map, , crop=True)

Four-pane contact sheet: original | overlay | coverage | measurement weight.

The last two panes are the ones worth studying. Coverage should show a thin soft
fringe along every foreground boundary; weight should show that fringe eaten away,
leaving only interiors. If weight is empty, the image cannot support a measurement.

* **Return type:**
  `ndarray`
