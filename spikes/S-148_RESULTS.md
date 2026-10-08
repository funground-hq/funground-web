# S-148 results: the two browser routes after the four clean performance fixes of Sprint 19

Question: after S-144 (state copy), S-145 (colour cache), S-146 (Vector numbers) and S-147 (glyph outline cache), how do Cairo-in-wasm and the Canvas IR route compare in Chrome now, and where does the time go inside Pyodide?

Branch (nothing committed or pushed): `spike/s148-rebench` in `C:\Projects\funground-web`, from `spike/s142-browser-bench`. `C:\Projects\playground`, `C:\Projects\playground-0.2` and `C:\Projects\funground-cairo-wasm` were not changed. The funground test suite was not run. Run on 9 October 2026 between 00:11 and 01:00, one job at a time.

## Short answer

1. **The fixes help Python by about a quarter on the sketches they target, and by less than the noise elsewhere.** Measured back to back in one session (before = the S-142 funground, after = `69d989c`): `draw()` excluding `sound-02` fell from 11.4 to 7.9 ms native (-31 %) and from 25.0 to 18.1 ms in Pyodide (-28 %) on the Cairo route; 10.8 to 8.1 ms native and 22.4 to 17.2 ms in Pyodide (-23 %) on the Canvas route. Per case: kinetic_type -32 to -40 %, paths-06 -33 to -50 %, text_dots -30 %, noise -30 % (Cairo route), gaussian -55 % native. `rangoli`, `sound-02` (all `synth.py`), `studios-03` and `poster_series` `draw()` did not change (they never were in the fixed code).
2. **End to end, in Chrome, the heavy examples moved 5 to 20 %, the same size as the noise.** Mean over the 10 heavy cases, 1x, page paints: Cairo 63.8 to 53.7 ms (3 repeats; 51.4 with 5), Canvas 89.0 to 55.4 ms (3 repeats; 66.6 with 5). Worker-paints variants: Cairo 58.9 to 58.5 ms (52.0 with 5), Canvas 71.4 to 67.8 ms (66.7 with 5). Native: Cairo 21.7 to 18.7 ms, IR 29.0 to 25.9 ms. Light sketches did not change (06 and 07: 4 ms Cairo, 1.3 ms Canvas; both inside 16.7 ms).
3. **The route comparison did not change.** Cairo-in-wasm is still at or ahead of the Canvas route on heavy sketches at 1x (mean end-to-end ratio Cairo/Canvas 0.72 before, 0.73 after with 5 repeats; the 3-repeat figure, 1.07, is inflated by three Canvas cases (gaussian, rhythm, text_as_geometry) whose median of three was 15 to 19 ms while the median of five is 32 to 38 ms), about equal at 2x (1.02 before, 0.94 after with 5 repeats, 0.75 with 3), and 3 to 9 times slower than Canvas on light sketches at 2x (`06`, `07`: 11.5 ms against 1.3 ms; the per-pixel copy). None of the fixes touches the two things that separate the routes: Cairo's copy and render in wasm (about 11 ms at 1x, 16 ms at 2x, mean) and the IR encode in Python (about 18 ms in Pyodide, unchanged).
4. **Where Pyodide time goes now (heavy mean, 1x, ms per frame):** `draw()` about 30 (18 without `sound-02`), Cairo render about 9, or IR encode about 18 (dict building 9.5, Text outline and rounded-Rect extras 2.6, `json.dumps` 5.7). JavaScript on the Canvas route is small: `JSON.parse` 0.8, `drawFrame` call 0.6 to 0.8, `postMessage` of the JSON string 0.0 to 0.3 (all as matrix means). `draw()` is the biggest single cost, then the encode, then Cairo.
5. **The native hotspot shares hold in Pyodide** (within about 5 points per file). Pyodide runs `draw()` 2.0 times slower than native on average (1.3 to 3.8 per case); pure-Python code (colour, vector, noise, state) is 2.5 to 3.8 times slower, while time spent in C extensions (pathops, Cairo calls) is 1.3 to 2.
6. **Pixels are unchanged:** Cairo route 12 of 12 byte-identical to the goldens in both painting variants and natively; Canvas route 12 of 12 within S-135's tolerance, numerically identical to S-142.
7. **Noise is large.** The same configuration differed between repeats by 1.5 to 3 times (end-to-end spread table below). Read nothing under about 25 % from the browser tables. The in-process Python timings of the profile section are steadier (two runs each, interleaved before and after).

## Before (S-142) and after (S-148), by route and group

Mean over the cases of the per-case medians (ms); ratio = after / before. Browser rows are the median of the repeats of each case (3 repeats as in S-142; the 5-repeat version follows). Heavy = the 10 heavy gallery examples; typical = Session 1 `05_text`, `06_animation`, `07_bounce`.

| group | scale | route | before: end to end | after (3 repeats) | after (5 repeats) |
|---|---|---|---|---|---|
| heavy | 1x | native Cairo | 21.7 | 18.7 (0.86) | 18.2 (0.84) |
| heavy | 1x | Chrome Cairo, page paints | 63.8 | 53.7 (0.84) | 51.4 (0.81) |
| heavy | 1x | Chrome Cairo, worker paints | 58.9 | 58.5 (0.99) | 52.0 (0.88) |
| heavy | 1x | native IR (encode only) | 29.0 | 25.9 (0.89) | 25.3 (0.87) |
| heavy | 1x | Chrome Canvas, page paints | 89.0 | 55.4 (0.62) | 66.6 (0.75) |
| heavy | 1x | Chrome Canvas, worker paints | 71.4 | 67.8 (0.95) | 66.7 (0.93) |
| heavy | 2x | native Cairo | 27.9 | 22.6 (0.81) | 22.1 (0.79) |
| heavy | 2x | Chrome Cairo, page paints | 75.3 | 53.1 (0.71) | 63.7 (0.85) |
| heavy | 2x | Chrome Cairo, worker paints | 67.2 | 72.5 (1.08) | 64.5 (0.96) |
| heavy | 2x | native IR (encode only) | 30.7 | 26.1 (0.85) | 26.2 (0.85) |
| heavy | 2x | Chrome Canvas, page paints | 74.3 | 72.4 (0.97) | 68.3 (0.92) |
| heavy | 2x | Chrome Canvas, worker paints | 71.8 | 61.5 (0.86) | 64.2 (0.89) |
| typical | 1x | Chrome Cairo, page paints | 7.0 | 6.2 (0.89) | 5.8 (0.83) |
| typical | 1x | Chrome Canvas, page paints | 6.0 | 4.8 (0.81) | 5.1 (0.86) |
| typical | 2x | Chrome Cairo, page paints | 14.1 | 13.1 (0.93) | 13.3 (0.95) |
| typical | 2x | Chrome Canvas, page paints | 6.0 | 5.6 (0.94) | 5.0 (0.83) |

Python phases only (mean over heavy cases, 1x, `draw()`; "excl." = without `sound-02`, whose time is all `synth.py`): see "Python time, before and after, back to back" below. The full phase means (draw, py other, render, encode, copy, message, parse, paint) for every group, scale and variant are in Appendix A (first table).

## Setup (what was measured and how)

Identical to S-142 except as listed.

| | |
|---|---|
| Machine | Windows 11, Core i5-1135G7, 8 GB, the maintainer's own Chrome running (as in S-142). The machine was visibly less loaded than during S-142 for some runs and not for others. |
| Browser | HeadlessChrome 154.0.0.0 (`--headless=new`), a fresh temporary profile per run, stopped by PID; `--force-device-scale-factor=2` for 2x. Headless: no vsync or GPU window; "painted" is the Canvas API call returning (open problem 1 of S-142 stands). |
| Pyodide | 314.0.7 (CPython 3.14.2) from jsDelivr, module worker; fontTools from Pyodide; uharfbuzz 0.56.3 from PyPI; pycairo 1.29.2 and skia-pathops 0.9.2 wheels from the funground-cairo-wasm CI artifact (run 37768002634), served from localhost. |
| funground | `git archive` of `C:\Projects\playground-0.2` branch `release-0.2-web` taken at `69d989c` (S-147), the end of the range under test; `start/step/finish` are in funground itself (S-060). The branch moved on during the session (S-149, S-150 commits up to `82af9bf`, including a `typography.py` change for `Path.translated`); those commits were not measured. Examples and goldens from the same tree (`examples/`, `tests/golden/`). |
| Native | CPython 3.14.7 from the playground venv, pygame-ce 2.5.8 for `sound-02`. |
| Matrix | The same 13 cases, both routes, page and worker painting, 1x and 2x, 30 timed frames after 5 warm-up (scripts: 1 warm-up and 10 runs), `random_seed(0)`, 3 repeats with different run orders; median of the three medians. A 4th and 5th repeat were added afterwards (see "Noise"). Native: 3 repeats (5 in the supplementary table). |

### Harness shims kept (all in `harness/s142/`, none in a sketch, none in funground)

1. `Host.web_run` / `web_show` replace `f.run` and `f.show` for the sketch's namespace. `web_run` now only calls the real `sketch.start(namespace, fps=, max_frames=)` and wraps the sketch's draw function in a timer. **The S-142 outside patch of the loop is gone**: nothing replaces `start`, `step` or `finish` (the S-142 harness already called them; it only needed `spike/s136-loop` to have them).
2. `BrowserPlatform` (a `HeadlessPlatform` subclass): `tick()` returns the rAF delta instead of sleeping, `present()` keeps the frame.
3. Canvas route: an IR-capturing `IrRenderer` stands in for `funground.renderers.cairo2d` (sys.modules stub, as S-133/S-136); `Host.encode` adds Text glyph outlines and the rounded-Rect path; Image and Pixels ops raise (no binary payloads). For `studios-03`, `-05`, `-06` the marks' `ink_bounds` are delegated to a real `CairoRenderer` (pycairo loaded lazily).
4. `mixer_stub.py` for `sound-02` (pygame.mixer cannot start in Pyodide).
5. Timers: the learner's `draw()` and the renderer's methods are wrapped for per-phase time.
6. The bundle (`tools/build_s142_bundle.py`) leaves out `platform/pygame_platform.py` and `gallery.py` and ships the fonts separately; unchanged. Its source default is now `fg_s148` (`git archive HEAD funground`).

New in S-148 (all in `harness/s148/` and `tools/s148_*.py`, plus path changes in the S-142 tools): `prof_shim.py` (phase timers and cProfile, same code natively and in Pyodide), `prof_worker.js` and `prof.html` (the Pyodide side and the `postMessage` test), `s148_prof_native.py`, `s148_report.py`. `tools/run_s142.py` gained `--page`; `tools/s142_report.py` gained `REPEATS`. The raw results are in `results_s148/` (git-ignored).

## Pixel checks

Method as S-142: after frame 30 the canvas is read back and compared with the golden (`tools/s142_pixels.py`); 1x only; `sound-02` has no golden.

| route / where | cases with a golden | byte-identical | S-135 tolerance | worst case |
|---|---|---|---|---|
| Cairo / page paints | 12 | **12** | - | - |
| Cairo / worker paints | 12 | **12** | - | - |
| Canvas / page paints | 12 | 0 | **12 pass** | rangoli: 2.71 % of pixels differ by more than 8, mean 0.34, max 76, off-edge 0.000 % |
| Canvas / worker paints | 12 | 0 | **12 pass** | identical numbers |
| native Cairo | 12 | **12** | - | - |

These are exactly S-142's figures: the four fixes (and the changes in `69d989c`'s tree) change no pixel. Not checked at 2x.


## Python time, before and after, back to back (the steadier numbers)

Because the browser tables are noisy, the Python phases were also measured inside one process per version: `harness/s148/prof_shim.py` runs each heavy case at 1x (5 warm-up and 20 timed frames; scripts: 1 and 5 runs), natively and in Pyodide in a worker, for the S-142 funground (`fg_s136`, `abd3865`) and the S-148 funground (`69d989c`). Order: native after, native before, (rebuild bundle) Pyodide before, (rebuild) Pyodide after, for both routes, then the whole sequence once more; each cell is the median of the two runs. Differences below about 15 % are still noise (two runs).

Means over the 10 heavy cases (ms per frame):

| | native before | native after | Pyodide before | Pyodide after |
|---|---|---|---|---|
| draw(), Cairo-route run | 17.5 | 15.3 | 37.1 | 30.6 |
| draw(), without sound-02 | 11.4 | 7.9 | 25.0 | 18.1 |
| draw(), Canvas-route run | 17.5 | 14.9 | 33.8 | 30.4 |
| draw(), without sound-02 | 10.8 | 8.1 | 22.4 | 17.2 |
| Cairo render | 6.4 | 5.2 | 10.4 | 8.8 |
| IR encode: build dicts / Text and Rect extras / json.dumps | 4.8 / 3.0 / 4.3 | 4.7 / 1.6 / 3.7 | 9.5 / 4.0 / 5.9 | 9.5 / 2.6 / 5.7 |

(The extras column re-runs `Host.encode` for Text and rounded-Rect ops, so it includes a second `op_to_jsonable` of those ops; the three columns slightly over-count their sum. The encode of the matrix is one measurement around the whole thing: 24.8 ms mean in Chrome, 10.0 native, after.)

The Cairo render got faster by the glyph-outline cache (S-147): `poster_series` 20.8 to 16.0 ms native and 25.5 to 21.1 ms in Pyodide, `text_dots` 6.7 to 4.6 and 13.8 to 9.9, `kinetic_type` 15.6 to 9.8 in Pyodide, `paths-06` 10.5 to 8.7. The IR encode of `poster_series` fell from 37 to 21 ms native and from 34.5 to 27.3 ms in Pyodide for the same reason; the Canvas encode of the other cases did not change (the fixes do not touch `ir.py`).

## Where the time goes inside Pyodide now

### Per case, Pyodide (ms per frame, median; native in brackets), both routes

(From `results_s148/prof-browser*-cairo.json` / `-canvas.json` and the native counterparts.)

## cairo route: Python time per frame, scale 1, back to back in this session (ms, median of 20 frames; median of 2 runs per cell): before = funground of S-142, after = release-0.2-web HEAD

| case | draw() native before -> after | draw() Pyodide before -> after | render native | render Pyodide | Pyodide / native draw (after) |
|---|---|---|---|---|---|
| projects-02_rangoli | 4.4 -> 4.4 (1.00) | 17.8 -> 17.1 (0.96) | 4.4 -> 4.4 | 14.7 -> 12.5 | 3.8x |
| projects-06_kinetic_type | 31.7 -> 21.4 (0.68) | 93.9 -> 56.5 (0.60) | 5.5 -> 4.7 | 15.6 -> 9.8 | 2.6x |
| text-09_text_dots | 12.9 -> 8.5 (0.66) | 30.5 -> 21.2 (0.70) | 6.7 -> 4.6 | 13.8 -> 9.9 | 2.5x |
| randomness-03_noise | 16.0 -> 10.5 (0.65) | 30.7 -> 21.6 (0.70) | 2.0 -> 1.4 | 3.3 -> 2.7 | 2.1x |
| sound-02_write_a_tune | 72.9 -> 82.3 (1.13) | 145.6 -> 142.6 (0.98) | 4.0 -> 4.8 | 7.5 -> 7.1 | 1.7x |
| randomness-02_gaussian_and_choice | 10.3 -> 4.7 (0.45) | 11.7 -> 10.4 (0.89) | 4.9 -> 3.5 | 4.0 -> 5.9 | 2.2x |
| studios-03_rhythm | 3.2 -> 2.4 (0.75) | 3.5 -> 3.2 (0.92) | 5.3 -> 4.4 | 5.3 -> 5.0 | 1.3x |
| studios-05_text_as_geometry | 6.7 -> 8.2 (1.22) | 10.2 -> 12.9 (1.26) | 3.0 -> 4.1 | 4.2 -> 4.9 | 1.6x |
| paths-06_outlines | 11.6 -> 5.8 (0.50) | 20.5 -> 13.8 (0.67) | 7.1 -> 4.4 | 10.5 -> 8.7 | 2.4x |
| studios-06_poster_series | 5.3 -> 4.7 (0.89) | 6.4 -> 6.3 (0.98) | 20.8 -> 16.0 | 25.5 -> 21.1 | 1.3x |

Mean draw() native: 17.5 -> 15.3 ms over 10 cases

Mean draw() pyodide: 37.1 -> 30.6 ms over 10 cases

## cairo route, Pyodide, after: where one frame goes (ms; native after in brackets)

| case | ops | JSON bytes | step | draw | other | render |
|---|---|---|---|---|---|---|
| projects-02_rangoli | 636 | - | 31.8 [8.9] | 17.1 [4.4] | 2.3 [0.0] | 12.5 [4.4] |
| projects-06_kinetic_type | 633 | - | 65.7 [26.5] | 56.5 [21.4] | -0.7 [0.4] | 9.8 [4.7] |
| text-09_text_dots | 507 | - | 31.1 [13.3] | 21.2 [8.5] | -0.0 [0.2] | 9.9 [4.6] |
| randomness-03_noise | 419 | - | 24.9 [12.0] | 21.6 [10.5] | 0.6 [0.1] | 2.7 [1.4] |
| sound-02_write_a_tune | 413 | - | 149.1 [87.3] | 142.6 [82.3] | -0.6 [0.1] | 7.1 [4.8] |
| randomness-02_gaussian_and_choice | 401 | - | 17.3 [8.4] | 10.4 [4.7] | 1.0 [0.3] | 5.9 [3.5] |
| studios-03_rhythm | 371 | - | 8.2 [6.8] | 3.2 [2.4] | 0.0 [0.0] | 5.0 [4.4] |
| studios-05_text_as_geometry | 290 | - | 19.2 [12.3] | 12.9 [8.2] | 0.0 [0.0] | 4.9 [4.1] |
| paths-06_outlines | 249 | - | 21.9 [10.0] | 13.8 [5.8] | -0.5 [-0.2] | 8.7 [4.4] |
| studios-06_poster_series | 229 | - | 28.4 [20.6] | 6.3 [4.7] | 0.9 [-0.1] | 21.1 [16.0] |

## cairo route: cProfile of draw(), share by file, after (first run; native | Pyodide)

