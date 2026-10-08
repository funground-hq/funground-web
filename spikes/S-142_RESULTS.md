# S-142 results: Cairo compiled to wasm vs Canvas 2D, in Chrome, same cases, same harness

Question: in Chrome on this machine, how does Cairo compiled to wasm (pycairo in Pyodide, the real `CairoRenderer`) compare with the Canvas 2D IR renderer (S-135), on the same cases and the same harness? The cloud spike (S-134) measured Node; this is the browser.

Branch (nothing committed or pushed): `spike/s142-browser-bench` in `C:\Projects\funground-web`, from `spike/s133-text-shim`. `C:\Projects\playground`, `C:\Projects\playground-0.2` and `C:\Projects\funground-cairo-wasm` were not changed. The funground test suite was not run.

## Short answer

- **On frame time the two routes are close; neither wins everywhere.** For the 10 heavy gallery examples the time is mostly Python (`draw()`, about 55 to 75 % of the frame). The renderer-specific part is Cairo's render (about 12 ms mean in wasm at 1x, 18 ms at 2x) against the IR encode (about 25 to 34 ms mean at 1x and 2x). In Chrome the Cairo route's end-to-end median was lower than the Canvas route's in 11 of 13 cases at 1x (mean ratio 0.7 to 0.8 on the heavy ones) and about equal at 2x (ratio 0.8 to 1.15 on the heavy ones). The ratio is dominated by the IR-to-JSON encode in Python, which S-136 already named as the open cost.
- **The Cairo route pays a per-pixel copy; the Canvas route pays per op.** Cairo's frame must leave the wasm heap and be swapped from BGRA to RGBA: 0.1 to 2 ms at 640x400 and **3 to 7 ms at 2x** (1280x800), plus about 1.5 ms to put it on the canvas. For tiny sketches (Session 1 `06_animation`, `07_bounce`) this makes Cairo the slower route: **4.8 ms vs 1.6 ms at 1x, 11.6 ms vs 1.3 ms at 2x**, with both well inside 16.7 ms.
- **Pixels.** The Cairo route's 30th frame is **byte-identical to the golden in 12 of 12 cases that have a golden** (both painting variants). The Canvas route passes S-135's tolerance in 12 of 12 (worst: 2.71 % of pixels differ by more than 8, mean 0.39).
- **A Canvas-only route cannot run three of the ten heavy examples** (`studios-03`, `-05`, `-06`): the marks and Grid vocabulary (S-132) measure ink with `CairoRenderer.ink_bounds`. They ran here with pycairo loaded only for measuring (see "Cases"). That is a finding for D-075: a Canvas route needs its own `ink_bounds` (or Cairo as the measuring tool).
- **The machine is noisy.** Three full repeats of every configuration differ by up to 2x for the same case (see the spread table). Medians of three are reported; differences under about 25 % between the routes are not safe to read.

## Setup (what was measured and how)

