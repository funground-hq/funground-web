// The funground browser runner, worker side (story S-153, docs/design/Web_Runner_Note.md in funground).
//
// A module worker that runs one learner's file with Pyodide and funground's host API (funground.web.Session).
// The page drives it; every message has a `type`.
//
//   page -> worker
//     init   {runtimeUrl?, pyodideUrl?, onnxruntimeUrl?, modelsScripts?}   load Pyodide and install everything; answers `ready`.
//                                           `onnxruntimeUrl` is the folder onnxruntime-web loads from (default below); `modelsScripts`
//                                           is {worker, glue}, the addresses of models-worker.js and models-glue.js
//     run    {source, filename, width, height, scale, files, seed?, stdin?}   start the file; answers `started`. `files` maps a path
//                                           to bytes: data beside the sketch, and other .py files it may import. `stdin` (S-272)
//                                           is a list of strings, the lines input() and sys.stdin read in order
//     step   {now}                          one display frame, `now` in seconds; answers `stepped`
//     event  {kind, x, y, button, key, keyCode, delta}   one input event (funground's InputEvent vocabulary)
//     microphone {samples}                  a Float32Array of mono samples (-1 to 1, 44 100 Hz) the microphone heard
//     camera {pixels, width, height}        one camera frame: RGBA bytes (a Uint8ClampedArray whose buffer is transferred)
//     camera-unavailable {reason}           the page could not open the camera; funground prints one line with the reason
//     keep   {id, note}                     run funground's f.keep(note) for the run (S-226): studio/NNN.png, .py and .json in the
//                                           run's folder, written before the answer; answers `kept`
//     stop                                  end the run (the sketch's finish() runs), so the worker can run another file;
//                                           answers `stopped`. Used by runner.js's `reuse` option (D-083)
//
//   worker -> page
//     ready    {versions, capabilities, timings, resources, fonts}   everything is installed and checked; capabilities is
//                                           CAPABILITIES (S-275); fonts is "on open" (S-211: each font is fetched when funground first opens it)
//     started  {width, height, running}         the file ran; the canvas size it asked for (logical pixels)
//     frame    {pixels, width, height}          RGBA bytes (physical pixels); the ArrayBuffer is transferred
//     stepped  {running}                        the step is done; false when the sketch has ended
//     output   {stream, text}                   one line of print() ("stdout") or of an error ("stderr"), without its newline; or
//                                               text with no newline yet, sent when input() reads or the run ends (S-272)
//     error    {message}                        the file or the setup failed (message is a Python traceback)
//     sound    {command, voice, fields, samples} a sound command for Web Audio (funground/platform/browser_audio.py has the
//                                               list); `samples` is a Float32Array whose buffer is transferred, for "load" only
//     microphone {command}                      "start", "stop" or "close": the sketch wants the microphone listened to or let go
//     camera   {command, fields}                "start" {width, height}, "stop" or "close": the sketch wants camera frames at that
//                                               size, or lets the camera go (camera.js)
//     stopped  {}                               the run asked to stop has ended; the worker is ready for another `run`
//     (the models worker, models-worker.js, is started by this worker, not by the page: see Models below)
//     kept     {id, ok, base?, files?, reason?}  the answer to `keep`: `files` names the files it wrote (each also sent as a
//                                               `file` message just before this one); `ok: false` with a plain `reason` when
//                                               there is no run to keep (it was stopped, or has ended)
//     file     {name, bytes, type}              a file the sketch wrote in its folder (S-212): new or changed since the run began,
//                                               or one the page passed in `files` that the sketch then rewrote (S-221); `bytes` is an ArrayBuffer (transferred), `type`
//                                               its MIME type. Sent after the step (or the script, or the stop) that wrote it, and
//                                               before that step's `stepped`
//
// A sketch that never returns (`while True:`) cannot answer `stop`: the page ends such a run by terminating the worker.
// A sketch that ends by itself finishes normally and says `stepped {running: false}`.
//
// Frames. funground hands over each finished frame as the Cairo surface's bytes (BGRA, premultiplied) in a view
// valid only during the call. We copy it once, into a fresh buffer, converting to the RGBA, straight-alpha bytes
// that ImageData wants, and transfer that buffer. Converting here, not on the page, keeps the page's thread free,
// and the copy has to happen anyway because the view dies when the call returns.
//
// Sound. funground makes every sound itself and keeps its own clock; the only thing it asks of a device is to play,
// stop and pause a buffer (platform/browser_audio.py). Each such request leaves as a `sound` message; the page plays
// the buffers with Web Audio (audio.js). A sound's samples travel once, with its first play. pygame is not loaded.
// The microphone is the reverse: the page's AudioWorklet posts chunks, and they go into the ring buffer that the
// desktop's microphone code fills, so level(), pitch() and the rest are unchanged. The camera is the same way round:
// the page sends frames, and funground keeps the latest for the sketch's next draw().
//
// Models (S-232, S-233). ml.pose(cam), ml.hand(cam) and ml.person(cam) find a body, a hand or the outline of a person with the
// same ONNX files as the desktop, run by onnxruntime-web. That takes tens of milliseconds, so it runs in a worker of its own (models-worker.js), started here the
// first time the sketch asks, and never inside the sketch's step. funground's Session is given `postModelsRequest`; a picture
// goes out with its buffer transferred, and at most one is in flight for each source and task (funground drops the others). The
// models worker answers with a message, which this worker handles between two steps, so a result never appears in the middle
// of a frame: it is pushed into the Session (`push_models` for points, `push_models_mask` for the person's mask), and the
// sketch's next ml.pose() call reads it. The answer is therefore the newest result the browser has, and may be one frame behind
// (contract ML3). The mask comes as bytes of the mask's own size (256 x 256); funground (Cairo, in C) stretches it over the picture.
// ml.words(mic) (S-234) is the same road for sound: a phrase goes out as float32 bytes (`phrase`), the words come back (`push_models_words`).
// ml.sound(mic) (S-250) sends a window of sound the same way (about twice a second) and gets the model's 521 scores back as float32 bytes
// (`push_models_sound`); the names are chosen in Python.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
// What this runner can do, as words a host can look for in `ready` before it sends work (S-275, D-142 a). A word is added
// by the story that ships it and never removed within a version line; tools/test_runner.py fails unless every word has
// passing checks named after it ("stdin: ...").
const CAPABILITIES = ["run", "stop", "stdin"];

