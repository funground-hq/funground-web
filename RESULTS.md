# S-135 results: the IR replayed on Canvas 2D against the Cairo goldens

Question: does the IR replayed on Canvas 2D match the Cairo goldens within a tolerance, for every op type?
Short answer: yes, in Chrome 154 on Windows, for all 20 op types. Nothing differs structurally; every
difference sits on anti-aliased edges. Firefox and Safari were not run (see Gaps).

## What was run

- 63 cases, all compared against Cairo pixels:
  - 13 Session-1 goldens (`tests/golden/*.png`: 01-10, 12, 13, 14; the task said 14, the repo has 13, because 11_delta_time is time-dependent and has none) and 24 gallery goldens;
  - 8 of the gallery frames again at pixel density 2 (reference: Cairo re-run at `FUNGROUND_BACKING_SCALE=2`, since no golden exists at 2x);
  - 18 synthetic cases (`tools/make_synthetic.py`), one per op type or feature, built straight from `funground.ir` and drawn by the real `CairoRenderer`. They cover what no golden frame contains: ResetClip, BeginGroup/EndGroup (nested, bounded, with a clip), erase (fill, stroke, shape, text, picture), all 17 blend modes, shadows, tint with source rectangles, pixel blocks at 1x and 2x, no_smooth, dashes, caps, joins, miter limits.
- All 37 golden-backed frames reproduce their golden byte for byte when re-run (`rerun_equals_golden` in each `ir.json`), so the goldens are the Cairo reference.
- IR is recorded from the real renderer: `CairoRenderer.draw/begin_frame/draw_batch/end_frame` are wrapped, so the browser replays exactly what Cairo was asked to draw (mid-frame batches, script canvases, layer overlays, picture snapshots, pixel blocks). Frames before the last Clear are dropped.
- Text arrives as `outlines` (the FillPath ops from `typography.py`); `fillText` is never used. Rounded rects carry a Python-built `path`. Pictures and pixel blocks travel as zlib-compressed premultiplied BGRA files.
- Pass criteria (from the note): at most 3 % of pixels differing (any channel off by more than 8), mean absolute difference at most 3, differences on edges only (`off_edge`: differing pixels with no edge within 5x5 in either image, at most 0.2 % and none above 64).
- Two Chrome rasterisers, because they gave different numbers: **GL** is Chrome's default headless setup here (software-backed GPU process, no discrete GPU); **CPU** is `--disable-gpu` (Skia software raster).

## Summary

| | GL | CPU |
|---|---|---|
| Cases passing all three criteria | 61 / 63 | 63 / 63 |
| Cases within 3 % differing | 61 / 63 | 63 / 63 |
| Highest mean abs difference | 1.02 | 0.67 |
| Cases with edges-only differences | 63 / 63 | 63 / 63 |
| Highest differing % | 3.79 (syn-text) | 2.16 (syn-images) |

The two GL failures (gallery-shapes-03_modes 3.59 %, syn-text 3.79 %) are frames made almost entirely of thin lines and small text; the diff images show only glyph and stroke edges, and mean differences are 1.02 and 0.74. They miss the 3 % count by under 1 point.

Evidence for architecture B: the structure is right everywhere. No op type needed a different design, only the workarounds listed below.

## Op types

Every op type passes in both modes except where a case it shares failed on edge density (GL, above); no failure is attributable to a single op.

| Op | Verdict | Notes |
|---|---|---|
| Clear | pass | SOURCE paint under the current matrix (a gradient follows the matrix: a real bug at 2x, found and fixed). Under a clip it uses the level stack below. |
| Circle, Ellipse, Rect (incl. radii), Line, Point | pass | Edge-only differences. |
| FillPath, StrokePath | pass | Non-zero fill; caps, joins, miter limits and dashes (offsets, odd counts, zero-length) match. |
| Text | pass | Via outlines. Small text has the most edge pixels, hence the highest counts. |
| Save, Restore, Concat, ResetMatrix | pass | Matrix tracked in JS (ResetMatrix needs the base matrix, kept per renderer). |
| ClipPath | pass | Nested, under transforms, inside groups. |
| ResetClip | pass with a workaround | Canvas cannot remove a clip. The renderer keeps its own level stack (matrix, clips added, cleared flag) and rebuilds the canvas state after a ResetClip and on the Restore that returns past it. Cost O(depth) per ResetClip. Also used by Clear and Pixels inside clips. |
| SetAntialias | partial | See "cannot match". |
| Image | pass | Scaled, fractional, tint (on premultiplied pixels), source rectangles, opacity, blend, erase, rotated, clipped, nearest under no_smooth. |
| Pixels | pass at 1x and 2x | Canvas `copy` also clears outside the shape, so the block is clipped to its rectangle first. |
| BeginGroup, EndGroup | pass | An offscreen canvas per group (bounded when bounds are given), same clip inherited, pasted with opacity and blend mode. Nested groups work. |
| Features | pass | 17 blend modes, erase (DEST_OUT), gradients (linear, radial, alpha stops, under transforms), opacity on every drawing op. |
| Shadows | pass with a rewrite | Canvas `shadowBlur` is not what Cairo draws, so the Cairo algorithm (up to 12 grown layers) is replicated. Painting 12 layers at 8-bit low alpha darkened the core by about 8 % on CPU raster; the fix adds layers into one group in whole-number alpha steps that track k/n of the total. |

