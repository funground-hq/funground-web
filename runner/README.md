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

- `createRunner({canvas, output, baseUrl, prewarm, onFrame, onFinish, onSound, onFile, ...})` (the options after `onSound` are in the table below). `baseUrl` is the folder holding
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
  and tools); `runner.audioState()` says whether sound is unlocked and what each voice is doing, and
  `runner.cameraState()` whether the camera is open (`null` when it is not).
- The camera (S-172). When the sketch calls `cam.start()`, the page asks the browser for the camera and, before each frame,
  sends the newest picture to the sketch, scaled to the size it asked for (`camera.js`). `cam.stop()`, Stop and the end of
  a run let it go, so the camera's light goes off. A refusal gives the sketch one line, "The camera is not available:
  ...", and no error. A page that runs sketches in an iframe must allow the camera: `<iframe allow="camera">`.
  Tested by `tools/test_camera.py` with Chrome's fake camera.
- Models (S-232). `ml.pose(cam)` and `ml.hand(cam)` work with the same sketch as on a computer. See "Models" below.
- `runner.info`: library versions, load times per stage and bytes fetched, as the first worker reported them.
- Options for the VS Code panel (S-156, S-158). All are off or default by default, so `demo.html` and the website behave as
  before. They go in `createRunner({...})` unless the table says `run()`.