const PYODIDE_PACKAGES = ["micropip", "fonttools"];     // from the Pyodide distribution, for every run
// onnxruntime-web, from jsDelivr at one exact version (the newest that was at least two weeks old when it was pinned: S-232, 2 November 2026).
// The folder holds ort.wasm.mjs (the library, wasm only) and the .wasm file it loads. The runner's `onnxruntimeUrl` option replaces it.
const ONNXRUNTIME = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/";

// Packages only some sketches need, loaded by run() when the file calls one of the functions listed (a call is a
// name followed by "(", so `f.get(x, y)` counts and `get` alone does not). Python imports cannot wait for a
// download, so the decision is made from the source before it runs; a function missing here fails with "No module
// named 'pygame'", which tools/check_on_demand.py catches. Why each group needs its packages:
//   pictures: funground.imaging decodes and changes pictures with pygame-ce; Pillow does its filters faster.
//   sound:    none. Under the runner funground plays through the page (see Sound above), so no sound function needs
//             pygame-ce. `spectrogram` is a picture (it makes one with load_pixels), so it is in the first group.
//   gifs:     funground writes a GIF with Pillow (export/motion.py), importing it when the save runs: `save_gif(...)`, or
//             `save("x.gif")`, where the file name is the signal and not the call (`contains`). An MP4 needs ffmpeg, which a
//             browser does not have: saving one raises funground's own "cannot find ffmpeg" error.
//   models:   `from funground import ml` imports funground-ml, a pure-Python wheel from our runtime folder (`wheels`, by manifest
//             role). Under the runner it needs no numpy, Pillow or onnxruntime: the models run in the models worker. A sketch
//             is recognised by its import (`matches`, regular expressions), because a call such as pose( is too common a word.
const ON_DEMAND = [
  { packages: ["pygame-ce", "pillow"], calls: ["load_image", "load_clip", "get", "load_pixels", "update_pixels", "filter", "apply_filter", "resize", "mask", "remove_color", "remove_background", "outline", "tint", "spectrogram"] },
  { packages: ["pillow"], calls: ["save_gif"], contains: [".gif"] },
  { wheels: ["funground-ml"], matches: [
    /\bfrom\s+funground\s+import\s+(?:\([^)]*\bml\b|[^\n#]*\bml\b)/,       // from funground import camera, ml    (also in brackets)
    /\bfrom\s+funground\.ml\s+import\b/, /\bimport\s+funground\.ml\b/, /\b(?:from|import)\s+funground_ml\b/,
  ] },
];

// What the sources (the sketch, and the .py files beside it) need: Pyodide packages and wheels of our own, each once.
function neededFor(sources) {
  const packages = new Set(), wheels = new Set();
  for (const { packages: pyodide = [], wheels: own = [], calls = [], contains = [], matches = [] } of ON_DEMAND) {
    const wanted = sources.some((source) =>
      (calls.length > 0 && new RegExp(String.raw`\b(${calls.join("|")})\s*\(`).test(source))
      || contains.some((text) => source.includes(text)) || matches.some((pattern) => pattern.test(source)));
    if (wanted) {
      pyodide.forEach((name) => packages.add(name));
      own.forEach((name) => wheels.add(name));
    }
  }
  return { packages: [...packages], wheels: [...wheels] };
}

let py = null;
let fonts = null;                       // {fetchFont, checks} for every Session (fontSupport)
let session = null;
let runtimeFolder = null;               // {url, manifest} of the runtime folder (for wheels installed on demand)
let onnxruntimeUrl = ONNXRUNTIME;
let modelsScripts = null;               // {worker, glue}: where models-worker.js and models-glue.js are
let modelsWorker = null;                // started by the first request for a model
const installed = new Set();            // wheels of our own already installed in this Python
let sketchFile = "sketch.py";
let known = new Map();                  // file name -> "size:modified" for each file of the run's folder already seen or sent

const post = (message, transfer = []) => postMessage(message, transfer);

// Output (S-272). Python writes bytes; each complete line goes to the page as one `output` message, as before. What is left
// without a newline (a prompt, a print(..., end="")) waits here until flushOutput(): before input() reads a line, and when
// a run ends. Pyodide's own line mode cannot do that, because it has no flush (S-271: a last line printed with end="" was lost,
// or, with `reuse`, came out at the front of the next run's output). Python's stdout stays line-buffered with this writer.
function lineWriter(stream) {
  const decoder = new TextDecoder();
  let pending = "";
  return {
    write(bytes) {
      pending += decoder.decode(bytes, { stream: true });
      const lines = pending.split("\n");
      pending = lines.pop();
      for (const text of lines) post({ type: "output", stream, text });
      return bytes.length;
    },
    flush() {
      pending += decoder.decode();
      if (pending) post({ type: "output", stream, text: pending });
      pending = "";
    },
  };
}
const writers = { stdout: lineWriter("stdout"), stderr: lineWriter("stderr") };

// Whatever Python still holds, then whatever is waiting here, goes out now.
function flushOutput() {
  if (!py) return;
  py.runPython("import sys\nsys.stdout.flush()\nsys.stderr.flush()");
  writers.stdout.flush();
  writers.stderr.flush();
}

// Input lines (S-272, D-139 a). With `stdin`, input() and sys.stdin read the run's lines in order; Pyodide adds the newline
// that input() takes off. Before each read the output is flushed, so input()'s prompt reaches the page first. When the lines
// run out, input() raises EOFError with one plain sentence (`use_input_lines` in the glue). Without `stdin`, Pyodide's own
// stdin is put back: input() raises OSError [Errno 29], as before S-272.
function setInputLines(stdin) {
  if (stdin === undefined || stdin === null) {
    py.setStdin();
    py.globals.get("use_input_lines")(null);
    return;
  }
  if (!Array.isArray(stdin) || stdin.some((line) => typeof line !== "string" || line.includes("\n"))) {
    throw new Error("run(): stdin must be a list of strings, one for each line input() reads, with no newline in them");
  }
  let next = 0;
  // input() has flushed Python's own buffer before it reads (measured, S-272), so only what waits here is sent: no call back into Python
  py.setStdin({ stdin: () => { writers.stdout.flush(); writers.stderr.flush(); return next < stdin.length ? stdin[next++] : null; } });
  py.globals.get("use_input_lines")(stdin.length);
}

// Fonts (S-211, D-114 b). funground's bundled fonts (4.2 MB, 2.4 MB of the wheel) are not in the wheel. Nothing is fetched at
// start-up: the Session is given `fetch_font`, and funground calls it the first time it opens a bundled font (typography.py,
// `_ensure_bundled`) and writes the bytes to its fonts folder. So a sketch that draws no text fetches no font, and one that
// draws text fetches only the fonts it uses (the Noto fallbacks only for emoji, symbols or Devanagari). Nothing here lists
// names: the manifest lists every file of funground/fonts, and funground decides what it opens. Design: RESULTS.md, section 5.
//
// The request is a synchronous XMLHttpRequest (allowed in a worker, and Python waits for the answer). The browser decodes a
// compressed answer (GitHub Pages compresses fonts), so this works on every host. funground checks the bytes against the
// manifest's size and SHA-256 (`fonts`) and raises one clear error if they differ.
function fontSupport(manifest, runtime) {
  const fonts = manifest.files.filter((f) => f.role === "font");
  const urls = new Map(fonts.map((f) => [f.font, new URL(f.name, runtime).href]));
  const checks = Object.fromEntries(fonts.map((f) => [f.font, { size: f.size, sha256: f.sha256 }]));
  const fetchFont = (name) => {
    const request = new XMLHttpRequest();
    request.open("GET", urls.get(name), false);
    request.responseType = "arraybuffer";
    request.send();
    if (request.status !== 200) throw new Error(`font ${name}: HTTP ${request.status}`);
    return new Uint8Array(request.response);
  };
  return { fetchFont, checks };
}

// Fonts from the web (S-230, D-119): `f.load_font("https://...")` calls this the first time, then funground keeps the copy in
// fonts/ beside the sketch with fonts/sources.json. Both are new files, so sendNewFiles passes them to the page, My files keeps
// them, and the next run is given them back: it reads no network. The same synchronous request as fetchFont; the font's site
// must allow the request (CORS), and funground turns a failure into one plain sentence (web.py, `_checked_url_fetcher`).
function fetchUrl(address) {
  const request = new XMLHttpRequest();
  request.open("GET", address, false);
  request.responseType = "arraybuffer";
  request.send();
  if (request.status !== 200) throw new Error(`HTTP ${request.status}`);
  return new Uint8Array(request.response);
}

// ---- setup

async function init({ runtimeUrl, pyodideUrl = PYODIDE, onnxruntimeUrl: onnxruntimeOption, modelsScripts: scripts }) {
  const runtime = new URL(runtimeUrl ?? "runtime/", import.meta.url);
  onnxruntimeUrl = onnxruntimeOption ?? ONNXRUNTIME;
  modelsScripts = scripts ?? { worker: new URL("models-worker.js", import.meta.url).href, glue: new URL("models-glue.js", import.meta.url).href };
  const timings = {};
  let t = performance.now();
  const lap = (name) => { timings[name] = Math.round(performance.now() - t); t = performance.now(); console.debug(`runner: ${name} ${timings[name]} ms`); };

  const { loadPyodide } = await import(pyodideUrl + "pyodide.mjs");
  py = await loadPyodide({
    indexURL: pyodideUrl,
    env: { SDL_VIDEODRIVER: "dummy", FUNGROUND_HEADLESS: "1", PYGAME_HIDE_SUPPORT_PROMPT: "1" },
  });
  py.setStdout({ write: writers.stdout.write });
  py.setStderr({ write: writers.stderr.write });
  lap("pyodide");

  const manifest = await (await fetch(new URL("manifest.json", runtime))).json();
  const wheelUrls = (role) => manifest.files.filter((f) => f.role === role).map((f) => new URL(f.name, runtime).href);
  await py.loadPackage(PYODIDE_PACKAGES, { messageCallback: console.log, errorCallback: console.error });   // not the learner's output
  lap("packages");

  // funground's dependencies, each from where it is found: the C-extension wheels (pycairo, uharfbuzz, skia-pathops) from
  // our own runtime folder, fonttools from Pyodide, svgelements and pypdf from PyPI (or from the runtime folder when its
  // manifest lists them as "dependency", for a host that must not reach PyPI), pygame-ce on demand (ON_DEMAND).
  // So funground itself is installed without dependencies: with them, micropip would fetch pygame-ce for every run.
  py.globals.set("c_wheels", wheelUrls("c-extension"));
  py.globals.set("dependency_wheels", wheelUrls("dependency"));
  py.globals.set("funground_wheel", wheelUrls("funground")[0]);
  await py.runPythonAsync(`
import micropip
await micropip.install(list(c_wheels), deps=False)
if dependency_wheels:
    await micropip.install(list(dependency_wheels), deps=False)
else:
    await micropip.install(["svgelements>=1.9", "pypdf>=5"])
await micropip.install(funground_wheel, deps=False)
`);
  fonts = fontSupport(manifest, runtime);
  runtimeFolder = { url: runtime, manifest };
  lap("wheels");

  py.runPython(PYTHON_GLUE, { filename: "<runner>" });                   // its frames are taken out of a learner's traceback (fail)
  const versions = py.globals.get("check_real_libraries")().toJs({ dict_converter: Object.fromEntries });
  lap("check");

  const resources = performance.getEntriesByType("resource").map((e) => ({ name: e.name, bytes: e.encodedBodySize, transfer: e.transferSize }));
  post({ type: "ready", versions, capabilities: CAPABILITIES, timings, resources, fonts: "on open" });
}

// Python side of the worker: a few small functions, kept here so that this file is the whole worker.
const PYTHON_GLUE = `
import importlib
import os
import shutil
import sys
import tempfile
from array import array

sys.dont_write_bytecode = True          # a helper edited and run again is always read from its source
run_folder = None

import builtins
_builtin_input = builtins.input

def use_input_lines(count):
    """S-272: with count lines given (setInputLines), input() raises one plain sentence when they run out instead of
    CPython's "EOF when reading a line"; with None, the built-in input() is put back."""
    if count is None:
        builtins.input = _builtin_input
        return

    def input(prompt=""):
        try:
            return _builtin_input(prompt)
        except EOFError:
            pass
        raise EOFError(f"input() has no more lines to read: this run was given {count}.")

    builtins.input = input

def enter_run_folder():
    """A new folder for this run's files: the working folder, and first on the import path, where "python sketch.py"
    puts the sketch's own folder. The last run's folder is deleted and leaves the path: a reused worker re-runs on every
    pause in typing, and its files (data/ pictures and sounds) live in memory."""
    global run_folder
    if run_folder is not None:
        if run_folder in sys.path:
            sys.path.remove(run_folder)
        os.chdir(tempfile.gettempdir())
        shutil.rmtree(run_folder, ignore_errors=True)
    run_folder = tempfile.mkdtemp()
    os.chdir(run_folder)
    sys.path.insert(0, run_folder)

def run_files():
    """The files in the run's folder as [name, size, modified] (names relative, with "/"), for the page to learn what the
    sketch saved (S-212)."""
    found = []
    for folder, _, names in os.walk(run_folder):
        for name in names:
            path = os.path.join(folder, name)
            info = os.stat(path)
            found.append([os.path.relpath(path, run_folder).replace(os.sep, "/"), info.st_size, info.st_mtime_ns])
    return found

def push_microphone(session, chunk):
    """Hand a Float32Array from the page to the session as an array of floats (to_bytes copies it once)."""
    samples = array("f")
    samples.frombytes(chunk.to_bytes())
    session.push_microphone(samples)

def push_camera(session, pixels, width, height):
    """Hand a camera frame (a Uint8ClampedArray of RGBA) from the page to the session (to_bytes copies it once)."""
    session.push_camera(pixels.to_bytes(), width, height)

def push_models(session, task, key, points, score, width, height):
    """Hand a model result from the page to the session: points is a Float64Array x0, y0, x1, y1, ... or None for nobody."""
    flat = None
    if points is not None:
        flat = array("d")
        flat.frombytes(points.to_bytes())
    session.push_models(task, key, flat, score, width, height)

def push_models_mask(session, task, key, mask, mask_width, mask_height, width, height):
    """Hand the person's mask from the page to the session: mask is a Uint8Array of mask_width * mask_height bytes (to_bytes copies it once)."""
    session.push_models_mask(task, key, mask.to_bytes(), mask_width, mask_height, width, height)

def push_models_words(session, task, key, text, score):
    """Hand the words heard in a phrase from the page to the session."""
    session.push_models_words(task, key, text, score)

def push_models_sound(session, task, key, scores):
    """Hand the sound model's 521 scores (a Float32Array) from the page to the session, as float32 bytes."""
    session.push_models_sound(task, key, scores.to_bytes())

def check_real_libraries():
    """Nothing is stubbed: the three C libraries are compiled extension modules (.so), and funground imports them."""
    versions = {}
    for module in ("cairo._cairo", "uharfbuzz._harfbuzz", "pathops._pathops"):
        loaded = importlib.import_module(module)
        if not loaded.__file__.endswith(".so"):
            raise RuntimeError(f"{module} is not a compiled library: {loaded.__file__}")
        versions[module.split(".")[0]] = loaded.__file__.rsplit("/", 1)[-1]
    import cairo, fontTools, uharfbuzz
    from funground.renderers.cairo2d import CairoRenderer      # the real renderer, which draws with pycairo
    import funground.typography, funground.pathops             # and the real text and path libraries
    versions.update(pycairo=cairo.version, cairo=cairo.cairo_version_string(), fonttools=fontTools.version,
                    uharfbuzz=uharfbuzz.__version__)
    return versions
`;

// ---- a run

async function run({ source, filename, width, height, scale, files, seed, stdin }) {
  sketchFile = filename;
  setInputLines(stdin);                                                    // this run's lines, or none (a reused worker forgets the last run's)
  py.globals.get("enter_run_folder")();                                    // a folder of its own: the file's files, saves and imports
  known = new Map();
  for (const [name, bytes] of Object.entries(files ?? {})) {               // beside the sketch: "data/photo.jpg", "helpers.py"
    const folder = name.split("/").slice(0, -1).join("/");
    if (folder) py.FS.mkdirTree(folder);
    py.FS.writeFile(name, new Uint8Array(bytes));
  }
  sendNewFiles({ record: true });                                          // what is there now is not the sketch's: only its later writes are sent,
                                                                           // a passed-in file too once the sketch rewrites it (a kept take.gif, S-221)
  const sources = [source, ...Object.entries(files ?? {}).filter(([name]) => name.endsWith(".py")).map(([, bytes]) => new TextDecoder().decode(bytes))];
  const needed = neededFor(sources);
  await py.loadPackage(needed.packages, { messageCallback: console.log, errorCallback: console.error });   // none for most sketches
  await installWheels(needed.wheels);
  const { Session } = py.pyimport("funground.web");
  session = Session(width, height, scale, postFrame, postSound, postMicrophoneRequest, postCameraRequest,
                    fonts.fetchFont, py.toPy(fonts.checks), fetchUrl, postModelsRequest);
  if (seed !== undefined) py.pyimport("funground").random_seed(seed);    // the Session's own sketch: a repeatable run (goldens)
  try {
    session.start(source, filename);
  } catch (error) {
    sendNewFiles();
    return fail(error);
  }
  sendNewFiles();                                                          // a script saves while it runs
  if (!session.running) flushOutput();                                     // a script has ended: its last line, even without a newline
  const [canvasWidth, canvasHeight] = session.canvas_size.toJs();
  post({ type: "started", width: canvasWidth, height: canvasHeight, running: session.running });
}

// Wheels of our own that a sketch needs (ON_DEMAND), by their role in the manifest, without their dependencies: funground-ml asks
// for onnxruntime, numpy and Pillow, which a page never uses (the models run in the models worker).
async function installWheels(roles) {
  const wanted = roles.filter((role) => !installed.has(role));
  if (!wanted.length) return;
  const urls = wanted.map((role) => {
    const file = runtimeFolder.manifest.files.find((f) => f.role === role);
    if (!file) throw new Error(`the runtime has no ${role} wheel: build it with tools/build_runtime.py`);
    return new URL(file.name, runtimeFolder.url).href;
  });
  py.globals.set("own_wheels", urls);
  await py.runPythonAsync("import micropip\nawait micropip.install(list(own_wheels), deps=False)");
  wanted.forEach((role) => installed.add(role));
}

function step({ now }) {
  let running = false;
  try {
    running = session.step(now);
  } catch (error) {
    fail(error);
  }
  sendNewFiles();                                                          // f.save() writes at the end of a frame: seen by the step that ends it
  if (!running) flushOutput();                                             // the sketch has ended
  post({ type: "stepped", running });
}

function microphone({ samples }) {
  if (session) py.globals.get("push_microphone")(session, samples);
}

function camera({ pixels, width, height }) {
  if (session) py.globals.get("push_camera")(session, pixels, width, height);
}

function cameraUnavailable({ reason }) {
  session?.camera_unavailable(reason);
}

// ---- models

// The models worker comes up with the first request, so a sketch that asks for no model never pays for it. Its answers are
// ordinary messages, handled here between two steps.
function startModelsWorker() {
  modelsWorker = new Worker(modelsScripts.worker, { type: "module" });
  modelsWorker.onmessage = (e) => {
    const message = e.data;
    try {
      if (message.type === "result" && message.task === "sound") {
        if (session) py.globals.get("push_models_sound")(session, message.task, message.key, message.scores);
      } else if (message.type === "result" && message.task === "words") {
        if (session) py.globals.get("push_models_words")(session, message.task, message.key, message.text, message.score);
      } else if (message.type === "result" && message.mask) {
        if (session) py.globals.get("push_models_mask")(session, message.task, message.key, message.mask, message.maskWidth, message.maskHeight, message.width, message.height);
      } else if (message.type === "result") {
        // `points ?? undefined`: Pyodide turns a JavaScript null into its own null object, and funground wants None
        if (session) py.globals.get("push_models")(session, message.task, message.key, message.points ?? undefined, message.score, message.width, message.height);
      } else if (message.type === "say") {
        post({ type: "output", stream: "stdout", text: message.text });
      } else if (message.type === "unavailable") {
        session?.models_unavailable(message.task, message.reason);
      }
    } catch (error) {
      post({ type: "output", stream: "stderr", text: `A model answer could not be used: ${String(error.message ?? error).split("\n").pop()}` });
    }
  };
  modelsWorker.onerror = (e) => post({ type: "output", stream: "stderr", text: `The models worker failed to load: ${e.message}` });
  modelsWorker.postMessage({
    type: "init", onnxruntimeUrl,
    tableUrl: new URL("models.json", runtimeFolder.url).href, glueUrl: modelsScripts.glue,
  });
}

// on_models(command, fields) from funground. `fields` is a Python dict that dies when the call returns, so what is needed is
// copied out: the picture's bytes into a new buffer, which is transferred.
function postModelsRequest(command, fields) {
  if (command === "close") return modelsWorker?.postMessage({ type: "close" });
  if (!modelsWorker) startModelsWorker();
  const request = fields.toJs({ dict_converter: Object.fromEntries });
  if (request.task === "words" || request.task === "sound") {              // a phrase or a window: float32 bytes, not a picture
    const samples = new Uint8Array(request.samples);                       // a copy that is ours to transfer
    return modelsWorker.postMessage({ type: "phrase", ...request, samples: samples.buffer }, [samples.buffer]);
  }
  const pixels = new Uint8Array(request.pixels);                           // a copy that is ours to transfer
  modelsWorker.postMessage({ type: "frame", ...request, pixels: pixels.buffer }, [pixels.buffer]);
}

function event({ kind, x, y, button, key, keyCode, delta }) {
  session?.push_event(kind, x, y, button ?? undefined, key ?? undefined, keyCode ?? undefined, delta ?? 0);
}

// A learner sees the traceback from their own file down, not the host's frames above it, nor the runner's own (input(): S-272).
// What the run printed comes first, a last line without a newline too.
function fail(error) {
  try { flushOutput(); } catch { /* Python itself is broken: the error says why */ }
  const message = String(error.message ?? error).replace(/^ {2}File "<runner>", line \d+, in .*\n(?: {4}.*\n)*/gm, "");
  const first = message.indexOf(`File "${sketchFile}"`);
  const trimmed = first < 0 ? message : "Traceback (most recent call last):\n  " + message.slice(first);
  post({ type: "error", message: trimmed });
}

// ---- files the sketch wrote (S-212)

const MIME_TYPES = { png: "image/png", pdf: "application/pdf", svg: "image/svg+xml", gif: "image/gif", mp4: "video/mp4",
  jpg: "image/jpeg", jpeg: "image/jpeg", txt: "text/plain", json: "application/json", csv: "text/csv", py: "text/x-python" };

// Compare the run folder's listing (name, size, modified time) with the last one: a file that is new or changed is sent to the
// page. `record` only notes what is there. funground has no hook for a save, and none is needed: a listing costs
// microseconds, and this runs after every step.
function sendNewFiles({ record = false } = {}) {
  const sent = [];
  for (const [name, size, modified] of py.globals.get("run_files")().toJs()) {
    const stamp = `${size}:${modified}`;
    if (known.get(name) === stamp) continue;
    known.set(name, stamp);
    if (record) continue;
    const bytes = py.FS.readFile(name);                                    // a copy, so its buffer can be transferred
    post({ type: "file", name, bytes: bytes.buffer, mime: MIME_TYPES[name.split(".").pop().toLowerCase()] ?? "application/octet-stream" }, [bytes.buffer]);
    sent.push(name);
  }
  return sent;
}

// Keep (S-226, D-113 b): the page's "Keep this" asks the running sketch to run f.keep(note). The Session writes the files at
// once (funground/web.py), so the same listing that finds a saved file finds them, and they are sent before the answer.
function keep({ id, note }) {
  if (!session) return post({ type: "kept", id, ok: false, reason: "The sketch is not running." });
  let base;
  try {
    base = session.keep(note ?? "");
  } catch (error) {
    const last = String(error.message ?? error).split("\n").filter((line) => line.trim()).pop() ?? "";
    const reason = last.replace(/^\w*Error: /, "");              // funground's own plain sentence, without the class name
    return post({ type: "kept", id, ok: false, reason });
  }
  const number = String(base).split("/").pop();                            // base is the run folder's path, ending studio/001
  const files = sendNewFiles().filter((name) => name.startsWith(`studio/${number}.`));
  post({ type: "kept", id, ok: true, base, files });
}

// ---- frames

// on_frame(data, width, height, stride) from funground: `data` is a Python memoryview of BGRA bytes, premultiplied.
function postFrame(data, width, height, stride) {
  const view = data.getBuffer("u8");
  try {
    const pixels = bgraToRgba(view.data, width, height, stride);
    post({ type: "frame", pixels: pixels.buffer, width, height }, [pixels.buffer]);
  } finally {
    view.release();
  }
}

// Little-endian words: BGRA bytes read as 0xAARRGGBB, RGBA bytes as 0xAABBGGRR. Cairo's colours are
// premultiplied by alpha, ImageData's are not, so a pixel that is not opaque is divided by its alpha.
function bgraToRgba(bytes, width, height, stride) {
  const aligned = bytes.byteOffset % 4 === 0 ? bytes : bytes.slice();
  const source = new Uint32Array(aligned.buffer, aligned.byteOffset, (stride * height) >> 2);
  const rowWords = stride >> 2;
  const pixels = new Uint32Array(width * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const v = source[y * rowWords + x];
      const a = v >>> 24;
      pixels[y * width + x] = a === 255 ? (v & 0xff00ff00) | ((v & 0xff) << 16) | ((v >>> 16) & 0xff) : unpremultiply(v, a);
    }
  }
  return pixels;
}

function unpremultiply(v, a) {
  if (a === 0) return 0;
  const unscale = (c) => Math.min(255, Math.round((c * 255) / a));
  return (a << 24 | unscale(v & 0xff) << 16 | unscale((v >>> 8) & 0xff) << 8 | unscale((v >>> 16) & 0xff)) >>> 0;
}

// ---- sound and microphone

// on_sound(command, voice, fields, samples) from funground. The arguments are Python proxies that die when the call
// returns, so everything the page needs is copied out here: `fields` into an object, `samples` (float32, interleaved)
// into a new buffer that is transferred.
function postSound(command, voice, fields, samples) {
  const message = { type: "sound", command, voice, fields: fields.toJs({ dict_converter: Object.fromEntries }), samples: null };
  if (!samples) return post(message);
  const view = samples.getBuffer();
  try {
    message.samples = new Float32Array(view.data);                 // a copy: the view dies when this call returns
    post(message, [message.samples.buffer]);
  } finally {
    view.release();
  }
}

function postMicrophoneRequest(command) {
  post({ type: "microphone", command });
}

// on_camera(command, fields): `fields` is a Python dict that dies when the call returns, so it is copied out.
function postCameraRequest(command, fields) {
  post({ type: "camera", command, fields: fields.toJs({ dict_converter: Object.fromEntries }) });
}

// ---- messages

function stop() {
  try {
    session?.stop();
  } catch (error) {
    fail(error);                                                           // an error in the sketch's finish()
  } finally {
    if (session) sendNewFiles();                                           // what the sketch saved in finish(), before the next run deletes its folder
    session = null;
    flushOutput();                                                         // what finish() printed, before the next run's output
    post({ type: "stopped" });
  }
}

const handlers = { init, run, step, event, microphone, camera, "camera-unavailable": cameraUnavailable, keep, stop };

self.onmessage = async (e) => {
  try {
    await handlers[e.data.type](e.data);
  } catch (error) {
    fail(error);
  }
};