## Ops that cannot match, and why

1. **no_smooth (SetAntialias false) for anything but filled axis-aligned rectangles.** Canvas 2D has no switch for path anti-aliasing. Filled rectangles are emulated exactly (pixel-centre rule, integer edges) and pictures use nearest filtering; circles, ellipses, lines, strokes and paths stay smooth where Cairo draws jagged pixels. Differences are edges only, but the look differs. A later fix would be a software scan-converter for these ops (not done).
2. **Exact values of partly transparent pictures and pixel blocks.** Canvas stores premultiplied pixels but `putImageData` takes un-premultiplied, so a round trip can change values by one or two levels (opaque pixels are exact). A `get`/`set` round trip through the canvas is not byte-exact.
3. **Image borders.** Cairo fades a scaled picture's outer pixel to transparent (EXTEND_NONE); Canvas clamps. Shows as a thin box in the diffs (max difference 101 to 113 there).
4. **Anti-aliasing is never identical.** The largest single-channel difference is 220 (one-pixel lines shifted by a fraction of a pixel); counts above 64 stay tiny.

## Gaps (honest)

- **Chrome 154 only.** Firefox is not installed and Safari cannot run on Windows, so the three-browser criterion is not met. Blend modes, gradients and interpolation are the likeliest to differ elsewhere. Edge is installed but is the same engine.
- Pixel density 2 is tested on 8 gallery frames and 2 synthetic cases; other ratios are not. Goldens exist only at 1x.
- The two Chrome rasterisers differ: GL gives 1.5 to 2 times more differing pixels. A real GPU and other platforms are unmeasured.
- Transport is not measured: the harness loads JSON; the Pyodide to JS handoff (JSON versus typed arrays) is not in the timing.
- Shadows are slow (a full-canvas group per layer, no bounds): 20 to 60 ms a frame. Bounding the layers would cut this; not done.
- Real frames are final frames; animations over many frames, and sketches that never Clear, are replayed from the last Clear.
- Hidden file layers, PDF/SVG paths and `ink_bounds` are out of scope.

## Timing (ms per frame)

The final frame replayed on a warm renderer, median of 7, including a one-pixel read-back to flush. Real cases (45, including 8 at 2x): Canvas GL median 2.0 ms, CPU median 0.5 ms; Cairo (pycairo from Python) median 1.0 ms. Slowest: compositing-01 (shadows) 52 ms GL / 63 ms CPU at 2x. Cold first run (JIT, picture decode) is 3 to 140 ms. Typical frames are well under the 12 ms budget in the note; shadow-heavy ones are not.

## Reproduce

```
PY=C:\Projects\playground\.venv\Scripts\python.exe
$PY tools/export_ir.py --all ; $PY tools/export_ir.py --hidpi ; $PY tools/make_synthetic.py
$PY tools/run_chrome.py --out results <cases...>            # batches of about 16
CHROME_EXTRA=--disable-gpu $PY tools/run_chrome.py --out results_cpu <cases...>
$PY tools/compare.py ; RESULTS_DIR=results_cpu $PY tools/compare.py ; $PY tools/summarize.py
```
`results/<case>/side.png` shows Cairo | Canvas | diff (grey = difference x4, yellow = differs on an edge, red = differs away from an edge).

## Tables

### Per case

Differing % = pixels with any channel off by more than 8 (of 255). Mean = mean absolute difference per channel. Max = largest single-channel difference. Off-edge % = differing pixels away from any edge. ms = the final frame replayed on a warm renderer (7 runs, median, includes a pixel read-back so the work is flushed); Cairo = pycairo replay of the same frame.

