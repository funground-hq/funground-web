# S-136 results: the inverted loop in a module worker, driven by requestAnimationFrame

Question: does a sketch run unchanged, driven by `requestAnimationFrame`, with Python in a module Web Worker
and no COOP/COEP headers?

Short answer: yes, in headless Chrome 154 on Windows, for Session-1 sketches without text. 60 fps steady,
stop in under a millisecond, input to drawn frame at most 1.25 frames. The desktop suite is green with the
inverted loop. Open problems are at the end; the largest is the cost of the IR hand-over for busy frames.

Branches (nothing committed or pushed): `spike/s136-loop` in `C:\Projects\playground-0.2` (the
loop change); `spike/s136-worker-loop` in `C:\Projects\funground-web` (this folder's harness).

## Pass criteria (set before the work)

| Criterion | Result | Verdict |
|---|---|---|
| Steady 60 fps in Chrome | 59.99 to 60.06 fps over 10 s for 06, 07, 08, 09 (rAF itself 60.1 to 60.2 Hz); worst rAF gap 17.5 ms | pass |
| Stop within 1 s | `worker.terminate()` returns in under 1 ms; a spinning sketch posted 590 heartbeats in 2 s and **0** in the 1 s after Stop; the page's rAF kept its 60 Hz while the worker spun | pass |
| Input to screen at most 2 frames | event to frame drawn: median 2.8 ms, p95 18.4 ms, max 20.7 ms (at most 1.25 frames); always shown by the first rAF callback after the event. Scan-out not measured (see Limits): worst case about 2 frames | pass on the measured stage, borderline in the worst case at the glass |
| Desktop suite green with the inverted loop | `3620 passed in 564.77s (0:09:24)` | pass |

Firefox and Safari were out of scope (D-074: Chrome first). No COOP/COEP headers: the page reported
`crossOriginIsolated: false` and `typeof SharedArrayBuffer === "undefined"`, so none of this used them.

## What was built

In `harness/s136/` (browser) and `tools/` (build and run):

- `shim.py`: runs in the worker. Stand-ins for the modules Pyodide lacks, `IrRenderer` (records the frame's
  ops), `BrowserPlatform`, and `Host` (`step(now_ms, events_json)` returns `[running, step_ms, encode_ms, ops_json]`).
- `worker.js`: module worker. Loads Pyodide 314.0.7 from `https://cdn.jsdelivr.net/pyodide/v314.0.7/full/`,
  `loadPackage("fonttools")`, unpacks `dist/funground.zip` into `/src`, imports `shim`, runs the sketch file up
  to `f.run()` (which now only calls `start()`), then answers `step` messages.
- `run.html`: the page. A rAF callback posts one `step` message (rAF timestamp plus the DOM events gathered
  since the last frame); if the worker has not answered the previous step, that tick is skipped and counted.
  The worker's reply is drawn with `renderer/ir_canvas.js` (S-135). Stop calls `worker.terminate()`.
  `?canvas=main` draws on the page, `?canvas=worker` transfers the canvas (OffscreenCanvas) to the worker.
  `?synth=mouse|key` dispatches synthetic `MouseEvent`/`KeyboardEvent`s on the page's own listeners.
- `tools/build_s136_bundle.py`: zips `funground/` from the playground-0.2 branch (36 files, 735 KB, **215 KB**
  zipped) without `platform/pygame_platform.py`, `renderers/cairo2d.py`, `export/`, `fonts/`, `gallery.py`, and
  copies `examples/session1` plus three test sketches (`hang`, `hang_hb`, `stress`) into `harness/s136/dist/`
  (git-ignored). `tools/run_s136.py` serves the repository on localhost with the venv Python, starts headless
  Chrome by PID, receives the result by POST and stops Chrome by PID.

Run it: `C:\Projects\playground\.venv\Scripts\python.exe tools/build_s136_bundle.py`, then
`... tools/run_s136.py "sketch=08_mouse&seconds=10&synth=mouse" --name x`. Results land in `results_s136/`
(git-ignored); the numbers below were copied from there.

## Canvas on the page or in the worker

Chosen for the spike: **on the page** (`canvas=main`), measured against the worker canvas.

- Measured: no difference that matters at these loads. 60.0 fps on the page; 58.9 and 59.6 fps with the
  worker canvas (3 and 0 skipped ticks, two 33 ms rAF gaps). The hand-over costs 0.05 to 0.24 ms (message) plus
  0.03 ms (JSON parse); drawing costs 0.1 ms.
- Why the page: the renderer needs things only the page has cheaply (image and font decoding, later the
  controls panel, a future Save as download), a transferred canvas cannot be resized afterwards (a 640x480
  sketch in a 640x400 canvas), and the cost of the hand-over is negligible.
- Why the worker would win later: a frame that takes 50 ms to draw (S-135: shadows 20 to 60 ms) would block
  the page's input and Stop button if drawn on the page. In the worker the frame time is step plus draw in
  series but the page stays free. Decide when S-137 or the editor gives a heavier sketch; the code supports both.

## Measurements

Headless Chrome 154 (`--headless=new`), Windows 11, a slow machine, one Chrome at a time with a fresh
profile, Python and server on localhost, Pyodide from jsDelivr. Time in the page with `performance.now()`;
Python times inside the worker with `time.perf_counter()`; message time is `timeOrigin + now()` stamped in
the worker and read in the page (same clock source). 10 s per run.

### Frames per second and where a frame's time goes (ms, per frame)

"Step" is `Sketch.step()` in wasm. "Encode" is `ir.op_to_jsonable` for every op plus `json.dumps`. "Transfer" is
`postMessage` of the JSON string. Draw is the JS cost of `drawFrame` without a read-back (the GPU work after it
is not included).

| run | fps | rAF Hz | skipped ticks | rAF gap p95 / max | Step mean / p95 | Encode mean / p95 | Transfer mean | Parse mean | Draw mean / p95 | Round trip mean |
|---|---|---|---|---|---|---|---|---|---|---|
| 06_animation | 60.04 | 60.14 | 0 | 16.9 / 17.4 | 0.60 / 0.90 | 0.25 / 0.40 | 0.05 | 0.03 | 0.10 / 0.20 | 1.51 |
| 07_bounce | 60.02 | 60.12 | 0 | 16.9 / 17.2 | 0.42 / 0.60 | 0.30 / 0.50 | 0.24 | 0.02 | 0.09 / 0.20 | 1.37 |
| 08_mouse (mouse input) | 60.06 | 60.16 | 0 | 16.9 / 17.0 | 0.77 / 1.20 | 0.29 / 0.50 | 0.15 | 0.03 | 0.11 / 0.20 | 1.75 |
| 09_keyboard (key input) | 59.99 | 60.19 | 1 | 16.9 / 17.5 | 0.59 / 0.90 | 0.24 / 0.40 | 0.24 | 0.02 | 0.09 / 0.20 | 1.52 |
| 08_mouse, worker canvas | 58.88 | 59.28 | 3 | 16.9 / 33.4 | 0.67 / 1.00 | 0.29 / 0.60 | 0.08 | 0.04 | 0.22 / 0.40 | 2.17 |
| 09_keyboard, worker canvas | 59.62 | 59.72 | 0 | 16.9 / 33.4 | 0.55 / 0.80 | 0.22 / 0.40 | 0.20 | 0.04 | 0.21 / 0.40 | 1.99 |
| stress: 500 translucent circles | **29.15** | 60.10 | 309 | 16.9 / 33.3 | **15.85 / 20.0** | **10.43 / 12.8** | 0.14 | 0.25 | 0.47 / 0.70 | 26.9 |
| stress, worker canvas | 28.67 | 60.13 | 314 | 16.9 / 18.6 | 15.70 / 21.3 | 10.16 / 13.3 | 0.13 | 0.25 | 0.60 / 0.90 | 27.4 |

Session-1 sketches are far inside the 16.7 ms budget: Python 0.4 to 0.8 ms, encode 0.25 to 0.3 ms, transfer
and draw together under 0.4 ms. Their frames are 5 to 10 ops. The stress sketch is not a Session-1 sketch; it is
there to find the limit. At 500 ops the frame costs 27 ms (step 16, encode 10), the page skips every second
tick and the sketch runs at 29 fps. Transfer, parse and draw stayed under 1.3 ms in total: the cost is on the
Python side, in making the ops, and in turning them into JSON.

The 08/09 runs received synthetic input (below). Canvas content was checked after the runs: 08 had 3156
non-white pixels at the end, and 06 and 09 had 1396 and 3024 in 3 s runs (in the 10 s runs the circle had moved
off the canvas).

### Input to screen

Synthetic input dispatched on the page's real listeners, one probe every 70 to 92 ms (an odd interval so that
probes land at different points in a frame): a `mousemove` to a new x (08), or a `keydown` of the right arrow (09).
A probe is answered by the first frame, from a step that carried it, whose first circle shows its effect
(x equal to the probe's x; or x different from the last frame before the key). Time is from `dispatchEvent`
to the end of the page's draw call.

| run | probes answered | ms mean | p50 | p95 | max | rAF callbacks between event and drawn frame |
|---|---|---|---|---|---|---|
| 08_mouse | 96 / 97 | 8.4 | 2.8 | 18.4 | 20.3 | always 1 |
| 09_keyboard | 48 / 48 | 7.8 | 2.6 | 18.1 | 20.1 | always 1 |
| 08_mouse, worker canvas | 97 / 97 | 5.2 | 2.9 | 18.6 | 19.4 | always 1 |
| 09_keyboard, worker canvas | 49 / 49 | 7.0 | 2.5 | 18.5 | 19.4 | always 1 |

The two clusters are the two cases: the event just before a rAF callback (about 2 to 3 ms: one step) or just after
one (about 17 to 20 ms: wait for the next callback, then one step). The one unanswered probe was the last one
before the run ended.

### Stop

The `hang` sketch calls `while True: pass` inside `draw()` from frame 30. `hang_hb` is the same but posts
`js.postMessage("hb")` every 5 ms from inside the loop, so the page can see whether the thread is alive.

| | page canvas | worker canvas |
|---|---|---|
| rAF callbacks on the page during the 2 s the worker spun | 120 (60 Hz kept) | 120 |
| frames drawn during those 2 s | 0 | 0 |
| `terminate()` call | 0.1 ms | 0 ms |
| heartbeats while spinning / in the 1 s after Stop | 592 / 0 | 589 / 0 |
| last heartbeat before Stop | 3.1 ms | 2.1 ms |

Stop needs no help from the sketch, and no SharedArrayBuffer. The sketch's state is lost, as expected.

### First load

Cold = a new, empty Chrome profile (nothing cached; jsDelivr and the link are whatever they were at the time).
Warm = a second run in the same profile (Chrome's HTTP cache). From navigation to the first frame drawn.

| | cold (17 runs, each in a new profile) | warm (1 run) |
|---|---|---|
| first frame | 5.9 to 8.0 s, median 6.4 s (`load_cold`: 6.7 s) | 3.6 s |
| Pyodide JS import | 0.10 s | 0.01 s |
| `loadPyodide` (download and compile the 9.6 MB wasm and stdlib) | 4.6 s (`load_cold`) | 2.4 s |
| `loadPackage("fonttools")` | 0.6 to 1.1 s | 0.2 s |
| fetch and unpack funground (215 KB zip, localhost) | 0.14 s | 0.12 s |
| `import funground` in wasm | 0.47 to 0.49 s | 0.55 s |
| run the sketch to `f.run()` (includes `setup()`) | under 1 ms | 1 ms |

Every measurement run started in a fresh profile, so each is a cold load; the spread is network and machine
noise. The breakdown column is from `load_cold` and `load_warm`. The S-139 budget (10 s on a 10 Mb/s link) is not
tested here: the link was whatever the machine has, unmeasured.

## What needed a stub or a change

Nothing in `funground/` changed except the loop (playground-0.2, `sketch.py`). Everything else is in
`harness/s136/shim.py`:

1. **`uharfbuzz`**: `typography.py:20` does `import uharfbuzz as hb` at import time, and `api.py` imports
   `Font` from it. Stand-in module in `sys.modules`; any use raises an `ImportError` that says text is not
   available in the browser build yet. Consequence: **no text**.
2. **`pathops`** (skia-pathops): `pathops.py` imports it and reads `PathVerb`, `LineCap`, `LineJoin` at module
   level (lines 16, 128, 129); reached by `paths.py` from `marks.py` from `exploring.py` from `api.py`. Stand-in
   with those three names as placeholders; any call raises. Consequence: no path booleans.
3. **`funground.renderers.cairo2d`**: `picture.py:20` imports `CairoRenderer` at import time, and `cairo2d.py`
   imports pycairo. Stand-in module whose `CairoRenderer` is the IR-capturing renderer (built lazily after
   funground's leaf modules exist). `default_renderer()` also resolves to it. Consequence: pictures, `get`/`set`
   pixels, filters, saving, layers' view, marks' `ink_bounds` and the controls panel do not work.
4. **`IrRenderer`**: a `Renderer` whose `render(frame)` stores the ops and whose `pixels()` returns an object
   with no pixels and the ops. `BrowserPlatform.present()` keeps them for the host.
5. **`BrowserPlatform`** (a subclass of `HeadlessPlatform`, which already is "input arrives from outside, no
   waiting"): `tick()` returns the difference of the page's rAF timestamps (and `1/fps` for the first step);
   `present()` keeps the ops; a space key also counts as the name `space` (pygame reports `" "` and answers
   `key_down("space")`); Escape does not end the sketch; `capture()` returns no pixels (so `max_frames` works).
6. **`f.run()`** is replaced in the worker (`funground.run` and `funground.api.run`) by a function that calls
   `start()` and returns. The product needs a switch for this (for example a platform attribute that says it is
   driven by a host); not done here because it is a change to `api.py` and the platform protocol.
7. **Pyodide package**: `fonttools` (typography imports it at load time). `pygame` is not needed to import
   funground: `imaging.py`, `sound.py` and `microphone_input.py` import it lazily.
8. **Left out of the zip** to prove nothing at import time needs them: `platform/pygame_platform.py`,
   `renderers/cairo2d.py`, `export/`, `fonts/`, `gallery.py`.

Sketches: ran in the browser and measured: `06_animation`, `07_bounce`, `08_mouse`, `09_keyboard`. Ran through
the same shim natively with pycairo and pygame blocked, not in the browser: `01`, `02`, `03`, `04`, `10`, `11`,
`12`. **Skipped: `05_text`, `13_transforms`, `14_paths`** (they call `f.text`). `12_default_window` is 640x480:
with the canvas on the page it resizes; with a worker canvas it cannot.

## Limits and open problems

1. **The cost of the hand-over grows with the ops.** `ir.op_to_jsonable` plus `json.dumps` cost 10 ms for 500 ops
   (20 us an op), more than half of the 27 ms frame; step is 16 ms of it. A sketch with a few hundred shapes a
   frame will not hold 60 fps. Options: encode only what the renderer reads, pack numbers into typed arrays
   (the S-135 note already suggests it), or share the live Python objects with JS (`toJs` proxies). The step
   itself (wasm Python, about 30 us an op) is the funground cost, and a faster IR is a product question.
2. **Headless Chrome only.** `--headless=new` gave a steady 60.1 Hz rAF without a visible window; no real
   display, no vsync, no GPU. Frames "drawn" are not frames "seen": scan-out is not measured, so the 2-frame
   input criterion is met for the stage we could measure (at most 1.25 frames, 20.7 ms) and not proven at the
   glass (worst case about 2 frames). A visible window and a high-speed camera, or a photodiode, would tell.
3. **Chrome 154 on one machine.** Firefox and Safari not run (out of scope). Background-tab throttling
   (rAF pauses when the tab is hidden) not tested.
4. **`f.run()` is patched from outside.** The product needs a supported way: web `f.run()` registers and returns.
5. **Not covered**: text (needs the shaper, S-133), pictures, pixels, filters, files (Cairo, S-134), sound and
   microphone (S-137), controls panel, `show()` and scripts, mouse wheel, touch, HiDPI (the platform reports 1.0;
   `devicePixelRatio` was 1), full screen, cursor.
6. **First step's `delta_time`** is `1/fps` rather than a measured time; `millis()` uses `perf_counter` (which in
   Pyodide follows `performance.now()`), not the page's rAF clock, so it can differ from `delta_time` by a frame.
7. **Escape** no longer stops a web sketch; the page's Stop button does. The Web_Target_Options note already
   asks that Escape not be the only way to stop.
8. **Skipped ticks keep the frame rate honest but lose time**: when a step takes longer than a frame the next rAF
   is skipped, not queued. That is the right choice (no growing queue); `delta_time` then shows the longer gap.
9. **Cold load is 5.9 to 8.0 s (median 6.4 s), about 4.6 s of it Pyodide.** Budget for S-139 (10 s on 10 Mb/s) not tested.
10. **The measurement uses Chrome's `--disable-renderer-backgrounding` and related flags** to keep timers honest in
    headless mode; a normal user's browser does not have them but has a visible, focused tab.

## Recommendation

L1 (inverted loop, Python in a module worker, page-driven) works as designed and costs nothing in complexity
that the desktop notices. Keep it. Next: (a) a supported web `f.run()`; (b) a cheaper IR hand-over before the
gallery's busy sketches are measured (S-135 + this: draw is not the problem); (c) a visible-window latency check
on the maintainer's display if the 2-frame criterion matters at the glass. L3 (SharedArrayBuffer input) is not
needed: nothing here lagged.
