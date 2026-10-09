# The funground browser runner

Runs a learner's funground sketch in a page: Python (Pyodide 314) in a module Web Worker, funground's host
API (`funground.web.Session`), the real Cairo renderer (pycairo), uharfbuzz and skia-pathops compiled to wasm.
Nothing is stubbed. Design: `docs/design/Web_Runner_Note.md` in funground (story S-153).

## Use it from a page

```html
<canvas id="canvas" width="640" height="400"></canvas>
<pre id="output"></pre>
<script type="module">
  import { createRunner } from "./runner/runner.js";

  const runner = await createRunner({
    canvas: document.getElementById("canvas"),
    output: document.getElementById("output"),   // print() and tracebacks; or a function (text, stream) => ...
  });                                             // resolves when Python is loaded
  const started = await runner.run(source, { filename: "sketch.py" });   // {ok, width, height}
  runner.stop();                                  // ends the run now, even `while True:`
</script>
```

- `createRunner({canvas, output, baseUrl, prewarm, onFrame, onFinish})`. `baseUrl` is the folder holding
  `worker.js` and `runtime/` (default: next to `runner.js`).
- `run(source, {filename, files, width, height})`: `files` maps a path to bytes (`{"data/photo.jpg": Uint8Array}`),
  written beside the sketch before it starts. `width`/`height` are the canvas size `f.full_screen()` fills until
  the sketch calls `f.size()` (default: the canvas element's size). Resolves when `setup()` has run (loop sketch) or
  the script has finished (`f.show()`); `{ok: false}` if the file failed (the traceback is in the output).
- The canvas is resized to the sketch's `canvas_size` (CSS pixels) with `devicePixelRatio` backing pixels. Mouse,
  wheel and keyboard events on the canvas are sent in logical pixels; the canvas takes focus when clicked.
- `stop()` terminates the worker (the sketch's `finish()` does not run). A sketch that ends by itself, or an error,
  ends the run normally. Either way a fresh worker starts loading at once (`prewarm: false` waits for the next `run`).
- `runner.info`: library versions, load times per stage and bytes fetched, as the first worker reported them.

## The runtime folder

`runtime/` (git-ignored) holds what the page loads from its own origin: GitHub release downloads carry no CORS
header, so the site copies these at build time.

    C:\Projects\playground\.venv\Scripts\python.exe tools/build_runtime.py --funground C:\Projects\playground-0.2

It downloads the three C-extension wheels from the `funground-cairo-wasm` release (checked against its
`SHA256SUMS.txt`), builds the funground wheel from the checkout, copies the examples, and writes `manifest.json`.
Pyodide itself comes from jsDelivr; `fonttools` from the Pyodide distribution; `svgelements` and `pypdf` from PyPI
through micropip. `pygame-ce` and `pillow` (Pyodide distribution) are loaded only for a sketch that calls a picture or
sound function (`ON_DEMAND` in `worker.js`; `tools/check_on_demand.py` keeps that list complete).

## Demo, tests

- `runner/demo.html`: serve the repository root with the venv's `python -m http.server` and open `/runner/demo.html`.
- `tools/test_runner.py --funground <checkout>`: headless Chrome, Session 1 and gallery examples against the goldens
  (byte for byte at 1x), Stop, errors, events. Reports in `tests/out/` (git-ignored). `--dpr 1.25` checks a fractional
  scale (size and not blank); `--limit 1 --skip-scenarios [--profile DIR]` measures first load.
- Numbers and how they were measured: `RESULTS.md`.

## Frames

funground hands each frame over as Cairo's bytes (BGRA, premultiplied) in a view valid only during the call. The
worker copies it once into a new buffer, converting to RGBA with straight alpha (what `ImageData` wants), and
transfers the buffer. Converting in the worker keeps the page's thread free; the copy is needed anyway.

## Known limits (S-153)

Measured results, criteria and noise caveats: `RESULTS.md`.

- Sound and microphone are S-137: the mixer is not started (`pygame-ce` is loaded for a sketch that calls a sound
  function, and plays nothing).
- **images-01 is not byte-identical to its golden** (50,454 pixels): Pyodide's JPEG decoder differs from the desktop
  one (PNG decodes identically). The other 14 of the 15 cases are byte-identical at 1x; at `--dpr 1.25` all 15 give a
  full, non-blank frame of the right size. A funground-side decision is needed (see RESULTS.md).
- **First-load budget (S-139) not met on this estimate**: 12.4 MB for a plain sketch (about 10 to 14 s on 10 Mb/s;
  budget 10 s); a repeat visit took 3.3 to 5.5 s here (budget 3 s). Pictures add 2.56 MB (pygame-ce and Pillow) and
  about 1.2 s cold, only for sketches that need them. The bundled fonts are 2.42 MB of the funground wheel.
- A function that needs pygame-ce and is missing from `ON_DEMAND` fails with "No module named 'pygame'":
  `tools/check_on_demand.py --funground <checkout>` finds such a function. `tint` is listed by hand.
- Chrome only was tried. Headless Chrome has no real vsync, so frame rates are not measured here.
- Each run needs a fresh worker (about 5 s on the slow test machine, hidden by `prewarm`).
- The maintainer ran the demo by hand in Chrome on 9 October 2026: animations, interaction, scripts and studios-03
  (an A4 script) render; code editing works. Two bugs found then are fixed: a script's frame was wiped when `started`
  set the canvas size, and at a fractional `devicePixelRatio` the page's rounding differed from funground's by a
  pixel. The canvas's backing size now comes only from the frames.