| Case | Size | Ops (last frame) | GL: diff % | mean | max | off-edge % | result | CPU: diff % | mean | max | off-edge % | result | ms GL | ms CPU | Cairo ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gallery-colour-01_colour_forms | 640x400 | 8 | 0.00 | 0.01 | 8 | 0.000 | pass | 0.19 | 0.03 | 29 | 0.000 | pass | 1.4 | 0.2 | 0.22 |
| gallery-colour-03_gradients | 640x400 | 9 | 0.01 | 0.25 | 34 | 0.000 | pass | 0.03 | 0.26 | 23 | 0.000 | pass | 1.1 | 1.5 | 0.82 |
| gallery-colour-03_gradients@2x | 1280x800 | 9 | 0.00 | 0.23 | 30 | 0.000 | pass | 0.03 | 0.23 | 32 | 0.000 | pass | 2.3 | 5.8 | 3.24 |
| gallery-compositing-01_blend_opacity_shadow | 640x400 | 24 | 0.90 | 0.23 | 107 | 0.000 | pass | 1.07 | 0.24 | 76 | 0.000 | pass | 29.4 | 17.8 | 13.42 |
| gallery-compositing-01_blend_opacity_shadow@2x | 1280x800 | 24 | 0.38 | 0.12 | 98 | 0.000 | pass | 0.35 | 0.10 | 57 | 0.000 | pass | 51.9 | 63.2 | 42.85 |
| gallery-compositing-02_graphics | 640x400 | 3 | 0.02 | 0.01 | 25 | 0.000 | pass | 0.02 | 0.00 | 24 | 0.000 | pass | 1.9 | 0.6 | 1.43 |
| gallery-compositing-03_scratch_card | 640x400 | 5 | 0.20 | 0.03 | 54 | 0.000 | pass | 0.05 | 0.02 | 34 | 0.000 | pass | 1.8 | 0.2 | 0.36 |
| gallery-compositing-04_layers | 640x400 | 2 | 0.01 | 0.00 | 21 | 0.000 | pass | 0.02 | 0.01 | 49 | 0.000 | pass | 1.4 | 0.2 | 0.06 |
| gallery-images-01_load_image | 640x400 | 14 | 0.51 | 0.17 | 105 | 0.000 | pass | 0.33 | 0.12 | 52 | 0.000 | pass | 3.2 | 0.9 | 4.26 |
| gallery-images-01_load_image@2x | 1280x800 | 14 | 0.85 | 0.44 | 101 | 0.000 | pass | 0.72 | 0.43 | 101 | 0.000 | pass | 3.1 | 8.0 | 4.23 |
| gallery-images-02_tint_and_parts | 640x400 | 14 | 0.58 | 0.31 | 176 | 0.000 | pass | 0.27 | 0.22 | 55 | 0.000 | pass | 5.1 | 2.6 | 4.94 |
| gallery-images-03_pixels | 640x400 | 23 | 0.16 | 0.03 | 56 | 0.000 | pass | 0.05 | 0.01 | 30 | 0.000 | pass | 2.5 | 0.7 | 9.89 |
| gallery-interaction-02_paint | 640x400 | 2 | 0.57 | 0.15 | 186 | 0.000 | pass | 0.26 | 0.06 | 56 | 0.000 | pass | 2.9 | 0.2 | 2.34 |
| gallery-lines-02_caps_joins_dashes | 640x400 | 30 | 0.99 | 0.22 | 156 | 0.000 | pass | 0.57 | 0.14 | 157 | 0.000 | pass | 2.7 | 0.5 | 1.69 |
| gallery-lines-03_pixel_art | 640x400 | 54 | 0.02 | 0.01 | 23 | 0.000 | pass | 0.07 | 0.02 | 38 | 0.000 | pass | 1.2 | 0.2 | 0.15 |
| gallery-paths-01_star | 640x400 | 4 | 0.82 | 0.12 | 58 | 0.000 | pass | 0.13 | 0.03 | 44 | 0.000 | pass | 1.0 | 0.2 | 0.24 |
| gallery-paths-02_path_and_clip | 640x400 | 53 | 0.52 | 0.09 | 47 | 0.000 | pass | 0.32 | 0.09 | 68 | 0.000 | pass | 1.7 | 0.6 | 0.56 |
| gallery-paths-02_path_and_clip@2x | 1280x800 | 53 | 0.16 | 0.04 | 48 | 0.000 | pass | 0.21 | 0.03 | 44 | 0.000 | pass | 3.4 | 3.1 | 0.99 |
| gallery-paths-04_holes | 640x400 | 5 | 0.39 | 0.07 | 68 | 0.000 | pass | 0.38 | 0.07 | 51 | 0.000 | pass | 1.8 | 0.6 | 0.30 |
| gallery-saving-02_transparent_png | 640x400 | 2 | 0.26 | 0.04 | 72 | 0.000 | pass | 0.30 | 0.05 | 76 | 0.000 | pass | 1.4 | 0.4 | 0.22 |
| gallery-shapes-03_modes | 640x400 | 87 | 3.59 | 1.02 | 221 | 0.000 | **FAIL** | 1.91 | 0.46 | 142 | 0.000 | pass | 15.3 | 2.3 | 13.75 |
| gallery-shapes-04_rounded | 640x400 | 13 | 0.76 | 0.16 | 82 | 0.000 | pass | 0.56 | 0.13 | 65 | 0.000 | pass | 10.5 | 10.8 | 8.11 |
| gallery-shapes-04_rounded@2x | 1280x800 | 13 | 0.40 | 0.10 | 74 | 0.000 | pass | 0.36 | 0.10 | 71 | 0.000 | pass | 27.4 | 26.2 | 21.42 |
| gallery-studios-01_placement | 420x595 | 55 | 0.12 | 0.06 | 33 | 0.000 | pass | 0.32 | 0.09 | 44 | 0.000 | pass | 1.1 | 0.2 | 0.57 |
| gallery-studios-03_rhythm | 842x595 | 371 | 0.24 | 0.07 | 76 | 0.000 | pass | 0.43 | 0.08 | 42 | 0.000 | pass | 2.9 | 0.9 | 5.37 |
| gallery-studios-03_rhythm@2x | 1684x1190 | 371 | 0.18 | 0.04 | 61 | 0.000 | pass | 0.15 | 0.05 | 51 | 0.000 | pass | 4.0 | 2.0 | 20.06 |
| gallery-studios-06_poster_series | 595x842 | 229 | 1.63 | 0.28 | 195 | 0.000 | pass | 1.28 | 0.23 | 65 | 0.000 | pass | 10.2 | 3.6 | 12.35 |
| gallery-studios-06_poster_series@2x | 1190x1684 | 229 | 0.94 | 0.16 | 105 | 0.000 | pass | 0.74 | 0.13 | 71 | 0.000 | pass | 9.1 | 4.3 | 14.75 |
| gallery-text-01_text | 640x400 | 5 | 0.90 | 0.21 | 96 | 0.000 | pass | 0.38 | 0.09 | 51 | 0.000 | pass | 2.8 | 0.4 | 2.34 |
| gallery-text-05_text_path | 640x400 | 25 | 1.36 | 0.23 | 68 | 0.000 | pass | 0.84 | 0.15 | 62 | 0.000 | pass | 3.3 | 0.7 | 2.15 |
| gallery-text-05_text_path@2x | 1280x800 | 25 | 0.74 | 0.12 | 84 | 0.000 | pass | 0.50 | 0.08 | 62 | 0.000 | pass | 3.8 | 1.3 | 4.66 |
| gallery-transforms-03_shear_and_matrices | 640x400 | 208 | 0.43 | 0.08 | 66 | 0.000 | pass | 0.60 | 0.10 | 53 | 0.000 | pass | 1.9 | 0.5 | 0.85 |
| session1-01_first_sketch | 640x400 | 2 | 0.09 | 0.01 | 25 | 0.000 | pass | 0.17 | 0.05 | 132 | 0.000 | pass | 1.9 | 0.4 | 0.09 |
| session1-02_shapes | 640x400 | 16 | 0.70 | 0.14 | 72 | 0.000 | pass | 1.04 | 0.41 | 144 | 0.000 | pass | 1.8 | 0.4 | 0.46 |
| session1-03_colors | 640x400 | 8 | 0.35 | 0.06 | 68 | 0.000 | pass | 0.81 | 0.22 | 147 | 0.000 | pass | 2.0 | 0.3 | 0.46 |
| session1-04_fill_stroke | 640x400 | 6 | 0.37 | 0.08 | 94 | 0.000 | pass | 0.32 | 0.08 | 74 | 0.000 | pass | 1.7 | 0.4 | 0.20 |
| session1-05_text | 640x400 | 5 | 0.61 | 0.09 | 85 | 0.000 | pass | 0.29 | 0.05 | 58 | 0.000 | pass | 2.0 | 0.3 | 1.49 |
| session1-06_animation | 640x400 | 2 | 0.04 | 0.01 | 21 | 0.000 | pass | 0.08 | 0.02 | 111 | 0.000 | pass | 1.2 | 0.1 | 0.06 |
| session1-07_bounce | 640x400 | 2 | 0.04 | 0.01 | 21 | 0.000 | pass | 0.08 | 0.02 | 111 | 0.000 | pass | 0.7 | 0.2 | 0.06 |
| session1-08_mouse | 640x400 | 3 | 0.05 | 0.01 | 47 | 0.000 | pass | 0.02 | 0.01 | 111 | 0.000 | pass | 1.6 | 0.2 | 0.05 |
| session1-09_keyboard | 640x400 | 2 | 0.06 | 0.01 | 24 | 0.000 | pass | 0.13 | 0.04 | 128 | 0.000 | pass | 1.1 | 0.3 | 0.07 |
| session1-10_helpers | 640x400 | 21 | 0.76 | 0.11 | 31 | 0.000 | pass | 0.83 | 0.26 | 126 | 0.000 | pass | 1.2 | 0.4 | 0.65 |
| session1-12_default_window | 640x480 | 2 | 0.07 | 0.01 | 25 | 0.000 | pass | 0.14 | 0.04 | 132 | 0.000 | pass | 0.8 | 0.2 | 0.09 |
| session1-13_transforms | 640x400 | 33 | 0.74 | 0.15 | 82 | 0.000 | pass | 0.50 | 0.10 | 54 | 0.000 | pass | 2.0 | 0.4 | 0.78 |
| session1-14_paths | 640x400 | 45 | 1.45 | 0.26 | 94 | 0.000 | pass | 1.19 | 0.29 | 104 | 0.000 | pass | 2.6 | 0.5 | 1.05 |
| syn-antialias | 400x300 | 106 | 1.23 | 0.59 | 165 | 0.000 | pass | 1.18 | 0.59 | 195 | 0.000 | pass | 1.5 | 0.5 | 0.31 |
| syn-blend | 400x300 | 36 | 0.04 | 0.26 | 16 | 0.000 | pass | 0.11 | 0.31 | 25 | 0.000 | pass | 3.5 | 1.1 | 2.33 |
| syn-clear | 400x300 | 8 | 0.00 | 0.13 | 1 | 0.000 | pass | 0.00 | 0.13 | 1 | 0.000 | pass | 1.1 | 0.4 | 0.13 |
| syn-clip | 400x300 | 36 | 0.46 | 0.13 | 112 | 0.000 | pass | 0.47 | 0.16 | 112 | 0.000 | pass | 2.9 | 0.4 | 0.20 |
| syn-erase | 400x300 | 13 | 0.76 | 0.34 | 73 | 0.000 | pass | 0.52 | 0.30 | 48 | 0.000 | pass | 2.7 | 0.8 | 1.86 |
| syn-fillpath | 400x300 | 10 | 0.98 | 0.17 | 86 | 0.000 | pass | 0.46 | 0.10 | 39 | 0.000 | pass | 1.2 | 0.2 | 0.19 |
| syn-gradients | 400x300 | 14 | 0.57 | 0.19 | 63 | 0.000 | pass | 0.47 | 0.20 | 44 | 0.000 | pass | 1.6 | 0.4 | 0.65 |
| syn-groups | 400x300 | 41 | 0.16 | 0.08 | 118 | 0.000 | pass | 0.63 | 0.25 | 120 | 0.000 | pass | 4.4 | 1.4 | 0.92 |
| syn-hidpi | 400x300 | 16 | 2.08 | 0.41 | 106 | 0.000 | pass | 1.98 | 0.44 | 106 | 0.000 | pass | 4.8 | 2.3 | 1.87 |
| syn-images | 400x300 | 26 | 2.15 | 0.64 | 113 | 0.000 | pass | 2.16 | 0.67 | 113 | 0.000 | pass | 2.6 | 0.8 | 0.64 |
| syn-opacity | 400x300 | 16 | 1.16 | 0.30 | 94 | 0.000 | pass | 0.83 | 0.26 | 39 | 0.000 | pass | 2.3 | 0.4 | 1.20 |
| syn-pixels | 400x300 | 14 | 0.02 | 0.09 | 15 | 0.000 | pass | 0.04 | 0.09 | 20 | 0.000 | pass | 1.2 | 0.3 | 0.15 |
| syn-pixels-2x | 400x300 | 8 | 0.69 | 0.11 | 47 | 0.000 | pass | 0.37 | 0.05 | 33 | 0.000 | pass | 1.0 | 0.2 | 0.18 |
| syn-shadow | 400x300 | 15 | 0.92 | 0.41 | 81 | 0.000 | pass | 0.76 | 0.39 | 67 | 0.000 | pass | 43.2 | 30.0 | 9.93 |
| syn-shapes | 400x300 | 21 | 1.04 | 0.19 | 220 | 0.000 | pass | 1.00 | 0.18 | 220 | 0.000 | pass | 1.4 | 0.2 | 0.41 |
| syn-strokes | 400x300 | 20 | 2.18 | 0.38 | 82 | 0.000 | pass | 1.54 | 0.29 | 75 | 0.000 | pass | 1.4 | 0.3 | 0.46 |
| syn-text | 400x300 | 15 | 3.79 | 0.74 | 105 | 0.000 | **FAIL** | 1.86 | 0.36 | 146 | 0.000 | pass | 4.1 | 1.3 | 3.92 |
| syn-transforms | 400x300 | 74 | 0.47 | 0.12 | 49 | 0.000 | pass | 0.50 | 0.12 | 42 | 0.000 | pass | 2.0 | 0.3 | 0.36 |