| Option | Default | What it does |
|---|---|---|
| `pyodideUrl` | jsDelivr (in `worker.js`) | The folder Pyodide loads from. |
| `onnxruntimeUrl` (S-232) | jsDelivr, one exact version (in `worker.js`) | The folder `onnxruntime-web` loads from, for `ml.pose()` and `ml.hand()`. It must hold `ort.wasm.mjs` and the `.wasm` file beside it. |
| `runtimeUrl` | `runtime/` under `baseUrl` | The folder holding `manifest.json` and the wheels. A manifest entry with role `dependency` is installed from there instead of PyPI. |
| `packages` (S-274) | left out | What is loaded besides Python. Left out or `["funground"]`: funground and its libraries, as always. `[]`: Pyodide alone, and `run()` runs plain Python. Anything else makes `createRunner` reject. See "What gets loaded" below. |
| `reuse` (D-083) | `false` | Run the next sketch in the same worker (the same Python) when the last one has ended, or stops when asked: a re-run takes about 0.1 s instead of loading Python again. funground's `Session` starts each sketch afresh. A sketch that does not stop within a second (`while True:`, or a long `setup()`) still has its worker ended, and a new Python loads (seconds). |
| `onRestart` | none | With `reuse`: called when that happens, so the page can say why the next run waits. |
| `spare` | `false` | While a sketch runs, keep the next run's worker loaded too, so that a re-run starts at once. Costs a second Python's memory. Not needed with `reuse`. |
| `onFile` (S-212) | none | Called with `{name, bytes, type}` for each file the sketch writes in its folder (see "Files the sketch saves" below). |
| `microphoneRefusal` | none | For a host that does not allow the microphone (VS Code's panel): the line a sketch that calls `mic.start()` gets in its output instead. The browser is not asked, and the sketch hears nothing (as after a refusal). |
| `cameraRefusal` (S-172) | none | For a host that does not allow the camera (VS Code's panel): why, in a few words. A sketch that calls `cam.start()` gets "The camera is not available: *reason*." in its output; the browser is not asked, and the camera is never ready (as after a refusal). |
| `run(source, {seed})` | none | Seed funground's random numbers for this run, so every run draws the same (tests compare frames with goldens). It is applied to the run's own sketch, after funground's `Session` is made. |
| `run(source, {stdin})` (S-272) | none | The lines `input()` reads, as a list of strings (see "Input lines" below). |

  A runner whose files are on another origin (a VS Code webview loads them from its resource origin) starts its worker from a
  `blob:` URL. Results: `spikes/S-156_RESULTS.md`, `vscode-extension/RESULTS.md`.
- Beside the sketch. Each run gets a fresh working folder, which is also first on Python's import path (as the sketch's own
  folder is under `python sketch.py`). `run(..., {files})` writes into it, so `files` can hold data (`data/photo.png`) and
  other `.py` files the sketch imports (`helpers.py`); modules imported that way are forgotten when the run stops, so an
  edited helper is read again.

## What the runner can do (S-275)

`runner.info.capabilities` lists what this runner can do, as words (D-142 a). A host looks for the word before it sends work
that needs it, instead of finding out from an error:

```js
const runner = await createRunner({ output });
if (!runner.info.capabilities?.includes("stdin")) refuse("This exercise needs input lines, which this runner cannot give.");
```

| Word | Since | Means |
|---|---|---|
| `run` | S-275 | `run(source, {...})` runs a file; `print()` and errors reach `output` |
| `stop` | S-275 | `stop()` ends a run at once, even one stuck in `while True:`, and the next run works |
| `stdin` | S-272 | `run(source, {stdin: [lines]})` gives the lines `input()` reads (below) |
| `check` | S-273 | `check(source, {tests})` runs a learner's code and then your tests on it (below) |

- A word is added by the story that ships it, and never removed within a version line. A runner older than S-275 has no
  `capabilities` at all: treat that as `["run", "stop"]`.
- Each word has checks of its own in `tools/test_runner.py`, named after it (`stdin: ...`). The suite fails if a word in the
  list has none, or if any of them fails.

## Input lines (S-272)

A host gives the lines a run reads, one string for each `input()` (D-139 a):

```js
await runner.run('name = input("Your name? ")\nprint("Hello,", name)', { filename: "main.py", stdin: ["Ada"] });
```

- `input()` returns the lines in order, and `sys.stdin.readline()` reads the same lines. A line must not contain a newline.
- The prompt is written to the output as CPython writes it, with no newline. It is sent as its own `output` message when
  `input()` reads, so the example's output is two messages, `Your name? ` and `Hello, Ada`. Joined, they read
  `Your name? \nHello, Ada`; CPython given the same line in a pipe prints `Your name? Hello, Ada` (WEB-D-001).
- When the lines run out, `input()` raises `EOFError: input() has no more lines to read: this run was given 1.`, and the run
  ends with an error, as any uncaught exception does.
- Without `stdin`, a run behaves as before S-272: `input()` raises `OSError: [Errno 29] I/O error`. Its prompt is now shown
  before the error (as the last output of the run, below).
- Nobody types: there is no interactive input. Waiting for a person's typing inside the worker needs cross-origin isolation,
  which is a later story.
- Output that has no newline yet, a prompt or a `print(..., end="")`, is sent when `input()` reads and when the run ends
  (the script finishes, the sketch ends or fails, or `stop()` with `reuse`). Before S-272 such a last line was lost, or with
  `reuse` came out at the front of the next run's output (S-271).

## Checks (S-273)

A host sends a learner's code and its tests, and gets one result for each test (D-139 a, D-141 a):

```js
const { tests, output, error } = await runner.check(source, {
  filename: "main.py",                                   // default
  stdin: ["Ada"],                                        // optional: the lines input() reads, as for run()
  files: { "data/words.txt": bytes },                    // optional: as for run()
  tests: [
    { name: "doubles", code: "assert double(4) == 8, 'double(4) should be 8'" },
    { name: "greets", code: "assert 'Hello, Ada' in output" },
  ],
});
// tests: [{ name: "doubles", passed: true, message: "" }, { name: "greets", passed: false, message: "This check failed: assert 'Hello, Ada' in output" }]
```

- The learner's code runs first, as a plain script in a new run folder. It does not go through funground's `Session`: there is no
  canvas and no `setup()` or `draw()`. What it prints is not streamed. It comes back in the answer as `output`, one string,
  exactly as printed, an `input()` prompt too: `"Name? Hello, Ada\n"`.
- If the code raises, or has a syntax error, `error` is the traceback from the learner's file down (with the source line and the
  `^` markers, as Python shows them), `tests` is `[]`, and no test runs. Otherwise `error` is `null`.