| | |
|---|---|
| Machine | Windows 11, 11th-gen Core i5-1135G7 (4 cores, 8 threads), 8 GB RAM, other applications open (the maintainer's own Chrome and Task Manager were running) |
| Browser | HeadlessChrome 154.0.0.0 (`--headless=new`), a fresh profile for every run, one Chrome at a time, stopped by its PID. **Headless has no real vsync and no GPU window**: "painted" means the Canvas API call returned; raster and scan-out are not in any number (see open problems). `crossOriginIsolated` false, no SharedArrayBuffer. |
| Python in the browser | Pyodide 314.0.7 (CPython 3.14.2) from jsDelivr, in a module Web Worker; fontTools from the Pyodide distribution; uharfbuzz 0.56.3 from PyPI with micropip (as S-133); pycairo 1.29.2 and skia-pathops 0.9.2 wheels from the CI artifact of run 37768002634, served from localhost |
| funground | `spike/s136-loop` of playground-0.2 (`abd3865`, release-0.2-web plus the start/step/finish loop; the working tree of `release-0.2-web` has no `step()` yet), extracted with `git archive`. Both routes use the same `Host` (`harness/s142/shim.py`); only the renderer differs. |
| Native | CPython 3.14.7 from `C:\Projects\playground\.venv`, the same `shim.py`, the same funground, pygame-ce 2.5.8 for `sound-02` (dummy audio) |
| Loop | The page calls `requestAnimationFrame`; each callback posts one `step` message unless the last is unanswered (then the tick is skipped and counted). 5 warm-up frames + 30 timed frames per case (the cloud bench's counts), `random_seed(0)`. Scripts (`f.show()`): the whole run is the frame, 1 warm-up + 10 timed runs (cloud used 3 to 10). Native: same counts, a fake 60 Hz clock. |
| Scales | 1x: native canvas size. 2x: Chrome started with `--force-device-scale-factor=2` (`devicePixelRatio` 2), funground's backing scale 2, canvas backing store 2x the CSS size. |
| Repeats | Every browser configuration (route x where it paints x scale = 8 pages) was run 3 times, native 3 times; tables show the median of the three runs' medians (p95: median of the three p95s). Run order differed between repeats. |
| Timer | `performance.now()`, which Chrome coarsens to 0.1 ms. Small numbers are quantised. |

### The routes and variants

| route | what happens to a frame | where it is painted |
|---|---|---|
| **Cairo** | The real `CairoRenderer` (pycairo in wasm) renders in Python. The surface's BGRA bytes are copied out of the wasm heap while swapping B and R (one pass over a `Uint32Array`). | *page paints*: the `ArrayBuffer` is transferred; the page makes an `ImageData` and calls `putImageData`. *worker paints*: the worker does `putImageData` on a transferred `OffscreenCanvas`. |
| **Canvas** | The IR renderer stand-in keeps the ops; Python encodes them (`op_to_jsonable` + `json.dumps`, plus the shaped glyph outlines of Text ops and the path of rounded Rects, as S-133). `renderer/ir_canvas.js` (S-135) draws them. | *page paints*: JSON string by `postMessage`, `JSON.parse`, `drawFrame` on the page. *worker paints*: parse and draw in the worker on a transferred `OffscreenCanvas`. |

### Phases in the tables (ms per frame, median / p95)

- **draw()**: the learner's `draw()` function (wrapped). **py other**: `step()` minus draw() minus the renderer (input, state, op bookkeeping).
- **Cairo render**: `CairoRenderer.render`/`draw_batch`/`begin_frame`/`end_frame` and the final flush (wrapped, counted once). Zero for the Canvas route (its drawing is in "paint").
- **encode (JSON)**: Canvas route only: the ops to JSON in Python.
- **wasm->JS copy**: Cairo route only: surface bytes out of the heap, with the B/R swap. (Native column: one `bytes()` copy.)
- **message**: `postMessage` from the worker's last act to the page's receipt (a transferred buffer or a string). Zero where the worker paints.
- **JSON.parse**, **paint**: Canvas route: parse, then `drawFrame`. Cairo route: `new ImageData` + `putImageData`. These are the JavaScript call times; the browser's own raster work comes later and is not included.
- **end to end**: from the page posting the step message (rAF callback) to the frame painted (page) or received (worker paints). It includes queueing and the message to the worker.
- **fps**: timed frames divided by the time from the first timed post to the last paint, under rAF. **skipped ticks**: rAF callbacks that found the previous step unanswered, in the timed window.
- Native "end to end" is step + encode (or copy) as measured around the call.

### Cases

The 10 heavy examples are the cloud bench's top 10 by IR ops in the 30th frame (`results/pyodide/bench.json`, `top`; the bench counted ops of every gallery example, ranked, took 10): rangoli, kinetic_type, text_dots, noise, write_a_tune, gaussian_and_choice, studios-03_rhythm (script), studios-05_text_as_geometry (script), outlines, poster_series. Three typical Session-1 sketches: `05_text` (text), `06_animation` (a moving circle), `07_bounce`. Sketch files are unchanged copies from `playground-0.2/examples`.

Deviations, all in the harness and none in a sketch:

1. **Canvas route, `studios-03`, `-05`, `-06`:** their marks measure ink with the renderer (`ink_bounds`, a Cairo recording surface). The pure IR renderer cannot, so these three ran with a real `CairoRenderer` used **only** for `ink_bounds` (pycairo loaded lazily, 0.15 s). Their `draw()` time on the Canvas route therefore includes Cairo measuring; drawing still goes through the IR route. In native, `studios-03` fails without this ("ink_bounds needs Cairo").
2. **`sound-02_write_a_tune`:** `pygame.mixer` cannot start in Pyodide, so the cloud spike's silent mixer stub (`harness/s142/mixer_stub.py`, copied from its repo) is installed after `pygame-ce` is loaded (0.65 s, not counted in boot or in the byte table). Nothing is played, so this case's `draw()` includes building the sound's samples. Sound is S-137.
3. **Frames come from the page's rAF clock** (`delta_time` = the gap between rAF timestamps), not the headless platform's fixed rate. The sketches' drawing does not depend on it, as the pixel check shows.

## Pixel checks (is the harness right?)

Method: a first pass of 30 frames per case at 1x; after frame 30 (a script: after its run) the canvas is read back with `getImageData`, saved as PNG, and compared with the golden (`tests/golden`, RGB) in `tools/s142_pixels.py`. Canvas route: S-135's measures (`tools/compare.py`: share of pixels differing by more than 8, mean absolute difference, edges only). Not checked at 2x (no 2x goldens for these sketches). `sound-02` has no golden.

| route / where | cases with a golden | byte-identical | S-135 tolerance | worst case |
|---|---|---|---|---|
| Cairo / page paints | 12 | **12** | - | - |
| Cairo / worker paints | 12 | **12** | - | - |
| Canvas / page paints | 12 | 0 | **12 pass** | rangoli: 2.71 % of pixels differ by more than 8, mean 0.34, max 76, off-edge 0.000 % |
| Canvas / worker paints | 12 | 0 | **12 pass** | identical numbers to page paints |

Native Cairo (`tools/s142_native.py`): the 30th frame is byte-identical to the golden in 12 of 12 as well. Full list: `results_s142/pixels.json`. The Cairo copy swaps B and R and does not un-premultiply; the canvases here are opaque, so premultiplied and straight alpha agree (the byte-identical result confirms it). A sketch with a transparent canvas would need the un-premultiply too (not measured).

## Phase means, to see where the time goes

Mean over cases of the per-case medians (ms), loop and script cases together: heavy = the 10 heavy examples, typical = the 3 Session-1 sketches. Same columns as the per-case tables.

| group | scale | route | draw() | py other | render | encode | wasm copy | message | parse | paint | end to end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| heavy | 1x | native Cairo | 15.5 | 0.1 | 5.6 | - | 0.2 | - | - | - | 21.7 |
| heavy | 1x | Chrome Cairo, page | 46.8 | 0.4 | 13.6 | - | 1.4 | 0.1 | - | 0.3 | 63.8 |
| heavy | 1x | Chrome Cairo, worker | 43.9 | 0.3 | 12.0 | - | 1.2 | 0.2 | - | 0.3 | 58.9 |
| heavy | 1x | native IR | 17.4 | 0.1 | - | 11.1 | - | - | - | - | 29.0 |
| heavy | 1x | Chrome Canvas, page | 51.1 | 0.4 | - | 33.9 | - | 0.3 | 1.1 | 0.8 | 89.0 |
| heavy | 1x | Chrome Canvas, worker | 43.4 | 0.3 | - | 24.9 | - | 0.2 | 0.7 | 0.7 | 71.4 |
| heavy | 2x | native Cairo | 16.8 | 0.1 | 8.5 | - | 1.1 | - | - | - | 27.9 |
| heavy | 2x | Chrome Cairo, page | 50.3 | 0.4 | 18.0 | - | 4.5 | 0.2 | - | 1.3 | 75.3 |
| heavy | 2x | Chrome Cairo, worker | 43.7 | 0.3 | 15.0 | - | 3.8 | 0.2 | - | 1.3 | 67.2 |
| heavy | 2x | native IR | 18.1 | 0.1 | - | 11.9 | - | - | - | - | 30.7 |
| heavy | 2x | Chrome Canvas, page | 42.7 | 0.3 | - | 26.1 | - | 0.3 | 0.8 | 0.6 | 74.3 |
| heavy | 2x | Chrome Canvas, worker | 42.9 | 0.3 | - | 24.5 | - | 0.1 | 0.7 | 0.8 | 71.8 |
| typical | 1x | native Cairo | 0.1 | 0.0 | 1.4 | - | 0.1 | - | - | - | 1.7 |
| typical | 1x | Chrome Cairo, page | 0.5 | 0.2 | 3.4 | - | 1.9 | 0.1 | - | 0.2 | 7.0 |
| typical | 1x | Chrome Canvas, page | 0.5 | 0.2 | - | 4.1 | - | 0.3 | 0.2 | 0.1 | 6.0 |
| typical | 2x | native Cairo | 0.2 | 0.1 | 1.6 | - | 1.1 | - | - | - | 3.3 |
| typical | 2x | Chrome Cairo, page | 0.5 | 0.2 | 5.2 | - | 5.3 | 0.2 | - | 1.6 | 14.1 |
| typical | 2x | Chrome Canvas, page | 0.5 | 0.2 | - | 4.2 | - | 0.2 | 0.1 | 0.1 | 6.0 |

(The "typical" mean contains `05_text`, whose text outlines dominate it; `06` and `07` are 0.1 ms of Python and 2 to 3 ops.)

Browser to native, heavy examples, same cases: `draw()` 3.0x (1x) and 3.0x (2x); Cairo render 2.4x (1x), 2.1x (2x). The cloud spike's Node figures were about 2.5x (Python) and 2.0x (Cairo): Chrome is a little slower than Node here (a shorter, colder run on a busier machine).


## Observations: where the time goes

1. **Python is the biggest cost in both routes, in Chrome as in Node.** `draw()` is 44 to 51 ms of a 59 to 89 ms mean heavy frame. Chrome runs it about 3x slower than native CPython. Neither renderer can change that; it is S-143's subject. Frame budgets (16.7 ms) are missed by every heavy example in every variant (fps 5 to 25), natively too for most (native end to end 6.6 to 82 ms).
2. **Cairo's own cost in wasm is moderate.** Render 2.1x to 2.4x native (13.6 vs 5.6 ms mean at 1x). With the copy and paint it is 15 to 17 ms mean for a heavy frame at 1x, 23 to 25 ms at 2x. The wasm to JS copy grows with pixels (1.4 ms mean at 1x, 4.5 ms at 2x, up to 6.7 ms for rangoli) and is pure overhead of this route. A faster swizzle (WebGL texture upload with a swizzle in the shader, or a SIMD wasm swap) was not tried; the loop used here is plain JavaScript.
3. **The Canvas route's cost is the encode, not the drawing.** JSON encode in Python is 25 to 34 ms mean for the heavy frames (33.9 page / 24.9 worker at 1x: the two figures are the same code; the difference is run-to-run noise), against 0.7 to 1.1 ms for parse and 0.6 to 0.8 ms for the `drawFrame` call. That is the S-136 finding (20 us an op in Python) at a larger scale: `kinetic_type` and `text_dots` have many glyph outline ops. The Canvas draw call time is small but **excludes rasterisation**, which happens after the call returns (see open problems); the Cairo route's `putImageData` has the same limit but uploads finished pixels.
4. **The Canvas route does not depend on the canvas size; the Cairo route does.** Canvas end to end barely moves from 1x to 2x (heavy mean 89 to 74 ms; within noise), while Cairo's render, copy and paint all scale with pixels (render 13.6 to 18.0 ms, copy 1.4 to 4.5 ms, paint 0.3 to 1.3 ms). At 2x the heavy-case ratio is about 1.0. For light sketches the Cairo route is 4 to 9x slower than Canvas at 2x (11 to 12 ms vs 1.3 to 1.8 ms for `06` and `07`), still inside 16.7 ms but with less room for the sketch.
5. **Painting in the worker (OffscreenCanvas) helps a little and mostly through the transfer.** The worker variants were faster than the page variants in most heavy cases (Cairo 58.9 vs 63.8 ms mean, Canvas 71.4 vs 89.0 ms at 1x) and equal at 2x; the message cost was small (0.1 to 0.4 ms) in both, so the gain is the page's parse and paint not sitting in the same rAF as the next post. These differences are inside the run-to-run spread (next table), so treat them as "no loss", not as a measured win. What the worker variant does give for certain is that the page stays free while a frame is drawn.
6. **fps.** Heavy sketches run at 5 to 25 fps under rAF in every variant (limited by Python); the three light sketches hold 57 to 62 fps in all variants except Cairo at 2x (`05_text` 32 fps page / 51 worker, within noise of 16.7 ms frames, with skipped ticks).
7. **Noise.** The same case differs between repeats by up to 2x (spread table above; the first repeat's Canvas 2x run was twice as fast as the later ones in Python time alone). A shared 8 GB laptop with other browsers open is not a stable benchmark host. The routes' ordering is stable only where the gap is large (encode vs render; light sketches).
8. **First load.** Cairo route: median 7.6 to 9.3 s to the last boot step, 8.3 to 9.9 s to the first frame, from a cold profile and the real network (Pyodide from jsDelivr). Canvas route: 7.7 to 8.7 s boot, 8.6 to 9.5 s first frame. Pycairo adds 0.1 to 0.15 s of install and **496,371 bytes**; the Cairo route downloads 13.9 MB against 13.4 MB (3.7 %). Both include 4.5 MB of fonts (all seven bundled files were fetched; S-139 can lazy-load them), 7.5 MB of Pyodide core, and the uharfbuzz wheel (981,875 bytes, size from the file: the browser did not report cross-origin PyPI sizes). Bytes are the browser's encoded body sizes for jsDelivr and the files' sizes for localhost; compression on a real server would change the localhost entries. `pygame-ce` (loaded only for `sound-02`) is not in the byte table: its download size was not measured. The load timings spread over about 1.5 s between runs; the Cairo route's extra time is inside that spread.

## Summary

| question | answer |
|---|---|
| Is Cairo in wasm slower than Canvas 2D in Chrome? | Not on heavy sketches: end to end it was lower in 11 of 13 cases at 1x and about equal at 2x. Python's draw() and (for Canvas) the JSON encode dominate. |
| Where is Cairo's route slower? | Light sketches at 2x: 11 to 12 ms vs about 1.5 ms (copy of 1280x800 pixels, render, ImageData). |
| Is the Cairo route exact? | Yes: 12 of 12 byte-identical at 1x, in both painting variants and natively. Canvas: 12 of 12 within S-135's tolerance. |
| What does the Canvas route lack? | `ink_bounds` (marks, the S-132 vocabulary, three of the ten heavy examples), pictures and pixels (binary payloads not wired in this harness), the controls panel, filters. |
| What does it cost to load? | Cairo route +496 KB and +0.1 to 0.15 s; both routes ~13.5 to 14 MB, 8 to 10 s cold here. |

## Open problems

1. **Headless Chrome, no GPU, no vsync.** Raster and scan-out are absent from every number. Canvas 2D commands are recorded and rasterised later (in headless: software), so the Canvas route's `paint` is a lower bound; S-135 measured 20 to 60 ms for shadows. `putImageData` also defers the upload. The achieved fps under rAF includes whatever work blocks the main thread, but not work on the raster or GPU thread. A visible window on the maintainer's display, or a `getImageData(0,0,1,1)` after each frame (not used because it changes Chrome's canvas mode), would show it. **Not measured.**
2. **Noisy host.** Three repeats; medians; differences under about 25 % between routes should not be read. A quiet machine and more repeats (or a CPU-pinned run) were not tried.
3. **One browser, one machine.** Chrome 154 on one laptop. Not tested: Firefox, Safari, Edge, a Chromebook, battery power, background-tab throttling.
4. **2x pixels not checked.** The pixel check ran at 1x only. 2x frames are not compared with goldens (the cloud spike's rendering at 2x is the reference for Cairo).
5. **Premultiplied alpha.** The Cairo copy does not un-premultiply; sketches with a transparent canvas, `erase`, or alpha layers shown over the page need it, which adds to the copy cost. Not measured.
6. **Canvas cases that could not run as designed.** Pictures, pixel ops and the controls panel: `Host.encode` raises for Image and Pixels ops (no binary payloads in this harness); none of the 13 cases use them. Rangoli creates controls (buttons, checkboxes); it ran in both routes and passes the pixel check, but the headless-style platform here has no controls panel, so the panel itself is untested.
7. **`sound-02`** ran with a stubbed mixer; it is the slowest case (5 fps) because `draw()` is 45 ms natively and about 177 ms in wasm (building the waveform each frame). Real browser audio is S-137.
8. **Unmeasured:** pygame-ce's download size; the memory use of the two routes (wasm heap and canvases); frame time distribution over long runs (30 frames only); JIT warm-up (the first frames are slower; warm-up was 5 frames as in the cloud bench); the Cairo route with a worker-side `ImageBitmap` or WebGL upload instead of `putImageData`.
9. **funground base.** The loop split (`start/step/finish`) is on `spike/s136-loop`, not yet in `release-0.2-web`; `f.run`/`f.show` are patched from outside as in S-133/S-136.

## Files

`harness/s142/` (`run.html`, `worker.js`, `shim.py`, `mixer_stub.py`; `dist/` is git-ignored and made by `tools/build_s142_bundle.py`), `tools/build_s142_bundle.py`, `tools/run_s142.py` (one browser configuration, by PID), `tools/s142_native.py` (native column), `tools/s142_pixels.py` (golden comparison), `tools/s142_report.py` (these tables). Raw results: `results_s142/` (git-ignored: `browser-<route>-<where>-<scale>x[.r2|.r3].json`, `native-<route>-<scale>x[.r2|.r3].json`, `snaps/`, `pixels.json`, `tables.md`).

Re-run: `build_s142_bundle.py`, then `run_s142.py --route cairo|canvas --where main|worker [--dpr 2] [--no-check]`, `s142_native.py --route cairo|canvas --scale 1|2`, `s142_pixels.py`, `s142_report.py`.

## All tables

(Generated by `tools/s142_report.py` from the 3 repeats; the first block is the summary, then first load, then one table per case.)

## Summary: end-to-end frame time, median of 3 runs (ms) and achieved fps

### 1x

| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) | fps Cairo page / worker | fps Canvas page / worker | Cairo(page) / Canvas(page) |
|---|---|---|---|---|---|---|---|---|---|
| projects-02_rangoli | 8.9 | 39.7 | 32.9 | 12.1 | 57.1 | 44.5 | 22 / 24 | 16 / 21 | 0.70 |
| projects-06_kinetic_type | 36.8 | 118.4 | 110.9 | 43.3 | 153.5 | 128.9 | 8 / 7 | 6 / 7 | 0.77 |
| text-09_text_dots | 15.7 | 53.6 | 55.6 | 23.7 | 157.3 | 68.8 | 16 / 15 | 6 / 13 | 0.34 |
| randomness-03_noise | 17.7 | 46.4 | 39.4 | 20.0 | 61.3 | 46.3 | 18 / 21 | 15 / 18 | 0.76 |
| sound-02_write_a_tune | 60.7 | 186.8 | 175.9 | 92.1 | 197.9 | 196.6 | 5 / 5 | 5 / 5 | 0.94 |
| randomness-02_gaussian_and_choice | 15.2 | 33.6 | 32.6 | 19.3 | 44.2 | 41.0 | 24 / 25 | 20 / 21 | 0.76 |
| studios-03_rhythm | 6.6 | 27.6 | 26.2 | 11.8 | 35.6 | 34.8 | - / - | - / - | 0.78 |
| studios-05_text_as_geometry | 14.0 | 28.6 | 27.8 | 12.2 | 38.4 | 34.1 | - / - | - / - | 0.74 |
| paths-06_outlines | 15.6 | 46.5 | 41.9 | 19.0 | 58.6 | 51.0 | 20 / 21 | 15 / 17 | 0.79 |
| studios-06_poster_series | 25.8 | 56.4 | 46.0 | 36.6 | 86.3 | 68.4 | 16 / 19 | 11 / 13 | 0.65 |
| s1-05_text | 4.7 | 11.5 | 11.8 | 4.0 | 14.8 | 12.5 | 57 / 55 | 52 / 49 | 0.78 |
| s1-06_animation | 0.2 | 4.8 | 4.5 | 0.1 | 1.6 | 1.7 | 61 / 60 | 62 / 62 | 3.00 |
| s1-07_bounce | 0.2 | 4.7 | 3.5 | 0.1 | 1.5 | 1.6 | 62 / 61 | 62 / 62 | 3.13 |

Mean Cairo/Canvas ratio of end-to-end medians (page paints), cases both routes ran: 1.09 over 13 cases.

### 2x

| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) | fps Cairo page / worker | fps Canvas page / worker | Cairo(page) / Canvas(page) |
|---|---|---|---|---|---|---|---|---|---|
| projects-02_rangoli | 12.9 | 51.9 | 44.6 | 12.9 | 49.7 | 42.3 | 17 / 18 | 19 / 21 | 1.04 |
| projects-06_kinetic_type | 39.5 | 146.7 | 123.2 | 49.7 | 140.6 | 127.2 | 7 / 7 | 6 / 7 | 1.04 |
| text-09_text_dots | 19.8 | 72.8 | 58.7 | 36.6 | 75.6 | 72.9 | 12 / 14 | 12 / 12 | 0.96 |
| randomness-03_noise | 16.8 | 53.4 | 50.7 | 19.4 | 49.2 | 49.2 | 16 / 17 | 18 / 17 | 1.09 |
| sound-02_write_a_tune | 82.2 | 197.5 | 185.6 | 92.8 | 186.3 | 199.3 | 5 / 5 | 5 / 5 | 1.06 |
| randomness-02_gaussian_and_choice | 19.3 | 40.1 | 35.4 | 16.7 | 42.9 | 37.2 | 23 / 24 | 21 / 22 | 0.93 |
| studios-03_rhythm | 14.9 | 35.2 | 36.9 | 9.1 | 30.5 | 28.5 | - / - | - / - | 1.15 |
| studios-05_text_as_geometry | 14.9 | 37.2 | 32.5 | 11.8 | 32.5 | 33.9 | - / - | - / - | 1.14 |
| paths-06_outlines | 26.6 | 54.5 | 46.4 | 22.2 | 57.7 | 52.5 | 16 / 20 | 16 / 17 | 0.94 |
| studios-06_poster_series | 32.5 | 63.3 | 57.5 | 35.5 | 78.2 | 74.8 | 14 / 16 | 12 / 12 | 0.81 |
| s1-05_text | 5.5 | 19.6 | 15.1 | 3.6 | 15.3 | 14.4 | 32 / 51 | 45 / 45 | 1.28 |
| s1-06_animation | 1.9 | 11.6 | 11.9 | 0.1 | 1.3 | 1.8 | 58 / 53 | 62 / 60 | 8.92 |
| s1-07_bounce | 2.6 | 11.1 | 11.9 | 0.0 | 1.4 | 1.5 | 57 / 55 | 62 / 60 | 7.93 |

Mean Cairo/Canvas ratio of end-to-end medians (page paints), cases both routes ran: 2.18 over 13 cases.

### Spread of the end-to-end median across the 3 runs (min - max, ms), Chrome, page paints, 1x

| case | Cairo | Canvas |
|---|---|---|
| projects-02_rangoli | 34.1 - 68.5 | 53.4 - 61.2 |
| projects-06_kinetic_type | 106.6 - 175.9 | 132.3 - 220.8 |
| text-09_text_dots | 48.4 - 58.3 | 88.6 - 213.6 |
| randomness-03_noise | 36.6 - 49.4 | 59.7 - 102.1 |
| sound-02_write_a_tune | 181.0 - 366.5 | 192.1 - 230.9 |
| randomness-02_gaussian_and_choice | 32.3 - 69.8 | 43.7 - 55.7 |
| studios-03_rhythm | 26.7 - 40.5 | 35.3 - 46.2 |
| studios-05_text_as_geometry | 28.0 - 39.3 | 33.2 - 41.1 |
| paths-06_outlines | 45.0 - 65.4 | 58.5 - 58.8 |
| studios-06_poster_series | 51.6 - 71.0 | 85.9 - 86.3 |
| s1-05_text | 6.8 - 18.7 | 12.5 - 14.9 |
| s1-06_animation | 4.2 - 5.5 | 1.2 - 1.6 |
| s1-07_bounce | 4.3 - 5.5 | 1.2 - 1.5 |

## First load (cold: fresh Chrome profile for every run; Pyodide and PyPI from the real network)

| route / where / dpr | Pyodide load | fonttools+micropip | uharfbuzz (micropip, PyPI) | pathops | pycairo | funground+fonts fetch | import funground | boot total | first frame since navigation |
|---|---|---|---|---|---|---|---|---|---|
| cairo / main / 1x (3 runs) | 5.85 s | 0.59 s | 1.21 s | 0.09 s | 0.15 s | 0.30 s | 0.51 s | 9.26 s | 9.93 s |
| cairo / main / 2x (3 runs) | 4.64 s | 0.86 s | 1.20 s | 0.08 s | 0.12 s | 0.28 s | 0.69 s | 7.62 s | 8.30 s |
| cairo / worker / 1x (3 runs) | 5.11 s | 1.06 s | 1.18 s | 0.08 s | 0.12 s | 0.34 s | 0.65 s | 8.16 s | 9.00 s |
| cairo / worker / 2x (3 runs) | 4.98 s | 0.57 s | 1.60 s | 0.07 s | 0.12 s | 0.30 s | 0.63 s | 8.42 s | 9.27 s |
| canvas / main / 1x (3 runs) | 4.92 s | 0.68 s | 1.34 s | 0.07 s | - s | 0.31 s | 0.67 s | 8.04 s | 8.76 s |
| canvas / main / 2x (3 runs) | 4.74 s | 0.65 s | 1.22 s | 0.07 s | - s | 0.26 s | 0.53 s | 7.67 s | 8.59 s |
| canvas / worker / 1x (3 runs) | 4.97 s | 1.35 s | 1.21 s | 0.08 s | - s | 0.29 s | 0.59 s | 8.66 s | 9.48 s |
| canvas / worker / 2x (3 runs) | 4.82 s | 1.40 s | 1.14 s | 0.06 s | - s | 0.29 s | 0.55 s | 8.53 s | 9.23 s |

Bytes downloaded at boot (encoded body sizes; localhost files are uncompressed; Pyodide's come gzip/brotli-free as reported):

| component | cairo route | canvas route |
|---|---|---|
| Pyodide core (pyodide.mjs, lock, stdlib zip, asm.wasm, asm.mjs) | 7,470,081 | 7,470,081 |
| uharfbuzz wheel (PyPI; size not reported by the browser) | 981,875 | 981,875 |
| skia-pathops wheel | 172,919 | 172,919 |
| pycairo wheel | 496,371 | 0 |
| funground.zip | 263,609 | 263,609 |
| shim, mixer stub, fonts.json | 14,682 | 14,682 |
| fonts (7 files, all loaded) | 4,543,184 | 4,543,184 |
| **total** | **13,942,721** | **13,446,350** |

## Tables per case (median / p95 in ms; fps and skipped ticks are for the 30 timed frames under rAF)

### projects-02_rangoli

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.4 / 5.2 | 0.1 / 0.1 | 4.1 / 4.6 | 0.0 / 0.0 | 0.3 / 0.3 | - | - | - | 8.9 / 9.9 | - | - |
| 1x | Chrome Cairo, page paints | 22.0 / 26.9 | 0.5 / 0.8 | 15.2 / 21.9 | 0.0 / 0.0 | 1.7 / 2.7 | 0.1 / 0.3 | - | 0.3 / 0.5 | 39.7 / 52.8 | 21.6 | 56 |
| 1x | Chrome Cairo, worker paints | 18.5 / 23.1 | 0.4 / 0.6 | 13.1 / 16.7 | 0.0 / 0.0 | 1.4 / 2.6 | 0.2 / 0.3 | - | 0.3 / 1.1 | 32.9 / 42.6 | 24.5 | 45 |
| 1x | native IR (encode only) | 4.3 / 4.7 | 0.1 / 0.1 | 0.0 / 0.0 | 7.6 / 10.6 | 0.0 / 0.0 | - | - | - | 12.1 / 15.2 | - | - |
| 1x | Chrome Canvas, page paints | 19.0 / 30.4 | 0.4 / 0.8 | 0.0 / 0.0 | 33.8 / 43.4 | - | 0.3 / 0.5 | 1.0 / 2.1 | 0.7 / 1.7 | 57.1 / 70.9 | 15.8 | 85 |
| 1x | Chrome Canvas, worker paints | 17.4 / 21.6 | 0.3 / 0.5 | 0.0 / 0.0 | 23.6 / 33.3 | - | 0.2 / 0.3 | 0.6 / 1.1 | 0.6 / 1.2 | 44.5 / 56.0 | 20.6 | 60 |
| 2x | native Cairo | 4.6 / 5.4 | 0.1 / 0.2 | 6.8 / 8.3 | 0.0 / 0.0 | 0.9 / 1.7 | - | - | - | 12.9 / 16.2 | - | - |
| 2x | Chrome Cairo, page paints | 21.4 / 29.5 | 0.5 / 0.7 | 21.9 / 27.7 | 0.0 / 0.0 | 6.7 / 8.7 | 0.2 / 0.4 | - | 1.5 / 2.1 | 51.9 / 65.3 | 17.1 | 78 |
| 2x | Chrome Cairo, worker paints | 18.8 / 26.6 | 0.4 / 0.7 | 18.0 / 24.7 | 0.0 / 0.0 | 3.7 / 6.7 | 0.2 / 0.3 | - | 1.3 / 2.4 | 44.6 / 56.4 | 17.7 | 74 |
| 2x | native IR (encode only) | 4.5 / 6.1 | 0.1 / 0.3 | 0.0 / 0.0 | 7.9 / 9.8 | 0.0 / 0.0 | - | - | - | 12.9 / 15.4 | - | - |
| 2x | Chrome Canvas, page paints | 17.4 / 27.7 | 0.3 / 0.6 | 0.0 / 0.0 | 26.3 / 34.1 | - | 0.3 / 0.5 | 0.8 / 1.9 | 0.7 / 1.2 | 49.7 / 61.7 | 18.8 | 69 |
| 2x | Chrome Canvas, worker paints | 18.0 / 22.9 | 0.4 / 0.6 | 0.0 / 0.0 | 21.3 / 33.6 | - | 0.1 / 0.2 | 0.6 / 1.2 | 0.6 / 1.1 | 42.3 / 61.4 | 20.8 | 59 |

### projects-06_kinetic_type

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 31.4 / 46.8 | 0.1 / 0.2 | 5.2 / 6.4 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 36.8 / 52.8 | - | - |
| 1x | Chrome Cairo, page paints | 101.5 / 137.8 | 0.7 / 1.3 | 15.0 / 22.9 | 0.0 / 0.0 | 1.0 / 1.5 | 0.1 / 0.2 | - | 0.2 / 0.3 | 118.4 / 157.0 | 7.9 | 204 |
| 1x | Chrome Cairo, worker paints | 97.9 / 169.6 | 0.7 / 1.6 | 13.8 / 29.6 | 0.0 / 0.0 | 0.9 / 2.2 | 0.2 / 0.3 | - | 0.2 / 0.7 | 110.9 / 186.5 | 7.5 | 218 |
| 1x | native IR (encode only) | 30.9 / 32.8 | 0.2 / 0.4 | 0.0 / 0.0 | 12.3 / 15.4 | 0.0 / 0.0 | - | - | - | 43.3 / 47.1 | - | - |
| 1x | Chrome Canvas, page paints | 111.5 / 146.7 | 0.8 / 1.4 | 0.0 / 0.0 | 39.3 / 57.7 | - | 0.4 / 0.5 | 1.1 / 2.3 | 0.8 / 1.9 | 153.5 / 219.6 | 6.0 | 280 |
| 1x | Chrome Canvas, worker paints | 91.0 / 107.3 | 0.6 / 1.1 | 0.0 / 0.0 | 36.1 / 50.6 | - | 0.2 / 0.3 | 1.0 / 1.8 | 0.8 / 1.2 | 128.9 / 151.3 | 7.2 | 227 |
| 2x | native Cairo | 30.8 / 32.8 | 0.2 / 0.2 | 7.6 / 9.2 | 0.0 / 0.0 | 0.6 / 1.0 | - | - | - | 39.5 / 41.8 | - | - |
| 2x | Chrome Cairo, page paints | 114.2 / 165.0 | 0.8 / 1.5 | 22.6 / 33.2 | 0.0 / 0.0 | 3.2 / 5.0 | 0.2 / 0.5 | - | 0.8 / 1.3 | 146.7 / 203.7 | 6.7 | 246 |
| 2x | Chrome Cairo, worker paints | 97.9 / 167.2 | 0.7 / 1.3 | 19.4 / 32.2 | 0.0 / 0.0 | 2.8 / 5.3 | 0.2 / 0.3 | - | 1.0 / 1.4 | 123.2 / 194.3 | 7.1 | 230 |
| 2x | native IR (encode only) | 34.3 / 41.0 | 0.2 / 0.4 | 0.0 / 0.0 | 14.6 / 23.0 | 0.0 / 0.0 | - | - | - | 49.7 / 71.4 | - | - |
| 2x | Chrome Canvas, page paints | 98.2 / 160.7 | 0.6 / 1.0 | 0.0 / 0.0 | 36.5 / 60.7 | - | 0.4 / 0.6 | 0.9 / 2.7 | 0.6 / 1.7 | 140.6 / 208.9 | 6.4 | 260 |
| 2x | Chrome Canvas, worker paints | 92.2 / 121.5 | 0.5 / 1.0 | 0.0 / 0.0 | 33.9 / 42.3 | - | 0.2 / 0.3 | 1.1 / 1.8 | 0.8 / 1.4 | 127.2 / 174.4 | 7.0 | 236 |

### text-09_text_dots

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 10.3 / 11.1 | 0.1 / 0.1 | 5.2 / 6.1 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 15.7 / 18.0 | - | - |
| 1x | Chrome Cairo, page paints | 36.2 / 50.1 | 0.6 / 0.8 | 15.4 / 20.4 | 0.0 / 0.0 | 0.9 / 1.8 | 0.0 / 0.1 | - | 0.2 / 0.3 | 53.6 / 70.9 | 16.0 | 86 |
| 1x | Chrome Cairo, worker paints | 36.4 / 50.9 | 0.5 / 1.3 | 15.4 / 29.8 | 0.0 / 0.0 | 1.1 / 2.6 | 0.2 / 0.2 | - | 0.2 / 0.4 | 55.6 / 80.7 | 14.9 | 91 |
| 1x | native IR (encode only) | 10.9 / 12.4 | 0.1 / 0.2 | 0.0 / 0.0 | 12.5 / 14.2 | 0.0 / 0.0 | - | - | - | 23.7 / 26.8 | - | - |
| 1x | Chrome Canvas, page paints | 73.4 / 96.1 | 0.9 / 3.2 | 0.0 / 0.0 | 79.6 / 106.7 | - | 0.4 / 1.9 | 2.6 / 4.6 | 1.9 / 3.6 | 157.3 / 198.6 | 6.2 | 263 |
| 1x | Chrome Canvas, worker paints | 33.4 / 46.8 | 0.5 / 0.8 | 0.0 / 0.0 | 28.7 / 45.2 | - | 0.2 / 0.3 | 0.9 / 1.7 | 0.8 / 1.5 | 68.8 / 89.5 | 12.9 | 114 |
| 2x | native Cairo | 11.0 / 13.6 | 0.2 / 0.2 | 7.2 / 8.7 | 0.0 / 0.0 | 0.8 / 1.4 | - | - | - | 19.8 / 22.7 | - | - |
| 2x | Chrome Cairo, page paints | 46.1 / 60.1 | 0.5 / 1.0 | 20.8 / 32.7 | 0.0 / 0.0 | 3.4 / 5.5 | 0.2 / 0.3 | - | 0.9 / 1.4 | 72.8 / 91.2 | 12.2 | 122 |
| 2x | Chrome Cairo, worker paints | 34.8 / 48.9 | 0.6 / 1.0 | 17.7 / 25.5 | 0.0 / 0.0 | 3.1 / 5.6 | 0.2 / 0.3 | - | 1.1 / 2.0 | 58.7 / 82.2 | 14.5 | 98 |
| 2x | native IR (encode only) | 16.8 / 23.3 | 0.2 / 0.7 | 0.0 / 0.0 | 19.7 / 27.2 | 0.0 / 0.0 | - | - | - | 36.6 / 49.0 | - | - |
| 2x | Chrome Canvas, page paints | 36.7 / 43.1 | 0.5 / 0.8 | 0.0 / 0.0 | 33.2 / 41.6 | - | 0.3 / 0.4 | 1.0 / 1.6 | 0.8 / 1.7 | 75.6 / 87.3 | 12.3 | 120 |
| 2x | Chrome Canvas, worker paints | 33.1 / 45.1 | 0.5 / 0.9 | 0.0 / 0.0 | 33.0 / 49.1 | - | 0.1 / 0.2 | 1.1 / 1.6 | 0.9 / 1.6 | 72.9 / 92.7 | 12.3 | 121 |

### randomness-03_noise

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 16.0 / 28.6 | 0.1 / 0.2 | 1.5 / 2.8 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 17.7 / 31.4 | - | - |
| 1x | Chrome Cairo, page paints | 39.5 / 51.0 | 0.4 / 0.7 | 3.8 / 5.9 | 0.0 / 0.0 | 1.0 / 1.4 | 0.1 / 0.2 | - | 0.2 / 0.3 | 46.4 / 58.7 | 17.8 | 73 |
| 1x | Chrome Cairo, worker paints | 32.7 / 52.6 | 0.4 / 0.9 | 3.2 / 6.1 | 0.0 / 0.0 | 0.9 / 1.5 | 0.1 / 0.2 | - | 0.2 / 0.3 | 39.4 / 58.2 | 21.4 | 56 |
| 1x | native IR (encode only) | 13.0 / 20.0 | 0.2 / 0.3 | 0.0 / 0.0 | 6.3 / 8.7 | 0.0 / 0.0 | - | - | - | 20.0 / 26.8 | - | - |
| 1x | Chrome Canvas, page paints | 39.5 / 50.1 | 0.5 / 1.3 | 0.0 / 0.0 | 18.5 / 23.4 | - | 0.3 / 0.4 | 0.4 / 0.6 | 1.0 / 1.6 | 61.3 / 78.8 | 15.1 | 92 |
| 1x | Chrome Canvas, worker paints | 33.1 / 42.7 | 0.4 / 0.6 | 0.0 / 0.0 | 12.0 / 19.1 | - | 0.2 / 0.3 | 0.3 / 0.5 | 0.7 / 1.2 | 46.3 / 65.1 | 18.0 | 73 |
| 2x | native Cairo | 12.9 / 20.2 | 0.2 / 0.2 | 2.3 / 3.9 | 0.0 / 0.0 | 1.0 / 1.4 | - | - | - | 16.8 / 24.3 | - | - |
| 2x | Chrome Cairo, page paints | 42.0 / 53.6 | 0.5 / 0.8 | 5.8 / 9.3 | 0.0 / 0.0 | 3.6 / 6.6 | 0.2 / 0.5 | - | 1.0 / 1.9 | 53.4 / 70.4 | 15.8 | 89 |
| 2x | Chrome Cairo, worker paints | 36.8 / 44.9 | 0.5 / 0.8 | 6.1 / 8.9 | 0.0 / 0.0 | 3.5 / 6.1 | 0.2 / 0.3 | - | 1.1 / 1.7 | 50.7 / 58.0 | 17.4 | 78 |
| 2x | native IR (encode only) | 12.6 / 22.3 | 0.1 / 0.2 | 0.0 / 0.0 | 6.1 / 10.2 | 0.0 / 0.0 | - | - | - | 19.4 / 33.9 | - | - |
| 2x | Chrome Canvas, page paints | 32.3 / 39.8 | 0.4 / 0.9 | 0.0 / 0.0 | 15.0 / 20.0 | - | 0.3 / 0.4 | 0.3 / 0.5 | 0.7 / 1.5 | 49.2 / 60.7 | 17.5 | 76 |
| 2x | Chrome Canvas, worker paints | 32.2 / 44.3 | 0.4 / 0.8 | 0.0 / 0.0 | 14.9 / 21.4 | - | 0.1 / 0.3 | 0.3 / 0.6 | 1.0 / 1.7 | 49.2 / 65.4 | 17.2 | 78 |

### sound-02_write_a_tune

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 57.2 / 84.5 | 0.1 / 0.2 | 3.3 / 6.1 | 0.0 / 0.0 | 0.1 / 0.3 | - | - | - | 60.7 / 88.0 | - | - |
| 1x | Chrome Cairo, page paints | 177.3 / 198.9 | 0.3 / 0.5 | 9.3 / 12.3 | 0.0 / 0.0 | 1.1 / 1.8 | 0.1 / 0.3 | - | 0.2 / 0.3 | 186.8 / 211.3 | 5.2 | 331 |
| 1x | Chrome Cairo, worker paints | 167.3 / 218.4 | 0.2 / 0.4 | 7.1 / 11.0 | 0.0 / 0.0 | 0.8 / 1.7 | 0.2 / 0.3 | - | 0.2 / 0.4 | 175.9 / 228.1 | 5.5 | 309 |
| 1x | native IR (encode only) | 81.7 / 100.4 | 0.1 / 0.2 | 0.0 / 0.0 | 10.0 / 15.8 | 0.0 / 0.0 | - | - | - | 92.1 / 113.3 | - | - |
| 1x | Chrome Canvas, page paints | 174.1 / 198.6 | 0.3 / 0.5 | 0.0 / 0.0 | 21.8 / 27.5 | - | 0.2 / 0.4 | 0.6 / 0.9 | 0.7 / 1.0 | 197.9 / 221.6 | 5.0 | 340 |
| 1x | Chrome Canvas, worker paints | 173.5 / 196.1 | 0.3 / 0.5 | 0.0 / 0.0 | 20.8 / 26.4 | - | 0.2 / 0.4 | 0.6 / 1.1 | 0.9 / 1.4 | 196.6 / 226.2 | 5.1 | 334 |
| 2x | native Cairo | 74.5 / 108.7 | 0.1 / 0.2 | 5.9 / 11.0 | 0.0 / 0.0 | 0.9 / 1.8 | - | - | - | 82.2 / 115.1 | - | - |
| 2x | Chrome Cairo, page paints | 181.6 / 218.1 | 0.3 / 0.4 | 11.9 / 16.9 | 0.0 / 0.0 | 3.7 / 6.3 | 0.1 / 0.3 | - | 1.1 / 1.8 | 197.5 / 237.6 | 5.0 | 339 |
| 2x | Chrome Cairo, worker paints | 168.8 / 209.4 | 0.3 / 0.5 | 9.2 / 13.6 | 0.0 / 0.0 | 3.3 / 5.0 | 0.2 / 0.3 | - | 1.2 / 1.8 | 185.6 / 228.7 | 5.3 | 316 |
| 2x | native IR (encode only) | 80.7 / 98.9 | 0.1 / 0.1 | 0.0 / 0.0 | 11.6 / 14.2 | 0.0 / 0.0 | - | - | - | 92.8 / 112.2 | - | - |
| 2x | Chrome Canvas, page paints | 159.7 / 184.4 | 0.2 / 0.4 | 0.0 / 0.0 | 19.5 / 25.4 | - | 0.3 / 0.4 | 0.5 / 0.9 | 0.6 / 1.2 | 186.3 / 211.1 | 5.4 | 317 |
| 2x | Chrome Canvas, worker paints | 173.3 / 241.4 | 0.3 / 0.4 | 0.0 / 0.0 | 22.1 / 32.2 | - | 0.1 / 0.3 | 0.6 / 1.2 | 0.9 / 1.6 | 199.3 / 262.4 | 4.7 | 363 |

### randomness-02_gaussian_and_choice

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 10.3 / 14.3 | 0.1 / 0.2 | 4.5 / 6.1 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 15.2 / 20.7 | - | - |
| 1x | Chrome Cairo, page paints | 23.9 / 32.1 | 0.5 / 0.7 | 7.6 / 9.6 | 0.0 / 0.0 | 1.1 / 1.8 | 0.1 / 0.2 | - | 0.2 / 0.3 | 33.6 / 42.7 | 23.9 | 48 |
| 1x | Chrome Cairo, worker paints | 22.5 / 27.3 | 0.4 / 0.7 | 7.3 / 9.0 | 0.0 / 0.0 | 1.0 / 1.5 | 0.1 / 0.2 | - | 0.2 / 0.3 | 32.6 / 38.2 | 25.1 | 42 |
| 1x | native IR (encode only) | 10.9 / 14.2 | 0.1 / 0.2 | 0.0 / 0.0 | 9.3 / 11.4 | 0.0 / 0.0 | - | - | - | 19.3 / 25.8 | - | - |
| 1x | Chrome Canvas, page paints | 24.6 / 29.9 | 0.5 / 0.8 | 0.0 / 0.0 | 17.8 / 19.8 | - | 0.2 / 0.4 | 0.4 / 0.6 | 0.4 / 0.6 | 44.2 / 58.2 | 20.5 | 60 |
| 1x | Chrome Canvas, worker paints | 23.6 / 29.5 | 0.4 / 0.6 | 0.0 / 0.0 | 15.9 / 19.1 | - | 0.2 / 0.3 | 0.4 / 0.5 | 0.5 / 0.8 | 41.0 / 48.6 | 21.3 | 56 |
| 2x | native Cairo | 8.3 / 16.6 | 0.2 / 0.3 | 7.6 / 13.8 | 0.0 / 0.0 | 1.2 / 2.1 | - | - | - | 19.3 / 31.7 | - | - |
| 2x | Chrome Cairo, page paints | 23.8 / 28.4 | 0.5 / 0.7 | 11.5 / 13.1 | 0.0 / 0.0 | 3.4 / 4.4 | 0.2 / 0.2 | - | 1.0 / 1.4 | 40.1 / 47.3 | 22.7 | 52 |
| 2x | Chrome Cairo, worker paints | 17.4 / 25.4 | 0.4 / 0.6 | 9.0 / 14.6 | 0.0 / 0.0 | 2.8 / 5.3 | 0.2 / 0.4 | - | 1.1 / 1.9 | 35.4 / 45.7 | 23.7 | 49 |
| 2x | native IR (encode only) | 7.3 / 13.6 | 0.1 / 0.2 | 0.0 / 0.0 | 7.5 / 10.2 | 0.0 / 0.0 | - | - | - | 16.7 / 24.4 | - | - |
| 2x | Chrome Canvas, page paints | 24.9 / 27.7 | 0.4 / 0.5 | 0.0 / 0.0 | 16.9 / 18.4 | - | 0.2 / 0.3 | 0.4 / 0.9 | 0.4 / 0.9 | 42.9 / 47.8 | 21.2 | 58 |
| 2x | Chrome Canvas, worker paints | 20.0 / 27.5 | 0.4 / 0.8 | 0.0 / 0.0 | 13.4 / 22.2 | - | 0.1 / 0.3 | 0.3 / 0.5 | 0.5 / 0.8 | 37.2 / 53.1 | 22.1 | 53 |

### studios-03_rhythm

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 1.9 / 4.0 | 0.0 / 0.0 | 3.3 / 6.5 | 0.0 / 0.0 | 0.4 / 0.8 | - | - | - | 6.6 / 13.3 | - | - |
| 1x | Chrome Cairo, page paints | 8.0 / 13.3 | 0.0 / 0.0 | 11.7 / 17.5 | 0.0 / 0.0 | 2.5 / 4.1 | 0.1 / 0.3 | - | 0.7 / 0.9 | 27.6 / 35.1 | - | - |
| 1x | Chrome Cairo, worker paints | 8.4 / 13.7 | 0.0 / 0.0 | 11.3 / 14.3 | 0.0 / 0.0 | 2.3 / 3.0 | 0.2 / 0.3 | - | 0.9 / 1.0 | 26.2 / 34.3 | - | - |
| 1x | native IR (encode only) | 2.1 / 3.7 | 0.0 / 0.0 | 0.0 / 0.0 | 7.8 / 11.9 | 0.0 / 0.0 | - | - | - | 11.8 / 17.0 | - | - |
| 1x | Chrome Canvas, page paints | 8.1 / 10.4 | 0.0 / 0.0 | 0.0 / 0.0 | 21.3 / 30.9 | - | 0.3 / 0.5 | 0.8 / 1.4 | 0.7 / 1.1 | 35.6 / 47.7 | - | - |
| 1x | Chrome Canvas, worker paints | 7.5 / 10.4 | 0.0 / 0.0 | 0.0 / 0.0 | 21.0 / 29.0 | - | 0.2 / 0.3 | 0.7 / 1.1 | 0.6 / 0.9 | 34.8 / 42.7 | - | - |
| 2x | native Cairo | 2.2 / 3.8 | 0.0 / 0.0 | 6.7 / 9.4 | 0.0 / 0.0 | 1.8 / 2.0 | - | - | - | 14.9 / 17.9 | - | - |
| 2x | Chrome Cairo, page paints | 9.4 / 12.8 | 0.0 / 0.0 | 14.9 / 16.5 | 0.0 / 0.0 | 6.9 / 10.9 | 0.2 / 0.7 | - | 2.6 / 4.3 | 35.2 / 46.0 | - | - |
| 2x | Chrome Cairo, worker paints | 9.4 / 10.9 | 0.0 / 0.0 | 12.6 / 15.5 | 0.0 / 0.0 | 8.0 / 8.3 | 0.2 / 0.3 | - | 2.3 / 3.1 | 36.9 / 41.3 | - | - |
| 2x | native IR (encode only) | 1.9 / 3.9 | 0.0 / 0.0 | 0.0 / 0.0 | 6.2 / 12.2 | 0.0 / 0.0 | - | - | - | 9.1 / 17.8 | - | - |
| 2x | Chrome Canvas, page paints | 7.2 / 9.1 | 0.0 / 0.0 | 0.0 / 0.0 | 19.1 / 26.7 | - | 0.2 / 0.3 | 0.8 / 0.9 | 0.7 / 0.9 | 30.5 / 39.1 | - | - |
| 2x | Chrome Canvas, worker paints | 6.0 / 9.1 | 0.0 / 0.0 | 0.0 / 0.0 | 14.4 / 23.7 | - | 0.2 / 0.3 | 0.5 / 1.1 | 0.7 / 1.1 | 28.5 / 40.4 | - | - |

### studios-05_text_as_geometry

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 8.2 / 10.2 | 0.0 / 0.0 | 3.7 / 4.1 | 0.0 / 0.0 | 0.4 / 0.5 | - | - | - | 14.0 / 16.3 | - | - |
| 1x | Chrome Cairo, page paints | 17.2 / 26.7 | 0.0 / 0.0 | 6.4 / 10.0 | 0.0 / 0.0 | 1.4 / 2.1 | 0.1 / 0.2 | - | 0.3 / 0.3 | 28.6 / 42.0 | - | - |
| 1x | Chrome Cairo, worker paints | 16.5 / 22.2 | 0.0 / 0.0 | 6.1 / 9.4 | 0.0 / 0.0 | 1.3 / 1.9 | 0.2 / 0.3 | - | 0.2 / 0.3 | 27.8 / 38.1 | - | - |
| 1x | native IR (encode only) | 6.0 / 9.6 | 0.0 / 0.0 | 0.0 / 0.0 | 5.4 / 10.1 | 0.0 / 0.0 | - | - | - | 12.2 / 19.6 | - | - |
| 1x | Chrome Canvas, page paints | 17.6 / 25.9 | 0.0 / 0.0 | 0.0 / 0.0 | 16.4 / 21.6 | - | 0.3 / 0.4 | 0.5 / 0.8 | 0.6 / 0.7 | 38.4 / 52.5 | - | - |
| 1x | Chrome Canvas, worker paints | 18.5 / 24.4 | 0.0 / 0.0 | 0.0 / 0.0 | 15.2 / 21.4 | - | 0.2 / 0.2 | 0.5 / 0.6 | 0.5 / 0.7 | 34.1 / 44.1 | - | - |
| 2x | native Cairo | 7.0 / 11.7 | 0.0 / 0.0 | 6.1 / 7.6 | 0.0 / 0.0 | 0.9 / 1.4 | - | - | - | 14.9 / 22.4 | - | - |
| 2x | Chrome Cairo, page paints | 18.8 / 22.9 | 0.0 / 0.0 | 9.6 / 13.6 | 0.0 / 0.0 | 4.1 / 4.4 | 0.2 / 0.3 | - | 1.4 / 1.7 | 37.2 / 41.4 | - | - |
| 2x | Chrome Cairo, worker paints | 16.5 / 19.6 | 0.0 / 0.0 | 8.6 / 9.6 | 0.0 / 0.0 | 4.2 / 4.4 | 0.2 / 0.3 | - | 1.3 / 1.7 | 32.5 / 37.1 | - | - |
| 2x | native IR (encode only) | 5.8 / 8.5 | 0.0 / 0.0 | 0.0 / 0.0 | 5.3 / 9.0 | 0.0 / 0.0 | - | - | - | 11.8 / 18.4 | - | - |
| 2x | Chrome Canvas, page paints | 15.7 / 23.5 | 0.0 / 0.0 | 0.0 / 0.0 | 13.8 / 23.5 | - | 0.3 / 0.3 | 0.4 / 0.6 | 0.4 / 0.7 | 32.5 / 48.5 | - | - |
| 2x | Chrome Canvas, worker paints | 18.7 / 23.5 | 0.0 / 0.0 | 0.0 / 0.0 | 13.4 / 20.4 | - | 0.2 / 0.4 | 0.4 / 0.6 | 0.6 / 0.9 | 33.9 / 45.6 | - | - |

### paths-06_outlines

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 10.8 / 17.8 | 0.1 / 0.2 | 5.5 / 9.7 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 15.6 / 26.1 | - | - |
| 1x | Chrome Cairo, page paints | 28.4 / 40.2 | 0.4 / 0.9 | 13.6 / 18.5 | 0.0 / 0.0 | 1.3 / 2.6 | 0.1 / 0.2 | - | 0.2 / 0.3 | 46.5 / 58.4 | 19.7 | 64 |
| 1x | Chrome Cairo, worker paints | 28.1 / 40.2 | 0.3 / 0.5 | 12.2 / 19.8 | 0.0 / 0.0 | 0.9 / 1.7 | 0.2 / 0.2 | - | 0.2 / 0.3 | 41.9 / 59.0 | 20.7 | 59 |
| 1x | native IR (encode only) | 8.6 / 15.5 | 0.1 / 0.2 | 0.0 / 0.0 | 9.3 / 19.3 | 0.0 / 0.0 | - | - | - | 19.0 / 35.4 | - | - |
| 1x | Chrome Canvas, page paints | 29.3 / 35.6 | 0.4 / 0.6 | 0.0 / 0.0 | 26.3 / 44.2 | - | 0.2 / 0.3 | 1.0 / 1.9 | 0.5 / 1.1 | 58.6 / 77.2 | 15.2 | 91 |
| 1x | Chrome Canvas, worker paints | 24.9 / 36.2 | 0.4 / 0.6 | 0.0 / 0.0 | 24.3 / 45.1 | - | 0.2 / 0.3 | 0.6 / 1.2 | 0.5 / 0.8 | 51.0 / 73.7 | 16.8 | 78 |
| 2x | native Cairo | 11.6 / 17.6 | 0.1 / 0.3 | 10.5 / 17.1 | 0.0 / 0.0 | 1.0 / 2.2 | - | - | - | 26.6 / 37.6 | - | - |
| 2x | Chrome Cairo, page paints | 30.9 / 35.2 | 0.4 / 0.6 | 20.3 / 25.3 | 0.0 / 0.0 | 3.6 / 5.1 | 0.2 / 0.3 | - | 1.0 / 1.7 | 54.5 / 64.0 | 16.4 | 82 |
| 2x | Chrome Cairo, worker paints | 25.5 / 32.4 | 0.3 / 0.6 | 12.1 / 19.9 | 0.0 / 0.0 | 2.2 / 4.1 | 0.2 / 0.3 | - | 0.8 / 1.5 | 46.4 / 55.0 | 20.0 | 63 |
| 2x | native IR (encode only) | 11.2 / 13.7 | 0.1 / 0.2 | 0.0 / 0.0 | 11.0 / 16.6 | 0.0 / 0.0 | - | - | - | 22.2 / 29.7 | - | - |
| 2x | Chrome Canvas, page paints | 23.9 / 37.2 | 0.3 / 0.6 | 0.0 / 0.0 | 24.7 / 35.7 | - | 0.3 / 0.4 | 0.8 / 1.2 | 0.5 / 0.8 | 57.7 / 79.8 | 16.0 | 87 |
| 2x | Chrome Canvas, worker paints | 23.4 / 37.0 | 0.4 / 0.6 | 0.0 / 0.0 | 22.9 / 42.2 | - | 0.2 / 0.3 | 0.8 / 1.2 | 0.7 / 1.3 | 52.5 / 71.7 | 16.8 | 80 |

### studios-06_poster_series

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.7 / 10.3 | 0.1 / 0.2 | 20.0 / 36.7 | 0.0 / 0.0 | 0.6 / 1.0 | - | - | - | 25.8 / 48.0 | - | - |
| 1x | Chrome Cairo, page paints | 14.4 / 20.1 | 0.3 / 0.5 | 38.3 / 48.9 | 0.0 / 0.0 | 2.1 / 3.5 | 0.1 / 0.3 | - | 0.6 / 1.2 | 56.4 / 69.0 | 16.0 | 86 |
| 1x | Chrome Cairo, worker paints | 11.0 / 18.4 | 0.2 / 0.4 | 30.5 / 40.7 | 0.0 / 0.0 | 1.4 / 3.0 | 0.1 / 0.2 | - | 0.5 / 1.1 | 46.0 / 58.3 | 18.8 | 66 |
| 1x | native IR (encode only) | 5.2 / 7.9 | 0.1 / 0.1 | 0.0 / 0.0 | 30.3 / 49.8 | 0.0 / 0.0 | - | - | - | 36.6 / 61.0 | - | - |
| 1x | Chrome Canvas, page paints | 13.8 / 20.6 | 0.2 / 0.4 | 0.0 / 0.0 | 64.3 / 89.3 | - | 0.4 / 0.6 | 2.7 / 3.3 | 0.9 / 1.5 | 86.3 / 118.8 | 11.1 | 137 |
| 1x | Chrome Canvas, worker paints | 11.4 / 18.5 | 0.2 / 0.4 | 0.0 / 0.0 | 51.5 / 75.9 | - | 0.2 / 0.3 | 1.8 / 3.1 | 0.9 / 1.3 | 68.4 / 104.5 | 12.5 | 116 |
| 2x | native Cairo | 5.6 / 9.8 | 0.1 / 0.3 | 24.6 / 40.3 | 0.0 / 0.0 | 2.1 / 4.0 | - | - | - | 32.5 / 52.0 | - | - |
| 2x | Chrome Cairo, page paints | 14.6 / 20.3 | 0.2 / 0.5 | 40.9 / 56.0 | 0.0 / 0.0 | 6.3 / 9.3 | 0.2 / 0.4 | - | 1.7 / 3.8 | 63.3 / 83.7 | 14.2 | 99 |
| 2x | Chrome Cairo, worker paints | 10.6 / 14.2 | 0.3 / 0.6 | 37.2 / 47.9 | 0.0 / 0.0 | 4.2 / 8.0 | 0.2 / 0.3 | - | 1.5 / 3.9 | 57.5 / 73.7 | 15.7 | 88 |
| 2x | native IR (encode only) | 5.5 / 8.2 | 0.1 / 0.2 | 0.0 / 0.0 | 29.4 / 51.6 | 0.0 / 0.0 | - | - | - | 35.5 / 59.7 | - | - |
| 2x | Chrome Canvas, page paints | 10.9 / 16.8 | 0.2 / 0.9 | 0.0 / 0.0 | 56.3 / 94.0 | - | 0.4 / 0.5 | 1.7 / 3.0 | 0.8 / 1.5 | 78.2 / 110.5 | 11.7 | 128 |
| 2x | Chrome Canvas, worker paints | 12.2 / 21.3 | 0.3 / 0.9 | 0.0 / 0.0 | 55.8 / 72.9 | - | 0.1 / 0.2 | 1.8 / 3.5 | 0.9 / 1.8 | 74.8 / 95.4 | 11.8 | 128 |

### s1-05_text

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.3 / 0.7 | 0.1 / 0.1 | 3.9 / 7.7 | 0.0 / 0.0 | 0.2 / 0.3 | - | - | - | 4.7 / 8.4 | - | - |
| 1x | Chrome Cairo, page paints | 0.9 / 1.4 | 0.2 / 0.3 | 8.2 / 12.1 | 0.0 / 0.0 | 1.4 / 1.9 | 0.1 / 0.3 | - | 0.2 / 0.3 | 11.5 / 16.9 | 57.3 | 2 |
| 1x | Chrome Cairo, worker paints | 0.8 / 1.3 | 0.2 / 0.4 | 7.9 / 11.8 | 0.0 / 0.0 | 1.4 / 2.1 | 0.2 / 0.3 | - | 0.3 / 0.4 | 11.8 / 15.1 | 54.8 | 2 |
| 1x | native IR (encode only) | 0.2 / 0.3 | 0.0 / 0.1 | 0.0 / 0.0 | 3.7 / 6.7 | 0.0 / 0.0 | - | - | - | 4.0 / 7.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.8 / 1.1 | 0.1 / 0.3 | 0.0 / 0.0 | 11.7 / 18.0 | - | 0.3 / 0.4 | 0.5 / 0.9 | 0.2 / 0.3 | 14.8 / 21.5 | 51.7 | 5 |
| 1x | Chrome Canvas, worker paints | 0.6 / 0.9 | 0.1 / 0.2 | 0.0 / 0.0 | 10.1 / 15.3 | - | 0.2 / 0.3 | 0.5 / 0.7 | 0.2 / 0.4 | 12.5 / 17.9 | 49.1 | 7 |
| 2x | native Cairo | 0.4 / 0.9 | 0.1 / 0.2 | 3.5 / 7.2 | 0.0 / 0.0 | 1.0 / 2.7 | - | - | - | 5.5 / 10.1 | - | - |
| 2x | Chrome Cairo, page paints | 1.1 / 1.5 | 0.2 / 0.4 | 11.0 / 15.7 | 0.0 / 0.0 | 4.8 / 7.1 | 0.2 / 0.3 | - | 1.6 / 1.9 | 19.6 / 27.5 | 31.7 | 28 |
| 2x | Chrome Cairo, worker paints | 0.6 / 1.2 | 0.1 / 0.3 | 9.2 / 12.0 | 0.0 / 0.0 | 3.0 / 4.5 | 0.2 / 0.3 | - | 0.9 / 1.9 | 15.1 / 18.5 | 50.5 | 7 |
| 2x | native IR (encode only) | 0.2 / 0.4 | 0.0 / 0.1 | 0.0 / 0.0 | 3.3 / 8.1 | 0.0 / 0.0 | - | - | - | 3.6 / 8.8 | - | - |
| 2x | Chrome Canvas, page paints | 0.9 / 1.1 | 0.1 / 0.3 | 0.0 / 0.0 | 12.2 / 18.4 | - | 0.3 / 0.4 | 0.4 / 1.0 | 0.2 / 0.3 | 15.3 / 22.5 | 45.0 | 10 |
| 2x | Chrome Canvas, worker paints | 0.7 / 1.2 | 0.1 / 0.3 | 0.0 / 0.0 | 11.7 / 21.3 | - | 0.2 / 0.3 | 0.5 / 0.9 | 0.3 / 0.4 | 14.4 / 23.7 | 45.2 | 8 |

### s1-06_animation

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.0 / 0.0 | 0.0 / 0.0 | 0.1 / 0.1 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 0.2 / 0.2 | - | - |
| 1x | Chrome Cairo, page paints | 0.3 / 0.7 | 0.2 / 0.5 | 1.0 / 1.3 | 0.0 / 0.0 | 2.1 / 2.6 | 0.1 / 0.4 | - | 0.2 / 0.4 | 4.8 / 6.0 | 61.3 | 0 |
| 1x | Chrome Cairo, worker paints | 0.3 / 0.5 | 0.3 / 0.4 | 0.9 / 1.4 | 0.0 / 0.0 | 1.6 / 2.2 | 0.2 / 0.3 | - | 0.3 / 0.4 | 4.5 / 5.7 | 59.7 | 1 |
| 1x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.4 / 0.5 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.3 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.6 / 2.2 | 61.9 | 0 |
| 1x | Chrome Canvas, worker paints | 0.3 / 0.4 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.7 / 2.4 | 61.8 | 0 |
| 2x | native Cairo | 0.1 / 0.5 | 0.0 / 0.2 | 0.5 / 2.7 | 0.0 / 0.0 | 0.9 / 2.4 | - | - | - | 1.9 / 5.2 | - | - |
| 2x | Chrome Cairo, page paints | 0.3 / 0.4 | 0.2 / 0.6 | 2.4 / 3.4 | 0.0 / 0.0 | 5.6 / 7.3 | 0.2 / 0.3 | - | 1.7 / 2.6 | 11.6 / 14.0 | 58.4 | 1 |
| 2x | Chrome Cairo, worker paints | 0.3 / 0.5 | 0.2 / 0.7 | 1.9 / 4.0 | 0.0 / 0.0 | 5.7 / 7.4 | 0.3 / 0.3 | - | 1.9 / 3.0 | 11.9 / 15.8 | 53.4 | 2 |
| 2x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 2x | Chrome Canvas, page paints | 0.3 / 0.4 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 0.0 / 0.1 | 0.1 / 0.2 | 1.3 / 1.6 | 61.8 | 0 |
| 2x | Chrome Canvas, worker paints | 0.3 / 0.5 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.4 | - | 0.2 / 0.5 | 0.0 / 0.1 | 0.1 / 0.6 | 1.8 / 3.7 | 59.9 | 0 |

### s1-07_bounce

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.0 / 0.0 | 0.0 / 0.0 | 0.1 / 0.2 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 0.2 / 0.3 | - | - |
| 1x | Chrome Cairo, page paints | 0.2 / 0.3 | 0.2 / 0.4 | 1.0 / 1.7 | 0.0 / 0.0 | 2.1 / 3.0 | 0.1 / 0.3 | - | 0.2 / 0.4 | 4.7 / 7.0 | 61.5 | 0 |
| 1x | Chrome Cairo, worker paints | 0.2 / 0.3 | 0.2 / 0.4 | 0.6 / 1.2 | 0.0 / 0.0 | 1.5 / 2.0 | 0.2 / 0.3 | - | 0.3 / 0.4 | 3.5 / 4.8 | 61.3 | 0 |
| 1x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.4 | 0.0 / 0.0 | 0.3 / 0.5 | - | 0.2 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.5 / 1.7 | 61.9 | 0 |
| 1x | Chrome Canvas, worker paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.4 | - | 0.2 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.6 / 2.3 | 61.8 | 0 |
| 2x | native Cairo | 0.1 / 0.3 | 0.1 / 0.3 | 0.7 / 4.4 | 0.0 / 0.0 | 1.3 / 2.7 | - | - | - | 2.6 / 8.1 | - | - |
| 2x | Chrome Cairo, page paints | 0.2 / 0.3 | 0.3 / 0.6 | 2.2 / 3.2 | 0.0 / 0.0 | 5.6 / 8.6 | 0.2 / 0.3 | - | 1.5 / 1.9 | 11.1 / 13.8 | 56.9 | 1 |
| 2x | Chrome Cairo, worker paints | 0.2 / 0.3 | 0.2 / 0.6 | 1.9 / 3.8 | 0.0 / 0.0 | 5.6 / 6.4 | 0.3 / 0.4 | - | 1.9 / 3.1 | 11.9 / 18.9 | 55.0 | 3 |
| 2x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.0 / 0.0 | - | - |
| 2x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.4 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 0.0 / 0.1 | 0.1 / 0.3 | 1.4 / 1.7 | 61.9 | 0 |
| 2x | Chrome Canvas, worker paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.7 | 0.0 / 0.1 | 0.1 / 0.4 | 1.5 / 2.0 | 59.8 | 0 |

## Tables per case (median / p95 in ms; fps and skipped ticks are for the 30 timed frames under rAF)

### projects-02_rangoli

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.4 / 5.2 | 0.1 / 0.1 | 4.1 / 4.6 | 0.0 / 0.0 | 0.3 / 0.3 | - | - | - | 8.9 / 9.9 | - | - |
| 1x | Chrome Cairo, page paints | 22.0 / 26.9 | 0.5 / 0.8 | 15.2 / 21.9 | 0.0 / 0.0 | 1.7 / 2.7 | 0.1 / 0.3 | - | 0.3 / 0.5 | 39.7 / 52.8 | 21.6 | 56 |
| 1x | Chrome Cairo, worker paints | 18.5 / 23.1 | 0.4 / 0.6 | 13.1 / 16.7 | 0.0 / 0.0 | 1.4 / 2.6 | 0.2 / 0.3 | - | 0.3 / 1.1 | 32.9 / 42.6 | 24.5 | 45 |
| 1x | native IR (encode only) | 4.3 / 4.7 | 0.1 / 0.1 | 0.0 / 0.0 | 7.6 / 10.6 | 0.0 / 0.0 | - | - | - | 12.1 / 15.2 | - | - |
| 1x | Chrome Canvas, page paints | 19.0 / 30.4 | 0.4 / 0.8 | 0.0 / 0.0 | 33.8 / 43.4 | - | 0.3 / 0.5 | 1.0 / 2.1 | 0.7 / 1.7 | 57.1 / 70.9 | 15.8 | 85 |
| 1x | Chrome Canvas, worker paints | 17.4 / 21.6 | 0.3 / 0.5 | 0.0 / 0.0 | 23.6 / 33.3 | - | 0.2 / 0.3 | 0.6 / 1.1 | 0.6 / 1.2 | 44.5 / 56.0 | 20.6 | 60 |
| 2x | native Cairo | 4.6 / 5.4 | 0.1 / 0.2 | 6.8 / 8.3 | 0.0 / 0.0 | 0.9 / 1.7 | - | - | - | 12.9 / 16.2 | - | - |
| 2x | Chrome Cairo, page paints | 21.4 / 29.5 | 0.5 / 0.7 | 21.9 / 27.7 | 0.0 / 0.0 | 6.7 / 8.7 | 0.2 / 0.4 | - | 1.5 / 2.1 | 51.9 / 65.3 | 17.1 | 78 |
| 2x | Chrome Cairo, worker paints | 18.8 / 26.6 | 0.4 / 0.7 | 18.0 / 24.7 | 0.0 / 0.0 | 3.7 / 6.7 | 0.2 / 0.3 | - | 1.3 / 2.4 | 44.6 / 56.4 | 17.7 | 74 |
| 2x | native IR (encode only) | 4.5 / 6.1 | 0.1 / 0.3 | 0.0 / 0.0 | 7.9 / 9.8 | 0.0 / 0.0 | - | - | - | 12.9 / 15.4 | - | - |
| 2x | Chrome Canvas, page paints | 17.4 / 27.7 | 0.3 / 0.6 | 0.0 / 0.0 | 26.3 / 34.1 | - | 0.3 / 0.5 | 0.8 / 1.9 | 0.7 / 1.2 | 49.7 / 61.7 | 18.8 | 69 |
| 2x | Chrome Canvas, worker paints | 18.0 / 22.9 | 0.4 / 0.6 | 0.0 / 0.0 | 21.3 / 33.6 | - | 0.1 / 0.2 | 0.6 / 1.2 | 0.6 / 1.1 | 42.3 / 61.4 | 20.8 | 59 |

### projects-06_kinetic_type

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 31.4 / 46.8 | 0.1 / 0.2 | 5.2 / 6.4 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 36.8 / 52.8 | - | - |
| 1x | Chrome Cairo, page paints | 101.5 / 137.8 | 0.7 / 1.3 | 15.0 / 22.9 | 0.0 / 0.0 | 1.0 / 1.5 | 0.1 / 0.2 | - | 0.2 / 0.3 | 118.4 / 157.0 | 7.9 | 204 |
| 1x | Chrome Cairo, worker paints | 97.9 / 169.6 | 0.7 / 1.6 | 13.8 / 29.6 | 0.0 / 0.0 | 0.9 / 2.2 | 0.2 / 0.3 | - | 0.2 / 0.7 | 110.9 / 186.5 | 7.5 | 218 |
| 1x | native IR (encode only) | 30.9 / 32.8 | 0.2 / 0.4 | 0.0 / 0.0 | 12.3 / 15.4 | 0.0 / 0.0 | - | - | - | 43.3 / 47.1 | - | - |
| 1x | Chrome Canvas, page paints | 111.5 / 146.7 | 0.8 / 1.4 | 0.0 / 0.0 | 39.3 / 57.7 | - | 0.4 / 0.5 | 1.1 / 2.3 | 0.8 / 1.9 | 153.5 / 219.6 | 6.0 | 280 |
| 1x | Chrome Canvas, worker paints | 91.0 / 107.3 | 0.6 / 1.1 | 0.0 / 0.0 | 36.1 / 50.6 | - | 0.2 / 0.3 | 1.0 / 1.8 | 0.8 / 1.2 | 128.9 / 151.3 | 7.2 | 227 |
| 2x | native Cairo | 30.8 / 32.8 | 0.2 / 0.2 | 7.6 / 9.2 | 0.0 / 0.0 | 0.6 / 1.0 | - | - | - | 39.5 / 41.8 | - | - |
| 2x | Chrome Cairo, page paints | 114.2 / 165.0 | 0.8 / 1.5 | 22.6 / 33.2 | 0.0 / 0.0 | 3.2 / 5.0 | 0.2 / 0.5 | - | 0.8 / 1.3 | 146.7 / 203.7 | 6.7 | 246 |
| 2x | Chrome Cairo, worker paints | 97.9 / 167.2 | 0.7 / 1.3 | 19.4 / 32.2 | 0.0 / 0.0 | 2.8 / 5.3 | 0.2 / 0.3 | - | 1.0 / 1.4 | 123.2 / 194.3 | 7.1 | 230 |
| 2x | native IR (encode only) | 34.3 / 41.0 | 0.2 / 0.4 | 0.0 / 0.0 | 14.6 / 23.0 | 0.0 / 0.0 | - | - | - | 49.7 / 71.4 | - | - |
| 2x | Chrome Canvas, page paints | 98.2 / 160.7 | 0.6 / 1.0 | 0.0 / 0.0 | 36.5 / 60.7 | - | 0.4 / 0.6 | 0.9 / 2.7 | 0.6 / 1.7 | 140.6 / 208.9 | 6.4 | 260 |
| 2x | Chrome Canvas, worker paints | 92.2 / 121.5 | 0.5 / 1.0 | 0.0 / 0.0 | 33.9 / 42.3 | - | 0.2 / 0.3 | 1.1 / 1.8 | 0.8 / 1.4 | 127.2 / 174.4 | 7.0 | 236 |

### text-09_text_dots

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 10.3 / 11.1 | 0.1 / 0.1 | 5.2 / 6.1 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 15.7 / 18.0 | - | - |
| 1x | Chrome Cairo, page paints | 36.2 / 50.1 | 0.6 / 0.8 | 15.4 / 20.4 | 0.0 / 0.0 | 0.9 / 1.8 | 0.0 / 0.1 | - | 0.2 / 0.3 | 53.6 / 70.9 | 16.0 | 86 |
| 1x | Chrome Cairo, worker paints | 36.4 / 50.9 | 0.5 / 1.3 | 15.4 / 29.8 | 0.0 / 0.0 | 1.1 / 2.6 | 0.2 / 0.2 | - | 0.2 / 0.4 | 55.6 / 80.7 | 14.9 | 91 |
| 1x | native IR (encode only) | 10.9 / 12.4 | 0.1 / 0.2 | 0.0 / 0.0 | 12.5 / 14.2 | 0.0 / 0.0 | - | - | - | 23.7 / 26.8 | - | - |
| 1x | Chrome Canvas, page paints | 73.4 / 96.1 | 0.9 / 3.2 | 0.0 / 0.0 | 79.6 / 106.7 | - | 0.4 / 1.9 | 2.6 / 4.6 | 1.9 / 3.6 | 157.3 / 198.6 | 6.2 | 263 |
| 1x | Chrome Canvas, worker paints | 33.4 / 46.8 | 0.5 / 0.8 | 0.0 / 0.0 | 28.7 / 45.2 | - | 0.2 / 0.3 | 0.9 / 1.7 | 0.8 / 1.5 | 68.8 / 89.5 | 12.9 | 114 |
| 2x | native Cairo | 11.0 / 13.6 | 0.2 / 0.2 | 7.2 / 8.7 | 0.0 / 0.0 | 0.8 / 1.4 | - | - | - | 19.8 / 22.7 | - | - |
| 2x | Chrome Cairo, page paints | 46.1 / 60.1 | 0.5 / 1.0 | 20.8 / 32.7 | 0.0 / 0.0 | 3.4 / 5.5 | 0.2 / 0.3 | - | 0.9 / 1.4 | 72.8 / 91.2 | 12.2 | 122 |
| 2x | Chrome Cairo, worker paints | 34.8 / 48.9 | 0.6 / 1.0 | 17.7 / 25.5 | 0.0 / 0.0 | 3.1 / 5.6 | 0.2 / 0.3 | - | 1.1 / 2.0 | 58.7 / 82.2 | 14.5 | 98 |
| 2x | native IR (encode only) | 16.8 / 23.3 | 0.2 / 0.7 | 0.0 / 0.0 | 19.7 / 27.2 | 0.0 / 0.0 | - | - | - | 36.6 / 49.0 | - | - |
| 2x | Chrome Canvas, page paints | 36.7 / 43.1 | 0.5 / 0.8 | 0.0 / 0.0 | 33.2 / 41.6 | - | 0.3 / 0.4 | 1.0 / 1.6 | 0.8 / 1.7 | 75.6 / 87.3 | 12.3 | 120 |
| 2x | Chrome Canvas, worker paints | 33.1 / 45.1 | 0.5 / 0.9 | 0.0 / 0.0 | 33.0 / 49.1 | - | 0.1 / 0.2 | 1.1 / 1.6 | 0.9 / 1.6 | 72.9 / 92.7 | 12.3 | 121 |

### randomness-03_noise

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 16.0 / 28.6 | 0.1 / 0.2 | 1.5 / 2.8 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 17.7 / 31.4 | - | - |
| 1x | Chrome Cairo, page paints | 39.5 / 51.0 | 0.4 / 0.7 | 3.8 / 5.9 | 0.0 / 0.0 | 1.0 / 1.4 | 0.1 / 0.2 | - | 0.2 / 0.3 | 46.4 / 58.7 | 17.8 | 73 |
| 1x | Chrome Cairo, worker paints | 32.7 / 52.6 | 0.4 / 0.9 | 3.2 / 6.1 | 0.0 / 0.0 | 0.9 / 1.5 | 0.1 / 0.2 | - | 0.2 / 0.3 | 39.4 / 58.2 | 21.4 | 56 |
| 1x | native IR (encode only) | 13.0 / 20.0 | 0.2 / 0.3 | 0.0 / 0.0 | 6.3 / 8.7 | 0.0 / 0.0 | - | - | - | 20.0 / 26.8 | - | - |
| 1x | Chrome Canvas, page paints | 39.5 / 50.1 | 0.5 / 1.3 | 0.0 / 0.0 | 18.5 / 23.4 | - | 0.3 / 0.4 | 0.4 / 0.6 | 1.0 / 1.6 | 61.3 / 78.8 | 15.1 | 92 |
| 1x | Chrome Canvas, worker paints | 33.1 / 42.7 | 0.4 / 0.6 | 0.0 / 0.0 | 12.0 / 19.1 | - | 0.2 / 0.3 | 0.3 / 0.5 | 0.7 / 1.2 | 46.3 / 65.1 | 18.0 | 73 |
| 2x | native Cairo | 12.9 / 20.2 | 0.2 / 0.2 | 2.3 / 3.9 | 0.0 / 0.0 | 1.0 / 1.4 | - | - | - | 16.8 / 24.3 | - | - |
| 2x | Chrome Cairo, page paints | 42.0 / 53.6 | 0.5 / 0.8 | 5.8 / 9.3 | 0.0 / 0.0 | 3.6 / 6.6 | 0.2 / 0.5 | - | 1.0 / 1.9 | 53.4 / 70.4 | 15.8 | 89 |
| 2x | Chrome Cairo, worker paints | 36.8 / 44.9 | 0.5 / 0.8 | 6.1 / 8.9 | 0.0 / 0.0 | 3.5 / 6.1 | 0.2 / 0.3 | - | 1.1 / 1.7 | 50.7 / 58.0 | 17.4 | 78 |
| 2x | native IR (encode only) | 12.6 / 22.3 | 0.1 / 0.2 | 0.0 / 0.0 | 6.1 / 10.2 | 0.0 / 0.0 | - | - | - | 19.4 / 33.9 | - | - |
| 2x | Chrome Canvas, page paints | 32.3 / 39.8 | 0.4 / 0.9 | 0.0 / 0.0 | 15.0 / 20.0 | - | 0.3 / 0.4 | 0.3 / 0.5 | 0.7 / 1.5 | 49.2 / 60.7 | 17.5 | 76 |
| 2x | Chrome Canvas, worker paints | 32.2 / 44.3 | 0.4 / 0.8 | 0.0 / 0.0 | 14.9 / 21.4 | - | 0.1 / 0.3 | 0.3 / 0.6 | 1.0 / 1.7 | 49.2 / 65.4 | 17.2 | 78 |

### sound-02_write_a_tune

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 57.2 / 84.5 | 0.1 / 0.2 | 3.3 / 6.1 | 0.0 / 0.0 | 0.1 / 0.3 | - | - | - | 60.7 / 88.0 | - | - |
| 1x | Chrome Cairo, page paints | 177.3 / 198.9 | 0.3 / 0.5 | 9.3 / 12.3 | 0.0 / 0.0 | 1.1 / 1.8 | 0.1 / 0.3 | - | 0.2 / 0.3 | 186.8 / 211.3 | 5.2 | 331 |
| 1x | Chrome Cairo, worker paints | 167.3 / 218.4 | 0.2 / 0.4 | 7.1 / 11.0 | 0.0 / 0.0 | 0.8 / 1.7 | 0.2 / 0.3 | - | 0.2 / 0.4 | 175.9 / 228.1 | 5.5 | 309 |
| 1x | native IR (encode only) | 81.7 / 100.4 | 0.1 / 0.2 | 0.0 / 0.0 | 10.0 / 15.8 | 0.0 / 0.0 | - | - | - | 92.1 / 113.3 | - | - |
| 1x | Chrome Canvas, page paints | 174.1 / 198.6 | 0.3 / 0.5 | 0.0 / 0.0 | 21.8 / 27.5 | - | 0.2 / 0.4 | 0.6 / 0.9 | 0.7 / 1.0 | 197.9 / 221.6 | 5.0 | 340 |
| 1x | Chrome Canvas, worker paints | 173.5 / 196.1 | 0.3 / 0.5 | 0.0 / 0.0 | 20.8 / 26.4 | - | 0.2 / 0.4 | 0.6 / 1.1 | 0.9 / 1.4 | 196.6 / 226.2 | 5.1 | 334 |
| 2x | native Cairo | 74.5 / 108.7 | 0.1 / 0.2 | 5.9 / 11.0 | 0.0 / 0.0 | 0.9 / 1.8 | - | - | - | 82.2 / 115.1 | - | - |
| 2x | Chrome Cairo, page paints | 181.6 / 218.1 | 0.3 / 0.4 | 11.9 / 16.9 | 0.0 / 0.0 | 3.7 / 6.3 | 0.1 / 0.3 | - | 1.1 / 1.8 | 197.5 / 237.6 | 5.0 | 339 |
| 2x | Chrome Cairo, worker paints | 168.8 / 209.4 | 0.3 / 0.5 | 9.2 / 13.6 | 0.0 / 0.0 | 3.3 / 5.0 | 0.2 / 0.3 | - | 1.2 / 1.8 | 185.6 / 228.7 | 5.3 | 316 |
| 2x | native IR (encode only) | 80.7 / 98.9 | 0.1 / 0.1 | 0.0 / 0.0 | 11.6 / 14.2 | 0.0 / 0.0 | - | - | - | 92.8 / 112.2 | - | - |
| 2x | Chrome Canvas, page paints | 159.7 / 184.4 | 0.2 / 0.4 | 0.0 / 0.0 | 19.5 / 25.4 | - | 0.3 / 0.4 | 0.5 / 0.9 | 0.6 / 1.2 | 186.3 / 211.1 | 5.4 | 317 |
| 2x | Chrome Canvas, worker paints | 173.3 / 241.4 | 0.3 / 0.4 | 0.0 / 0.0 | 22.1 / 32.2 | - | 0.1 / 0.3 | 0.6 / 1.2 | 0.9 / 1.6 | 199.3 / 262.4 | 4.7 | 363 |

### randomness-02_gaussian_and_choice

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 10.3 / 14.3 | 0.1 / 0.2 | 4.5 / 6.1 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 15.2 / 20.7 | - | - |
| 1x | Chrome Cairo, page paints | 23.9 / 32.1 | 0.5 / 0.7 | 7.6 / 9.6 | 0.0 / 0.0 | 1.1 / 1.8 | 0.1 / 0.2 | - | 0.2 / 0.3 | 33.6 / 42.7 | 23.9 | 48 |
| 1x | Chrome Cairo, worker paints | 22.5 / 27.3 | 0.4 / 0.7 | 7.3 / 9.0 | 0.0 / 0.0 | 1.0 / 1.5 | 0.1 / 0.2 | - | 0.2 / 0.3 | 32.6 / 38.2 | 25.1 | 42 |
| 1x | native IR (encode only) | 10.9 / 14.2 | 0.1 / 0.2 | 0.0 / 0.0 | 9.3 / 11.4 | 0.0 / 0.0 | - | - | - | 19.3 / 25.8 | - | - |
| 1x | Chrome Canvas, page paints | 24.6 / 29.9 | 0.5 / 0.8 | 0.0 / 0.0 | 17.8 / 19.8 | - | 0.2 / 0.4 | 0.4 / 0.6 | 0.4 / 0.6 | 44.2 / 58.2 | 20.5 | 60 |
| 1x | Chrome Canvas, worker paints | 23.6 / 29.5 | 0.4 / 0.6 | 0.0 / 0.0 | 15.9 / 19.1 | - | 0.2 / 0.3 | 0.4 / 0.5 | 0.5 / 0.8 | 41.0 / 48.6 | 21.3 | 56 |
| 2x | native Cairo | 8.3 / 16.6 | 0.2 / 0.3 | 7.6 / 13.8 | 0.0 / 0.0 | 1.2 / 2.1 | - | - | - | 19.3 / 31.7 | - | - |
| 2x | Chrome Cairo, page paints | 23.8 / 28.4 | 0.5 / 0.7 | 11.5 / 13.1 | 0.0 / 0.0 | 3.4 / 4.4 | 0.2 / 0.2 | - | 1.0 / 1.4 | 40.1 / 47.3 | 22.7 | 52 |
| 2x | Chrome Cairo, worker paints | 17.4 / 25.4 | 0.4 / 0.6 | 9.0 / 14.6 | 0.0 / 0.0 | 2.8 / 5.3 | 0.2 / 0.4 | - | 1.1 / 1.9 | 35.4 / 45.7 | 23.7 | 49 |
| 2x | native IR (encode only) | 7.3 / 13.6 | 0.1 / 0.2 | 0.0 / 0.0 | 7.5 / 10.2 | 0.0 / 0.0 | - | - | - | 16.7 / 24.4 | - | - |
| 2x | Chrome Canvas, page paints | 24.9 / 27.7 | 0.4 / 0.5 | 0.0 / 0.0 | 16.9 / 18.4 | - | 0.2 / 0.3 | 0.4 / 0.9 | 0.4 / 0.9 | 42.9 / 47.8 | 21.2 | 58 |
| 2x | Chrome Canvas, worker paints | 20.0 / 27.5 | 0.4 / 0.8 | 0.0 / 0.0 | 13.4 / 22.2 | - | 0.1 / 0.3 | 0.3 / 0.5 | 0.5 / 0.8 | 37.2 / 53.1 | 22.1 | 53 |

### studios-03_rhythm

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 1.9 / 4.0 | 0.0 / 0.0 | 3.3 / 6.5 | 0.0 / 0.0 | 0.4 / 0.8 | - | - | - | 6.6 / 13.3 | - | - |
| 1x | Chrome Cairo, page paints | 8.0 / 13.3 | 0.0 / 0.0 | 11.7 / 17.5 | 0.0 / 0.0 | 2.5 / 4.1 | 0.1 / 0.3 | - | 0.7 / 0.9 | 27.6 / 35.1 | - | - |
| 1x | Chrome Cairo, worker paints | 8.4 / 13.7 | 0.0 / 0.0 | 11.3 / 14.3 | 0.0 / 0.0 | 2.3 / 3.0 | 0.2 / 0.3 | - | 0.9 / 1.0 | 26.2 / 34.3 | - | - |
| 1x | native IR (encode only) | 2.1 / 3.7 | 0.0 / 0.0 | 0.0 / 0.0 | 7.8 / 11.9 | 0.0 / 0.0 | - | - | - | 11.8 / 17.0 | - | - |
| 1x | Chrome Canvas, page paints | 8.1 / 10.4 | 0.0 / 0.0 | 0.0 / 0.0 | 21.3 / 30.9 | - | 0.3 / 0.5 | 0.8 / 1.4 | 0.7 / 1.1 | 35.6 / 47.7 | - | - |
| 1x | Chrome Canvas, worker paints | 7.5 / 10.4 | 0.0 / 0.0 | 0.0 / 0.0 | 21.0 / 29.0 | - | 0.2 / 0.3 | 0.7 / 1.1 | 0.6 / 0.9 | 34.8 / 42.7 | - | - |
| 2x | native Cairo | 2.2 / 3.8 | 0.0 / 0.0 | 6.7 / 9.4 | 0.0 / 0.0 | 1.8 / 2.0 | - | - | - | 14.9 / 17.9 | - | - |
| 2x | Chrome Cairo, page paints | 9.4 / 12.8 | 0.0 / 0.0 | 14.9 / 16.5 | 0.0 / 0.0 | 6.9 / 10.9 | 0.2 / 0.7 | - | 2.6 / 4.3 | 35.2 / 46.0 | - | - |
| 2x | Chrome Cairo, worker paints | 9.4 / 10.9 | 0.0 / 0.0 | 12.6 / 15.5 | 0.0 / 0.0 | 8.0 / 8.3 | 0.2 / 0.3 | - | 2.3 / 3.1 | 36.9 / 41.3 | - | - |
| 2x | native IR (encode only) | 1.9 / 3.9 | 0.0 / 0.0 | 0.0 / 0.0 | 6.2 / 12.2 | 0.0 / 0.0 | - | - | - | 9.1 / 17.8 | - | - |
| 2x | Chrome Canvas, page paints | 7.2 / 9.1 | 0.0 / 0.0 | 0.0 / 0.0 | 19.1 / 26.7 | - | 0.2 / 0.3 | 0.8 / 0.9 | 0.7 / 0.9 | 30.5 / 39.1 | - | - |
| 2x | Chrome Canvas, worker paints | 6.0 / 9.1 | 0.0 / 0.0 | 0.0 / 0.0 | 14.4 / 23.7 | - | 0.2 / 0.3 | 0.5 / 1.1 | 0.7 / 1.1 | 28.5 / 40.4 | - | - |

### studios-05_text_as_geometry

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 8.2 / 10.2 | 0.0 / 0.0 | 3.7 / 4.1 | 0.0 / 0.0 | 0.4 / 0.5 | - | - | - | 14.0 / 16.3 | - | - |
| 1x | Chrome Cairo, page paints | 17.2 / 26.7 | 0.0 / 0.0 | 6.4 / 10.0 | 0.0 / 0.0 | 1.4 / 2.1 | 0.1 / 0.2 | - | 0.3 / 0.3 | 28.6 / 42.0 | - | - |
| 1x | Chrome Cairo, worker paints | 16.5 / 22.2 | 0.0 / 0.0 | 6.1 / 9.4 | 0.0 / 0.0 | 1.3 / 1.9 | 0.2 / 0.3 | - | 0.2 / 0.3 | 27.8 / 38.1 | - | - |
| 1x | native IR (encode only) | 6.0 / 9.6 | 0.0 / 0.0 | 0.0 / 0.0 | 5.4 / 10.1 | 0.0 / 0.0 | - | - | - | 12.2 / 19.6 | - | - |
| 1x | Chrome Canvas, page paints | 17.6 / 25.9 | 0.0 / 0.0 | 0.0 / 0.0 | 16.4 / 21.6 | - | 0.3 / 0.4 | 0.5 / 0.8 | 0.6 / 0.7 | 38.4 / 52.5 | - | - |
| 1x | Chrome Canvas, worker paints | 18.5 / 24.4 | 0.0 / 0.0 | 0.0 / 0.0 | 15.2 / 21.4 | - | 0.2 / 0.2 | 0.5 / 0.6 | 0.5 / 0.7 | 34.1 / 44.1 | - | - |
| 2x | native Cairo | 7.0 / 11.7 | 0.0 / 0.0 | 6.1 / 7.6 | 0.0 / 0.0 | 0.9 / 1.4 | - | - | - | 14.9 / 22.4 | - | - |
| 2x | Chrome Cairo, page paints | 18.8 / 22.9 | 0.0 / 0.0 | 9.6 / 13.6 | 0.0 / 0.0 | 4.1 / 4.4 | 0.2 / 0.3 | - | 1.4 / 1.7 | 37.2 / 41.4 | - | - |
| 2x | Chrome Cairo, worker paints | 16.5 / 19.6 | 0.0 / 0.0 | 8.6 / 9.6 | 0.0 / 0.0 | 4.2 / 4.4 | 0.2 / 0.3 | - | 1.3 / 1.7 | 32.5 / 37.1 | - | - |
| 2x | native IR (encode only) | 5.8 / 8.5 | 0.0 / 0.0 | 0.0 / 0.0 | 5.3 / 9.0 | 0.0 / 0.0 | - | - | - | 11.8 / 18.4 | - | - |
| 2x | Chrome Canvas, page paints | 15.7 / 23.5 | 0.0 / 0.0 | 0.0 / 0.0 | 13.8 / 23.5 | - | 0.3 / 0.3 | 0.4 / 0.6 | 0.4 / 0.7 | 32.5 / 48.5 | - | - |
| 2x | Chrome Canvas, worker paints | 18.7 / 23.5 | 0.0 / 0.0 | 0.0 / 0.0 | 13.4 / 20.4 | - | 0.2 / 0.4 | 0.4 / 0.6 | 0.6 / 0.9 | 33.9 / 45.6 | - | - |

### paths-06_outlines

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 10.8 / 17.8 | 0.1 / 0.2 | 5.5 / 9.7 | 0.0 / 0.0 | 0.1 / 0.2 | - | - | - | 15.6 / 26.1 | - | - |
| 1x | Chrome Cairo, page paints | 28.4 / 40.2 | 0.4 / 0.9 | 13.6 / 18.5 | 0.0 / 0.0 | 1.3 / 2.6 | 0.1 / 0.2 | - | 0.2 / 0.3 | 46.5 / 58.4 | 19.7 | 64 |
| 1x | Chrome Cairo, worker paints | 28.1 / 40.2 | 0.3 / 0.5 | 12.2 / 19.8 | 0.0 / 0.0 | 0.9 / 1.7 | 0.2 / 0.2 | - | 0.2 / 0.3 | 41.9 / 59.0 | 20.7 | 59 |
| 1x | native IR (encode only) | 8.6 / 15.5 | 0.1 / 0.2 | 0.0 / 0.0 | 9.3 / 19.3 | 0.0 / 0.0 | - | - | - | 19.0 / 35.4 | - | - |
| 1x | Chrome Canvas, page paints | 29.3 / 35.6 | 0.4 / 0.6 | 0.0 / 0.0 | 26.3 / 44.2 | - | 0.2 / 0.3 | 1.0 / 1.9 | 0.5 / 1.1 | 58.6 / 77.2 | 15.2 | 91 |
| 1x | Chrome Canvas, worker paints | 24.9 / 36.2 | 0.4 / 0.6 | 0.0 / 0.0 | 24.3 / 45.1 | - | 0.2 / 0.3 | 0.6 / 1.2 | 0.5 / 0.8 | 51.0 / 73.7 | 16.8 | 78 |
| 2x | native Cairo | 11.6 / 17.6 | 0.1 / 0.3 | 10.5 / 17.1 | 0.0 / 0.0 | 1.0 / 2.2 | - | - | - | 26.6 / 37.6 | - | - |
| 2x | Chrome Cairo, page paints | 30.9 / 35.2 | 0.4 / 0.6 | 20.3 / 25.3 | 0.0 / 0.0 | 3.6 / 5.1 | 0.2 / 0.3 | - | 1.0 / 1.7 | 54.5 / 64.0 | 16.4 | 82 |
| 2x | Chrome Cairo, worker paints | 25.5 / 32.4 | 0.3 / 0.6 | 12.1 / 19.9 | 0.0 / 0.0 | 2.2 / 4.1 | 0.2 / 0.3 | - | 0.8 / 1.5 | 46.4 / 55.0 | 20.0 | 63 |
| 2x | native IR (encode only) | 11.2 / 13.7 | 0.1 / 0.2 | 0.0 / 0.0 | 11.0 / 16.6 | 0.0 / 0.0 | - | - | - | 22.2 / 29.7 | - | - |
| 2x | Chrome Canvas, page paints | 23.9 / 37.2 | 0.3 / 0.6 | 0.0 / 0.0 | 24.7 / 35.7 | - | 0.3 / 0.4 | 0.8 / 1.2 | 0.5 / 0.8 | 57.7 / 79.8 | 16.0 | 87 |
| 2x | Chrome Canvas, worker paints | 23.4 / 37.0 | 0.4 / 0.6 | 0.0 / 0.0 | 22.9 / 42.2 | - | 0.2 / 0.3 | 0.8 / 1.2 | 0.7 / 1.3 | 52.5 / 71.7 | 16.8 | 80 |

### studios-06_poster_series

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 4.7 / 10.3 | 0.1 / 0.2 | 20.0 / 36.7 | 0.0 / 0.0 | 0.6 / 1.0 | - | - | - | 25.8 / 48.0 | - | - |
| 1x | Chrome Cairo, page paints | 14.4 / 20.1 | 0.3 / 0.5 | 38.3 / 48.9 | 0.0 / 0.0 | 2.1 / 3.5 | 0.1 / 0.3 | - | 0.6 / 1.2 | 56.4 / 69.0 | 16.0 | 86 |
| 1x | Chrome Cairo, worker paints | 11.0 / 18.4 | 0.2 / 0.4 | 30.5 / 40.7 | 0.0 / 0.0 | 1.4 / 3.0 | 0.1 / 0.2 | - | 0.5 / 1.1 | 46.0 / 58.3 | 18.8 | 66 |
| 1x | native IR (encode only) | 5.2 / 7.9 | 0.1 / 0.1 | 0.0 / 0.0 | 30.3 / 49.8 | 0.0 / 0.0 | - | - | - | 36.6 / 61.0 | - | - |
| 1x | Chrome Canvas, page paints | 13.8 / 20.6 | 0.2 / 0.4 | 0.0 / 0.0 | 64.3 / 89.3 | - | 0.4 / 0.6 | 2.7 / 3.3 | 0.9 / 1.5 | 86.3 / 118.8 | 11.1 | 137 |
| 1x | Chrome Canvas, worker paints | 11.4 / 18.5 | 0.2 / 0.4 | 0.0 / 0.0 | 51.5 / 75.9 | - | 0.2 / 0.3 | 1.8 / 3.1 | 0.9 / 1.3 | 68.4 / 104.5 | 12.5 | 116 |
| 2x | native Cairo | 5.6 / 9.8 | 0.1 / 0.3 | 24.6 / 40.3 | 0.0 / 0.0 | 2.1 / 4.0 | - | - | - | 32.5 / 52.0 | - | - |
| 2x | Chrome Cairo, page paints | 14.6 / 20.3 | 0.2 / 0.5 | 40.9 / 56.0 | 0.0 / 0.0 | 6.3 / 9.3 | 0.2 / 0.4 | - | 1.7 / 3.8 | 63.3 / 83.7 | 14.2 | 99 |
| 2x | Chrome Cairo, worker paints | 10.6 / 14.2 | 0.3 / 0.6 | 37.2 / 47.9 | 0.0 / 0.0 | 4.2 / 8.0 | 0.2 / 0.3 | - | 1.5 / 3.9 | 57.5 / 73.7 | 15.7 | 88 |
| 2x | native IR (encode only) | 5.5 / 8.2 | 0.1 / 0.2 | 0.0 / 0.0 | 29.4 / 51.6 | 0.0 / 0.0 | - | - | - | 35.5 / 59.7 | - | - |
| 2x | Chrome Canvas, page paints | 10.9 / 16.8 | 0.2 / 0.9 | 0.0 / 0.0 | 56.3 / 94.0 | - | 0.4 / 0.5 | 1.7 / 3.0 | 0.8 / 1.5 | 78.2 / 110.5 | 11.7 | 128 |
| 2x | Chrome Canvas, worker paints | 12.2 / 21.3 | 0.3 / 0.9 | 0.0 / 0.0 | 55.8 / 72.9 | - | 0.1 / 0.2 | 1.8 / 3.5 | 0.9 / 1.8 | 74.8 / 95.4 | 11.8 | 128 |

### s1-05_text

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.3 / 0.7 | 0.1 / 0.1 | 3.9 / 7.7 | 0.0 / 0.0 | 0.2 / 0.3 | - | - | - | 4.7 / 8.4 | - | - |
| 1x | Chrome Cairo, page paints | 0.9 / 1.4 | 0.2 / 0.3 | 8.2 / 12.1 | 0.0 / 0.0 | 1.4 / 1.9 | 0.1 / 0.3 | - | 0.2 / 0.3 | 11.5 / 16.9 | 57.3 | 2 |
| 1x | Chrome Cairo, worker paints | 0.8 / 1.3 | 0.2 / 0.4 | 7.9 / 11.8 | 0.0 / 0.0 | 1.4 / 2.1 | 0.2 / 0.3 | - | 0.3 / 0.4 | 11.8 / 15.1 | 54.8 | 2 |
| 1x | native IR (encode only) | 0.2 / 0.3 | 0.0 / 0.1 | 0.0 / 0.0 | 3.7 / 6.7 | 0.0 / 0.0 | - | - | - | 4.0 / 7.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.8 / 1.1 | 0.1 / 0.3 | 0.0 / 0.0 | 11.7 / 18.0 | - | 0.3 / 0.4 | 0.5 / 0.9 | 0.2 / 0.3 | 14.8 / 21.5 | 51.7 | 5 |
| 1x | Chrome Canvas, worker paints | 0.6 / 0.9 | 0.1 / 0.2 | 0.0 / 0.0 | 10.1 / 15.3 | - | 0.2 / 0.3 | 0.5 / 0.7 | 0.2 / 0.4 | 12.5 / 17.9 | 49.1 | 7 |
| 2x | native Cairo | 0.4 / 0.9 | 0.1 / 0.2 | 3.5 / 7.2 | 0.0 / 0.0 | 1.0 / 2.7 | - | - | - | 5.5 / 10.1 | - | - |
| 2x | Chrome Cairo, page paints | 1.1 / 1.5 | 0.2 / 0.4 | 11.0 / 15.7 | 0.0 / 0.0 | 4.8 / 7.1 | 0.2 / 0.3 | - | 1.6 / 1.9 | 19.6 / 27.5 | 31.7 | 28 |
| 2x | Chrome Cairo, worker paints | 0.6 / 1.2 | 0.1 / 0.3 | 9.2 / 12.0 | 0.0 / 0.0 | 3.0 / 4.5 | 0.2 / 0.3 | - | 0.9 / 1.9 | 15.1 / 18.5 | 50.5 | 7 |
| 2x | native IR (encode only) | 0.2 / 0.4 | 0.0 / 0.1 | 0.0 / 0.0 | 3.3 / 8.1 | 0.0 / 0.0 | - | - | - | 3.6 / 8.8 | - | - |
| 2x | Chrome Canvas, page paints | 0.9 / 1.1 | 0.1 / 0.3 | 0.0 / 0.0 | 12.2 / 18.4 | - | 0.3 / 0.4 | 0.4 / 1.0 | 0.2 / 0.3 | 15.3 / 22.5 | 45.0 | 10 |
| 2x | Chrome Canvas, worker paints | 0.7 / 1.2 | 0.1 / 0.3 | 0.0 / 0.0 | 11.7 / 21.3 | - | 0.2 / 0.3 | 0.5 / 0.9 | 0.3 / 0.4 | 14.4 / 23.7 | 45.2 | 8 |

### s1-06_animation

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.0 / 0.0 | 0.0 / 0.0 | 0.1 / 0.1 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 0.2 / 0.2 | - | - |
| 1x | Chrome Cairo, page paints | 0.3 / 0.7 | 0.2 / 0.5 | 1.0 / 1.3 | 0.0 / 0.0 | 2.1 / 2.6 | 0.1 / 0.4 | - | 0.2 / 0.4 | 4.8 / 6.0 | 61.3 | 0 |
| 1x | Chrome Cairo, worker paints | 0.3 / 0.5 | 0.3 / 0.4 | 0.9 / 1.4 | 0.0 / 0.0 | 1.6 / 2.2 | 0.2 / 0.3 | - | 0.3 / 0.4 | 4.5 / 5.7 | 59.7 | 1 |
| 1x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.4 / 0.5 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.3 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.6 / 2.2 | 61.9 | 0 |
| 1x | Chrome Canvas, worker paints | 0.3 / 0.4 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.7 / 2.4 | 61.8 | 0 |
| 2x | native Cairo | 0.1 / 0.5 | 0.0 / 0.2 | 0.5 / 2.7 | 0.0 / 0.0 | 0.9 / 2.4 | - | - | - | 1.9 / 5.2 | - | - |
| 2x | Chrome Cairo, page paints | 0.3 / 0.4 | 0.2 / 0.6 | 2.4 / 3.4 | 0.0 / 0.0 | 5.6 / 7.3 | 0.2 / 0.3 | - | 1.7 / 2.6 | 11.6 / 14.0 | 58.4 | 1 |
| 2x | Chrome Cairo, worker paints | 0.3 / 0.5 | 0.2 / 0.7 | 1.9 / 4.0 | 0.0 / 0.0 | 5.7 / 7.4 | 0.3 / 0.3 | - | 1.9 / 3.0 | 11.9 / 15.8 | 53.4 | 2 |
| 2x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 2x | Chrome Canvas, page paints | 0.3 / 0.4 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 0.0 / 0.1 | 0.1 / 0.2 | 1.3 / 1.6 | 61.8 | 0 |
| 2x | Chrome Canvas, worker paints | 0.3 / 0.5 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.4 | - | 0.2 / 0.5 | 0.0 / 0.1 | 0.1 / 0.6 | 1.8 / 3.7 | 59.9 | 0 |

### s1-07_bounce

| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x | native Cairo | 0.0 / 0.0 | 0.0 / 0.0 | 0.1 / 0.2 | 0.0 / 0.0 | 0.1 / 0.1 | - | - | - | 0.2 / 0.3 | - | - |
| 1x | Chrome Cairo, page paints | 0.2 / 0.3 | 0.2 / 0.4 | 1.0 / 1.7 | 0.0 / 0.0 | 2.1 / 3.0 | 0.1 / 0.3 | - | 0.2 / 0.4 | 4.7 / 7.0 | 61.5 | 0 |
| 1x | Chrome Cairo, worker paints | 0.2 / 0.3 | 0.2 / 0.4 | 0.6 / 1.2 | 0.0 / 0.0 | 1.5 / 2.0 | 0.2 / 0.3 | - | 0.3 / 0.4 | 3.5 / 4.8 | 61.3 | 0 |
| 1x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.1 / 0.1 | - | - |
| 1x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.4 | 0.0 / 0.0 | 0.3 / 0.5 | - | 0.2 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.5 / 1.7 | 61.9 | 0 |
| 1x | Chrome Canvas, worker paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.4 | - | 0.2 / 0.4 | 0.0 / 0.1 | 0.1 / 0.2 | 1.6 / 2.3 | 61.8 | 0 |
| 2x | native Cairo | 0.1 / 0.3 | 0.1 / 0.3 | 0.7 / 4.4 | 0.0 / 0.0 | 1.3 / 2.7 | - | - | - | 2.6 / 8.1 | - | - |
| 2x | Chrome Cairo, page paints | 0.2 / 0.3 | 0.3 / 0.6 | 2.2 / 3.2 | 0.0 / 0.0 | 5.6 / 8.6 | 0.2 / 0.3 | - | 1.5 / 1.9 | 11.1 / 13.8 | 56.9 | 1 |
| 2x | Chrome Cairo, worker paints | 0.2 / 0.3 | 0.2 / 0.6 | 1.9 / 3.8 | 0.0 / 0.0 | 5.6 / 6.4 | 0.3 / 0.4 | - | 1.9 / 3.1 | 11.9 / 18.9 | 55.0 | 3 |
| 2x | native IR (encode only) | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | - | - | - | 0.0 / 0.0 | - | - |
| 2x | Chrome Canvas, page paints | 0.2 / 0.3 | 0.2 / 0.4 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.3 | 0.0 / 0.1 | 0.1 / 0.3 | 1.4 / 1.7 | 61.9 | 0 |
| 2x | Chrome Canvas, worker paints | 0.2 / 0.3 | 0.2 / 0.3 | 0.0 / 0.0 | 0.2 / 0.3 | - | 0.2 / 0.7 | 0.0 / 0.1 | 0.1 / 0.4 | 1.5 / 2.0 | 59.8 | 0 |