**projects-02_rangoli** (profiled draw 8.5 ms native, 50.8 ms Pyodide; 16010 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/sketch.py | 2.26 | 27 | 14.68 | 29 |
| funground/pathops.py | 1.71 | 20 | 7.65 | 15 |
| funground/color.py | 1.10 | 13 | 7.42 | 15 |
| funground/api.py | 0.74 | 9 | 5.47 | 11 |
| funground/geometry.py | 0.87 | 10 | 5.00 | 10 |
| funground/state.py | 0.60 | 7 | 3.10 | 6 |
| USER sketch | 0.42 | 5 | 2.20 | 4 |

**projects-06_kinetic_type** (profiled draw 66.1 ms native, 343.6 ms Pyodide; 165995 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/color.py | 18.73 | 28 | 115.81 | 34 |
| funground/vector.py | 15.21 | 23 | 80.54 | 23 |
| funground/noise.py | 12.53 | 19 | 53.17 | 15 |
| funground/sketch.py | 5.00 | 8 | 25.44 | 7 |
| funground/api.py | 3.94 | 6 | 20.20 | 6 |
| funground/state.py | 3.52 | 5 | 17.54 | 5 |
| USER sketch | 3.98 | 6 | 16.20 | 5 |

**text-09_text_dots** (profiled draw 21.2 ms native, 109.1 ms Pyodide; 50788 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/color.py | 6.39 | 30 | 37.31 | 34 |
| funground/sketch.py | 4.80 | 23 | 22.91 | 21 |
| funground/state.py | 2.95 | 14 | 13.30 | 12 |
| funground/api.py | 2.30 | 11 | 11.47 | 11 |
| funground/geometry.py | 2.67 | 13 | 11.43 | 10 |
| funground/typography.py | 0.52 | 2 | 3.73 | 3 |
| USER sketch | 0.55 | 3 | 2.81 | 3 |

**randomness-03_noise** (profiled draw 24.9 ms native, 103.1 ms Pyodide; 44718 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/color.py | 6.14 | 25 | 30.76 | 30 |
| funground/noise.py | 6.49 | 26 | 24.27 | 24 |
| funground/sketch.py | 4.18 | 17 | 17.48 | 17 |
| funground/state.py | 3.01 | 12 | 11.15 | 11 |
| funground/api.py | 1.97 | 8 | 9.06 | 9 |
| USER sketch | 0.86 | 3 | 3.14 | 3 |
| funground/shapes.py | 0.51 | 2 | 2.23 | 2 |

**sound-02_write_a_tune** (profiled draw 74.0 ms native, 147.3 ms Pyodide; 12270 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/synth.py | 69.01 | 93 | 128.18 | 87 |
| funground/sketch.py | 1.39 | 2 | 5.54 | 4 |
| funground/sound.py | 1.04 | 1 | 4.03 | 3 |
| USER sketch | 0.99 | 1 | 3.80 | 3 |
| funground/api.py | 0.67 | 1 | 2.44 | 2 |
| funground/ir.py | 0.26 | 0 | 1.30 | 1 |
| funground/geometry.py | 0.24 | 0 | 0.93 | 1 |

**randomness-02_gaussian_and_choice** (profiled draw 16.2 ms native, 51.5 ms Pyodide; 24107 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/sketch.py | 4.27 | 26 | 12.84 | 25 |
| random.py | 2.77 | 17 | 8.56 | 17 |
| funground/api.py | 2.47 | 15 | 8.32 | 16 |
| funground/state.py | 3.22 | 20 | 8.28 | 16 |
| C/other | 0.59 | 4 | 4.51 | 9 |
| funground/color.py | 1.24 | 8 | 3.96 | 8 |
| USER sketch | 0.90 | 6 | 2.54 | 5 |

**studios-03_rhythm** (profiled draw 9.1 ms native, 37.0 ms Pyodide; 10057 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/renderers/cairo2d.py | 3.66 | 40 | 14.10 | 38 |
| funground/typography.py | 0.94 | 10 | 7.50 | 20 |
| funground/marks.py | 1.32 | 15 | 6.07 | 16 |
| funground/geometry.py | 0.67 | 7 | 2.53 | 7 |
| shim.py | 1.09 | 12 | 1.60 | 4 |
| funground/sketch.py | 0.37 | 4 | 1.13 | 3 |
| C/other | 0.15 | 2 | 0.93 | 3 |

**studios-05_text_as_geometry** (profiled draw 12.8 ms native, 53.0 ms Pyodide; 15079 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/renderers/cairo2d.py | 6.80 | 53 | 24.13 | 46 |
| funground/sketch.py | 1.18 | 9 | 6.67 | 13 |
| funground/pathops.py | 1.55 | 12 | 5.67 | 11 |
| funground/geometry.py | 0.58 | 4 | 3.77 | 7 |
| funground/marks.py | 0.58 | 5 | 3.53 | 7 |
| funground/api.py | 0.34 | 3 | 2.00 | 4 |
| funground/typography.py | 0.23 | 2 | 1.63 | 3 |

**paths-06_outlines** (profiled draw 14.4 ms native, 47.2 ms Pyodide; 15634 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/pathops.py | 5.08 | 35 | 14.93 | 32 |
| funground/sketch.py | 2.38 | 17 | 8.32 | 18 |
| funground/geometry.py | 1.42 | 10 | 4.62 | 10 |
| funground/state.py | 1.45 | 10 | 4.56 | 10 |
| funground/color.py | 1.05 | 7 | 4.17 | 9 |
| funground/api.py | 0.98 | 7 | 3.60 | 8 |
| enum.py | 0.34 | 2 | 1.29 | 3 |

**studios-06_poster_series** (profiled draw 9.4 ms native, 23.8 ms Pyodide; 9047 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/surface.py | 1.98 | 21 | 5.88 | 25 |
| funground/marks.py | 1.57 | 17 | 4.26 | 18 |
| funground/sketch.py | 1.40 | 15 | 2.49 | 10 |
| funground/state.py | 0.79 | 8 | 1.81 | 8 |
| C/other | 0.21 | 2 | 1.75 | 7 |
| funground/geometry.py | 0.66 | 7 | 1.74 | 7 |
| funground/api.py | 0.47 | 5 | 1.46 | 6 |

## cProfile of the Cairo render step, share by file, after (native | Pyodide)

**projects-02_rangoli** (profiled 6.7 ms native, 30.3 ms Pyodide): funground/renderers/cairo2d.py 90% | 88%; funground/geometry.py 9% | 11%; prof_shim.py 1% | 0%; shim.py 0% | 0%; C/other 0% | 0%

**projects-06_kinetic_type** (profiled 7.7 ms native, 34.9 ms Pyodide): funground/renderers/cairo2d.py 88% | 78%; funground/typography.py 10% | 21%; C/other 0% | 1%; funground/geometry.py 0% | 0%; prof_shim.py 1% | 0%

**text-09_text_dots** (profiled 6.8 ms native, 32.1 ms Pyodide): funground/renderers/cairo2d.py 85% | 73%; funground/typography.py 13% | 25%; C/other 0% | 1%; funground/geometry.py 1% | 0%; prof_shim.py 1% | 0%

**randomness-03_noise** (profiled 3.3 ms native, 15.5 ms Pyodide): funground/renderers/cairo2d.py 97% | 99%; prof_shim.py 2% | 1%; funground/ir.py 0% | 0%; shim.py 0% | 0%; C/other 0% | 0%

**sound-02_write_a_tune** (profiled 8.5 ms native, 25.8 ms Pyodide): funground/renderers/cairo2d.py 86% | 87%; funground/geometry.py 8% | 7%; funground/typography.py 3% | 5%; fontTools 1% | 0%; shim.py 0% | 0%

**randomness-02_gaussian_and_choice** (profiled 7.4 ms native, 14.3 ms Pyodide): funground/renderers/cairo2d.py 98% | 99%; prof_shim.py 2% | 1%; shim.py 0% | 0%; funground/ir.py 0% | 0%; C/other 0% | 0%

**paths-06_outlines** (profiled 7.4 ms native, 21.2 ms Pyodide): funground/renderers/cairo2d.py 83% | 67%; funground/typography.py 14% | 30%; funground/geometry.py 1% | 1%; C/other 0% | 1%; prof_shim.py 1% | 0%

**studios-06_poster_series** (profiled 16.8 ms native, 48.5 ms Pyodide): funground/renderers/cairo2d.py 70% | 48%; funground/typography.py 28% | 48%; funground/geometry.py 1% | 2%; C/other 0% | 2%; prof_shim.py 1% | 0%


## canvas route: Python time per frame, scale 1, back to back in this session (ms, median of 20 frames; median of 2 runs per cell): before = funground of S-142, after = release-0.2-web HEAD

| case | draw() native before -> after | draw() Pyodide before -> after | encode native before -> after | encode Pyodide before -> after | Pyodide / native draw (after) |
|---|---|---|---|---|---|
| projects-02_rangoli | 4.5 -> 4.1 (0.91) | 14.0 -> 12.8 (0.92) | 7.9 -> 7.8 | 23.0 -> 23.4 | 3.2x |
| projects-06_kinetic_type | 31.7 -> 21.4 (0.67) | 86.1 -> 61.4 (0.71) | 12.3 -> 11.4 | 32.4 -> 32.0 | 2.9x |
| text-09_text_dots | 12.8 -> 11.2 (0.88) | 26.5 -> 24.8 (0.94) | 14.4 -> 16.0 | 31.4 -> 29.1 | 2.2x |
| randomness-03_noise | 13.1 -> 10.9 (0.83) | 19.9 -> 20.8 (1.04) | 6.0 -> 6.0 | 10.0 -> 11.1 | 1.9x |
| sound-02_write_a_tune | 77.3 -> 76.5 (0.99) | 136.2 -> 148.9 (1.09) | 8.1 -> 8.1 | 15.3 -> 13.5 | 1.9x |
| randomness-02_gaussian_and_choice | 9.7 -> 6.1 (0.63) | 15.6 -> 7.5 (0.48) | 7.5 -> 8.4 | 12.0 -> 9.3 | 1.2x |
| studios-03_rhythm | 2.9 -> 2.8 (0.97) | 3.9 -> 2.9 (0.73) | 8.7 -> 8.0 | 11.1 -> 9.8 | 1.0x |
| studios-05_text_as_geometry | 5.2 -> 4.6 (0.89) | 12.5 -> 9.8 (0.78) | 4.8 -> 4.6 | 9.1 -> 9.3 | 2.1x |
| paths-06_outlines | 10.8 -> 6.8 (0.63) | 16.3 -> 10.0 (0.61) | 13.1 -> 8.9 | 15.2 -> 12.4 | 1.5x |
| studios-06_poster_series | 6.7 -> 4.6 (0.70) | 7.0 -> 5.2 (0.75) | 37.2 -> 21.0 | 34.5 -> 27.3 | 1.1x |

Mean draw() native: 17.5 -> 14.9 ms over 10 cases

Mean draw() pyodide: 33.8 -> 30.4 ms over 10 cases

## canvas route, Pyodide, after: where one frame goes (ms; native after in brackets)

| case | ops | JSON bytes | step | draw | other | build | extra | dumps |
|---|---|---|---|---|---|---|---|---|
| projects-02_rangoli | 636 | 143746 | 13.1 [4.1] | 12.8 [4.1] | 0.2 [0.1] | 15.9 [4.8] | 1.8 [0.5] | 5.7 [2.4] |
| projects-06_kinetic_type | 633 | 199959.5 | 62.1 [21.5] | 61.4 [21.4] | 0.6 [0.2] | 18.9 [6.2] | 3.8 [1.4] | 9.4 [3.8] |
| text-09_text_dots | 507 | 203383 | 25.3 [11.4] | 24.8 [11.2] | 0.5 [0.2] | 14.8 [7.8] | 4.6 [2.9] | 9.6 [5.4] |
| randomness-03_noise | 419 | 60313 | 21.1 [11.0] | 20.8 [10.9] | 0.3 [0.1] | 9.6 [5.1] | 0.0 [0.0] | 1.5 [0.9] |
| sound-02_write_a_tune | 413 | 76341.5 | 149.0 [76.7] | 148.9 [76.5] | 0.1 [0.2] | 9.3 [5.4] | 1.1 [0.7] | 3.1 [2.0] |
| randomness-02_gaussian_and_choice | 401 | 61602 | 7.7 [6.3] | 7.5 [6.1] | 0.1 [0.1] | 7.8 [6.7] | 0.0 [0.0] | 1.6 [1.7] |
| studios-03_rhythm | 371 | 86958 | 2.9 [2.8] | 2.9 [2.8] | 0.0 [0.0] | 3.8 [3.1] | 2.7 [1.9] | 3.3 [3.0] |
| studios-05_text_as_geometry | 290 | 61333 | 9.8 [4.6] | 9.8 [4.6] | 0.0 [0.0] | 7.0 [3.4] | 0.0 [0.0] | 2.3 [1.2] |
| paths-06_outlines | 249 | 127706 | 10.1 [6.9] | 10.0 [6.8] | 0.1 [0.1] | 5.2 [3.1] | 2.4 [1.9] | 4.8 [3.9] |
| studios-06_poster_series | 229 | 355581 | 5.3 [4.7] | 5.2 [4.6] | 0.1 [0.1] | 2.3 [1.4] | 9.4 [6.8] | 15.6 [12.8] |

## canvas route: cProfile of draw(), share by file, after (first run; native | Pyodide)

**projects-02_rangoli** (profiled draw 12.6 ms native, 46.8 ms Pyodide; 16010 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/sketch.py | 3.58 | 28 | 13.16 | 28 |
| funground/color.py | 1.45 | 12 | 7.49 | 16 |
| funground/pathops.py | 2.64 | 21 | 7.09 | 15 |
| funground/api.py | 1.07 | 9 | 4.71 | 10 |
| funground/geometry.py | 1.18 | 9 | 4.56 | 10 |
| funground/state.py | 0.86 | 7 | 3.10 | 7 |
| USER sketch | 0.66 | 5 | 1.96 | 4 |

**projects-06_kinetic_type** (profiled draw 65.3 ms native, 334.5 ms Pyodide; 165995 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/color.py | 18.67 | 29 | 109.16 | 33 |
| funground/vector.py | 15.09 | 23 | 81.69 | 24 |
| funground/noise.py | 12.34 | 19 | 52.54 | 16 |
| funground/sketch.py | 4.88 | 7 | 25.07 | 7 |
| funground/api.py | 3.86 | 6 | 19.23 | 6 |
| USER sketch | 3.85 | 6 | 16.81 | 5 |
| funground/state.py | 3.44 | 5 | 16.31 | 5 |

**text-09_text_dots** (profiled draw 25.9 ms native, 106.8 ms Pyodide; 50788 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/color.py | 7.74 | 30 | 35.31 | 33 |
| funground/sketch.py | 5.84 | 23 | 22.80 | 21 |
| funground/state.py | 3.56 | 14 | 13.39 | 13 |
| funground/geometry.py | 3.26 | 13 | 11.89 | 11 |
| funground/api.py | 2.77 | 11 | 10.93 | 10 |
| funground/typography.py | 0.68 | 3 | 3.62 | 3 |
| USER sketch | 0.70 | 3 | 2.89 | 3 |

**randomness-03_noise** (profiled draw 32.2 ms native, 111.2 ms Pyodide; 44718 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/color.py | 7.99 | 25 | 31.36 | 28 |
| funground/noise.py | 8.30 | 26 | 26.51 | 24 |
| funground/sketch.py | 5.38 | 17 | 18.35 | 16 |
| funground/state.py | 4.00 | 12 | 11.88 | 11 |
| funground/api.py | 2.52 | 8 | 9.32 | 8 |
| USER sketch | 1.15 | 4 | 3.50 | 3 |
| funground/shapes.py | 0.63 | 2 | 2.67 | 2 |

**sound-02_write_a_tune** (profiled draw 79.2 ms native, 162.8 ms Pyodide; 12270 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/synth.py | 73.94 | 93 | 144.60 | 89 |
| funground/sketch.py | 1.51 | 2 | 4.70 | 3 |
| funground/sound.py | 1.11 | 1 | 3.95 | 2 |
| USER sketch | 1.06 | 1 | 3.23 | 2 |
| funground/api.py | 0.70 | 1 | 2.49 | 2 |
| C/other | 0.05 | 0 | 1.20 | 1 |
| funground/ir.py | 0.26 | 0 | 1.14 | 1 |

**randomness-02_gaussian_and_choice** (profiled draw 21.6 ms native, 46.0 ms Pyodide; 24107 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/sketch.py | 5.71 | 26 | 11.82 | 26 |
| random.py | 3.59 | 17 | 8.54 | 19 |
| funground/state.py | 4.37 | 20 | 8.16 | 18 |
| funground/api.py | 3.25 | 15 | 7.89 | 17 |
| funground/color.py | 1.64 | 8 | 3.84 | 8 |
| USER sketch | 1.22 | 6 | 2.17 | 5 |
| funground/paint.py | 0.53 | 2 | 1.25 | 3 |

**studios-03_rhythm** (profiled draw 17.2 ms native, 71.2 ms Pyodide; 33309 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/ir.py | 6.88 | 40 | 33.03 | 46 |
| dataclasses.py | 2.67 | 16 | 14.10 | 20 |
| funground/typography.py | 0.82 | 5 | 5.30 | 7 |
| funground/marks.py | 1.31 | 8 | 4.97 | 7 |
| encoder.py | 2.27 | 13 | 3.97 | 6 |
| shim.py | 1.35 | 8 | 3.40 | 5 |
| funground/geometry.py | 0.64 | 4 | 2.30 | 3 |

**studios-05_text_as_geometry** (profiled draw 30.8 ms native, 75.9 ms Pyodide; 52222 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/ir.py | 13.05 | 42 | 36.97 | 49 |
| dataclasses.py | 4.39 | 14 | 12.73 | 17 |
| funground/renderers/cairo2d.py | 4.02 | 13 | 8.67 | 11 |
| funground/sketch.py | 1.53 | 5 | 3.50 | 5 |
| funground/pathops.py | 1.72 | 6 | 3.03 | 4 |
| encoder.py | 1.64 | 5 | 1.97 | 3 |
| funground/geometry.py | 0.75 | 2 | 1.87 | 2 |

**paths-06_outlines** (profiled draw 14.7 ms native, 30.9 ms Pyodide; 15634 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/pathops.py | 5.17 | 35 | 9.24 | 30 |
| funground/sketch.py | 2.41 | 16 | 5.64 | 18 |
| funground/geometry.py | 1.46 | 10 | 3.25 | 11 |
| funground/state.py | 1.47 | 10 | 3.14 | 10 |
| funground/color.py | 1.04 | 7 | 2.79 | 9 |
| funground/api.py | 1.00 | 7 | 2.00 | 6 |
| USER sketch | 0.51 | 3 | 0.94 | 3 |

**studios-06_poster_series** (profiled draw 10.2 ms native, 19.2 ms Pyodide; 9127 Python calls/frame)

| file | native ms | native % | Pyodide ms | Pyodide % |
|---|---|---|---|---|
| funground/surface.py | 2.26 | 22 | 4.70 | 25 |
| funground/marks.py | 1.82 | 18 | 3.61 | 19 |
| funground/sketch.py | 1.12 | 11 | 2.23 | 12 |
| funground/geometry.py | 0.77 | 8 | 1.60 | 8 |
| funground/state.py | 0.90 | 9 | 1.60 | 8 |
| funground/renderers/cairo2d.py | 0.69 | 7 | 0.93 | 5 |
| funground/api.py | 0.50 | 5 | 0.91 | 5 |


## postMessage of a frame, worker to page (ms, median of 12; latency = sent to received in the page, includes the clone/decode before onmessage)

| case | ops | JSON bytes | string: send / latency / page JSON.parse | object: send / latency | UTF-8 buffer (transferred): send / latency / decode+parse | flat Float64Array (transferred, 14 numbers per op): send / latency |
|---|---|---|---|---|---|---|
| projects-02_rangoli | 636 | 143,754 | 0.00 / 0.10 / 0.70 | 0.70 / 1.70 | 0.00 / 0.00 / 0.70 | 0.00 / 0.00 |
| projects-06_kinetic_type | 633 | 199,959 | 0.00 / 0.20 / 0.80 | 0.80 / 1.70 | 0.00 / 0.10 / 1.00 | 0.00 / 0.00 |
| text-09_text_dots | 507 | 203,383 | 0.00 / 0.20 / 0.90 | 0.90 / 1.90 | 0.00 / 0.10 / 1.10 | 0.00 / 0.10 |
| randomness-03_noise | 419 | 60,310 | 0.00 / 0.10 / 0.40 | 0.40 / 1.00 | 0.00 / 0.10 / 0.40 | 0.00 / 0.00 |
| sound-02_write_a_tune | 413 | 79,231 | 0.00 / 0.10 / 0.40 | 0.50 / 0.90 | 0.00 / 0.10 / 0.40 | 0.00 / 0.10 |
| randomness-02_gaussian_and_choice | 401 | 61,602 | 0.00 / 0.00 / 0.30 | 0.20 / 0.60 | 0.00 / 0.00 / 0.30 | 0.00 / 0.00 |
| studios-03_rhythm | 371 | 86,958 | 0.00 / 0.10 / 0.70 | 0.60 / 1.30 | 0.00 / 0.10 / 0.70 | 0.00 / 0.10 |
| studios-05_text_as_geometry | 290 | 61,333 | 0.00 / 0.00 / 0.20 | 0.20 / 0.50 | 0.00 / 0.00 / 0.20 | 0.00 / 0.00 |
| paths-06_outlines | 249 | 127,706 | 0.00 / 0.00 / 0.60 | 0.70 / 1.60 | 0.00 / 0.10 / 0.90 | 0.00 / 0.10 |
| studios-06_poster_series | 229 | 355,581 | 0.10 / 0.30 / 2.60 | 2.80 / 5.10 | 0.10 / 0.10 / 2.30 | 0.00 / 0.10 |


## Answers to S-143's open questions (Pyodide half)

**1. Do the native hotspot shares hold in Pyodide? Yes.** Per file, the cProfile share of `draw()` differs by at most about 7 points between native and Pyodide in 9 of 10 cases (the exception is `studios-03`, `typography.py` 10 | 20 %) (examples, native | Pyodide: `kinetic_type` color.py 28 | 34 %, vector.py 23 | 23 %, noise.py 19 | 15 %; `text_dots` color.py 30 | 34 %, sketch.py 23 | 21 %, state.py 14 | 12 %; `noise` color.py 25 | 30 %, noise.py 26 | 24 %; `sound-02` synth.py 93 | 87 %). Pyodide runs `draw()` 2.0 times slower than native on average (sum over the heavy cases; per case 1.3 to 3.8). The spread follows the kind of code: pure-Python code (colour, vector, noise, state, wrappers) is 2 to 3.8 times slower; code that spends its time in C extensions is 1.3 to 2 times (`sound-02`, `studios-03`, `poster_series`, pathops conversion). The Cairo render is 1.1 to 2.8 times native (mean 8.8 against 5.2 ms). Because the shares hold, a fix measured natively is a safe guide for Pyodide; the wall-clock gain is 2 to 3 times the native one for Python-bound sketches. The cProfile run itself is 3 to 6 times slower than the timer run in Pyodide for Python-bound cases, so only the shares were used.

What the four fixes did not reach, in the shares measured now (Pyodide, after; same order natively):

| remaining hotspot | where | share of `draw()` | note |
|---|---|---|---|
| colours from numbers | `color.py` `parse` -> `Color.__post_init__` -> `_component`, called from `sketch.py` `read_color` | 28 to 34 % in `kinetic_type`, `text_dots`, `noise`; 8 to 16 % elsewhere | S-145 caches colour **strings** only; `fill(r, g, b)`, grey numbers and tuples are still parsed and validated on every call (1895 parses per frame in `kinetic_type`) |
| Vector numbers | `vector.py` `_number`, `_is_number`, `__init__`, `copy` | 23 % of `kinetic_type` (12 000 `_number` calls a frame) | S-146 removed the ABC check; two Python calls per number remain |
| state copy | `state.py` `with_` | 5 to 14 % (`text_dots` 12 %, 513 calls a frame) | still builds a 30-field object per style call |
| Perlin noise | `noise.py` `__call__` | 15 to 24 % | pure Python, inherent |
| sound synthesis | `synth.py` | 87 to 93 % of `sound-02` | untouched; numpy would remove most of it |
| path conversion | `pathops.py` | 15 to 32 % of `rangoli`, `paths-06` | mostly inherent |
| glyph placement in the render | `typography.py` | 21 to 48 % of the Cairo render in `text_dots`, `kinetic_type`, `paths-06`, `poster_series` (was most of it before S-147) | the scaled outlines are cached, the translation per glyph per frame is not |

**2. What do `json.dumps`, the per-op dict building, `JSON.parse` and `drawFrame` cost?** Heavy mean, one frame, Pyodide: dict building (`op_to_jsonable`) 9.5 ms, the Text-outline and rounded-Rect extras 2.6 ms, `json.dumps` 5.7 ms (about 18 ms in all, 150 KB of JSON a frame on average, 415 ops: 23 microseconds an op to build and 14 to dump). Dict building plus extras is 68 % of the encode in Pyodide (63 % native; S-143 measured 70 to 80 % native before the fixes), `json.dumps` 32 % (37 % native). On the JavaScript side, as matrix means: `JSON.parse` 0.8 ms, the `drawFrame` call 0.6 to 0.8 ms, the message 0.2 ms: about 1.6 ms, 6 to 9 % of the Python encode. Per case the encode is at most 32 ms (`kinetic_type`), and 27 ms for `poster_series` whose 355 KB of glyph outlines are 15.6 ms of `json.dumps` alone. **The Canvas route's cost is still the Python encode** (unchanged by this sprint: `ir.py` is untouched), and it is now about as large as the Cairo render plus copy it replaces (Cairo render 8.8 plus copy 1.2 plus paint 0.3 against encode 18 to 25 plus JS 1.6, 1x). `drawFrame` rasterisation is not in these numbers (open problem 1).

**3. `postMessage`: the object or a transferred buffer?** Measured in the worker-to-page direction on the real last frame of each heavy case (`tools/run_s142.py --page harness/s148/prof.html`, 12 messages of each kind, one in flight at a time; median):

| payload | send call | received in page after | page-side decode | total to a usable array of ops |
|---|---|---|---|---|
| JSON string | 0.0 ms | 0.0 to 0.3 ms | `JSON.parse` 0.2 to 2.6 ms | 0.3 to 2.9 ms |
| parsed object (structured clone) | 0.2 to 2.8 ms | 0.5 to 5.1 ms | none | 0.5 to 5.1 ms |
| the JSON as a transferred UTF-8 `ArrayBuffer` | 0.0 to 0.1 ms | 0.0 to 0.1 ms | `TextDecoder` + `JSON.parse` 0.2 to 2.3 ms | same as the string |
| a transferred `Float64Array` of 14 numbers an op (a size stand-in, not a real encoding) | 0.0 ms | 0.0 to 0.1 ms | none | below 0.1 ms |

Sending the object is about twice as slow as sending the string and parsing it, and costs the worker as well as the page; the transferred buffer buys nothing over the string. A flat numeric buffer would remove both the message and the parse (1.5 ms of a 55 ms frame, under 3 %) but only if Python can produce it faster than it produces the dicts; that production cost was not measured (S-143's finding is that the cost is Python reading each op's attributes, which a binary format does not avoid). **Recommendation from the numbers: keep the JSON string; `postMessage` is not a cost worth designing around.** The first-frame cost (S-143 question 4) was not measured separately; boot is 7 to 9 s cold in every variant (table below).

Questions 5 and 6 of S-143, answered by what the runs showed: the bounded colour cache (`lru_cache(maxsize=512)`) lived across 13 cases in one interpreter in every run, with identical pixels; and the glyph-outline cache now helps the web path (`poster_series`: Cairo render 25.5 to 21.1 ms, Canvas encode 34.5 to 27.3 ms in Pyodide), as S-143 predicted.

## Observations

1. **The fixes are real and behaviour-preserving, and visible in Python time**: about a quarter off `draw()` in Python-bound sketches in both environments, a fifth off the Cairo render where text is involved. They do not show cleanly in the end-to-end browser numbers, because the end-to-end spread between repeats (2 to 3 times) is larger than the gain (10 to 30 %).
2. **The 16.7 ms budget is still missed by every heavy example in every variant** (fps 5 to 31 for the heavy loop examples, 57 to 62 fps for the light ones at 1x; Chrome Canvas gaussian reached 53 fps in one repeat set). At 1x the best heavy cases are `gaussian` and `studios-03` at about 15 to 27 ms. Reaching the budget for heavy sketches needs the Python halved again: numeric colours, Vector, state copy and the encode (a style table or flat tuples, S-143's E1) are the measured remaining items.
3. **Neither route wins everywhere, as in S-142.** Cairo-in-wasm: always correct, pays the per-pixel copy and render (about 11 ms at 1x, 16 ms at 2x for heavy sketches, 4.4 ms for a light sketch at 1x, 11.5 ms at 2x). Canvas: no pixel cost, pays the Python encode (18 to 25 ms for heavy sketches) and is approximate to S-135's tolerance, but a light sketch costs 1.3 ms at either scale.
4. **Painting in the worker made no measurable difference** (Cairo 1x heavy: 58.5 against 53.7 ms; Canvas 67.8 against 55.4 ms; the 5-repeat figures are 52.0 against 51.4 and 66.7 against 66.6). The worker variants keep the page free; they are not faster.
5. **First load** (3 repeats each, cold profile, real network): Cairo route 6.9 to 8.6 s to the last boot step, first frame 7.5 to 9.4 s; Canvas route 7.4 to 9.0 s (one 13.4 s outlier) and 8.2 to 9.9 s (one 14.7 s). `funground.zip` is 265,071 bytes (S-142: 263,609). Totals: 13.94 MB Cairo, 13.45 MB Canvas, as before.

## Noise (stated plainly)

The maintainer's own Chrome and other applications were running on this 8 GB machine. For the same configuration and case the median end-to-end time differed between repeats by 1.5 to 3 times: at 1x with page painting, Cairo `rangoli` 21.4 to 39.6 ms, `kinetic_type` 42.7 to 84.2 ms, `noise` 20.2 to 88.4 ms, `sound-02` 95 to 370 ms; Canvas `gaussian` 14.9 to 34.5 ms, `text_dots` 37.0 to 79.8 ms, `kinetic_type` 55.0 to 126.4 ms (5 repeats, "Spread" tables below). The spread is as large as in S-142 and, in the first three repeats, Canvas page-painting cases were sometimes much faster than in S-142 (`gaussian` 44.2 to 15.1 ms) and not in the later ones. Therefore:

- Any change under about 25 % in a browser table is noise unless it repeats in the 5-repeat set and the native column agrees. In this report that leaves: the native column (steadier: -14 % Cairo, -11 % IR, heavy mean, 1x), the Python-only profile section, and the Cairo page-painting rows (-16 to -19 % at 1x). The worker rows and every 2x row should be read as unchanged.
- The "before" numbers are S-142's own (a different, busier day); the back-to-back Python comparison is the fair one.
- Medians, not means, throughout; the group tables are means of per-case medians, so one outlier case (`sound-02`, 5 fps) weighs about a tenth.
- `other` can be slightly negative in the profile tables: it is the difference of three medians.

## Open problems

1. **Headless Chrome, no GPU, no vsync**: rasterisation and scan-out are not in any number (S-142 open problem 1, unchanged). The Canvas route's `paint` is a lower bound.
2. **Noisy host.** A quiet machine, a CPU-pinned run and 10 or more repeats would settle the sub-25 % questions; not done. Two more repeats than the brief asked for were run to show the spread.
3. **One browser, one machine** (Chrome 154, one laptop). Firefox, Safari, Edge, battery power and background-tab throttling were not tested.
4. **2x pixels not checked** (no goldens at 2x); premultiplied alpha not handled in the Cairo copy (transparent canvases need the un-premultiply).
5. **The funground tree moved during the session.** The bench is `69d989c` (S-147). `82af9bf` also carries S-149 (`Path.translated`, a `typography.py` change) and doc commits; not measured.
6. **Profile caveats.** cProfile inflates Python 3 to 6 times in Pyodide; shares only. Two runs per cell for the before/after pairs. For the script cases (`studios-03`, `-05`) the profile covers the whole run, and on the Canvas route the encode too (hence `ir.py`, `dataclasses.py` and `encoder.py` at 40 to 70 % in those two). `sound-02` is `synth.py` almost entirely.
7. **`postMessage` test is a stand-in for the binary case.** The `Float64Array` has the size of 14 numbers an op, not a real encoding; the Python cost of producing a flat buffer was not measured (S-143 prototype E2 suggests it is not much cheaper than the dicts natively).
8. **First-frame and cold-cache costs** (S-143 question 4) not measured separately; JS decode of a style-table format not measured; memory of the two routes not measured.
9. **Candidate stories from the measured remainder** (for the main session, not decided here): a numeric-colour fast path or cache in `Color.parse` (up to 34 % of `draw()` in three heavy sketches); a cheaper `Vector` construction; `GraphicsState.with_`; glyph translation per frame in the render and in the encode (outlines as shared data plus an offset); a style table or flat tuple IR (S-143 E1) since the encode is now the largest route-specific cost; numpy for `synth.py:find_pitch`; the wasm-to-JS pixel copy at 2x.
10. **A Canvas-only route still needs `ink_bounds`** for the marks vocabulary (three of ten heavy examples; S-142 finding, unchanged).

## Files

Harness: `harness/s142/` (unchanged except that its dist is built from `fg_s148`), `harness/s148/` (`prof_shim.py`, `prof_worker.js`, `prof.html`). Tools: `tools/build_s142_bundle.py`, `run_s142.py` (`--page`), `s142_native.py`, `s142_pixels.py`, `s142_report.py` (`REPEATS`), `s148_prof_native.py`, `s148_report.py` (`tools/s148_report.py > ...tables_ba.md`; `--more` for 5 repeats; `--prof`). Raw results in `results_s148/` (git-ignored): `browser-<route>-<where>-<scale>x[.r2 to .r5].json`, `native-<route>-<scale>x[.r2 to .r5].json`, `prof-native[-before][2]-<route>-1x.json`, `prof[-before][2]-browser-<route>.json`, `pixels.json`, `snaps/`, `tables*.md`.

Re-run: build the source (`git -C C:/Projects/playground-0.2 archive HEAD funground | tar -x -C <scratch>/fg_s148`), `build_s142_bundle.py`, then `run_s142.py --route cairo|canvas --where main|worker [--dpr 2] [--no-check] [--name ...]`, `s142_native.py`, `s142_pixels.py`, `s148_prof_native.py --route ...`, `run_s142.py --route ... --where worker --page harness/s148/prof.html --no-check --name prof-browser-<route>`, `s148_report.py`.


# Appendix A: before -> after, 3 repeats (the S-142 matrix as specified)

### Before (S-142) -> after (S-148): mean over the cases of the per-case medians, ms (ratio after / before)

| group | scale | route | draw() | py other | render | encode | wasm copy | message | parse | paint | end to end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| heavy (10) | 1x | native Cairo | 15.5 -> 13.2 (0.85) | 0.1 -> 0.1 (0.95) | 5.6 -> 4.7 (0.83) | 0.0 -> 0.0 (-) | 0.2 -> 0.2 (0.94) | - -> - (-) | - -> - (-) | - -> - (-) | 21.7 -> 18.7 (0.86) |
| heavy (10) | 1x | Chrome Cairo, page paints | 46.8 -> 39.1 (0.83) | 0.4 -> 0.4 (0.97) | 13.6 -> 11.6 (0.85) | 0.0 -> 0.0 (-) | 1.4 -> 1.3 (0.94) | 0.1 -> 0.2 (2.22) | - -> - (-) | 0.3 -> 0.3 (1.03) | 63.8 -> 53.7 (0.84) |
| heavy (10) | 1x | Chrome Cairo, worker paints | 43.9 -> 43.1 (0.98) | 0.3 -> 0.4 (1.13) | 12.0 -> 12.5 (1.04) | 0.0 -> 0.0 (-) | 1.2 -> 1.3 (1.07) | 0.2 -> 0.1 (0.53) | - -> - (-) | 0.3 -> 0.3 (1.00) | 58.9 -> 58.5 (0.99) |
| heavy (10) | 1x | native IR (encode only) | 17.4 -> 14.9 (0.86) | 0.1 -> 0.1 (0.85) | 0.0 -> 0.0 (-) | 11.1 -> 10.2 (0.92) | 0.0 -> 0.0 (-) | - -> - (-) | - -> - (-) | - -> - (-) | 29.0 -> 25.9 (0.89) |
| heavy (10) | 1x | Chrome Canvas, page paints | 51.1 -> 30.9 (0.60) | 0.4 -> 0.3 (0.70) | 0.0 -> 0.0 (-) | 33.9 -> 21.3 (0.63) | - -> - (-) | 0.3 -> 0.2 (0.77) | 1.1 -> 0.7 (0.60) | 0.8 -> 0.5 (0.65) | 89.0 -> 55.4 (0.62) |
| heavy (10) | 1x | Chrome Canvas, worker paints | 43.4 -> 39.1 (0.90) | 0.3 -> 0.3 (1.06) | 0.0 -> 0.0 (-) | 24.9 -> 25.1 (1.01) | - -> - (-) | 0.2 -> 0.1 (0.40) | 0.7 -> 0.8 (1.12) | 0.7 -> 0.8 (1.16) | 71.4 -> 67.8 (0.95) |
| heavy (10) | 2x | native Cairo | 16.8 -> 13.9 (0.82) | 0.1 -> 0.1 (0.72) | 8.5 -> 6.6 (0.77) | 0.0 -> 0.0 (-) | 1.1 -> 1.1 (0.94) | - -> - (-) | - -> - (-) | - -> - (-) | 27.9 -> 22.6 (0.81) |
| heavy (10) | 2x | Chrome Cairo, page paints | 50.3 -> 33.1 (0.66) | 0.4 -> 0.3 (0.68) | 18.0 -> 12.9 (0.71) | 0.0 -> 0.0 (-) | 4.5 -> 3.8 (0.85) | 0.2 -> 0.1 (0.53) | - -> - (-) | 1.3 -> 1.3 (0.98) | 75.3 -> 53.1 (0.71) |
| heavy (10) | 2x | Chrome Cairo, worker paints | 43.7 -> 45.4 (1.04) | 0.3 -> 0.4 (1.17) | 15.0 -> 17.5 (1.17) | 0.0 -> 0.0 (-) | 3.8 -> 4.7 (1.23) | 0.2 -> 0.1 (0.65) | - -> - (-) | 1.3 -> 1.6 (1.23) | 67.2 -> 72.5 (1.08) |
| heavy (10) | 2x | native IR (encode only) | 18.1 -> 14.5 (0.80) | 0.1 -> 0.1 (0.78) | 0.0 -> 0.0 (-) | 11.9 -> 10.9 (0.91) | 0.0 -> 0.0 (-) | - -> - (-) | - -> - (-) | - -> - (-) | 30.7 -> 26.1 (0.85) |
| heavy (10) | 2x | Chrome Canvas, page paints | 42.7 -> 40.8 (0.96) | 0.3 -> 0.4 (1.24) | 0.0 -> 0.0 (-) | 26.1 -> 26.8 (1.02) | - -> - (-) | 0.3 -> 0.3 (0.87) | 0.8 -> 0.9 (1.14) | 0.6 -> 0.7 (1.19) | 74.3 -> 72.4 (0.97) |
| heavy (10) | 2x | Chrome Canvas, worker paints | 42.9 -> 34.5 (0.81) | 0.3 -> 0.3 (0.84) | 0.0 -> 0.0 (-) | 24.5 -> 21.7 (0.89) | - -> - (-) | 0.1 -> 0.1 (0.79) | 0.7 -> 0.7 (0.95) | 0.8 -> 0.7 (0.91) | 71.8 -> 61.5 (0.86) |
| typical (3) | 1x | native Cairo | 0.1 -> 0.1 (0.63) | 0.0 -> 0.0 (0.75) | 1.4 -> 0.8 (0.58) | 0.0 -> 0.0 (-) | 0.1 -> 0.1 (0.94) | - -> - (-) | - -> - (-) | - -> - (-) | 1.7 -> 1.0 (0.60) |
| typical (3) | 1x | Chrome Cairo, page paints | 0.5 -> 0.4 (0.86) | 0.2 -> 0.2 (1.00) | 3.4 -> 2.9 (0.85) | 0.0 -> 0.0 (-) | 1.9 -> 1.6 (0.88) | 0.1 -> 0.2 (2.00) | - -> - (-) | 0.2 -> 0.2 (1.00) | 7.0 -> 6.2 (0.89) |
| typical (3) | 1x | native IR (encode only) | 0.1 -> 0.0 (0.65) | 0.0 -> 0.0 (1.18) | 0.0 -> 0.0 (-) | 1.3 -> 1.0 (0.76) | 0.0 -> 0.0 (-) | - -> - (-) | - -> - (-) | - -> - (-) | 1.4 -> 1.1 (0.76) |
| typical (3) | 1x | Chrome Canvas, page paints | 0.5 -> 0.3 (0.64) | 0.2 -> 0.2 (1.00) | 0.0 -> 0.0 (-) | 4.1 -> 3.3 (0.82) | - -> - (-) | 0.3 -> 0.2 (0.75) | 0.2 -> 0.1 (0.80) | 0.1 -> 0.1 (1.00) | 6.0 -> 4.8 (0.81) |
| typical (3) | 2x | native Cairo | 0.2 -> 0.1 (0.51) | 0.1 -> 0.0 (0.66) | 1.6 -> 1.0 (0.66) | 0.0 -> 0.0 (-) | 1.1 -> 1.0 (0.91) | - -> - (-) | - -> - (-) | - -> - (-) | 3.3 -> 2.5 (0.74) |
| typical (3) | 2x | Chrome Cairo, page paints | 0.5 -> 0.4 (0.69) | 0.2 -> 0.2 (1.00) | 5.2 -> 4.5 (0.87) | 0.0 -> 0.0 (-) | 5.3 -> 4.9 (0.93) | 0.2 -> 0.1 (0.67) | - -> - (-) | 1.6 -> 1.2 (0.73) | 14.1 -> 13.1 (0.93) |
| typical (3) | 2x | native IR (encode only) | 0.1 -> 0.0 (0.76) | 0.0 -> 0.0 (1.36) | 0.0 -> 0.0 (-) | 1.1 -> 1.0 (0.86) | 0.0 -> 0.0 (-) | - -> - (-) | - -> - (-) | - -> - (-) | 1.2 -> 1.1 (0.87) |
| typical (3) | 2x | Chrome Canvas, page paints | 0.5 -> 0.4 (0.79) | 0.2 -> 0.2 (1.00) | 0.0 -> 0.0 (-) | 4.2 -> 3.9 (0.93) | - -> - (-) | 0.2 -> 0.1 (0.57) | 0.1 -> 0.2 (1.50) | 0.1 -> 0.1 (1.00) | 6.0 -> 5.6 (0.94) |

### End to end per case, median of 3, ms: before -> after (ratio)

### 1x

| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) |
|---|---|---|---|---|---|---|
| projects-02_rangoli | 8.9 -> 9.1 (1.02) | 39.7 -> 38.0 (0.96) | 32.9 -> 32.0 (0.97) | 12.1 -> 11.9 (0.99) | 57.1 -> 45.6 (0.80) | 44.5 -> 48.8 (1.10) |
| projects-06_kinetic_type | 36.8 -> 27.6 (0.75) | 118.4 -> 77.0 (0.65) | 110.9 -> 169.8 (1.53) | 43.3 -> 34.7 (0.80) | 153.5 -> 110.4 (0.72) | 128.9 -> 129.0 (1.00) |
| text-09_text_dots | 15.7 -> 13.9 (0.88) | 53.6 -> 46.7 (0.87) | 55.6 -> 56.2 (1.01) | 23.7 -> 20.4 (0.86) | 157.3 -> 72.0 (0.46) | 68.8 -> 75.0 (1.09) |
| randomness-03_noise | 17.7 -> 11.1 (0.63) | 46.4 -> 33.9 (0.73) | 39.4 -> 38.6 (0.98) | 20.0 -> 14.9 (0.75) | 61.3 -> 47.5 (0.77) | 46.3 -> 48.5 (1.05) |
| sound-02_write_a_tune | 60.7 -> 66.3 (1.09) | 186.8 -> 181.8 (0.97) | 175.9 -> 142.8 (0.81) | 92.1 -> 87.6 (0.95) | 197.9 -> 115.8 (0.59) | 196.6 -> 178.2 (0.91) |
| randomness-02_gaussian_and_choice | 15.2 -> 7.8 (0.52) | 33.6 -> 27.2 (0.81) | 32.6 -> 25.1 (0.77) | 19.3 -> 12.4 (0.64) | 44.2 -> 15.1 (0.34) | 41.0 -> 34.3 (0.84) |
| studios-03_rhythm | 6.6 -> 6.7 (1.01) | 27.6 -> 23.9 (0.87) | 26.2 -> 22.3 (0.85) | 11.8 -> 14.9 (1.27) | 35.6 -> 15.8 (0.44) | 34.8 -> 30.4 (0.87) |
| studios-05_text_as_geometry | 14.0 -> 13.5 (0.97) | 28.6 -> 29.1 (1.02) | 27.8 -> 29.4 (1.06) | 12.2 -> 13.0 (1.06) | 38.4 -> 18.6 (0.48) | 34.1 -> 36.3 (1.06) |
| paths-06_outlines | 15.6 -> 12.0 (0.77) | 46.5 -> 36.0 (0.77) | 41.9 -> 30.6 (0.73) | 19.0 -> 23.8 (1.25) | 58.6 -> 49.0 (0.84) | 51.0 -> 37.0 (0.73) |
| studios-06_poster_series | 25.8 -> 19.3 (0.75) | 56.4 -> 43.3 (0.77) | 46.0 -> 38.5 (0.84) | 36.6 -> 24.9 (0.68) | 86.3 -> 64.6 (0.75) | 68.4 -> 61.0 (0.89) |
| s1-05_text | 4.7 -> 2.5 (0.53) | 11.5 -> 9.9 (0.86) | 11.8 -> 10.0 (0.85) | 4.0 -> 3.0 (0.74) | 14.8 -> 11.9 (0.80) | 12.5 -> 10.7 (0.86) |
| s1-06_animation | 0.2 -> 0.3 (1.52) | 4.8 -> 4.4 (0.92) | 4.5 -> 4.3 (0.96) | 0.1 -> 0.1 (1.21) | 1.6 -> 1.3 (0.81) | 1.7 -> 1.6 (0.94) |
| s1-07_bounce | 0.2 -> 0.3 (1.52) | 4.7 -> 4.3 (0.91) | 3.5 -> 4.3 (1.23) | 0.1 -> 0.1 (1.48) | 1.5 -> 1.3 (0.87) | 1.6 -> 1.6 (1.00) |

### 2x

| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) |
|---|---|---|---|---|---|---|
| projects-02_rangoli | 12.9 -> 12.6 (0.98) | 51.9 -> 25.1 (0.48) | 44.6 -> 47.7 (1.07) | 12.9 -> 12.0 (0.93) | 49.7 -> 50.8 (1.02) | 42.3 -> 42.1 (1.00) |
| projects-06_kinetic_type | 39.5 -> 29.2 (0.74) | 146.7 -> 48.7 (0.33) | 123.2 -> 113.0 (0.92) | 49.7 -> 34.8 (0.70) | 140.6 -> 117.0 (0.83) | 127.2 -> 105.2 (0.83) |
| text-09_text_dots | 19.8 -> 15.8 (0.80) | 72.8 -> 28.4 (0.39) | 58.7 -> 104.1 (1.77) | 36.6 -> 21.1 (0.58) | 75.6 -> 72.8 (0.96) | 72.9 -> 59.6 (0.82) |
| randomness-03_noise | 16.8 -> 11.6 (0.69) | 53.4 -> 27.5 (0.51) | 50.7 -> 54.4 (1.07) | 19.4 -> 15.8 (0.82) | 49.2 -> 69.4 (1.41) | 49.2 -> 42.3 (0.86) |
| sound-02_write_a_tune | 82.2 -> 77.7 (0.95) | 197.5 -> 188.7 (0.96) | 185.6 -> 197.4 (1.06) | 92.8 -> 83.9 (0.90) | 186.3 -> 188.4 (1.01) | 199.3 -> 174.5 (0.88) |
| randomness-02_gaussian_and_choice | 19.3 -> 11.7 (0.60) | 40.1 -> 32.2 (0.80) | 35.4 -> 35.2 (0.99) | 16.7 -> 11.1 (0.67) | 42.9 -> 35.7 (0.83) | 37.2 -> 28.7 (0.77) |
| studios-03_rhythm | 14.9 -> 13.8 (0.93) | 35.2 -> 37.3 (1.06) | 36.9 -> 33.2 (0.90) | 9.1 -> 12.2 (1.34) | 30.5 -> 33.7 (1.10) | 28.5 -> 28.4 (1.00) |
| studios-05_text_as_geometry | 14.9 -> 18.2 (1.22) | 37.2 -> 36.9 (0.99) | 32.5 -> 36.1 (1.11) | 11.8 -> 15.7 (1.33) | 32.5 -> 38.7 (1.19) | 33.9 -> 35.6 (1.05) |
| paths-06_outlines | 26.6 -> 16.1 (0.61) | 54.5 -> 45.8 (0.84) | 46.4 -> 45.2 (0.97) | 22.2 -> 16.3 (0.74) | 57.7 -> 47.4 (0.82) | 52.5 -> 40.6 (0.77) |
| studios-06_poster_series | 32.5 -> 19.4 (0.60) | 63.3 -> 60.4 (0.95) | 57.5 -> 58.8 (1.02) | 35.5 -> 38.3 (1.08) | 78.2 -> 70.5 (0.90) | 74.8 -> 58.4 (0.78) |
| s1-05_text | 5.5 -> 3.6 (0.65) | 19.6 -> 15.0 (0.77) | 15.1 -> 17.2 (1.14) | 3.6 -> 3.1 (0.86) | 15.3 -> 14.0 (0.92) | 14.4 -> 12.1 (0.84) |
| s1-06_animation | 1.9 -> 1.9 (0.99) | 11.6 -> 11.5 (0.99) | 11.9 -> 13.1 (1.10) | 0.1 -> 0.1 (0.92) | 1.3 -> 1.5 (1.15) | 1.8 -> 1.5 (0.83) |
| s1-07_bounce | 2.6 -> 1.9 (0.75) | 11.1 -> 12.7 (1.14) | 11.9 -> 13.7 (1.15) | 0.0 -> 0.1 (1.95) | 1.4 -> 1.4 (1.00) | 1.5 -> 1.5 (1.00) |

### Cairo (page paints) / Canvas (page paints) end-to-end ratio, before -> after

| case | 1x before | 1x after | 2x before | 2x after |
|---|---|---|---|---|
| projects-02_rangoli | 0.70 | 0.83 | 1.04 | 0.49 |
| projects-06_kinetic_type | 0.77 | 0.70 | 1.04 | 0.42 |
| text-09_text_dots | 0.34 | 0.65 | 0.96 | 0.39 |
| randomness-03_noise | 0.76 | 0.71 | 1.09 | 0.40 |
| sound-02_write_a_tune | 0.94 | 1.57 | 1.06 | 1.00 |
| randomness-02_gaussian_and_choice | 0.76 | 1.80 | 0.93 | 0.90 |
| studios-03_rhythm | 0.78 | 1.51 | 1.15 | 1.11 |
| studios-05_text_as_geometry | 0.74 | 1.56 | 1.14 | 0.95 |
| paths-06_outlines | 0.79 | 0.73 | 0.94 | 0.97 |
| studios-06_poster_series | 0.65 | 0.67 | 0.81 | 0.86 |
| s1-05_text | 0.78 | 0.83 | 1.28 | 1.07 |
| s1-06_animation | 3.00 | 3.38 | 8.92 | 7.67 |
| s1-07_bounce | 3.13 | 3.31 | 7.93 | 9.07 |

Mean ratio heavy: 1x before 0.72, 1x after 1.07, 2x before 1.02, 2x after 0.75

Mean ratio typical: 1x before 2.30, 1x after 2.51, 2x before 6.04, 2x after 5.94

### Spread of the 3 repeats, end-to-end medians (min - max), page paints, 1x, after

| case | Cairo | Canvas |
|---|---|---|
| projects-02_rangoli | 37.8 - 39.6 | 22.3 - 46.5 |
| projects-06_kinetic_type | 73.3 - 84.2 | 55.0 - 126.4 |
| text-09_text_dots | 44.5 - 76.6 | 37.0 - 79.8 |
| randomness-03_noise | 31.6 - 88.4 | 28.1 - 56.1 |
| sound-02_write_a_tune | 175.1 - 370.3 | 103.3 - 175.5 |
| randomness-02_gaussian_and_choice | 24.5 - 27.5 | 14.9 - 33.1 |
| studios-03_rhythm | 22.8 - 25.0 | 15.1 - 32.9 |
| studios-05_text_as_geometry | 23.8 - 41.1 | 16.9 - 40.2 |
| paths-06_outlines | 33.3 - 36.1 | 20.6 - 50.2 |
| studios-06_poster_series | 43.1 - 43.4 | 31.1 - 73.6 |
| s1-05_text | 9.5 - 10.7 | 6.0 - 13.7 |
| s1-06_animation | 3.9 - 4.7 | 1.2 - 1.8 |
| s1-07_bounce | 4.1 - 4.6 | 1.2 - 1.4 |


# Appendix B: the same with 5 repeats (supplementary)

### Before (S-142) -> after (S-148): mean over the cases of the per-case medians, ms (ratio after / before)

| group | scale | route | draw() | py other | render | encode | wasm copy | message | parse | paint | end to end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| heavy (10) | 1x | native Cairo | 15.5 -> 12.9 (0.83) | 0.1 -> 0.1 (0.85) | 5.6 -> 4.6 (0.82) | 0.0 -> 0.0 (-) | 0.2 -> 0.2 (0.91) | - -> - (-) | - -> - (-) | - -> - (-) | 21.7 -> 18.2 (0.84) |
| heavy (10) | 1x | Chrome Cairo, page paints | 46.8 -> 37.5 (0.80) | 0.4 -> 0.3 (0.86) | 13.6 -> 10.8 (0.79) | 0.0 -> 0.0 (-) | 1.4 -> 1.2 (0.86) | 0.1 -> 0.2 (2.00) | - -> - (-) | 0.3 -> 0.3 (0.87) | 63.8 -> 51.4 (0.81) |
| heavy (10) | 1x | Chrome Cairo, worker paints | 43.9 -> 38.2 (0.87) | 0.3 -> 0.3 (1.00) | 12.0 -> 10.5 (0.87) | 0.0 -> 0.0 (-) | 1.2 -> 1.2 (0.99) | 0.2 -> 0.1 (0.59) | - -> - (-) | 0.3 -> 0.3 (1.00) | 58.9 -> 52.0 (0.88) |
| heavy (10) | 1x | native IR (encode only) | 17.4 -> 14.8 (0.85) | 0.1 -> 0.1 (0.81) | 0.0 -> 0.0 (-) | 11.1 -> 10.0 (0.90) | 0.0 -> 0.0 (-) | - -> - (-) | - -> - (-) | - -> - (-) | 29.0 -> 25.3 (0.87) |
| heavy (10) | 1x | Chrome Canvas, page paints | 51.1 -> 37.3 (0.73) | 0.4 -> 0.3 (0.75) | 0.0 -> 0.0 (-) | 33.9 -> 24.8 (0.73) | - -> - (-) | 0.3 -> 0.2 (0.77) | 1.1 -> 0.8 (0.68) | 0.8 -> 0.6 (0.73) | 89.0 -> 66.6 (0.75) |
| heavy (10) | 1x | Chrome Canvas, worker paints | 43.4 -> 38.5 (0.89) | 0.3 -> 0.3 (0.94) | 0.0 -> 0.0 (-) | 24.9 -> 24.8 (1.00) | - -> - (-) | 0.2 -> 0.1 (0.55) | 0.7 -> 0.8 (1.07) | 0.7 -> 0.8 (1.12) | 71.4 -> 66.7 (0.93) |
| heavy (10) | 2x | native Cairo | 16.8 -> 13.8 (0.82) | 0.1 -> 0.1 (0.70) | 8.5 -> 6.5 (0.76) | 0.0 -> 0.0 (-) | 1.1 -> 1.0 (0.92) | - -> - (-) | - -> - (-) | - -> - (-) | 27.9 -> 22.1 (0.79) |
| heavy (10) | 2x | Chrome Cairo, page paints | 50.3 -> 40.1 (0.80) | 0.4 -> 0.3 (0.81) | 18.0 -> 15.5 (0.86) | 0.0 -> 0.0 (-) | 4.5 -> 4.4 (0.97) | 0.2 -> 0.2 (0.89) | - -> - (-) | 1.3 -> 1.4 (1.08) | 75.3 -> 63.7 (0.85) |
| heavy (10) | 2x | Chrome Cairo, worker paints | 43.7 -> 40.2 (0.92) | 0.3 -> 0.4 (1.03) | 15.0 -> 15.7 (1.05) | 0.0 -> 0.0 (-) | 3.8 -> 4.5 (1.19) | 0.2 -> 0.1 (0.60) | - -> - (-) | 1.3 -> 1.4 (1.14) | 67.2 -> 64.5 (0.96) |
| heavy (10) | 2x | native IR (encode only) | 18.1 -> 14.7 (0.82) | 0.1 -> 0.1 (0.72) | 0.0 -> 0.0 (-) | 11.9 -> 10.7 (0.90) | 0.0 -> 0.0 (-) | - -> - (-) | - -> - (-) | - -> - (-) | 30.7 -> 26.2 (0.85) |
| heavy (10) | 2x | Chrome Canvas, page paints | 42.7 -> 38.3 (0.90) | 0.3 -> 0.3 (1.10) | 0.0 -> 0.0 (-) | 26.1 -> 25.5 (0.97) | - -> - (-) | 0.3 -> 0.2 (0.50) | 0.8 -> 0.8 (1.07) | 0.6 -> 0.7 (1.08) | 74.3 -> 68.3 (0.92) |
| heavy (10) | 2x | Chrome Canvas, worker paints | 42.9 -> 36.5 (0.85) | 0.3 -> 0.3 (0.88) | 0.0 -> 0.0 (-) | 24.5 -> 23.0 (0.94) | - -> - (-) | 0.1 -> 0.1 (0.79) | 0.7 -> 0.8 (1.04) | 0.8 -> 0.7 (0.97) | 71.8 -> 64.2 (0.89) |
| typical (3) | 1x | native Cairo | 0.1 -> 0.1 (0.64) | 0.0 -> 0.0 (0.75) | 1.4 -> 0.9 (0.65) | 0.0 -> 0.0 (-) | 0.1 -> 0.1 (0.94) | - -> - (-) | - -> - (-) | - -> - (-) | 1.7 -> 1.1 (0.64) |
| typical (3) | 1x | Chrome Cairo, page paints | 0.5 -> 0.4 (0.86) | 0.2 -> 0.2 (1.00) | 3.4 -> 2.7 (0.80) | 0.0 -> 0.0 (-) | 1.9 -> 1.6 (0.86) | 0.1 -> 0.2 (2.00) | - -> - (-) | 0.2 -> 0.2 (1.00) | 7.0 -> 5.8 (0.83) |
| typical (3) | 1x | native IR (encode only) | 0.1 -> 0.0 (0.66) | 0.0 -> 0.0 (1.23) | 0.0 -> 0.0 (-) | 1.3 -> 1.0 (0.77) | 0.0 -> 0.0 (-) | - -> - (-) | - -> - (-) | - -> - (-) | 1.4 -> 1.1 (0.78) |
| typical (3) | 1x | Chrome Canvas, page paints | 0.5 -> 0.3 (0.71) | 0.2 -> 0.2 (1.00) | 0.0 -> 0.0 (-) | 4.1 -> 3.6 (0.88) | - -> - (-) | 0.3 -> 0.2 (0.75) | 0.2 -> 0.2 (1.00) | 0.1 -> 0.1 (1.00) | 6.0 -> 5.1 (0.86) |
| typical (3) | 2x | native Cairo | 0.2 -> 0.1 (0.49) | 0.1 -> 0.0 (0.65) | 1.6 -> 1.0 (0.65) | 0.0 -> 0.0 (-) | 1.1 -> 1.0 (0.91) | - -> - (-) | - -> - (-) | - -> - (-) | 3.3 -> 2.5 (0.74) |
| typical (3) | 2x | Chrome Cairo, page paints | 0.5 -> 0.4 (0.75) | 0.2 -> 0.2 (1.00) | 5.2 -> 4.6 (0.88) | 0.0 -> 0.0 (-) | 5.3 -> 5.4 (1.02) | 0.2 -> 0.2 (1.00) | - -> - (-) | 1.6 -> 1.6 (1.02) | 14.1 -> 13.3 (0.95) |
| typical (3) | 2x | native IR (encode only) | 0.1 -> 0.1 (0.92) | 0.0 -> 0.0 (1.33) | 0.0 -> 0.0 (-) | 1.1 -> 1.4 (1.21) | 0.0 -> 0.0 (-) | - -> - (-) | - -> - (-) | - -> - (-) | 1.2 -> 1.5 (1.20) |
| typical (3) | 2x | Chrome Canvas, page paints | 0.5 -> 0.3 (0.71) | 0.2 -> 0.2 (1.00) | 0.0 -> 0.0 (-) | 4.2 -> 3.4 (0.81) | - -> - (-) | 0.2 -> 0.1 (0.43) | 0.1 -> 0.2 (1.25) | 0.1 -> 0.1 (1.00) | 6.0 -> 5.0 (0.83) |

### End to end per case, median of 3, ms: before -> after (ratio)

### 1x

| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) |
|---|---|---|---|---|---|---|
| projects-02_rangoli | 8.9 -> 9.1 (1.02) | 39.7 -> 38.0 (0.96) | 32.9 -> 34.4 (1.05) | 12.1 -> 11.8 (0.98) | 57.1 -> 46.5 (0.81) | 44.5 -> 43.9 (0.99) |
| projects-06_kinetic_type | 36.8 -> 25.7 (0.70) | 118.4 -> 77.0 (0.65) | 110.9 -> 97.2 (0.88) | 43.3 -> 33.2 (0.77) | 153.5 -> 111.3 (0.73) | 128.9 -> 118.6 (0.92) |
| text-09_text_dots | 15.7 -> 13.0 (0.83) | 53.6 -> 44.5 (0.83) | 55.6 -> 46.2 (0.83) | 23.7 -> 20.1 (0.85) | 157.3 -> 64.7 (0.41) | 68.8 -> 75.0 (1.09) |
| randomness-03_noise | 17.7 -> 10.2 (0.58) | 46.4 -> 31.6 (0.68) | 39.4 -> 38.6 (0.98) | 20.0 -> 14.7 (0.73) | 61.3 -> 44.4 (0.72) | 46.3 -> 48.5 (1.05) |
| sound-02_write_a_tune | 60.7 -> 66.3 (1.09) | 186.8 -> 175.1 (0.94) | 175.9 -> 161.5 (0.92) | 92.1 -> 87.6 (0.95) | 197.9 -> 175.5 (0.89) | 196.6 -> 178.2 (0.91) |
| randomness-02_gaussian_and_choice | 15.2 -> 7.8 (0.52) | 33.6 -> 24.5 (0.73) | 32.6 -> 25.1 (0.77) | 19.3 -> 12.4 (0.64) | 44.2 -> 32.2 (0.73) | 41.0 -> 34.3 (0.84) |
| studios-03_rhythm | 6.6 -> 7.1 (1.08) | 27.6 -> 22.8 (0.83) | 26.2 -> 23.3 (0.89) | 11.8 -> 13.6 (1.15) | 35.6 -> 32.2 (0.90) | 34.8 -> 31.9 (0.92) |
| studios-05_text_as_geometry | 14.0 -> 11.5 (0.82) | 28.6 -> 23.8 (0.83) | 27.8 -> 28.4 (1.02) | 12.2 -> 13.0 (1.06) | 38.4 -> 38.0 (0.99) | 34.1 -> 36.3 (1.06) |
| paths-06_outlines | 15.6 -> 12.0 (0.77) | 46.5 -> 33.3 (0.72) | 41.9 -> 30.6 (0.73) | 19.0 -> 21.2 (1.11) | 58.6 -> 49.0 (0.84) | 51.0 -> 38.9 (0.76) |
| studios-06_poster_series | 25.8 -> 19.5 (0.75) | 56.4 -> 43.1 (0.76) | 46.0 -> 34.8 (0.76) | 36.6 -> 25.1 (0.68) | 86.3 -> 71.8 (0.83) | 68.4 -> 61.0 (0.89) |
| s1-05_text | 4.7 -> 2.7 (0.56) | 11.5 -> 9.5 (0.83) | 11.8 -> 10.0 (0.85) | 4.0 -> 3.1 (0.76) | 14.8 -> 12.7 (0.86) | 12.5 -> 13.2 (1.06) |
| s1-06_animation | 0.2 -> 0.3 (1.52) | 4.8 -> 3.9 (0.81) | 4.5 -> 4.4 (0.98) | 0.1 -> 0.1 (1.21) | 1.6 -> 1.3 (0.81) | 1.7 -> 1.6 (0.94) |
| s1-07_bounce | 0.2 -> 0.3 (1.65) | 4.7 -> 4.1 (0.87) | 3.5 -> 4.3 (1.23) | 0.1 -> 0.1 (1.63) | 1.5 -> 1.4 (0.93) | 1.6 -> 1.6 (1.00) |

### 2x

| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) |
|---|---|---|---|---|---|---|
| projects-02_rangoli | 12.9 -> 12.0 (0.93) | 51.9 -> 49.1 (0.95) | 44.6 -> 47.5 (1.07) | 12.9 -> 11.7 (0.91) | 49.7 -> 50.8 (1.02) | 42.3 -> 44.7 (1.06) |
| projects-06_kinetic_type | 39.5 -> 28.9 (0.73) | 146.7 -> 91.0 (0.62) | 123.2 -> 92.2 (0.75) | 49.7 -> 33.1 (0.66) | 140.6 -> 116.6 (0.83) | 127.2 -> 107.4 (0.84) |
| text-09_text_dots | 19.8 -> 15.7 (0.79) | 72.8 -> 51.1 (0.70) | 58.7 -> 60.5 (1.03) | 36.6 -> 20.0 (0.55) | 75.6 -> 66.3 (0.88) | 72.9 -> 61.7 (0.85) |
| randomness-03_noise | 16.8 -> 11.6 (0.69) | 53.4 -> 38.7 (0.72) | 50.7 -> 50.1 (0.99) | 19.4 -> 14.8 (0.76) | 49.2 -> 47.3 (0.96) | 49.2 -> 44.0 (0.89) |
| sound-02_write_a_tune | 82.2 -> 77.7 (0.95) | 197.5 -> 188.7 (0.96) | 185.6 -> 188.5 (1.02) | 92.8 -> 87.7 (0.94) | 186.3 -> 178.1 (0.96) | 199.3 -> 181.1 (0.91) |
| randomness-02_gaussian_and_choice | 19.3 -> 11.7 (0.60) | 40.1 -> 33.4 (0.83) | 35.4 -> 35.2 (0.99) | 16.7 -> 11.1 (0.67) | 42.9 -> 35.7 (0.83) | 37.2 -> 31.5 (0.85) |
| studios-03_rhythm | 14.9 -> 13.8 (0.93) | 35.2 -> 37.3 (1.06) | 36.9 -> 37.5 (1.02) | 9.1 -> 13.4 (1.47) | 30.5 -> 31.8 (1.04) | 28.5 -> 32.1 (1.13) |
| studios-05_text_as_geometry | 14.9 -> 16.5 (1.10) | 37.2 -> 37.2 (1.00) | 32.5 -> 36.0 (1.11) | 11.8 -> 15.5 (1.32) | 32.5 -> 38.7 (1.19) | 33.9 -> 35.6 (1.05) |
| paths-06_outlines | 26.6 -> 13.8 (0.52) | 54.5 -> 47.8 (0.88) | 46.4 -> 44.1 (0.95) | 22.2 -> 18.9 (0.85) | 57.7 -> 47.4 (0.82) | 52.5 -> 40.6 (0.77) |
| studios-06_poster_series | 32.5 -> 19.4 (0.60) | 63.3 -> 62.5 (0.99) | 57.5 -> 53.1 (0.92) | 35.5 -> 35.8 (1.01) | 78.2 -> 70.0 (0.90) | 74.8 -> 63.6 (0.85) |
| s1-05_text | 5.5 -> 3.6 (0.65) | 19.6 -> 16.7 (0.85) | 15.1 -> 17.2 (1.14) | 3.6 -> 4.3 (1.21) | 15.3 -> 12.3 (0.80) | 14.4 -> 13.5 (0.94) |
| s1-06_animation | 1.9 -> 1.9 (0.99) | 11.6 -> 11.5 (0.99) | 11.9 -> 12.2 (1.03) | 0.1 -> 0.1 (0.88) | 1.3 -> 1.3 (1.00) | 1.8 -> 1.5 (0.83) |
| s1-07_bounce | 2.6 -> 1.9 (0.75) | 11.1 -> 11.8 (1.06) | 11.9 -> 13.1 (1.10) | 0.0 -> 0.0 (1.12) | 1.4 -> 1.3 (0.93) | 1.5 -> 1.6 (1.07) |

### Cairo (page paints) / Canvas (page paints) end-to-end ratio, before -> after

| case | 1x before | 1x after | 2x before | 2x after |
|---|---|---|---|---|
| projects-02_rangoli | 0.70 | 0.82 | 1.04 | 0.97 |
| projects-06_kinetic_type | 0.77 | 0.69 | 1.04 | 0.78 |
| text-09_text_dots | 0.34 | 0.69 | 0.96 | 0.77 |
| randomness-03_noise | 0.76 | 0.71 | 1.09 | 0.82 |
| sound-02_write_a_tune | 0.94 | 1.00 | 1.06 | 1.06 |
| randomness-02_gaussian_and_choice | 0.76 | 0.76 | 0.93 | 0.94 |
| studios-03_rhythm | 0.78 | 0.71 | 1.15 | 1.17 |
| studios-05_text_as_geometry | 0.74 | 0.63 | 1.14 | 0.96 |
| paths-06_outlines | 0.79 | 0.68 | 0.94 | 1.01 |
| studios-06_poster_series | 0.65 | 0.60 | 0.81 | 0.89 |
| s1-05_text | 0.78 | 0.75 | 1.28 | 1.36 |
| s1-06_animation | 3.00 | 3.00 | 8.92 | 8.85 |
| s1-07_bounce | 3.13 | 2.93 | 7.93 | 9.08 |

Mean ratio heavy: 1x before 0.72, 1x after 0.73, 2x before 1.02, 2x after 0.94

Mean ratio typical: 1x before 2.30, 1x after 2.23, 2x before 6.04, 2x after 6.43

### Spread of the 3 repeats, end-to-end medians (min - max), page paints, 1x, after

| case | Cairo | Canvas |
|---|---|---|
| projects-02_rangoli | 21.4 - 39.6 | 22.3 - 52.8 |
| projects-06_kinetic_type | 42.7 - 84.2 | 55.0 - 126.4 |
| text-09_text_dots | 23.8 - 76.6 | 37.0 - 79.8 |
| randomness-03_noise | 20.2 - 88.4 | 28.1 - 56.1 |
| sound-02_write_a_tune | 95.4 - 370.3 | 103.3 - 184.5 |
| randomness-02_gaussian_and_choice | 11.3 - 27.5 | 14.9 - 34.5 |
| studios-03_rhythm | 11.2 - 25.0 | 15.1 - 34.4 |
| studios-05_text_as_geometry | 13.3 - 41.1 | 16.9 - 40.2 |
| paths-06_outlines | 14.7 - 36.1 | 20.6 - 50.6 |
| studios-06_poster_series | 18.6 - 43.4 | 31.1 - 75.2 |
| s1-05_text | 5.4 - 10.7 | 6.0 - 13.7 |
| s1-06_animation | 3.8 - 4.7 | 1.2 - 2.0 |
| s1-07_bounce | 3.9 - 4.6 | 1.2 - 1.7 |


# Appendix C: S-148 tables in the S-142 format (3 repeats, after only)

### Summary: end-to-end frame time, median of 3 runs (ms) and achieved fps

### 1x

| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) | fps Cairo page / worker | fps Canvas page / worker | Cairo(page) / Canvas(page) |
|---|---|---|---|---|---|---|---|---|---|
| projects-02_rangoli | 9.1 | 38.0 | 32.0 | 11.9 | 45.6 | 48.8 | 20 / 25 | 19 / 17 | 0.83 |
| projects-06_kinetic_type | 27.6 | 77.0 | 169.8 | 34.7 | 110.4 | 129.0 | 11 / 6 | 8 / 7 | 0.70 |
| text-09_text_dots | 13.9 | 46.7 | 56.2 | 20.4 | 72.0 | 75.0 | 18 / 16 | 12 / 12 | 0.65 |
| randomness-03_noise | 11.1 | 33.9 | 38.6 | 14.9 | 47.5 | 48.5 | 24 / 22 | 18 / 18 | 0.71 |
| sound-02_write_a_tune | 66.3 | 181.8 | 142.8 | 87.6 | 115.8 | 178.2 | 5 / 6 | 7 / 5 | 1.57 |
| randomness-02_gaussian_and_choice | 7.8 | 27.2 | 25.1 | 12.4 | 15.1 | 34.3 | 30 / 31 | 53 / 25 | 1.80 |
| studios-03_rhythm | 6.7 | 23.9 | 22.3 | 14.9 | 15.8 | 30.4 | - / - | - / - | 1.51 |
| studios-05_text_as_geometry | 13.5 | 29.1 | 29.4 | 13.0 | 18.6 | 36.3 | - / - | - / - | 1.56 |
| paths-06_outlines | 12.0 | 36.0 | 30.6 | 23.8 | 49.0 | 37.0 | 22 / 25 | 17 / 20 | 0.73 |
| studios-06_poster_series | 19.3 | 43.3 | 38.5 | 24.9 | 64.6 | 61.0 | 21 / 21 | 13 / 14 | 0.67 |
| s1-05_text | 2.5 | 9.9 | 10.0 | 3.0 | 11.9 | 10.7 | 61 / 59 | 61 / 57 | 0.83 |
| s1-06_animation | 0.3 | 4.4 | 4.3 | 0.1 | 1.3 | 1.6 | 61 / 62 | 62 / 62 | 3.38 |
| s1-07_bounce | 0.3 | 4.3 | 4.3 | 0.1 | 1.3 | 1.6 | 61 / 60 | 62 / 62 | 3.31 |

Mean Cairo/Canvas ratio of end-to-end medians (page paints), cases both routes ran: 1.41 over 13 cases.

### 2x

| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) | fps Cairo page / worker | fps Canvas page / worker | Cairo(page) / Canvas(page) |
|---|---|---|---|---|---|---|---|---|---|
| projects-02_rangoli | 12.6 | 25.1 | 47.7 | 12.0 | 50.8 | 42.1 | 30 / 17 | 17 / 20 | 0.49 |
| projects-06_kinetic_type | 29.2 | 48.7 | 113.0 | 34.8 | 117.0 | 105.2 | 19 / 8 | 8 / 9 | 0.42 |
| text-09_text_dots | 15.8 | 28.4 | 104.1 | 21.1 | 72.8 | 59.6 | 29 / 10 | 12 / 15 | 0.39 |
| randomness-03_noise | 11.6 | 27.5 | 54.4 | 15.8 | 69.4 | 42.3 | 30 / 15 | 13 / 19 | 0.40 |
| sound-02_write_a_tune | 77.7 | 188.7 | 197.4 | 83.9 | 188.4 | 174.5 | 5 / 5 | 5 / 6 | 1.00 |
| randomness-02_gaussian_and_choice | 11.7 | 32.2 | 35.2 | 11.1 | 35.7 | 28.7 | 25 / 24 | 23 / 28 | 0.90 |
| studios-03_rhythm | 13.8 | 37.3 | 33.2 | 12.2 | 33.7 | 28.4 | - / - | - / - | 1.11 |
| studios-05_text_as_geometry | 18.2 | 36.9 | 36.1 | 15.7 | 38.7 | 35.6 | - / - | - / - | 0.95 |
| paths-06_outlines | 16.1 | 45.8 | 45.2 | 16.3 | 47.4 | 40.6 | 21 / 20 | 19 / 20 | 0.97 |
| studios-06_poster_series | 19.4 | 60.4 | 58.8 | 38.3 | 70.5 | 58.4 | 16 / 15 | 13 / 15 | 0.86 |
| s1-05_text | 3.6 | 15.0 | 17.2 | 3.1 | 14.0 | 12.1 | 51 / 37 | 52 / 54 | 1.07 |
| s1-06_animation | 1.9 | 11.5 | 13.1 | 0.1 | 1.5 | 1.5 | 59 / 50 | 62 / 62 | 7.67 |
| s1-07_bounce | 1.9 | 12.7 | 13.7 | 0.1 | 1.4 | 1.5 | 55 / 55 | 62 / 62 | 9.07 |

Mean Cairo/Canvas ratio of end-to-end medians (page paints), cases both routes ran: 1.95 over 13 cases.

### Spread of the end-to-end median across the 3 runs (min - max, ms), Chrome, page paints, 1x

| case | Cairo | Canvas |
|---|---|---|
| projects-02_rangoli | 37.8 - 39.6 | 22.3 - 46.5 |
| projects-06_kinetic_type | 73.3 - 84.2 | 55.0 - 126.4 |
| text-09_text_dots | 44.5 - 76.6 | 37.0 - 79.8 |
| randomness-03_noise | 31.6 - 88.4 | 28.1 - 56.1 |
| sound-02_write_a_tune | 175.1 - 370.3 | 103.3 - 175.5 |
| randomness-02_gaussian_and_choice | 24.5 - 27.5 | 14.9 - 33.1 |
| studios-03_rhythm | 22.8 - 25.0 | 15.1 - 32.9 |
| studios-05_text_as_geometry | 23.8 - 41.1 | 16.9 - 40.2 |
| paths-06_outlines | 33.3 - 36.1 | 20.6 - 50.2 |
| studios-06_poster_series | 43.1 - 43.4 | 31.1 - 73.6 |
| s1-05_text | 9.5 - 10.7 | 6.0 - 13.7 |
| s1-06_animation | 3.9 - 4.7 | 1.2 - 1.8 |
| s1-07_bounce | 4.1 - 4.6 | 1.2 - 1.4 |

### First load (cold: fresh Chrome profile for every run; Pyodide and PyPI from the real network)

| route / where / dpr | Pyodide load | fonttools+micropip | uharfbuzz (micropip, PyPI) | pathops | pycairo | funground+fonts fetch | import funground | boot total | first frame since navigation |
|---|---|---|---|---|---|---|---|---|---|
| cairo / main / 1x (3 runs) | 4.78 s | 0.56 s | 1.29 s | 0.08 s | 0.12 s | 0.29 s | 0.54 s | 7.84 s | 8.73 s |
| cairo / main / 2x (3 runs) | 4.16 s | 0.82 s | 1.15 s | 0.07 s | 0.09 s | 0.30 s | 0.37 s | 6.87 s | 7.45 s |
| cairo / worker / 1x (3 runs) | 5.12 s | 0.65 s | 1.21 s | 0.08 s | 0.13 s | 0.31 s | 0.60 s | 8.57 s | 9.36 s |
| cairo / worker / 2x (3 runs) | 4.20 s | 1.04 s | 1.28 s | 0.07 s | 0.12 s | 0.28 s | 0.60 s | 7.70 s | 8.75 s |
| canvas / main / 1x (3 runs) | 4.88 s | 0.69 s | 1.36 s | 0.09 s | - s | 0.31 s | 0.56 s | 7.96 s | 8.62 s |
| canvas / main / 2x (3 runs) | 5.10 s | 1.14 s | 1.22 s | 0.08 s | - s | 0.29 s | 0.69 s | 8.96 s | 9.87 s |
| canvas / worker / 1x (3 runs) | 5.76 s | 0.93 s | 1.27 s | 0.10 s | - s | 0.35 s | 0.71 s | 13.40 s | 14.74 s |
| canvas / worker / 2x (3 runs) | 4.64 s | 0.62 s | 1.29 s | 0.08 s | - s | 0.29 s | 0.48 s | 7.44 s | 8.23 s |

Bytes downloaded at boot (encoded body sizes; localhost files are uncompressed; Pyodide's come gzip/brotli-free as reported):

| component | cairo route | canvas route |
|---|---|---|
| Pyodide core (pyodide.mjs, lock, stdlib zip, asm.wasm, asm.mjs) | 7,470,081 | 7,470,081 |
| uharfbuzz wheel (PyPI; size not reported by the browser) | 981,875 | 981,875 |
| skia-pathops wheel | 172,919 | 172,919 |
| pycairo wheel | 496,371 | 0 |
| funground.zip | 265,071 | 265,071 |
| shim, mixer stub, fonts.json | 14,682 | 14,682 |
| fonts (7 files, all loaded) | 4,543,184 | 4,543,184 |
| **total** | **13,944,183** | **13,447,812** |

### Tables per case (median / p95 in ms; fps and skipped ticks are for the 30 timed frames under rAF)

### projects-02_rangoli

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.2 / 5.4 | 0.1 / 0.2 | 4.2 / 5.3 | 0.0 / 0.0 | 0.3 / 0.6 | - | - | - | 9.1 / 11.2 | - | - |
| 1x | Chrome Cairo, page paints | 19.9 / 27.9 | 0.5 / 0.8 | 14.7 / 20.4 | 0.0 / 0.0 | 1.7 / 2.9 | 0.2 / 0.3 | - | 0.3 / 0.5 | 38.0 / 48.7 | 20.1 | 63 |
| 1x | Chrome Cairo, worker paints | 18.2 / 25.6 | 0.4 / 0.7 | 12.3 / 17.1 | 0.0 / 0.0 | 1.4 / 2.0 | 0.1 / 0.2 | - | 0.3 / 0.8 | 32.0 / 45.8 | 25.0 | 45 |
| 1x | native IR (encode only) | 4.0 / 4.1 | 0.1 / 0.1 | 0.0 / 0.0 | 7.7 / 7.9 | 0.0 / 0.0 | - | - | - | 11.9 / 12.1 | - | - |
| 1x | Chrome Canvas, page paints | 17.0 / 25.8 | 0.3 / 0.8 | 0.0 / 0.0 | 26.1 / 31.5 | - | 0.3 / 0.4 | 0.7 / 1.2 | 0.5 / 1.0 | 45.6 / 62.0 | 19.4 | 66 |
| 1x | Chrome Canvas, worker paints | 18.3 / 28.3 | 0.5 / 0.9 | 0.0 / 0.0 | 27.2 / 41.0 | - | 0.1 / 0.3 | 0.9 / 2.2 | 0.8 / 1.5 | 48.8 / 71.6 | 17.2 | 77 |
| 2x | native Cairo | 4.3 / 5.9 | 0.1 / 0.2 | 6.8 / 8.9 | 0.0 / 0.0 | 1.0 / 1.5 | - | - | - | 12.6 / 15.4 | - | - |
| 2x | Chrome Cairo, page paints | 9.7 / 13.0 | 0.3 / 0.5 | 10.3 / 13.4 | 0.0 / 0.0 | 2.7 / 4.4 | 0.1 / 0.3 | - | 1.0 / 1.6 | 25.1 / 32.4 | 30.2 | 32 |
| 2x | Chrome Cairo, worker paints | 20.8 / 28.0 | 0.5 / 1.0 | 20.0 / 31.2 | 0.0 / 0.0 | 5.0 / 7.1 | 0.1 / 0.3 | - | 1.6 / 2.7 | 47.7 / 69.1 | 17.3 | 79 |
| 2x | native IR (encode only) | 4.1 / 5.0 | 0.1 / 0.2 | 0.0 / 0.0 | 7.6 / 10.0 | 0.0 / 0.0 | - | - | - | 12.0 / 15.1 | - | - |
| 2x | Chrome Canvas, page paints | 17.9 / 28.7 | 0.4 / 0.7 | 0.0 / 0.0 | 27.6 / 39.0 | - | 0.3 / 0.5 | 0.9 / 1.8 | 0.7 / 1.5 | 50.8 / 68.0 | 17.2 | 78 |
| 2x | Chrome Canvas, worker paints | 16.5 / 22.5 | 0.3 / 0.5 | 0.0 / 0.0 | 22.5 / 30.7 | - | 0.1 / 0.3 | 0.6 / 1.2 | 0.6 / 1.2 | 42.1 / 55.8 | 20.3 | 62 |

### projects-06_kinetic_type

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 21.8 / 24.2 | 0.2 / 0.2 | 4.7 / 6.1 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 27.6 / 29.6 | - | - |
| 1x | Chrome Cairo, page paints | 63.1 / 88.3 | 0.6 / 1.1 | 11.2 / 18.5 | 0.0 / 0.0 | 0.7 / 1.5 | 0.2 / 0.3 | - | 0.2 / 0.3 | 77.0 / 108.2 | 11.4 | 133 |
| 1x | Chrome Cairo, worker paints | 140.1 / 175.9 | 1.0 / 1.7 | 27.2 / 35.7 | 0.0 / 0.0 | 1.3 / 2.1 | 0.1 / 0.3 | - | 0.3 / 0.4 | 169.8 / 217.9 | 5.5 | 302 |
| 1x | native IR (encode only) | 22.3 / 22.9 | 0.1 / 0.5 | 0.0 / 0.0 | 12.0 / 15.7 | 0.0 / 0.0 | - | - | - | 34.7 / 36.7 | - | - |
| 1x | Chrome Canvas, page paints | 71.9 / 100.8 | 0.6 / 1.3 | 0.0 / 0.0 | 35.6 / 51.0 | - | 0.3 / 0.5 | 0.9 / 2.1 | 0.7 / 1.5 | 110.4 / 146.6 | 8.0 | 201 |
| 1x | Chrome Canvas, worker paints | 80.0 / 128.3 | 0.7 / 1.2 | 0.0 / 0.0 | 44.0 / 68.8 | - | 0.1 / 0.4 | 1.5 / 2.5 | 1.2 / 2.0 | 129.0 / 203.7 | 7.1 | 234 |
| 2x | native Cairo | 21.4 / 27.7 | 0.1 / 0.2 | 6.9 / 11.8 | 0.0 / 0.0 | 0.6 / 1.0 | - | - | - | 29.2 / 36.7 | - | - |
| 2x | Chrome Cairo, page paints | 35.6 / 39.1 | 0.3 / 0.5 | 9.4 / 11.0 | 0.0 / 0.0 | 1.7 / 2.3 | 0.1 / 0.2 | - | 0.6 / 1.0 | 48.7 / 53.5 | 18.6 | 69 |
| 2x | Chrome Cairo, worker paints | 83.5 / 117.5 | 0.8 / 2.0 | 23.4 / 43.7 | 0.0 / 0.0 | 3.1 / 9.0 | 0.1 / 0.2 | - | 1.1 / 3.1 | 113.0 / 203.2 | 7.7 | 211 |
| 2x | native IR (encode only) | 21.5 / 23.7 | 0.1 / 0.3 | 0.0 / 0.0 | 12.2 / 14.5 | 0.0 / 0.0 | - | - | - | 34.8 / 41.9 | - | - |
| 2x | Chrome Canvas, page paints | 75.4 / 134.8 | 0.7 / 1.9 | 0.0 / 0.0 | 37.7 / 78.8 | - | 0.4 / 0.8 | 1.1 / 2.2 | 0.7 / 2.0 | 117.0 / 229.4 | 7.6 | 213 |
| 2x | Chrome Canvas, worker paints | 66.9 / 101.9 | 0.5 / 0.9 | 0.0 / 0.0 | 30.5 / 51.3 | - | 0.1 / 0.2 | 1.0 / 2.5 | 0.9 / 1.6 | 105.2 / 148.3 | 8.7 | 184 |

### text-09_text_dots

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 8.9 / 9.3 | 0.1 / 0.2 | 4.7 / 5.0 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 13.9 / 14.5 | - | - |
| 1x | Chrome Cairo, page paints | 30.5 / 43.4 | 0.6 / 0.8 | 13.2 / 19.2 | 0.0 / 0.0 | 1.0 / 1.8 | 0.2 / 0.3 | - | 0.2 / 0.4 | 46.7 / 71.1 | 17.8 | 74 |
| 1x | Chrome Cairo, worker paints | 37.1 / 65.2 | 0.6 / 1.1 | 16.6 / 26.4 | 0.0 / 0.0 | 1.4 / 2.3 | 0.1 / 0.3 | - | 0.2 / 0.4 | 56.2 / 93.0 | 15.7 | 88 |
| 1x | native IR (encode only) | 8.7 / 12.0 | 0.1 / 0.2 | 0.0 / 0.0 | 11.5 / 14.0 | 0.0 / 0.0 | - | - | - | 20.4 / 26.8 | - | - |
| 1x | Chrome Canvas, page paints | 31.9 / 44.2 | 0.6 / 1.0 | 0.0 / 0.0 | 34.7 / 50.5 | - | 0.2 / 0.5 | 1.0 / 1.9 | 0.8 / 1.8 | 72.0 / 101.1 | 12.0 | 124 |
| 1x | Chrome Canvas, worker paints | 35.2 / 40.7 | 0.5 / 1.0 | 0.0 / 0.0 | 37.0 / 54.3 | - | 0.1 / 0.3 | 1.5 / 1.9 | 1.0 / 1.6 | 75.0 / 91.4 | 12.2 | 121 |
| 2x | native Cairo | 8.8 / 10.9 | 0.1 / 0.2 | 6.0 / 6.5 | 0.0 / 0.0 | 0.7 / 0.9 | - | - | - | 15.8 / 18.3 | - | - |
| 2x | Chrome Cairo, page paints | 16.2 / 21.3 | 0.4 / 0.5 | 8.6 / 10.4 | 0.0 / 0.0 | 1.9 / 2.4 | 0.1 / 0.1 | - | 0.7 / 1.0 | 28.4 / 35.3 | 29.2 | 33 |
| 2x | Chrome Cairo, worker paints | 60.6 / 85.2 | 0.8 / 1.3 | 28.0 / 41.5 | 0.0 / 0.0 | 5.0 / 7.7 | 0.2 / 0.2 | - | 1.4 / 2.3 | 104.1 / 145.9 | 10.3 | 148 |
| 2x | native IR (encode only) | 8.9 / 9.6 | 0.1 / 0.2 | 0.0 / 0.0 | 11.6 / 12.7 | 0.0 / 0.0 | - | - | - | 21.1 / 22.5 | - | - |
| 2x | Chrome Canvas, page paints | 32.2 / 55.6 | 0.6 / 0.9 | 0.0 / 0.0 | 34.0 / 60.3 | - | 0.4 / 0.6 | 1.2 / 2.7 | 0.9 / 1.9 | 72.8 / 115.2 | 11.9 | 124 |
| 2x | Chrome Canvas, worker paints | 26.3 / 30.1 | 0.4 / 0.7 | 0.0 / 0.0 | 28.7 / 36.5 | - | 0.1 / 0.3 | 1.0 / 1.7 | 1.0 / 1.6 | 59.6 / 68.5 | 14.7 | 96 |

### randomness-03_noise

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 9.2 / 11.0 | 0.1 / 0.2 | 1.3 / 1.6 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 11.1 / 12.5 | - | - |
| 1x | Chrome Cairo, page paints | 28.4 / 38.9 | 0.5 / 1.0 | 3.1 / 5.9 | 0.0 / 0.0 | 0.9 / 2.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 33.9 / 46.7 | 24.1 | 46 |
| 1x | Chrome Cairo, worker paints | 32.5 / 37.1 | 0.4 / 0.7 | 3.1 / 4.6 | 0.0 / 0.0 | 1.0 / 1.7 | 0.0 / 0.2 | - | 0.2 / 0.3 | 38.6 / 43.4 | 22.1 | 54 |
| 1x | native IR (encode only) | 9.3 / 15.0 | 0.1 / 0.2 | 0.0 / 0.0 | 5.2 / 8.2 | 0.0 / 0.0 | - | - | - | 14.9 / 23.5 | - | - |
| 1x | Chrome Canvas, page paints | 29.7 / 39.6 | 0.4 / 0.6 | 0.0 / 0.0 | 15.0 / 21.1 | - | 0.2 / 0.3 | 0.3 / 0.7 | 0.8 / 1.6 | 47.5 / 58.8 | 17.8 | 73 |
| 1x | Chrome Canvas, worker paints | 32.1 / 40.8 | 0.5 / 1.0 | 0.0 / 0.0 | 15.6 / 21.8 | - | 0.1 / 0.3 | 0.3 / 0.6 | 0.8 / 1.7 | 48.5 / 65.9 | 18.5 | 72 |
| 2x | native Cairo | 9.1 / 9.4 | 0.1 / 0.2 | 1.6 / 2.1 | 0.0 / 0.0 | 0.6 / 0.8 | - | - | - | 11.6 / 13.1 | - | - |
| 2x | Chrome Cairo, page paints | 19.7 / 25.3 | 0.4 / 0.7 | 3.5 / 4.6 | 0.0 / 0.0 | 2.5 / 3.4 | 0.1 / 0.3 | - | 0.8 / 1.3 | 27.5 / 34.3 | 29.7 | 32 |
| 2x | Chrome Cairo, worker paints | 35.6 / 61.3 | 0.6 / 1.2 | 6.9 / 12.4 | 0.0 / 0.0 | 4.3 / 8.3 | 0.1 / 0.2 | - | 1.5 / 3.6 | 54.4 / 91.8 | 15.3 | 91 |
| 2x | native IR (encode only) | 10.0 / 14.0 | 0.1 / 0.2 | 0.0 / 0.0 | 5.7 / 6.6 | 0.0 / 0.0 | - | - | - | 15.8 / 21.8 | - | - |
| 2x | Chrome Canvas, page paints | 42.8 / 57.5 | 0.6 / 0.9 | 0.0 / 0.0 | 22.4 / 30.7 | - | 0.2 / 0.4 | 0.4 / 0.8 | 1.2 / 2.0 | 69.4 / 84.2 | 12.8 | 115 |
| 2x | Chrome Canvas, worker paints | 24.2 / 37.2 | 0.5 / 0.6 | 0.0 / 0.0 | 13.5 / 18.9 | - | 0.1 / 0.3 | 0.3 / 0.5 | 0.8 / 1.4 | 42.3 / 54.7 | 19.3 | 66 |

### sound-02_write_a_tune

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 62.0 / 89.9 | 0.1 / 0.2 | 3.4 / 5.6 | 0.0 / 0.0 | 0.1 / 0.3 | - | - | - | 66.3 / 93.2 | - | - |
| 1x | Chrome Cairo, page paints | 173.9 / 218.2 | 0.3 / 0.6 | 8.7 / 14.8 | 0.0 / 0.0 | 1.1 / 2.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 181.8 / 233.9 | 5.3 | 317 |
| 1x | Chrome Cairo, worker paints | 135.3 / 191.8 | 0.3 / 0.5 | 6.3 / 10.1 | 0.0 / 0.0 | 0.7 / 1.6 | 0.1 / 0.2 | - | 0.2 / 0.4 | 142.8 / 205.9 | 6.4 | 262 |
| 1x | native IR (encode only) | 77.8 / 98.6 | 0.1 / 0.2 | 0.0 / 0.0 | 9.2 / 15.3 | 0.0 / 0.0 | - | - | - | 87.6 / 110.0 | - | - |
| 1x | Chrome Canvas, page paints | 104.4 / 194.7 | 0.2 / 0.4 | 0.0 / 0.0 | 9.9 / 24.1 | - | 0.2 / 0.4 | 0.3 / 0.6 | 0.4 / 0.8 | 115.8 / 218.8 | 7.0 | 238 |
| 1x | Chrome Canvas, worker paints | 156.3 / 189.4 | 0.3 / 0.5 | 0.0 / 0.0 | 16.4 / 23.1 | - | 0.0 / 0.2 | 0.4 / 0.9 | 0.7 / 1.2 | 178.2 / 210.2 | 5.5 | 307 |
| 2x | native Cairo | 70.7 / 93.9 | 0.1 / 0.1 | 4.8 / 7.6 | 0.0 / 0.0 | 0.8 / 1.4 | - | - | - | 77.7 / 104.0 | - | - |
| 2x | Chrome Cairo, page paints | 172.7 / 203.5 | 0.2 / 0.5 | 11.3 / 14.5 | 0.0 / 0.0 | 3.2 / 5.1 | 0.1 / 0.6 | - | 1.1 / 1.8 | 188.7 / 220.2 | 5.1 | 333 |
| 2x | Chrome Cairo, worker paints | 179.8 / 208.3 | 0.3 / 0.6 | 9.5 / 16.5 | 0.0 / 0.0 | 3.4 / 4.7 | 0.1 / 0.2 | - | 1.2 / 2.0 | 197.4 / 227.0 | 5.1 | 339 |
| 2x | native IR (encode only) | 74.8 / 93.9 | 0.1 / 0.1 | 0.0 / 0.0 | 8.3 / 13.4 | 0.0 / 0.0 | - | - | - | 83.9 / 108.2 | - | - |
| 2x | Chrome Canvas, page paints | 163.1 / 207.2 | 0.3 / 0.4 | 0.0 / 0.0 | 19.2 / 23.0 | - | 0.2 / 0.3 | 0.5 / 0.8 | 0.7 / 1.0 | 188.4 / 228.7 | 5.4 | 315 |
| 2x | Chrome Canvas, worker paints | 152.6 / 181.0 | 0.2 / 0.4 | 0.0 / 0.0 | 18.6 / 22.5 | - | 0.1 / 0.3 | 0.5 / 0.9 | 0.7 / 1.2 | 174.5 / 203.6 | 5.6 | 302 |

### randomness-02_gaussian_and_choice

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.4 / 9.2 | 0.1 / 0.2 | 3.1 / 6.6 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 7.8 / 15.3 | - | - |
| 1x | Chrome Cairo, page paints | 15.8 / 20.1 | 0.5 / 1.0 | 8.1 / 10.6 | 0.0 / 0.0 | 1.1 / 2.2 | 0.2 / 0.4 | - | 0.2 / 0.6 | 27.2 / 32.2 | 29.7 | 32 |
| 1x | Chrome Cairo, worker paints | 14.9 / 17.7 | 0.3 / 0.6 | 7.2 / 9.7 | 0.0 / 0.0 | 1.0 / 1.7 | 0.1 / 0.2 | - | 0.2 / 0.4 | 25.1 / 29.8 | 30.8 | 30 |
| 1x | native IR (encode only) | 4.8 / 9.3 | 0.1 / 0.2 | 0.0 / 0.0 | 6.9 / 12.0 | 0.0 / 0.0 | - | - | - | 12.4 / 20.7 | - | - |
| 1x | Chrome Canvas, page paints | 6.7 / 9.6 | 0.2 / 0.4 | 0.0 / 0.0 | 7.3 / 8.4 | - | 0.2 / 0.4 | 0.2 / 0.3 | 0.2 / 0.3 | 15.1 / 19.4 | 53.1 | 5 |
| 1x | Chrome Canvas, worker paints | 15.8 / 18.0 | 0.3 / 0.5 | 0.0 / 0.0 | 16.3 / 18.7 | - | 0.1 / 0.1 | 0.4 / 0.5 | 0.5 / 0.7 | 34.3 / 37.9 | 24.6 | 45 |
| 2x | native Cairo | 4.8 / 9.2 | 0.1 / 0.2 | 5.2 / 10.1 | 0.0 / 0.0 | 0.8 / 1.6 | - | - | - | 11.7 / 21.6 | - | - |
| 2x | Chrome Cairo, page paints | 14.0 / 20.3 | 0.4 / 1.0 | 11.7 / 14.6 | 0.0 / 0.0 | 3.3 / 5.6 | 0.1 / 0.3 | - | 1.1 / 1.5 | 32.2 / 41.4 | 24.6 | 46 |
| 2x | Chrome Cairo, worker paints | 16.5 / 18.5 | 0.4 / 0.6 | 12.9 / 14.1 | 0.0 / 0.0 | 3.5 / 5.2 | 0.1 / 0.5 | - | 1.3 / 2.2 | 35.2 / 39.3 | 23.6 | 48 |
| 2x | native IR (encode only) | 4.3 / 8.6 | 0.1 / 0.2 | 0.0 / 0.0 | 5.9 / 10.6 | 0.0 / 0.0 | - | - | - | 11.1 / 19.0 | - | - |
| 2x | Chrome Canvas, page paints | 17.1 / 19.6 | 0.4 / 0.9 | 0.0 / 0.0 | 16.9 / 20.1 | - | 0.2 / 0.3 | 0.4 / 0.5 | 0.5 / 0.9 | 35.7 / 41.3 | 22.7 | 51 |
| 2x | Chrome Canvas, worker paints | 12.7 / 19.3 | 0.3 / 0.5 | 0.0 / 0.0 | 14.0 / 19.4 | - | 0.1 / 0.2 | 0.4 / 0.6 | 0.5 / 0.7 | 28.7 / 41.5 | 27.7 | 37 |

### studios-03_rhythm

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 1.8 / 4.4 | 0.0 / 0.0 | 3.2 / 5.0 | 0.0 / 0.0 | 0.4 / 0.6 | - | - | - | 6.7 / 12.7 | - | - |
| 1x | Chrome Cairo, page paints | 7.8 / 8.8 | 0.0 / 0.0 | 9.8 / 19.3 | 0.0 / 0.0 | 2.5 / 5.9 | 0.2 / 0.4 | - | 0.8 / 1.0 | 23.9 / 50.7 | - | - |
| 1x | Chrome Cairo, worker paints | 7.0 / 9.0 | 0.0 / 0.0 | 9.4 / 12.2 | 0.0 / 0.0 | 2.1 / 3.2 | 0.1 / 0.2 | - | 0.7 / 1.0 | 22.3 / 27.7 | - | - |
| 1x | native IR (encode only) | 2.6 / 3.7 | 0.0 / 0.0 | 0.0 / 0.0 | 10.3 / 11.9 | 0.0 / 0.0 | - | - | - | 14.9 / 16.6 | - | - |
| 1x | Chrome Canvas, page paints | 4.2 / 5.7 | 0.0 / 0.0 | 0.0 / 0.0 | 8.4 / 11.4 | - | 0.2 / 0.3 | 0.4 / 0.8 | 0.4 / 0.5 | 15.8 / 18.5 | - | - |
| 1x | Chrome Canvas, worker paints | 6.7 / 7.8 | 0.0 / 0.0 | 0.0 / 0.0 | 17.6 / 19.7 | - | 0.1 / 0.1 | 0.5 / 0.9 | 0.8 / 1.0 | 30.4 / 34.1 | - | - |
| 2x | native Cairo | 2.4 / 5.1 | 0.0 / 0.0 | 6.6 / 9.1 | 0.0 / 0.0 | 2.1 / 3.1 | - | - | - | 13.8 / 20.6 | - | - |
| 2x | Chrome Cairo, page paints | 7.9 / 10.2 | 0.0 / 0.0 | 13.0 / 19.3 | 0.0 / 0.0 | 8.9 / 9.8 | 0.1 / 0.5 | - | 2.9 / 3.3 | 37.3 / 44.2 | - | - |
| 2x | Chrome Cairo, worker paints | 8.8 / 10.1 | 0.0 / 0.0 | 12.4 / 14.4 | 0.0 / 0.0 | 7.3 / 9.1 | 0.1 / 0.2 | - | 2.3 / 2.9 | 33.2 / 39.4 | - | - |
| 2x | native IR (encode only) | 2.2 / 3.2 | 0.0 / 0.0 | 0.0 / 0.0 | 8.7 / 10.1 | 0.0 / 0.0 | - | - | - | 12.2 / 14.8 | - | - |
| 2x | Chrome Canvas, page paints | 6.8 / 7.7 | 0.0 / 0.0 | 0.0 / 0.0 | 20.4 / 22.6 | - | 0.2 / 0.4 | 0.7 / 0.9 | 0.7 / 1.1 | 33.7 / 36.2 | - | - |
| 2x | Chrome Canvas, worker paints | 5.8 / 7.3 | 0.0 / 0.0 | 0.0 / 0.0 | 16.6 / 19.6 | - | 0.2 / 0.3 | 0.6 / 1.0 | 0.6 / 0.9 | 28.4 / 29.4 | - | - |

### studios-05_text_as_geometry

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 8.7 / 10.9 | 0.0 / 0.0 | 3.4 / 4.9 | 0.0 / 0.0 | 0.3 / 0.5 | - | - | - | 13.5 / 16.1 | - | - |
| 1x | Chrome Cairo, page paints | 18.3 / 25.1 | 0.0 / 0.0 | 6.5 / 9.7 | 0.0 / 0.0 | 1.3 / 1.9 | 0.2 / 0.3 | - | 0.2 / 0.3 | 29.1 / 37.2 | - | - |
| 1x | Chrome Cairo, worker paints | 17.3 / 20.4 | 0.0 / 0.0 | 6.3 / 6.8 | 0.0 / 0.0 | 1.2 / 1.7 | 0.1 / 0.2 | - | 0.2 / 0.3 | 29.4 / 30.0 | - | - |
| 1x | native IR (encode only) | 6.7 / 8.7 | 0.0 / 0.0 | 0.0 / 0.0 | 5.5 / 9.1 | 0.0 / 0.0 | - | - | - | 13.0 / 18.6 | - | - |
| 1x | Chrome Canvas, page paints | 8.4 / 11.1 | 0.0 / 0.0 | 0.0 / 0.0 | 6.9 / 17.4 | - | 0.2 / 0.3 | 0.3 / 0.5 | 0.3 / 0.5 | 18.6 / 26.7 | - | - |
| 1x | Chrome Canvas, worker paints | 18.9 / 23.6 | 0.0 / 0.0 | 0.0 / 0.0 | 14.8 / 19.9 | - | 0.1 / 0.1 | 0.5 / 0.6 | 0.5 / 0.6 | 36.3 / 47.1 | - | - |
| 2x | native Cairo | 8.2 / 9.8 | 0.0 / 0.0 | 6.7 / 7.8 | 0.0 / 0.0 | 1.3 / 1.6 | - | - | - | 18.2 / 21.1 | - | - |
| 2x | Chrome Cairo, page paints | 18.3 / 30.2 | 0.0 / 0.0 | 9.1 / 12.3 | 0.0 / 0.0 | 3.5 / 4.9 | 0.1 / 0.4 | - | 1.2 / 1.7 | 36.9 / 48.4 | - | - |
| 2x | Chrome Cairo, worker paints | 17.8 / 20.5 | 0.0 / 0.0 | 9.0 / 10.6 | 0.0 / 0.0 | 4.3 / 5.8 | 0.2 / 0.3 | - | 1.5 / 2.8 | 36.1 / 39.7 | - | - |
| 2x | native IR (encode only) | 7.4 / 10.2 | 0.0 / 0.0 | 0.0 / 0.0 | 7.9 / 8.7 | 0.0 / 0.0 | - | - | - | 15.7 / 19.8 | - | - |
| 2x | Chrome Canvas, page paints | 19.2 / 23.9 | 0.0 / 0.0 | 0.0 / 0.0 | 16.1 / 20.9 | - | 0.2 / 0.3 | 0.5 / 0.7 | 0.6 / 0.7 | 38.7 / 49.5 | - | - |
| 2x | Chrome Canvas, worker paints | 16.5 / 20.0 | 0.0 / 0.0 | 0.0 / 0.0 | 13.9 / 15.6 | - | 0.1 / 0.2 | 0.4 / 0.6 | 0.5 / 0.6 | 35.6 / 37.3 | - | - |

### paths-06_outlines

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 6.8 / 11.0 | 0.1 / 0.2 | 5.1 / 8.2 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 12.0 / 23.1 | - | - |
| 1x | Chrome Cairo, page paints | 21.3 / 23.7 | 0.3 / 0.5 | 12.2 / 15.0 | 0.0 / 0.0 | 0.9 / 1.4 | 0.2 / 0.3 | - | 0.2 / 0.3 | 36.0 / 47.1 | 22.5 | 53 |
| 1x | Chrome Cairo, worker paints | 17.9 / 25.0 | 0.3 / 0.5 | 11.1 / 14.2 | 0.0 / 0.0 | 1.0 / 1.7 | 0.1 / 0.2 | - | 0.2 / 0.3 | 30.6 / 39.9 | 24.6 | 46 |
| 1x | native IR (encode only) | 9.5 / 11.7 | 0.1 / 0.2 | 0.0 / 0.0 | 14.0 / 19.3 | 0.0 / 0.0 | - | - | - | 23.8 / 31.5 | - | - |
| 1x | Chrome Canvas, page paints | 22.3 / 29.4 | 0.3 / 0.6 | 0.0 / 0.0 | 22.8 / 41.0 | - | 0.2 / 0.3 | 0.8 / 1.4 | 0.5 / 0.7 | 49.0 / 70.5 | 16.8 | 79 |
| 1x | Chrome Canvas, worker paints | 17.1 / 21.7 | 0.3 / 0.6 | 0.0 / 0.0 | 19.2 / 38.4 | - | 0.0 / 0.1 | 0.6 / 1.1 | 0.6 / 0.9 | 37.0 / 63.7 | 20.1 | 62 |
| 2x | native Cairo | 5.8 / 10.0 | 0.1 / 0.1 | 7.2 / 11.5 | 0.0 / 0.0 | 1.0 / 1.5 | - | - | - | 16.1 / 23.6 | - | - |
| 2x | Chrome Cairo, page paints | 22.2 / 27.3 | 0.3 / 0.4 | 18.0 / 19.7 | 0.0 / 0.0 | 3.6 / 4.4 | 0.1 / 0.4 | - | 1.3 / 1.6 | 45.8 / 51.2 | 20.9 | 60 |
| 2x | Chrome Cairo, worker paints | 19.0 / 25.3 | 0.4 / 0.7 | 16.8 / 22.1 | 0.0 / 0.0 | 3.5 / 6.7 | 0.2 / 0.3 | - | 1.2 / 2.1 | 45.2 / 56.6 | 19.8 | 64 |
| 2x | native IR (encode only) | 6.0 / 9.7 | 0.1 / 0.1 | 0.0 / 0.0 | 10.0 / 14.6 | 0.0 / 0.0 | - | - | - | 16.3 / 23.8 | - | - |
| 2x | Chrome Canvas, page paints | 21.2 / 26.9 | 0.3 / 0.6 | 0.0 / 0.0 | 22.4 / 44.9 | - | 0.2 / 0.3 | 0.9 / 1.4 | 0.5 / 0.8 | 47.4 / 65.7 | 18.8 | 67 |
| 2x | Chrome Canvas, worker paints | 15.2 / 23.2 | 0.3 / 0.4 | 0.0 / 0.0 | 17.7 / 35.7 | - | 0.1 / 0.3 | 0.8 / 1.1 | 0.6 / 0.8 | 40.6 / 63.0 | 20.2 | 61 |

### studios-06_poster_series

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.3 / 6.9 | 0.1 / 0.1 | 13.6 / 21.1 | 0.0 / 0.0 | 0.4 / 0.8 | - | - | - | 19.3 / 30.7 | - | - |
| 1x | Chrome Cairo, page paints | 12.1 / 13.3 | 0.3 / 0.4 | 28.2 / 32.0 | 0.0 / 0.0 | 2.1 / 2.3 | 0.2 / 0.3 | - | 0.7 / 1.0 | 43.3 / 47.2 | 21.0 | 58 |
| 1x | Chrome Cairo, worker paints | 10.6 / 11.5 | 0.2 / 0.4 | 25.2 / 28.9 | 0.0 / 0.0 | 1.7 / 2.2 | 0.1 / 0.3 | - | 0.6 / 0.9 | 38.5 / 43.1 | 21.4 | 54 |
| 1x | native IR (encode only) | 3.4 / 6.0 | 0.1 / 0.1 | 0.0 / 0.0 | 19.7 / 34.2 | 0.0 / 0.0 | - | - | - | 24.9 / 39.5 | - | - |
| 1x | Chrome Canvas, page paints | 12.4 / 19.2 | 0.2 / 0.4 | 0.0 / 0.0 | 46.7 / 70.3 | - | 0.3 / 0.4 | 1.8 / 3.4 | 0.7 / 1.3 | 64.6 / 93.7 | 13.1 | 111 |
| 1x | Chrome Canvas, worker paints | 10.7 / 18.0 | 0.2 / 0.4 | 0.0 / 0.0 | 43.0 / 83.2 | - | 0.1 / 0.4 | 1.7 / 3.2 | 1.0 / 1.6 | 61.0 / 102.2 | 13.8 | 105 |
| 2x | native Cairo | 3.4 / 6.1 | 0.1 / 0.1 | 13.7 / 24.0 | 0.0 / 0.0 | 1.6 / 2.8 | - | - | - | 19.4 / 32.8 | - | - |
| 2x | Chrome Cairo, page paints | 14.6 / 17.4 | 0.2 / 0.4 | 33.8 / 40.8 | 0.0 / 0.0 | 6.8 / 9.0 | 0.1 / 0.5 | - | 2.1 / 3.7 | 60.4 / 68.8 | 15.6 | 88 |
| 2x | Chrome Cairo, worker paints | 11.5 / 18.4 | 0.3 / 0.7 | 35.9 / 45.2 | 0.0 / 0.0 | 7.2 / 12.6 | 0.1 / 0.3 | - | 2.5 / 3.8 | 58.8 / 76.2 | 14.6 | 97 |
| 2x | native IR (encode only) | 5.8 / 8.5 | 0.1 / 0.2 | 0.0 / 0.0 | 30.5 / 50.4 | 0.0 / 0.0 | - | - | - | 38.3 / 57.7 | - | - |
| 2x | Chrome Canvas, page paints | 12.7 / 18.3 | 0.3 / 0.5 | 0.0 / 0.0 | 51.0 / 72.1 | - | 0.3 / 0.5 | 2.1 / 3.3 | 0.9 / 1.5 | 70.5 / 103.8 | 13.4 | 109 |
| 2x | Chrome Canvas, worker paints | 8.8 / 14.6 | 0.2 / 0.5 | 0.0 / 0.0 | 41.0 / 55.0 | - | 0.1 / 0.3 | 1.5 / 2.8 | 0.7 / 1.2 | 58.4 / 72.5 | 15.2 | 92 |

### s1-05_text

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.2 / 0.2 | 0.0 / 0.0 | 2.1 / 2.7 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 2.5 / 3.1 | - | - |
| 1x | Chrome Cairo, page paints | 0.8 / 1.4 | 0.2 / 0.3 | 6.5 / 7.3 | 0.0 / 0.0 | 1.4 / 1.7 | 0.2 / 0.3 | - | 0.2 / 0.3 | 9.9 / 11.8 | 60.8 | 0 |
| 1x | Chrome Cairo, worker paints | 0.6 / 1.0 | 0.1 / 0.3 | 6.3 / 8.0 | 0.0 / 0.0 | 1.4 / 1.8 | 0.1 / 0.2 | - | 0.3 / 0.4 | 10.0 / 11.8 | 58.9 | 0 |
| 1x | native IR (encode only) | 0.1 / 0.2 | 0.0 / 0.0 | 0.0 / 0.0 | 2.8 / 5.3 | 0.0 / 0.0 | - | - | - | 3.0 / 5.7 | - | - |
| 1x | Chrome Canvas, page paints | 0.5 / 0.8 | 0.1 / 0.2 | 0.0 / 0.0 | 9.5 / 12.2 | - | 0.2 / 0.3 | 0.4 / 0.7 | 0.2 / 0.3 | 11.9 / 15.1 | 60.6 | 0 |
| 1x | Chrome Canvas, worker paints | 0.5 / 0.9 | 0.1 / 0.3 | 0.0 / 0.0 | 8.6 / 13.8 | - | 0.1 / 0.1 | 0.4 / 0.7 | 0.2 / 0.4 | 10.7 / 16.8 | 56.6 | 2 |
| 2x | native Cairo | 0.2 / 0.3 | 0.0 / 0.1 | 2.2 / 3.5 | 0.0 / 0.0 | 0.8 / 1.4 | - | - | - | 3.6 / 5.4 | - | - |
| 2x | Chrome Cairo, page paints | 0.7 / 1.1 | 0.2 / 0.3 | 8.3 / 10.4 | 0.0 / 0.0 | 3.8 / 5.2 | 0.1 / 0.2 | - | 0.9 / 1.8 | 15.0 / 19.4 | 51.2 | 7 |
| 2x | Chrome Cairo, worker paints | 0.7 / 1.4 | 0.2 / 0.4 | 7.9 / 11.2 | 0.0 / 0.0 | 4.9 / 7.2 | 0.2 / 0.4 | - | 1.7 / 3.2 | 17.2 / 22.2 | 37.5 | 16 |
| 2x | native IR (encode only) | 0.1 / 0.3 | 0.0 / 0.0 | 0.0 / 0.0 | 2.8 / 6.1 | 0.0 / 0.0 | - | - | - | 3.1 / 6.5 | - | - |
| 2x | Chrome Canvas, page paints | 0.7 / 0.9 | 0.1 / 0.3 | 0.0 / 0.0 | 11.1 / 16.7 | - | 0.2 / 0.3 | 0.6 / 1.0 | 0.2 / 0.3 | 14.0 / 26.8 | 51.9 | 5 |
| 2x | Chrome Canvas, worker paints | 0.4 / 0.7 | 0.1 / 0.3 | 0.0 / 0.0 | 9.5 / 17.1 | - | 0.1 / 0.2 | 0.5 / 0.7 | 0.2 / 0.4 | 12.1 / 20.6 | 54.2 | 4 |

### s1-06_animation

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.0 / 0.1 | 0.0 / 0.0 | 0.1 / 0.2 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 0.3 / 0.4 | - | - |
| 1x | Chrome Cairo, page paints | 0.2 / 0.4 | 0.2 / 0.4 | 1.0 / 1.7 | 0.0 / 0.0 | 1.8 / 2.3 | 0.2 / 0.4 | - | 0.2 / 0.3 | 4.4 / 5.8 | 61.5 | 0 |
| 1x | Chrome Cairo, worker paints | 0.2 / 0.3 | 0.3 / 0.5 | 0.9 / 1.3 | 0.0 / 0.0 | 1.7 / 2.1 | 0.1 / 0.3 | - | 0.3 / 0.4 | 4.3 / 5.4 | 61.6 | 0 |
| 1x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.2 / 0.4 | 0.2 / 0.3 | 0.0 / 0.0 | 0.3 / 0.4 | - | 0.2 / 0.3 | 0.0 / 0.1 | 0.1 / 0.2 | 1.3 / 1.7 | 61.9 | 0 |
| 1x | Chrome Canvas, worker paints | 0.2 / 0.3 | 0.1 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.1 / 0.2 | 0.0 / 0.1 | 0.1 / 0.3 | 1.6 / 2.2 | 61.8 | 0 |
| 2x | native Cairo | 0.0 / 0.1 | 0.0 / 0.0 | 0.4 / 0.5 | 0.0 / 0.0 | 1.1 / 1.3 | - | - | - | 1.9 / 2.2 | - | - |
| 2x | Chrome Cairo, page paints | 0.2 / 0.4 | 0.2 / 0.6 | 2.3 / 3.3 | 0.0 / 0.0 | 5.9 / 7.0 | 0.1 / 0.7 | - | 1.4 / 3.1 | 11.5 / 14.2 | 58.7 | 1 |
| 2x | Chrome Cairo, worker paints | 0.2 / 0.4 | 0.3 / 0.9 | 3.2 / 5.2 | 0.0 / 0.0 | 5.7 / 9.0 | 0.1 / 0.3 | - | 1.9 / 3.3 | 13.1 / 18.3 | 50.3 | 6 |
| 2x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 2x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.3 / 0.4 | - | 0.1 / 0.3 | 0.0 / 0.1 | 0.1 / 0.2 | 1.5 / 1.7 | 61.8 | 0 |
| 2x | Chrome Canvas, worker paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.5 / 1.8 | 61.9 | 0 |

### s1-07_bounce

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.0 / 0.0 | 0.0 / 0.0 | 0.2 / 0.3 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 0.3 / 0.5 | - | - |
| 1x | Chrome Cairo, page paints | 0.2 / 0.4 | 0.2 / 0.4 | 1.2 / 1.6 | 0.0 / 0.0 | 1.7 / 2.3 | 0.2 / 0.4 | - | 0.2 / 0.5 | 4.3 / 5.6 | 61.5 | 0 |
| 1x | Chrome Cairo, worker paints | 0.1 / 0.3 | 0.2 / 0.4 | 0.9 / 1.7 | 0.0 / 0.0 | 1.8 / 2.3 | 0.1 / 0.3 | - | 0.3 / 0.6 | 4.3 / 6.4 | 59.5 | 0 |
| 1x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 0.0 / 0.1 | 0.1 / 0.2 | 1.3 / 1.8 | 61.9 | 0 |
| 1x | Chrome Canvas, worker paints | 0.1 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.4 | - | 0.1 / 0.2 | 0.0 / 0.1 | 0.1 / 0.2 | 1.6 / 2.4 | 61.7 | 0 |
| 2x | native Cairo | 0.1 / 0.1 | 0.0 / 0.1 | 0.5 / 0.8 | 0.0 / 0.0 | 1.0 / 1.3 | - | - | - | 1.9 / 2.3 | - | - |
| 2x | Chrome Cairo, page paints | 0.2 / 0.4 | 0.3 / 0.9 | 3.0 / 5.1 | 0.0 / 0.0 | 5.1 / 9.1 | 0.2 / 0.5 | - | 1.2 / 1.4 | 12.7 / 16.9 | 55.2 | 3 |
| 2x | Chrome Cairo, worker paints | 0.2 / 0.4 | 0.3 / 0.9 | 2.7 / 4.1 | 0.0 / 0.0 | 6.2 / 8.1 | 0.1 / 0.3 | - | 1.9 / 3.4 | 13.7 / 20.0 | 54.6 | 3 |
| 2x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 2x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.4 | 0.0 / 0.0 | 0.3 / 0.4 | - | 0.1 / 0.2 | 0.0 / 0.1 | 0.1 / 0.2 | 1.4 / 1.7 | 61.9 | 0 |
| 2x | Chrome Canvas, worker paints | 0.2 / 0.2 | 0.1 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.1 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.5 / 1.7 | 61.9 | 0 |

### Tables per case (median / p95 in ms; fps and skipped ticks are for the 30 timed frames under rAF)

### projects-02_rangoli

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.2 / 5.4 | 0.1 / 0.2 | 4.2 / 5.3 | 0.0 / 0.0 | 0.3 / 0.6 | - | - | - | 9.1 / 11.2 | - | - |
| 1x | Chrome Cairo, page paints | 19.9 / 27.9 | 0.5 / 0.8 | 14.7 / 20.4 | 0.0 / 0.0 | 1.7 / 2.9 | 0.2 / 0.3 | - | 0.3 / 0.5 | 38.0 / 48.7 | 20.1 | 63 |
| 1x | Chrome Cairo, worker paints | 18.2 / 25.6 | 0.4 / 0.7 | 12.3 / 17.1 | 0.0 / 0.0 | 1.4 / 2.0 | 0.1 / 0.2 | - | 0.3 / 0.8 | 32.0 / 45.8 | 25.0 | 45 |
| 1x | native IR (encode only) | 4.0 / 4.1 | 0.1 / 0.1 | 0.0 / 0.0 | 7.7 / 7.9 | 0.0 / 0.0 | - | - | - | 11.9 / 12.1 | - | - |
| 1x | Chrome Canvas, page paints | 17.0 / 25.8 | 0.3 / 0.8 | 0.0 / 0.0 | 26.1 / 31.5 | - | 0.3 / 0.4 | 0.7 / 1.2 | 0.5 / 1.0 | 45.6 / 62.0 | 19.4 | 66 |
| 1x | Chrome Canvas, worker paints | 18.3 / 28.3 | 0.5 / 0.9 | 0.0 / 0.0 | 27.2 / 41.0 | - | 0.1 / 0.3 | 0.9 / 2.2 | 0.8 / 1.5 | 48.8 / 71.6 | 17.2 | 77 |
| 2x | native Cairo | 4.3 / 5.9 | 0.1 / 0.2 | 6.8 / 8.9 | 0.0 / 0.0 | 1.0 / 1.5 | - | - | - | 12.6 / 15.4 | - | - |
| 2x | Chrome Cairo, page paints | 9.7 / 13.0 | 0.3 / 0.5 | 10.3 / 13.4 | 0.0 / 0.0 | 2.7 / 4.4 | 0.1 / 0.3 | - | 1.0 / 1.6 | 25.1 / 32.4 | 30.2 | 32 |
| 2x | Chrome Cairo, worker paints | 20.8 / 28.0 | 0.5 / 1.0 | 20.0 / 31.2 | 0.0 / 0.0 | 5.0 / 7.1 | 0.1 / 0.3 | - | 1.6 / 2.7 | 47.7 / 69.1 | 17.3 | 79 |
| 2x | native IR (encode only) | 4.1 / 5.0 | 0.1 / 0.2 | 0.0 / 0.0 | 7.6 / 10.0 | 0.0 / 0.0 | - | - | - | 12.0 / 15.1 | - | - |
| 2x | Chrome Canvas, page paints | 17.9 / 28.7 | 0.4 / 0.7 | 0.0 / 0.0 | 27.6 / 39.0 | - | 0.3 / 0.5 | 0.9 / 1.8 | 0.7 / 1.5 | 50.8 / 68.0 | 17.2 | 78 |
| 2x | Chrome Canvas, worker paints | 16.5 / 22.5 | 0.3 / 0.5 | 0.0 / 0.0 | 22.5 / 30.7 | - | 0.1 / 0.3 | 0.6 / 1.2 | 0.6 / 1.2 | 42.1 / 55.8 | 20.3 | 62 |

### projects-06_kinetic_type

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 21.8 / 24.2 | 0.2 / 0.2 | 4.7 / 6.1 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 27.6 / 29.6 | - | - |
| 1x | Chrome Cairo, page paints | 63.1 / 88.3 | 0.6 / 1.1 | 11.2 / 18.5 | 0.0 / 0.0 | 0.7 / 1.5 | 0.2 / 0.3 | - | 0.2 / 0.3 | 77.0 / 108.2 | 11.4 | 133 |
| 1x | Chrome Cairo, worker paints | 140.1 / 175.9 | 1.0 / 1.7 | 27.2 / 35.7 | 0.0 / 0.0 | 1.3 / 2.1 | 0.1 / 0.3 | - | 0.3 / 0.4 | 169.8 / 217.9 | 5.5 | 302 |
| 1x | native IR (encode only) | 22.3 / 22.9 | 0.1 / 0.5 | 0.0 / 0.0 | 12.0 / 15.7 | 0.0 / 0.0 | - | - | - | 34.7 / 36.7 | - | - |
| 1x | Chrome Canvas, page paints | 71.9 / 100.8 | 0.6 / 1.3 | 0.0 / 0.0 | 35.6 / 51.0 | - | 0.3 / 0.5 | 0.9 / 2.1 | 0.7 / 1.5 | 110.4 / 146.6 | 8.0 | 201 |
| 1x | Chrome Canvas, worker paints | 80.0 / 128.3 | 0.7 / 1.2 | 0.0 / 0.0 | 44.0 / 68.8 | - | 0.1 / 0.4 | 1.5 / 2.5 | 1.2 / 2.0 | 129.0 / 203.7 | 7.1 | 234 |
| 2x | native Cairo | 21.4 / 27.7 | 0.1 / 0.2 | 6.9 / 11.8 | 0.0 / 0.0 | 0.6 / 1.0 | - | - | - | 29.2 / 36.7 | - | - |
| 2x | Chrome Cairo, page paints | 35.6 / 39.1 | 0.3 / 0.5 | 9.4 / 11.0 | 0.0 / 0.0 | 1.7 / 2.3 | 0.1 / 0.2 | - | 0.6 / 1.0 | 48.7 / 53.5 | 18.6 | 69 |
| 2x | Chrome Cairo, worker paints | 83.5 / 117.5 | 0.8 / 2.0 | 23.4 / 43.7 | 0.0 / 0.0 | 3.1 / 9.0 | 0.1 / 0.2 | - | 1.1 / 3.1 | 113.0 / 203.2 | 7.7 | 211 |
| 2x | native IR (encode only) | 21.5 / 23.7 | 0.1 / 0.3 | 0.0 / 0.0 | 12.2 / 14.5 | 0.0 / 0.0 | - | - | - | 34.8 / 41.9 | - | - |
| 2x | Chrome Canvas, page paints | 75.4 / 134.8 | 0.7 / 1.9 | 0.0 / 0.0 | 37.7 / 78.8 | - | 0.4 / 0.8 | 1.1 / 2.2 | 0.7 / 2.0 | 117.0 / 229.4 | 7.6 | 213 |
| 2x | Chrome Canvas, worker paints | 66.9 / 101.9 | 0.5 / 0.9 | 0.0 / 0.0 | 30.5 / 51.3 | - | 0.1 / 0.2 | 1.0 / 2.5 | 0.9 / 1.6 | 105.2 / 148.3 | 8.7 | 184 |

### text-09_text_dots

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 8.9 / 9.3 | 0.1 / 0.2 | 4.7 / 5.0 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 13.9 / 14.5 | - | - |
| 1x | Chrome Cairo, page paints | 30.5 / 43.4 | 0.6 / 0.8 | 13.2 / 19.2 | 0.0 / 0.0 | 1.0 / 1.8 | 0.2 / 0.3 | - | 0.2 / 0.4 | 46.7 / 71.1 | 17.8 | 74 |
| 1x | Chrome Cairo, worker paints | 37.1 / 65.2 | 0.6 / 1.1 | 16.6 / 26.4 | 0.0 / 0.0 | 1.4 / 2.3 | 0.1 / 0.3 | - | 0.2 / 0.4 | 56.2 / 93.0 | 15.7 | 88 |
| 1x | native IR (encode only) | 8.7 / 12.0 | 0.1 / 0.2 | 0.0 / 0.0 | 11.5 / 14.0 | 0.0 / 0.0 | - | - | - | 20.4 / 26.8 | - | - |
| 1x | Chrome Canvas, page paints | 31.9 / 44.2 | 0.6 / 1.0 | 0.0 / 0.0 | 34.7 / 50.5 | - | 0.2 / 0.5 | 1.0 / 1.9 | 0.8 / 1.8 | 72.0 / 101.1 | 12.0 | 124 |
| 1x | Chrome Canvas, worker paints | 35.2 / 40.7 | 0.5 / 1.0 | 0.0 / 0.0 | 37.0 / 54.3 | - | 0.1 / 0.3 | 1.5 / 1.9 | 1.0 / 1.6 | 75.0 / 91.4 | 12.2 | 121 |
| 2x | native Cairo | 8.8 / 10.9 | 0.1 / 0.2 | 6.0 / 6.5 | 0.0 / 0.0 | 0.7 / 0.9 | - | - | - | 15.8 / 18.3 | - | - |
| 2x | Chrome Cairo, page paints | 16.2 / 21.3 | 0.4 / 0.5 | 8.6 / 10.4 | 0.0 / 0.0 | 1.9 / 2.4 | 0.1 / 0.1 | - | 0.7 / 1.0 | 28.4 / 35.3 | 29.2 | 33 |
| 2x | Chrome Cairo, worker paints | 60.6 / 85.2 | 0.8 / 1.3 | 28.0 / 41.5 | 0.0 / 0.0 | 5.0 / 7.7 | 0.2 / 0.2 | - | 1.4 / 2.3 | 104.1 / 145.9 | 10.3 | 148 |
| 2x | native IR (encode only) | 8.9 / 9.6 | 0.1 / 0.2 | 0.0 / 0.0 | 11.6 / 12.7 | 0.0 / 0.0 | - | - | - | 21.1 / 22.5 | - | - |
| 2x | Chrome Canvas, page paints | 32.2 / 55.6 | 0.6 / 0.9 | 0.0 / 0.0 | 34.0 / 60.3 | - | 0.4 / 0.6 | 1.2 / 2.7 | 0.9 / 1.9 | 72.8 / 115.2 | 11.9 | 124 |
| 2x | Chrome Canvas, worker paints | 26.3 / 30.1 | 0.4 / 0.7 | 0.0 / 0.0 | 28.7 / 36.5 | - | 0.1 / 0.3 | 1.0 / 1.7 | 1.0 / 1.6 | 59.6 / 68.5 | 14.7 | 96 |

### randomness-03_noise

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 9.2 / 11.0 | 0.1 / 0.2 | 1.3 / 1.6 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 11.1 / 12.5 | - | - |
| 1x | Chrome Cairo, page paints | 28.4 / 38.9 | 0.5 / 1.0 | 3.1 / 5.9 | 0.0 / 0.0 | 0.9 / 2.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 33.9 / 46.7 | 24.1 | 46 |
| 1x | Chrome Cairo, worker paints | 32.5 / 37.1 | 0.4 / 0.7 | 3.1 / 4.6 | 0.0 / 0.0 | 1.0 / 1.7 | 0.0 / 0.2 | - | 0.2 / 0.3 | 38.6 / 43.4 | 22.1 | 54 |
| 1x | native IR (encode only) | 9.3 / 15.0 | 0.1 / 0.2 | 0.0 / 0.0 | 5.2 / 8.2 | 0.0 / 0.0 | - | - | - | 14.9 / 23.5 | - | - |
| 1x | Chrome Canvas, page paints | 29.7 / 39.6 | 0.4 / 0.6 | 0.0 / 0.0 | 15.0 / 21.1 | - | 0.2 / 0.3 | 0.3 / 0.7 | 0.8 / 1.6 | 47.5 / 58.8 | 17.8 | 73 |
| 1x | Chrome Canvas, worker paints | 32.1 / 40.8 | 0.5 / 1.0 | 0.0 / 0.0 | 15.6 / 21.8 | - | 0.1 / 0.3 | 0.3 / 0.6 | 0.8 / 1.7 | 48.5 / 65.9 | 18.5 | 72 |
| 2x | native Cairo | 9.1 / 9.4 | 0.1 / 0.2 | 1.6 / 2.1 | 0.0 / 0.0 | 0.6 / 0.8 | - | - | - | 11.6 / 13.1 | - | - |
| 2x | Chrome Cairo, page paints | 19.7 / 25.3 | 0.4 / 0.7 | 3.5 / 4.6 | 0.0 / 0.0 | 2.5 / 3.4 | 0.1 / 0.3 | - | 0.8 / 1.3 | 27.5 / 34.3 | 29.7 | 32 |
| 2x | Chrome Cairo, worker paints | 35.6 / 61.3 | 0.6 / 1.2 | 6.9 / 12.4 | 0.0 / 0.0 | 4.3 / 8.3 | 0.1 / 0.2 | - | 1.5 / 3.6 | 54.4 / 91.8 | 15.3 | 91 |
| 2x | native IR (encode only) | 10.0 / 14.0 | 0.1 / 0.2 | 0.0 / 0.0 | 5.7 / 6.6 | 0.0 / 0.0 | - | - | - | 15.8 / 21.8 | - | - |
| 2x | Chrome Canvas, page paints | 42.8 / 57.5 | 0.6 / 0.9 | 0.0 / 0.0 | 22.4 / 30.7 | - | 0.2 / 0.4 | 0.4 / 0.8 | 1.2 / 2.0 | 69.4 / 84.2 | 12.8 | 115 |
| 2x | Chrome Canvas, worker paints | 24.2 / 37.2 | 0.5 / 0.6 | 0.0 / 0.0 | 13.5 / 18.9 | - | 0.1 / 0.3 | 0.3 / 0.5 | 0.8 / 1.4 | 42.3 / 54.7 | 19.3 | 66 |

### sound-02_write_a_tune

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 62.0 / 89.9 | 0.1 / 0.2 | 3.4 / 5.6 | 0.0 / 0.0 | 0.1 / 0.3 | - | - | - | 66.3 / 93.2 | - | - |
| 1x | Chrome Cairo, page paints | 173.9 / 218.2 | 0.3 / 0.6 | 8.7 / 14.8 | 0.0 / 0.0 | 1.1 / 2.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 181.8 / 233.9 | 5.3 | 317 |
| 1x | Chrome Cairo, worker paints | 135.3 / 191.8 | 0.3 / 0.5 | 6.3 / 10.1 | 0.0 / 0.0 | 0.7 / 1.6 | 0.1 / 0.2 | - | 0.2 / 0.4 | 142.8 / 205.9 | 6.4 | 262 |
| 1x | native IR (encode only) | 77.8 / 98.6 | 0.1 / 0.2 | 0.0 / 0.0 | 9.2 / 15.3 | 0.0 / 0.0 | - | - | - | 87.6 / 110.0 | - | - |
| 1x | Chrome Canvas, page paints | 104.4 / 194.7 | 0.2 / 0.4 | 0.0 / 0.0 | 9.9 / 24.1 | - | 0.2 / 0.4 | 0.3 / 0.6 | 0.4 / 0.8 | 115.8 / 218.8 | 7.0 | 238 |
| 1x | Chrome Canvas, worker paints | 156.3 / 189.4 | 0.3 / 0.5 | 0.0 / 0.0 | 16.4 / 23.1 | - | 0.0 / 0.2 | 0.4 / 0.9 | 0.7 / 1.2 | 178.2 / 210.2 | 5.5 | 307 |
| 2x | native Cairo | 70.7 / 93.9 | 0.1 / 0.1 | 4.8 / 7.6 | 0.0 / 0.0 | 0.8 / 1.4 | - | - | - | 77.7 / 104.0 | - | - |
| 2x | Chrome Cairo, page paints | 172.7 / 203.5 | 0.2 / 0.5 | 11.3 / 14.5 | 0.0 / 0.0 | 3.2 / 5.1 | 0.1 / 0.6 | - | 1.1 / 1.8 | 188.7 / 220.2 | 5.1 | 333 |
| 2x | Chrome Cairo, worker paints | 179.8 / 208.3 | 0.3 / 0.6 | 9.5 / 16.5 | 0.0 / 0.0 | 3.4 / 4.7 | 0.1 / 0.2 | - | 1.2 / 2.0 | 197.4 / 227.0 | 5.1 | 339 |
| 2x | native IR (encode only) | 74.8 / 93.9 | 0.1 / 0.1 | 0.0 / 0.0 | 8.3 / 13.4 | 0.0 / 0.0 | - | - | - | 83.9 / 108.2 | - | - |
| 2x | Chrome Canvas, page paints | 163.1 / 207.2 | 0.3 / 0.4 | 0.0 / 0.0 | 19.2 / 23.0 | - | 0.2 / 0.3 | 0.5 / 0.8 | 0.7 / 1.0 | 188.4 / 228.7 | 5.4 | 315 |
| 2x | Chrome Canvas, worker paints | 152.6 / 181.0 | 0.2 / 0.4 | 0.0 / 0.0 | 18.6 / 22.5 | - | 0.1 / 0.3 | 0.5 / 0.9 | 0.7 / 1.2 | 174.5 / 203.6 | 5.6 | 302 |

### randomness-02_gaussian_and_choice

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.4 / 9.2 | 0.1 / 0.2 | 3.1 / 6.6 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 7.8 / 15.3 | - | - |
| 1x | Chrome Cairo, page paints | 15.8 / 20.1 | 0.5 / 1.0 | 8.1 / 10.6 | 0.0 / 0.0 | 1.1 / 2.2 | 0.2 / 0.4 | - | 0.2 / 0.6 | 27.2 / 32.2 | 29.7 | 32 |
| 1x | Chrome Cairo, worker paints | 14.9 / 17.7 | 0.3 / 0.6 | 7.2 / 9.7 | 0.0 / 0.0 | 1.0 / 1.7 | 0.1 / 0.2 | - | 0.2 / 0.4 | 25.1 / 29.8 | 30.8 | 30 |
| 1x | native IR (encode only) | 4.8 / 9.3 | 0.1 / 0.2 | 0.0 / 0.0 | 6.9 / 12.0 | 0.0 / 0.0 | - | - | - | 12.4 / 20.7 | - | - |
| 1x | Chrome Canvas, page paints | 6.7 / 9.6 | 0.2 / 0.4 | 0.0 / 0.0 | 7.3 / 8.4 | - | 0.2 / 0.4 | 0.2 / 0.3 | 0.2 / 0.3 | 15.1 / 19.4 | 53.1 | 5 |
| 1x | Chrome Canvas, worker paints | 15.8 / 18.0 | 0.3 / 0.5 | 0.0 / 0.0 | 16.3 / 18.7 | - | 0.1 / 0.1 | 0.4 / 0.5 | 0.5 / 0.7 | 34.3 / 37.9 | 24.6 | 45 |
| 2x | native Cairo | 4.8 / 9.2 | 0.1 / 0.2 | 5.2 / 10.1 | 0.0 / 0.0 | 0.8 / 1.6 | - | - | - | 11.7 / 21.6 | - | - |
| 2x | Chrome Cairo, page paints | 14.0 / 20.3 | 0.4 / 1.0 | 11.7 / 14.6 | 0.0 / 0.0 | 3.3 / 5.6 | 0.1 / 0.3 | - | 1.1 / 1.5 | 32.2 / 41.4 | 24.6 | 46 |
| 2x | Chrome Cairo, worker paints | 16.5 / 18.5 | 0.4 / 0.6 | 12.9 / 14.1 | 0.0 / 0.0 | 3.5 / 5.2 | 0.1 / 0.5 | - | 1.3 / 2.2 | 35.2 / 39.3 | 23.6 | 48 |
| 2x | native IR (encode only) | 4.3 / 8.6 | 0.1 / 0.2 | 0.0 / 0.0 | 5.9 / 10.6 | 0.0 / 0.0 | - | - | - | 11.1 / 19.0 | - | - |
| 2x | Chrome Canvas, page paints | 17.1 / 19.6 | 0.4 / 0.9 | 0.0 / 0.0 | 16.9 / 20.1 | - | 0.2 / 0.3 | 0.4 / 0.5 | 0.5 / 0.9 | 35.7 / 41.3 | 22.7 | 51 |
| 2x | Chrome Canvas, worker paints | 12.7 / 19.3 | 0.3 / 0.5 | 0.0 / 0.0 | 14.0 / 19.4 | - | 0.1 / 0.2 | 0.4 / 0.6 | 0.5 / 0.7 | 28.7 / 41.5 | 27.7 | 37 |

### studios-03_rhythm

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 1.8 / 4.4 | 0.0 / 0.0 | 3.2 / 5.0 | 0.0 / 0.0 | 0.4 / 0.6 | - | - | - | 6.7 / 12.7 | - | - |
| 1x | Chrome Cairo, page paints | 7.8 / 8.8 | 0.0 / 0.0 | 9.8 / 19.3 | 0.0 / 0.0 | 2.5 / 5.9 | 0.2 / 0.4 | - | 0.8 / 1.0 | 23.9 / 50.7 | - | - |
| 1x | Chrome Cairo, worker paints | 7.0 / 9.0 | 0.0 / 0.0 | 9.4 / 12.2 | 0.0 / 0.0 | 2.1 / 3.2 | 0.1 / 0.2 | - | 0.7 / 1.0 | 22.3 / 27.7 | - | - |
| 1x | native IR (encode only) | 2.6 / 3.7 | 0.0 / 0.0 | 0.0 / 0.0 | 10.3 / 11.9 | 0.0 / 0.0 | - | - | - | 14.9 / 16.6 | - | - |
| 1x | Chrome Canvas, page paints | 4.2 / 5.7 | 0.0 / 0.0 | 0.0 / 0.0 | 8.4 / 11.4 | - | 0.2 / 0.3 | 0.4 / 0.8 | 0.4 / 0.5 | 15.8 / 18.5 | - | - |
| 1x | Chrome Canvas, worker paints | 6.7 / 7.8 | 0.0 / 0.0 | 0.0 / 0.0 | 17.6 / 19.7 | - | 0.1 / 0.1 | 0.5 / 0.9 | 0.8 / 1.0 | 30.4 / 34.1 | - | - |
| 2x | native Cairo | 2.4 / 5.1 | 0.0 / 0.0 | 6.6 / 9.1 | 0.0 / 0.0 | 2.1 / 3.1 | - | - | - | 13.8 / 20.6 | - | - |
| 2x | Chrome Cairo, page paints | 7.9 / 10.2 | 0.0 / 0.0 | 13.0 / 19.3 | 0.0 / 0.0 | 8.9 / 9.8 | 0.1 / 0.5 | - | 2.9 / 3.3 | 37.3 / 44.2 | - | - |
| 2x | Chrome Cairo, worker paints | 8.8 / 10.1 | 0.0 / 0.0 | 12.4 / 14.4 | 0.0 / 0.0 | 7.3 / 9.1 | 0.1 / 0.2 | - | 2.3 / 2.9 | 33.2 / 39.4 | - | - |
| 2x | native IR (encode only) | 2.2 / 3.2 | 0.0 / 0.0 | 0.0 / 0.0 | 8.7 / 10.1 | 0.0 / 0.0 | - | - | - | 12.2 / 14.8 | - | - |
| 2x | Chrome Canvas, page paints | 6.8 / 7.7 | 0.0 / 0.0 | 0.0 / 0.0 | 20.4 / 22.6 | - | 0.2 / 0.4 | 0.7 / 0.9 | 0.7 / 1.1 | 33.7 / 36.2 | - | - |
| 2x | Chrome Canvas, worker paints | 5.8 / 7.3 | 0.0 / 0.0 | 0.0 / 0.0 | 16.6 / 19.6 | - | 0.2 / 0.3 | 0.6 / 1.0 | 0.6 / 0.9 | 28.4 / 29.4 | - | - |

### studios-05_text_as_geometry

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 8.7 / 10.9 | 0.0 / 0.0 | 3.4 / 4.9 | 0.0 / 0.0 | 0.3 / 0.5 | - | - | - | 13.5 / 16.1 | - | - |
| 1x | Chrome Cairo, page paints | 18.3 / 25.1 | 0.0 / 0.0 | 6.5 / 9.7 | 0.0 / 0.0 | 1.3 / 1.9 | 0.2 / 0.3 | - | 0.2 / 0.3 | 29.1 / 37.2 | - | - |
| 1x | Chrome Cairo, worker paints | 17.3 / 20.4 | 0.0 / 0.0 | 6.3 / 6.8 | 0.0 / 0.0 | 1.2 / 1.7 | 0.1 / 0.2 | - | 0.2 / 0.3 | 29.4 / 30.0 | - | - |
| 1x | native IR (encode only) | 6.7 / 8.7 | 0.0 / 0.0 | 0.0 / 0.0 | 5.5 / 9.1 | 0.0 / 0.0 | - | - | - | 13.0 / 18.6 | - | - |
| 1x | Chrome Canvas, page paints | 8.4 / 11.1 | 0.0 / 0.0 | 0.0 / 0.0 | 6.9 / 17.4 | - | 0.2 / 0.3 | 0.3 / 0.5 | 0.3 / 0.5 | 18.6 / 26.7 | - | - |
| 1x | Chrome Canvas, worker paints | 18.9 / 23.6 | 0.0 / 0.0 | 0.0 / 0.0 | 14.8 / 19.9 | - | 0.1 / 0.1 | 0.5 / 0.6 | 0.5 / 0.6 | 36.3 / 47.1 | - | - |
| 2x | native Cairo | 8.2 / 9.8 | 0.0 / 0.0 | 6.7 / 7.8 | 0.0 / 0.0 | 1.3 / 1.6 | - | - | - | 18.2 / 21.1 | - | - |
| 2x | Chrome Cairo, page paints | 18.3 / 30.2 | 0.0 / 0.0 | 9.1 / 12.3 | 0.0 / 0.0 | 3.5 / 4.9 | 0.1 / 0.4 | - | 1.2 / 1.7 | 36.9 / 48.4 | - | - |
| 2x | Chrome Cairo, worker paints | 17.8 / 20.5 | 0.0 / 0.0 | 9.0 / 10.6 | 0.0 / 0.0 | 4.3 / 5.8 | 0.2 / 0.3 | - | 1.5 / 2.8 | 36.1 / 39.7 | - | - |
| 2x | native IR (encode only) | 7.4 / 10.2 | 0.0 / 0.0 | 0.0 / 0.0 | 7.9 / 8.7 | 0.0 / 0.0 | - | - | - | 15.7 / 19.8 | - | - |
| 2x | Chrome Canvas, page paints | 19.2 / 23.9 | 0.0 / 0.0 | 0.0 / 0.0 | 16.1 / 20.9 | - | 0.2 / 0.3 | 0.5 / 0.7 | 0.6 / 0.7 | 38.7 / 49.5 | - | - |
| 2x | Chrome Canvas, worker paints | 16.5 / 20.0 | 0.0 / 0.0 | 0.0 / 0.0 | 13.9 / 15.6 | - | 0.1 / 0.2 | 0.4 / 0.6 | 0.5 / 0.6 | 35.6 / 37.3 | - | - |

### paths-06_outlines

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 6.8 / 11.0 | 0.1 / 0.2 | 5.1 / 8.2 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 12.0 / 23.1 | - | - |
| 1x | Chrome Cairo, page paints | 21.3 / 23.7 | 0.3 / 0.5 | 12.2 / 15.0 | 0.0 / 0.0 | 0.9 / 1.4 | 0.2 / 0.3 | - | 0.2 / 0.3 | 36.0 / 47.1 | 22.5 | 53 |
| 1x | Chrome Cairo, worker paints | 17.9 / 25.0 | 0.3 / 0.5 | 11.1 / 14.2 | 0.0 / 0.0 | 1.0 / 1.7 | 0.1 / 0.2 | - | 0.2 / 0.3 | 30.6 / 39.9 | 24.6 | 46 |
| 1x | native IR (encode only) | 9.5 / 11.7 | 0.1 / 0.2 | 0.0 / 0.0 | 14.0 / 19.3 | 0.0 / 0.0 | - | - | - | 23.8 / 31.5 | - | - |
| 1x | Chrome Canvas, page paints | 22.3 / 29.4 | 0.3 / 0.6 | 0.0 / 0.0 | 22.8 / 41.0 | - | 0.2 / 0.3 | 0.8 / 1.4 | 0.5 / 0.7 | 49.0 / 70.5 | 16.8 | 79 |
| 1x | Chrome Canvas, worker paints | 17.1 / 21.7 | 0.3 / 0.6 | 0.0 / 0.0 | 19.2 / 38.4 | - | 0.0 / 0.1 | 0.6 / 1.1 | 0.6 / 0.9 | 37.0 / 63.7 | 20.1 | 62 |
| 2x | native Cairo | 5.8 / 10.0 | 0.1 / 0.1 | 7.2 / 11.5 | 0.0 / 0.0 | 1.0 / 1.5 | - | - | - | 16.1 / 23.6 | - | - |
| 2x | Chrome Cairo, page paints | 22.2 / 27.3 | 0.3 / 0.4 | 18.0 / 19.7 | 0.0 / 0.0 | 3.6 / 4.4 | 0.1 / 0.4 | - | 1.3 / 1.6 | 45.8 / 51.2 | 20.9 | 60 |
| 2x | Chrome Cairo, worker paints | 19.0 / 25.3 | 0.4 / 0.7 | 16.8 / 22.1 | 0.0 / 0.0 | 3.5 / 6.7 | 0.2 / 0.3 | - | 1.2 / 2.1 | 45.2 / 56.6 | 19.8 | 64 |
| 2x | native IR (encode only) | 6.0 / 9.7 | 0.1 / 0.1 | 0.0 / 0.0 | 10.0 / 14.6 | 0.0 / 0.0 | - | - | - | 16.3 / 23.8 | - | - |
| 2x | Chrome Canvas, page paints | 21.2 / 26.9 | 0.3 / 0.6 | 0.0 / 0.0 | 22.4 / 44.9 | - | 0.2 / 0.3 | 0.9 / 1.4 | 0.5 / 0.8 | 47.4 / 65.7 | 18.8 | 67 |
| 2x | Chrome Canvas, worker paints | 15.2 / 23.2 | 0.3 / 0.4 | 0.0 / 0.0 | 17.7 / 35.7 | - | 0.1 / 0.3 | 0.8 / 1.1 | 0.6 / 0.8 | 40.6 / 63.0 | 20.2 | 61 |

### studios-06_poster_series

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.3 / 6.9 | 0.1 / 0.1 | 13.6 / 21.1 | 0.0 / 0.0 | 0.4 / 0.8 | - | - | - | 19.3 / 30.7 | - | - |
| 1x | Chrome Cairo, page paints | 12.1 / 13.3 | 0.3 / 0.4 | 28.2 / 32.0 | 0.0 / 0.0 | 2.1 / 2.3 | 0.2 / 0.3 | - | 0.7 / 1.0 | 43.3 / 47.2 | 21.0 | 58 |
| 1x | Chrome Cairo, worker paints | 10.6 / 11.5 | 0.2 / 0.4 | 25.2 / 28.9 | 0.0 / 0.0 | 1.7 / 2.2 | 0.1 / 0.3 | - | 0.6 / 0.9 | 38.5 / 43.1 | 21.4 | 54 |
| 1x | native IR (encode only) | 3.4 / 6.0 | 0.1 / 0.1 | 0.0 / 0.0 | 19.7 / 34.2 | 0.0 / 0.0 | - | - | - | 24.9 / 39.5 | - | - |
| 1x | Chrome Canvas, page paints | 12.4 / 19.2 | 0.2 / 0.4 | 0.0 / 0.0 | 46.7 / 70.3 | - | 0.3 / 0.4 | 1.8 / 3.4 | 0.7 / 1.3 | 64.6 / 93.7 | 13.1 | 111 |
| 1x | Chrome Canvas, worker paints | 10.7 / 18.0 | 0.2 / 0.4 | 0.0 / 0.0 | 43.0 / 83.2 | - | 0.1 / 0.4 | 1.7 / 3.2 | 1.0 / 1.6 | 61.0 / 102.2 | 13.8 | 105 |
| 2x | native Cairo | 3.4 / 6.1 | 0.1 / 0.1 | 13.7 / 24.0 | 0.0 / 0.0 | 1.6 / 2.8 | - | - | - | 19.4 / 32.8 | - | - |
| 2x | Chrome Cairo, page paints | 14.6 / 17.4 | 0.2 / 0.4 | 33.8 / 40.8 | 0.0 / 0.0 | 6.8 / 9.0 | 0.1 / 0.5 | - | 2.1 / 3.7 | 60.4 / 68.8 | 15.6 | 88 |
| 2x | Chrome Cairo, worker paints | 11.5 / 18.4 | 0.3 / 0.7 | 35.9 / 45.2 | 0.0 / 0.0 | 7.2 / 12.6 | 0.1 / 0.3 | - | 2.5 / 3.8 | 58.8 / 76.2 | 14.6 | 97 |
| 2x | native IR (encode only) | 5.8 / 8.5 | 0.1 / 0.2 | 0.0 / 0.0 | 30.5 / 50.4 | 0.0 / 0.0 | - | - | - | 38.3 / 57.7 | - | - |
| 2x | Chrome Canvas, page paints | 12.7 / 18.3 | 0.3 / 0.5 | 0.0 / 0.0 | 51.0 / 72.1 | - | 0.3 / 0.5 | 2.1 / 3.3 | 0.9 / 1.5 | 70.5 / 103.8 | 13.4 | 109 |
| 2x | Chrome Canvas, worker paints | 8.8 / 14.6 | 0.2 / 0.5 | 0.0 / 0.0 | 41.0 / 55.0 | - | 0.1 / 0.3 | 1.5 / 2.8 | 0.7 / 1.2 | 58.4 / 72.5 | 15.2 | 92 |

### s1-05_text

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.2 / 0.2 | 0.0 / 0.0 | 2.1 / 2.7 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 2.5 / 3.1 | - | - |
| 1x | Chrome Cairo, page paints | 0.8 / 1.4 | 0.2 / 0.3 | 6.5 / 7.3 | 0.0 / 0.0 | 1.4 / 1.7 | 0.2 / 0.3 | - | 0.2 / 0.3 | 9.9 / 11.8 | 60.8 | 0 |
| 1x | Chrome Cairo, worker paints | 0.6 / 1.0 | 0.1 / 0.3 | 6.3 / 8.0 | 0.0 / 0.0 | 1.4 / 1.8 | 0.1 / 0.2 | - | 0.3 / 0.4 | 10.0 / 11.8 | 58.9 | 0 |
| 1x | native IR (encode only) | 0.1 / 0.2 | 0.0 / 0.0 | 0.0 / 0.0 | 2.8 / 5.3 | 0.0 / 0.0 | - | - | - | 3.0 / 5.7 | - | - |
| 1x | Chrome Canvas, page paints | 0.5 / 0.8 | 0.1 / 0.2 | 0.0 / 0.0 | 9.5 / 12.2 | - | 0.2 / 0.3 | 0.4 / 0.7 | 0.2 / 0.3 | 11.9 / 15.1 | 60.6 | 0 |
| 1x | Chrome Canvas, worker paints | 0.5 / 0.9 | 0.1 / 0.3 | 0.0 / 0.0 | 8.6 / 13.8 | - | 0.1 / 0.1 | 0.4 / 0.7 | 0.2 / 0.4 | 10.7 / 16.8 | 56.6 | 2 |
| 2x | native Cairo | 0.2 / 0.3 | 0.0 / 0.1 | 2.2 / 3.5 | 0.0 / 0.0 | 0.8 / 1.4 | - | - | - | 3.6 / 5.4 | - | - |
| 2x | Chrome Cairo, page paints | 0.7 / 1.1 | 0.2 / 0.3 | 8.3 / 10.4 | 0.0 / 0.0 | 3.8 / 5.2 | 0.1 / 0.2 | - | 0.9 / 1.8 | 15.0 / 19.4 | 51.2 | 7 |
| 2x | Chrome Cairo, worker paints | 0.7 / 1.4 | 0.2 / 0.4 | 7.9 / 11.2 | 0.0 / 0.0 | 4.9 / 7.2 | 0.2 / 0.4 | - | 1.7 / 3.2 | 17.2 / 22.2 | 37.5 | 16 |
| 2x | native IR (encode only) | 0.1 / 0.3 | 0.0 / 0.0 | 0.0 / 0.0 | 2.8 / 6.1 | 0.0 / 0.0 | - | - | - | 3.1 / 6.5 | - | - |
| 2x | Chrome Canvas, page paints | 0.7 / 0.9 | 0.1 / 0.3 | 0.0 / 0.0 | 11.1 / 16.7 | - | 0.2 / 0.3 | 0.6 / 1.0 | 0.2 / 0.3 | 14.0 / 26.8 | 51.9 | 5 |
| 2x | Chrome Canvas, worker paints | 0.4 / 0.7 | 0.1 / 0.3 | 0.0 / 0.0 | 9.5 / 17.1 | - | 0.1 / 0.2 | 0.5 / 0.7 | 0.2 / 0.4 | 12.1 / 20.6 | 54.2 | 4 |

### s1-06_animation

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.0 / 0.1 | 0.0 / 0.0 | 0.1 / 0.2 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 0.3 / 0.4 | - | - |
| 1x | Chrome Cairo, page paints | 0.2 / 0.4 | 0.2 / 0.4 | 1.0 / 1.7 | 0.0 / 0.0 | 1.8 / 2.3 | 0.2 / 0.4 | - | 0.2 / 0.3 | 4.4 / 5.8 | 61.5 | 0 |
| 1x | Chrome Cairo, worker paints | 0.2 / 0.3 | 0.3 / 0.5 | 0.9 / 1.3 | 0.0 / 0.0 | 1.7 / 2.1 | 0.1 / 0.3 | - | 0.3 / 0.4 | 4.3 / 5.4 | 61.6 | 0 |
| 1x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.2 / 0.4 | 0.2 / 0.3 | 0.0 / 0.0 | 0.3 / 0.4 | - | 0.2 / 0.3 | 0.0 / 0.1 | 0.1 / 0.2 | 1.3 / 1.7 | 61.9 | 0 |
| 1x | Chrome Canvas, worker paints | 0.2 / 0.3 | 0.1 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.1 / 0.2 | 0.0 / 0.1 | 0.1 / 0.3 | 1.6 / 2.2 | 61.8 | 0 |
| 2x | native Cairo | 0.0 / 0.1 | 0.0 / 0.0 | 0.4 / 0.5 | 0.0 / 0.0 | 1.1 / 1.3 | - | - | - | 1.9 / 2.2 | - | - |
| 2x | Chrome Cairo, page paints | 0.2 / 0.4 | 0.2 / 0.6 | 2.3 / 3.3 | 0.0 / 0.0 | 5.9 / 7.0 | 0.1 / 0.7 | - | 1.4 / 3.1 | 11.5 / 14.2 | 58.7 | 1 |
| 2x | Chrome Cairo, worker paints | 0.2 / 0.4 | 0.3 / 0.9 | 3.2 / 5.2 | 0.0 / 0.0 | 5.7 / 9.0 | 0.1 / 0.3 | - | 1.9 / 3.3 | 13.1 / 18.3 | 50.3 | 6 |
| 2x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 2x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.3 / 0.4 | - | 0.1 / 0.3 | 0.0 / 0.1 | 0.1 / 0.2 | 1.5 / 1.7 | 61.8 | 0 |
| 2x | Chrome Canvas, worker paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.5 / 1.8 | 61.9 | 0 |

### s1-07_bounce

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.0 / 0.0 | 0.0 / 0.0 | 0.2 / 0.3 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 0.3 / 0.5 | - | - |
| 1x | Chrome Cairo, page paints | 0.2 / 0.4 | 0.2 / 0.4 | 1.2 / 1.6 | 0.0 / 0.0 | 1.7 / 2.3 | 0.2 / 0.4 | - | 0.2 / 0.5 | 4.3 / 5.6 | 61.5 | 0 |
| 1x | Chrome Cairo, worker paints | 0.1 / 0.3 | 0.2 / 0.4 | 0.9 / 1.7 | 0.0 / 0.0 | 1.8 / 2.3 | 0.1 / 0.3 | - | 0.3 / 0.6 | 4.3 / 6.4 | 59.5 | 0 |
| 1x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 0.0 / 0.1 | 0.1 / 0.2 | 1.3 / 1.8 | 61.9 | 0 |
| 1x | Chrome Canvas, worker paints | 0.1 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.4 | - | 0.1 / 0.2 | 0.0 / 0.1 | 0.1 / 0.2 | 1.6 / 2.4 | 61.7 | 0 |
| 2x | native Cairo | 0.1 / 0.1 | 0.0 / 0.1 | 0.5 / 0.8 | 0.0 / 0.0 | 1.0 / 1.3 | - | - | - | 1.9 / 2.3 | - | - |
| 2x | Chrome Cairo, page paints | 0.2 / 0.4 | 0.3 / 0.9 | 3.0 / 5.1 | 0.0 / 0.0 | 5.1 / 9.1 | 0.2 / 0.5 | - | 1.2 / 1.4 | 12.7 / 16.9 | 55.2 | 3 |
| 2x | Chrome Cairo, worker paints | 0.2 / 0.4 | 0.3 / 0.9 | 2.7 / 4.1 | 0.0 / 0.0 | 6.2 / 8.1 | 0.1 / 0.3 | - | 1.9 / 3.4 | 13.7 / 20.0 | 54.6 | 3 |
| 2x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 2x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.4 | 0.0 / 0.0 | 0.3 / 0.4 | - | 0.1 / 0.2 | 0.0 / 0.1 | 0.1 / 0.2 | 1.4 / 1.7 | 61.9 | 0 |
| 2x | Chrome Canvas, worker paints | 0.2 / 0.2 | 0.1 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.1 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.5 / 1.7 | 61.9 | 0 |

