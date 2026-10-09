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

- `createRunner({canvas, output, baseUrl, prewarm, onFrame, onFinish, onSound})`. `baseUrl` is the folder holding
  `worker.js` and `runtime/` (default: next to `runner.js`).
- `run(source, {filename, files, width, height})`: `files` maps a path to bytes (`{"data/photo.jpg": Uint8Array}`),
  written beside the sketch before it starts. `width`/`height` are the canvas size `f.full_screen()` fills until
  the sketch calls `f.size()` (default: the canvas element's size). Resolves when `setup()` has run (loop sketch) or
  the script has finished (`f.show()`); `{ok: false}` if the file failed (the traceback is in the output).
- The canvas is resized to the sketch's `canvas_size` (CSS pixels) with `devicePixelRatio` backing pixels. Mouse,
  wheel and keyboard events on the canvas are sent in logical pixels; the canvas takes focus when clicked.
- `stop()` terminates the worker (the sketch's `finish()` does not run). A sketch that ends by itself, or an error,
  ends the run normally. Either way a fresh worker starts loading at once (`prewarm: false` waits for the next `run`).
- Sound and the microphone work with no setup (next section). `onSound(message)` sees each sound command (for tests
  and tools); `runner.audioState()` says whether sound is unlocked and what each voice is doing.
- `runner.info`: library versions, load times per stage and bytes fetched, as the first worker reported them.
- Options added for the VS Code panel (spike S-156; all off by default): `pyodideUrl` and `runtimeUrl` (where Pyodide and
  the wheels load from), `run(..., {seed})` (a repeatable run), `spare` (keep the next worker loaded) and `reuse` (run the
  next sketch in the same worker when the last one stops on request; a sketch that does not stop within 250 ms has its
  worker ended). A runner whose files are on another origin starts its worker from a `blob:` URL. A manifest entry with
  role `dependency` is installed from the runtime folder instead of PyPI. Results: `spikes/S-156_RESULTS.md`.

## The runtime folder

`runtime/` (git-ignored) holds what the page loads from its own origin: GitHub release downloads carry no CORS
header, so the site copies these at build time.

    C:\Projects\playground\.venv\Scripts\python.exe tools/build_runtime.py --funground C:\Projects\playground-0.2

It downloads the three C-extension wheels from the `funground-cairo-wasm` release (checked against its
`SHA256SUMS.txt`), builds the funground wheel from the checkout, copies the examples, and writes `manifest.json`.
Pyodide itself comes from jsDelivr; `fonttools` from the Pyodide distribution; `svgelements` and `pypdf` from PyPI
through micropip. `pygame-ce` and `pillow` (Pyodide distribution) are loaded only for a sketch that calls a picture
function (`ON_DEMAND` in `worker.js`; `tools/check_on_demand.py` keeps that list complete). Sound does not need them.
`build_runtime.py --offline` rebuilds the funground wheel and the examples without downloading, keeping the
C-extension wheels already in `runtime/wheels/` (checked against `manifest.json`).

## Sound and the microphone (S-137)

funground makes every sound in Python and keeps its own clock; the worker posts each sound's samples (once) and its
play, pause, stop, volume and pan commands as `sound` messages, and `audio.js` plays them with Web Audio. pygame-ce is
not loaded. Design and message list: `docs/design/Web_Runner_Note.md` in funground, "Sound and microphone".

- A browser keeps a page silent until the visitor clicks or presses a key on it. `Run` is such a click, and the first
  click or key on the page also unlocks sound. A sound a sketch starts before that is skipped, with one line in the
  output (it is not an error), and is not started later.
- The microphone is opened when the sketch calls `mic.start()`: the browser asks permission, `microphone-worklet.js`
  (an AudioWorklet) posts chunks of 1024 mono samples, and the worker puts them into the ring buffer the desktop code
  fills. Until you allow it, `level()` is 0 and `pitch()` is `None`. A refusal is one line in the output. The
  microphone is never played back. Choosing a microphone by name (`f.microphone("USB")`) is desktop-only.
- `f.load_sound()` reads 16-bit WAV files here; OGG and MP3 raise a `ValueError` that says so.

### Try the sound (for a person, with ears)

Serve the repository (`C:\Projects\playground\.venv\Scripts\python.exe -m http.server` from its root), open
`/runner/demo.html` in Chrome and pick an example (the sound ones are in the list).

1. `sound-02_write_a_tune`: press Run. You should hear a tune with a soft pad under it, starting at once, in tune and
   without clicks. Press Stop: the sound must stop at once.
2. `sound-03_sargam_over_a_drone`, `music-04_hear_a_raga`, `music-05_tala`: a drone or a tala that loops. Listen at
   the loop point for a click or a gap (the desktop version has none), and for the tala's accent on the first beat.
3. Left and right: in a sketch, `snd.pan(-1)` should come from the left speaker only, and `snd.pan(1)` from the right.
4. `sound-04_tuner` (or `music-06_see_your_voice`): Chrome asks to use the microphone. Allow it, then sing or whistle a
   steady note. The tuner should name your note, and the bar should move when you speak. Deny it once, to see the line
   in the output (reset it with the icon in the address bar).
5. Reload the page and press Run without clicking anywhere else first. Run is itself a click, so sound should play. To
   see the "Sound is off" line, start a sketch from code that runs on load.

Beyond that, listen for: a delay between a key press and its sound (Web Audio adds a few tens of milliseconds over the
desktop); crackling while a sketch draws heavily (the worker makes the samples and the page plays them, so heavy
drawing should not touch the audio); and a microphone that comes back out of the speakers (it must not).

## Demo, tests

- `runner/demo.html`: serve the repository root with the venv's `python -m http.server` and open `/runner/demo.html`.
- `tools/test_runner.py --funground <checkout>`: headless Chrome, Session 1 and gallery examples against the goldens
  (byte for byte at 1x), Stop, errors, events. Reports in `tests/out/` (git-ignored). `--dpr 1.25` checks a fractional
  scale (size and not blank); `--limit 1 --skip-scenarios [--profile DIR]` measures first load.
- `tools/test_sound.py --funground <checkout>`: sound and the microphone (S-137) in headless Chrome with a fake microphone:
  the examples' sound commands against CPython's, audible output at the speakers, the fake microphone's level reaching
  the sketch, and the skip-before-a-gesture line. Report in `tests/out/sound_report.json`.
- Numbers and how they were measured: `RESULTS.md`.

## Frames

funground hands each frame over as Cairo's bytes (BGRA, premultiplied) in a view valid only during the call. The
worker copies it once into a new buffer, converting to RGBA with straight alpha (what `ImageData` wants), and
transfers the buffer. Converting in the worker keeps the page's thread free; the copy is needed anyway.

## Known limits (S-153)

Measured results, criteria and noise caveats: `RESULTS.md`.

- Sound and microphone: S-137, above. Nobody has listened yet (the tests check the samples and that the speakers get a
  signal); the list above is for the maintainer.
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