- Each test then runs in order, in the same Python. Its `code` is Python. It sees the learner's names (functions, variables) and two more:
  `output` (the string the learner printed) and `source` (the learner's code as one string). A test gets its own shallow copy of
  those names, so a name one test sets is not seen by the next. A list it changes in place is. What a test prints is discarded.
- `passed` is true when the test's code runs without an exception. When it does not, `message` says why:
  - `assert x == 1, "text"` gives `text`.
  - `assert x == 1` with no text gives `This check failed: assert x == 1`.
  - Any other exception gives `The check raised NameError: name 'totl' is not defined`.
  - `message` is `""` when the test passed.
- Messages: the page sends `{type: "check", source, filename, stdin, files, tests}` and the worker answers
  `{type: "checked", tests, output, error}` (the worker's table is at the top of `worker.js`).
- `check()` ends a run in progress first, uses the same worker, and follows the same `reuse` rules as `run()`. It counts as the run
  in progress: `onFinish("ended")` is called when it is answered. A host that never calls `check()` sees no change.
- **A test that never ends** (`while True:`) cannot answer. The host calls `stop()`, which ends the worker as it does for a sketch,
  and the promise resolves with `error: "The check was stopped."`. There is no timeout in the runner: the host decides how long to wait.
- For test writers: a test sees the learner's whole program. A check on the source text (`"for" in source`) is easy to fool, with a
  comment or a string. Prefer checking what the code does: call the function, look at `output`.

## Files the sketch saves (S-212)

`f.save("poster.png")`, `f.save("poster.pdf")`, `f.save("art.svg")`, `f.save_gif(...)` and a plain `open("x.txt", "w")` write into the
sketch's own folder (the one `files` were written to). The runner tells the page about them:

```js
const runner = await createRunner({ canvas, onFile: ({ name, bytes, type }) => offerDownload(name, new Blob([bytes], { type })) });
```

- `name` is the path in the sketch's folder (`"out.png"`, `"frames/0001.png"`), `bytes` a `Uint8Array` with the whole file, `type`
  its MIME type (`image/png`, `application/pdf`, `image/svg+xml`, `image/gif`, `video/mp4`; other files `application/octet-stream`).
- Which files: new or changed since the run began. A file the page passed in `files` is sent only when the sketch
  rewrites it (a take kept in Play's My files and recorded again, S-221). The worker lists the folder (name,
  size, modified time) after every step, after a script's last line, and after the sketch's `finish()` when the run is stopped
  with `reuse`. So a save in an animation arrives within the frame that made it, once; saving the same name again sends it again.
- `onFile` can be called after `onFinish` (the last frame saved, then the run ended). Without `reuse`, `stop()` ends the worker at
  once: files saved up to the last finished step have arrived, a `finish()` that saves has not run.
- A GIF is made with Pillow, loaded when the source says `save_gif(` or `.gif`. An MP4 needs ffmpeg, which a browser does not have:
  the sketch gets funground's "cannot find ffmpeg" error.

## Keeping the picture (S-226)

`runner.keep(note)` asks the run in progress to do what `f.keep(note)` does in a sketch: it saves the picture, a copy of the code and a record as
`studio/001.png`, `studio/001.py` and `studio/001.json` (the next free number) in the sketch's folder. Each file reaches `onFile` as any saved file does,
once, before the promise resolves.

```js
const result = await runner.keep("I kept the low circle because it looks deliberate");
// { ok: true, base: "/tmp/tmpab12/studio/001", files: ["studio/001.json", "studio/001.png", "studio/001.py"] }
// { ok: false, reason: "The sketch is not running, so there is no picture to keep. Run it, then keep." }
```

- It keeps the frame on the screen, now: the files are written before the answer, however the sketch draws. A sketch that called `f.no_loop()` can be kept,
  and so can a script that has finished drawing, with `reuse` (Play's preview uses it): without it the worker is ended with the run. The code in `studio/001.py` is the code that was run.
- Before the first frame there is nothing to keep yet: the files arrive with the first frame, so `files` can be empty. After Stop, after an error or
  after `f.stop()` the picture is gone: the answer is `{ ok: false, reason }`.
- It also resolves `{ ok: false }` if the worker does not answer within ten seconds.

## The runner's files

`files.json` names the runner's own scripts. A site that serves the runner copies exactly those, and `runtime/`
(funground-hq.github.io's `tools/assemble.py`). A new script goes on the list in the same change that adds it:
`tools/check_runner_files.py` fails when a script loads one that is not named, when a named one is missing, or when
a script in `runner/` is not named, and `tools/build_runtime.py` runs it before building. On 7 Nov 2026 the site's
own list lacked `models-glue.js` and `models-worker.js`, and no sketch could start in Play.

## The runtime folder

`runtime/` (git-ignored) holds what the page loads from its own origin: GitHub release downloads carry no CORS
header, so the site copies these at build time.

    C:\Projects\playground\.venv\Scripts\python.exe tools/build_runtime.py --funground C:\Projects\playground-0.2

It downloads the three C-extension wheels from the `funground-cairo-wasm` release (checked against its
`SHA256SUMS.txt`), builds the funground wheel from the checkout, copies the examples, and writes `manifest.json`.
Pyodide itself comes from jsDelivr; `fonttools` from the Pyodide distribution; `svgelements` and `pypdf` from PyPI
through micropip. `pygame-ce` and `pillow` (Pyodide distribution) are loaded only for a sketch that calls a picture
function (`ON_DEMAND` in `worker.js`; `tools/check_on_demand.py` keeps that list complete). Sound does not need them. Pillow alone
is loaded for `save_gif(` or a `.gif` in the source.
The bundled fonts (`funground/fonts/*.ttf`, 2.4 MB of the wheel) are not in the funground wheel (S-211): they are copied to
`runtime/fonts/<name>.ttf.bin` and the manifest lists each (role `font`). Nothing is fetched at start-up. `worker.js` gives the
funground `Session` a `fetch_font` function (a synchronous request) and the manifest's sizes and SHA-256, and funground calls it the
first time it opens a bundled font: a sketch with no text fetches none, plain text fetches `DejaVuSans.ttf` (757 KB), the Noto
fallbacks come only for emoji, symbols or Devanagari. There is no list of names to keep complete. It works on every host,
including one that compresses fonts (GitHub Pages does). A font whose bytes differ from the manifest gives one clear error naming it.
`runner.info.fonts` is `"on open"`. Design and numbers: `RESULTS.md`, section 5.
It also builds `funground_ml-*.whl` from the checkout's `ml/` folder (S-232; `--ml` names another) and writes `models.json`.
`build_runtime.py --offline` rebuilds the funground wheel and the examples without downloading, keeping the
C-extension wheels already in `runtime/wheels/` (checked against `manifest.json`).

## What gets loaded (S-274)

`createRunner({packages})` says what the worker loads besides Python (D-140 a, D-144 e):

| `packages` | What is fetched | What `run()` does |
|---|---|---|
| left out | Pyodide, `micropip`, `fonttools`, `manifest.json`, the three C-extension wheels, `svgelements`, `pypdf` and the funground wheel | funground's `Session` runs the file |
| `["funground"]` | the same as left out, the same files | the same |
| `[]` | Pyodide alone: nothing from `runtime/`, no `micropip`, no wheels, no fonts | the file runs as a plain Python script |

- A host that says nothing gets exactly the start it always had. Play and the VS Code panel do not change.
- Anything else (another name, or not a list) makes `createRunner` reject with one sentence: `packages can only be [] or ["funground"]
  in this runner; other packages come later (S-276)`. S-276 widens the same list to Pyodide packages and a host's own wheels.
- **funground is implicit wherever it is loaded.** It is always installed at start, never when a file imports it: the source cannot say
  for sure whether a file needs it (a file that defines `draw()` and never calls `run()` still runs as a sketch, D-088). When it is loaded, every script and sketch goes through its `Session`,
  with or without `import funground`. There is no plain-script path in a runner that has funground (`check()` is the one exception, S-273).
- **S-271 measured the difference** on a cold load: Pyodide alone transfers 6.24 MB and is ready in 4.3 s, against 10.34 MB and 7.3 s
  for the full start.
- **Pyodide alone.** `run(source, {filename, files, stdin})` writes the files to a new run folder and runs `source` as `python filename`
  would. `print()` is streamed to `output` as in a funground script, an uncaught error is trimmed to the learner's file and line, and
  `started` answers `{ok: true, width, height}` with the size `run()` was given. The run ends then (`onFinish("ended")`, or
  `"error"`), as a script that has finished drawing does. There is no canvas, no frame, no sound, and none of the on-demand packages.
  `check()` and `stop()` work as before.
- A file that imports funground there gets one plain error from its own line, instead of `No module named 'funground'`:
  `ModuleNotFoundError: This runner was started without funground, so "import funground" cannot work here.`
- `runner.info.versions` holds `python` and `pyodide` (a full runner lists its libraries too). `runner.info.fonts` is `"none"`.
  `runner.info.capabilities` is the same list.

## Models (S-232)

`ml.pose(cam)`, `ml.hand(cam)` and `ml.person(cam)` (the `funground-ml` package) find a body, a hand or the outline of a person. The sketch is the same file as on a computer
and has no `async`. Design: `docs/design/Web_Runner_Note.md` (Models) and `ML_Package_Note.md` in funground.

- **The models worker.** `models-worker.js` is a module worker that `worker.js` starts the first time a sketch asks for a model, so a
  sketch that asks for none pays nothing. Inference runs there, beside the sketch, never inside its step. `worker.js` relays each picture
  to it (the buffer is transferred) and, between two steps, pushes each answer into funground's `Session` (`push_models`). At most one picture is in flight for each source and task; the others are dropped.
  So `ml.pose(cam)` gives the newest answer the browser has: `None` until the first arrives, and it can be one frame behind.
  `models-glue.js` does the pictures-in, points-out work (the JavaScript twin of funground-ml's `_glue.py`: the same thresholds and the same
  rule for reusing a found box). For `ml.person` it also has the model's input (`stretchToTensor`: Pillow's bilinear resize written out) and output: the worker
  answers with the 256 x 256 mask as bytes (`push_models_mask`), and Python stretches it over the picture in Cairo (3.7 ms at 640 x 480 in Pyodide).
- **onnxruntime-web.** Loaded in the models worker from `https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/` (`ONNXRUNTIME` in
  `worker.js`): `ort.wasm.mjs`, the wasm build only, with `wasmPaths` at the same folder. The version is exact; it was the newest that
  was at least two weeks old when it was pinned (2 November 2026). The runner option `onnxruntimeUrl` replaces the folder (it must end with
  the same files). It has no telemetry to switch off: at that version the loader fetches its own `.wasm` file and nothing else.
- **The model files.** `tools/build_runtime.py` writes `runtime/models.json` (manifest role `models`) from funground-ml's
  `_models.py`: the Hugging Face address (pinned to a commit), size and SHA-256 of the five files, and which make each task (two for pose and hand, one for person). The
  worker downloads a file once, checks it with `crypto.subtle.digest`, and keeps it in Cache Storage (`funground-models-v1`). Later runs, offline too,
  read the kept copy, which is checked again when read. The first time, the sketch's output gets one line, the desktop's with the
  folder wording changed: `Downloading the pose model, 18 MB, once. After that the browser keeps a copy.` (`8 MB` for the hand.) With no connection and no copy, or a file that fails its check, the sketch gets one sentence
  (the desktop's, ending "after that the browser keeps a copy") and `None`.
- **On demand.** A sketch (or a `.py` file beside it) that contains `from funground import ml` makes `worker.js` install the
  `funground-ml` wheel (`runtime/wheels/funground_ml-*.whl`, pure Python, manifest role `funground-ml`), without its dependencies. No numpy, Pillow or onnxruntime is
  loaded in Python. `ON_DEMAND` has the entry (`wheels` and `matches`); `tools/check_on_demand.py` still checks the pygame list.
- **Tested** by `tools/test_models.py` (see "Demo, tests"). Chrome's WebAssembly runs on one thread here: Play is not cross-origin isolated, so `onnxruntime-web` uses
  one thread.

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
  microphone is never played back. Choosing a microphone by name (`sound.microphone("USB")`) is desktop-only.
- `sound.load()` reads 16-bit WAV files here; OGG and MP3 raise a `ValueError` that says so.

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
  (byte for byte at 1x), Stop, errors, events, fonts on demand (request counts) and saved files (`onFile`). Reports in `tests/out/` (git-ignored). `--dpr 1.25` checks a fractional
  scale (size and not blank); `--limit 1 --skip-scenarios [--profile DIR]` measures first load.
- `tools/test_sound.py --funground <checkout>`: sound and the microphone (S-137) in headless Chrome with a fake microphone:
  the examples' sound commands against CPython's, audible output at the speakers, the fake microphone's level reaching
  the sketch, and the skip-before-a-gesture line. Report in `tests/out/sound_report.json`.
- `tools/test_models.py --ml-python <python with funground-ml>`: `ml.pose()` and `ml.hand()` (S-232) in headless Chrome, started by
  `tools/chrome_page.mjs` (Node and `playwright-core`, its own temporary profile). The same sketch (`tests/runner/models_sketch.py`) runs on the desktop
  with `onnxruntime` and in the runner with `onnxruntime-web`, on funground's two test photographs; every point must agree within 5 px.
  It also checks the download line and the cache (a second run reads the kept copy and asks the model site for nothing), the no-connection and wrong-checksum sentences, a camera sketch that loads no numpy or Pillow, and measures
  answers a second. The model site is answered from `ml/tests/.models` (`--live` downloads from huggingface.co for real). Report in `tests/out/models_report.json`.
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
  about 1.2 s cold, only for sketches that need them. The bundled fonts were 2.42 MB of the funground wheel; since S-211 they are fetched on demand, which brings a first load of a sketch without text to
  about 10.1 MB (RESULTS.md, section 5).
- A function that needs pygame-ce and is missing from `ON_DEMAND` fails with "No module named 'pygame'":
  `tools/check_on_demand.py --funground <checkout>` finds such a function. `tint` is listed by hand.
- Chrome only was tried. Headless Chrome has no real vsync, so frame rates are not measured here.
- Each run needs a fresh worker (about 5 s on the slow test machine, hidden by `prewarm`).
- The maintainer ran the demo by hand in Chrome on 9 October 2026: animations, interaction, scripts and studios-03
  (an A4 script) render; code editing works. Two bugs found then are fixed: a script's frame was wiped when `started`
  set the canvas size, and at a fractional `devicePixelRatio` the page's rounding differed from funground's by a
  pixel. The canvas's backing size now comes only from the frames.