### Per op type

Cases = how many of the 63 cases contain the op. Pass counts are for GL / CPU raster (see 'Two Chrome rasterisers'). Worst = highest differing-pixel percentage among the cases that contain it (every such case also contains other ops).

| Op type | Cases | Pass GL | Pass CPU | Worst diff % (GL / CPU) | Dedicated case |
|---|---|---|---|---|---|
| Clear | 63 | 61/63 | 63/63 | 3.79 / 2.16 | syn-clear |
| Circle | 43 | 42/43 | 43/43 | 3.59 / 1.98 | syn-shapes |
| Ellipse | 9 | 8/9 | 9/9 | 3.59 / 1.91 | syn-shapes |
| Rect | 45 | 44/45 | 45/45 | 3.59 / 2.16 | syn-shapes |
| Line | 16 | 16/16 | 16/16 | 2.18 / 1.98 | syn-shapes |
| Point | 5 | 5/5 | 5/5 | 1.04 / 1.04 | syn-shapes |
| Text | 27 | 25/27 | 27/27 | 3.79 / 1.98 | syn-text |
| Save | 31 | 29/31 | 31/31 | 3.79 / 2.16 | syn-transforms |
| Restore | 31 | 29/31 | 31/31 | 3.79 / 2.16 | syn-transforms |
| Concat | 25 | 23/25 | 25/25 | 3.79 / 2.16 | syn-transforms |
| ClipPath | 15 | 14/15 | 15/15 | 3.79 / 2.16 | syn-clip |
| ResetClip | 2 | 2/2 | 2/2 | 0.46 / 0.63 | syn-clip |
| FillPath | 17 | 17/17 | 17/17 | 1.63 / 1.28 | syn-fillpath |
| StrokePath | 17 | 17/17 | 17/17 | 2.18 / 1.98 | syn-strokes |
| SetAntialias | 3 | 3/3 | 3/3 | 1.23 / 1.18 | syn-antialias |
| ResetMatrix | 2 | 2/2 | 2/2 | 0.47 / 0.60 | syn-transforms |
| Image | 12 | 11/12 | 12/12 | 3.59 / 2.16 | syn-images |
| Pixels | 3 | 3/3 | 3/3 | 0.69 / 0.37 | syn-pixels / syn-pixels-2x |
| BeginGroup | 2 | 2/2 | 2/2 | 2.08 / 1.98 | syn-groups |
| EndGroup | 2 | 2/2 | 2/2 | 2.08 / 1.98 | syn-groups |

- GL: real cases (n=45) warm ms/frame: median 2.00, mean 5.20, max 51.9 (gallery-compositing-01_blend_opacity_shadow@2x)
- CPU: real cases (n=45) warm ms/frame: median 0.50, mean 3.66, max 63.2 (gallery-compositing-01_blend_opacity_shadow@2x)
- Cairo (pycairo) real cases: median 0.99, mean 4.54, max 42.8
- GL: 61/63 cases pass; 61 within 3 % differing; mean abs diff max 1.02; edges_only in 63/63
- CPU: 63/63 cases pass; 63 within 3 % differing; mean abs diff max 0.67; edges_only in 63/63
