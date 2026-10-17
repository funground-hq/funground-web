// The funground browser runner, worker side (story S-153, docs/design/Web_Runner_Note.md in funground).
//
// A module worker that runs one learner's file with Pyodide and funground's host API (funground.web.Session).
// The page drives it; every message has a `type`.
//
//   page -> worker
//     init   {runtimeUrl?, pyodideUrl?}     load Pyodide and install everything; answers `ready`
//     run    {source, filename, width, height, scale, files, seed?}   start the file; answers `started`. `files` maps a path
//                                           to bytes: data beside the sketch, and other .py files it may import
//     step   {now}                          one display frame, `now` in seconds; answers `stepped`
//     event  {kind, x, y, button, key, keyCode, delta}   one input event (funground's InputEvent vocabulary)
//     microphone {samples}                  a Float32Array of mono samples (-1 to 1, 44 100 Hz) the microphone heard
//     camera {pixels, width, height}        one camera frame: RGBA bytes (a Uint8ClampedArray whose buffer is transferred)
//     camera-unavailable {reason}           the page could not open the camera; funground prints one line with the reason
//     stop                                  end the run (the sketch's finish() runs), so the worker can run another file;
//                                           answers `stopped`. Used by runner.js's `reuse` option (D-083)
//
//   worker -> page
//     ready    {versions, timings, resources, fonts}   everything is installed and checked; fonts is "lazy" or "eager" (S-211)
//     started  {width, height, running}         the file ran; the canvas size it asked for (logical pixels)
//     frame    {pixels, width, height}          RGBA bytes (physical pixels); the ArrayBuffer is transferred
//     stepped  {running}                        the step is done; false when the sketch has ended
//     output   {stream, text}                   one line of print() ("stdout") or of an error ("stderr")
//     error    {message}                        the file or the setup failed (message is a Python traceback)
//     sound    {command, voice, fields, samples} a sound command for Web Audio (funground/platform/browser_audio.py has the
//                                               list); `samples` is a Float32Array whose buffer is transferred, for "load" only
//     microphone {command}                      "start", "stop" or "close": the sketch wants the microphone listened to or let go
//     camera   {command, fields}                "start" {width, height}, "stop" or "close": the sketch wants camera frames at that
//                                               size, or lets the camera go (camera.js)
//     stopped  {}                               the run asked to stop has ended; the worker is ready for another `run`
//     file     {name, bytes, type}              a file the sketch wrote in its folder (S-212): new or changed since the run began,
//                                               not one the page passed in `files`; `bytes` is an ArrayBuffer (transferred), `type`
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

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const PYODIDE_PACKAGES = ["micropip", "fonttools"];     // from the Pyodide distribution, for every run

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
const ON_DEMAND = [
  { packages: ["pygame-ce", "pillow"], calls: ["load_image", "load_clip", "get", "load_pixels", "update_pixels", "filter", "apply_filter", "resize", "mask", "tint", "spectrogram"] },
  { packages: ["pillow"], calls: ["save_gif"], contains: [".gif"] },
];

function packagesFor(source) {
  const wanted = new Set();
  for (const { packages, calls, contains = [] } of ON_DEMAND) {
    if (new RegExp(String.raw`\b(${calls.join("|")})\s*\(`).test(source) || contains.some((text) => source.includes(text))) packages.forEach((name) => wanted.add(name));
  }
  return [...wanted];
}

let py = null;
let session = null;
let sketchFile = "sketch.py";
let known = new Map();                  // file name -> "size:modified" for each file of the run's folder already seen or sent
let passedIn = new Set();               // the names of the files the page passed in `files`: never reported

const post = (message, transfer = []) => postMessage(message, transfer);
const output = (stream) => (text) => post({ type: "output", stream, text });

// Fonts (S-211). funground's bundled fonts (4.2 MB, 2.4 MB of the wheel) are not in the wheel. Each is a lazy file in
// the fonts folder funground reads (typography.FONT_DIR): the browser fetches it, with a synchronous request (allowed in a
// worker), the first time Python opens it, so a sketch that draws no text fetches no font and one that draws text
// fetches only the fonts it uses (the Noto fallbacks only for emoji, symbols or Devanagari). Nothing here lists names:
// the manifest lists every file of funground/fonts, and funground decides what it opens. Design: RESULTS.md, section 5.
//
// A lazy file trusts the host: its length comes from a HEAD request and must be the bytes the GET sends. A host that compresses
// the font, or sends another length, would give Python a corrupt font. So one font is probed first: if the host answers HEAD
// with the manifest's size and no Content-Encoding, the fonts are lazy; otherwise they are all fetched now, checked against
// the manifest's size and SHA-256, and written to the same paths (slower, always correct). Returns "lazy" or "eager".
async function installFonts(manifest, runtime) {
  const folder = py.runPython("import importlib.util; importlib.util.find_spec('funground').submodule_search_locations[0] + '/fonts'");
  const fonts = manifest.files.filter((f) => f.role === "font");
  const urlOf = (font) => new URL(font.name, runtime).href;
  if (fonts.length === 0) return "lazy";
  let lazy = false;
  try {
    const head = await fetch(urlOf(fonts[0]), { method: "HEAD" });
    lazy = head.ok && Number(head.headers.get("Content-Length")) === fonts[0].size && !head.headers.get("Content-Encoding");
  } catch { /* unreachable: the eager path below reports the failure */ }
  if (lazy) {
    for (const font of fonts) py.FS.createLazyFile(folder, font.font, urlOf(font), true, false);
    return "lazy";
  }
  await Promise.all(fonts.map(async (font) => {
    const response = await fetch(urlOf(font));
    if (!response.ok) throw new Error(`font ${font.font}: HTTP ${response.status}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length !== font.size) throw new Error(`font ${font.font}: ${bytes.length} bytes, the manifest says ${font.size}`);
    if (crypto.subtle) {
      const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
      if (digest !== font.sha256) throw new Error(`font ${font.font}: SHA-256 differs from the manifest`);
    }
    py.FS.writeFile(`${folder}/${font.font}`, bytes);
  }));
  return "eager";
}

// ---- setup

async function init({ runtimeUrl, pyodideUrl = PYODIDE }) {
  const runtime = new URL(runtimeUrl ?? "runtime/", import.meta.url);
  const timings = {};
  let t = performance.now();
  const lap = (name) => { timings[name] = Math.round(performance.now() - t); t = performance.now(); console.debug(`runner: ${name} ${timings[name]} ms`); };

  const { loadPyodide } = await import(pyodideUrl + "pyodide.mjs");
  py = await loadPyodide({
    indexURL: pyodideUrl,
    stdout: output("stdout"),
    stderr: output("stderr"),
    env: { SDL_VIDEODRIVER: "dummy", FUNGROUND_HEADLESS: "1", PYGAME_HIDE_SUPPORT_PROMPT: "1" },
  });
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
  const fonts = await installFonts(manifest, runtime);
  console.debug(`runner: fonts ${fonts}`);
  lap("wheels");

  py.runPython(PYTHON_GLUE);
  const versions = py.globals.get("check_real_libraries")().toJs({ dict_converter: Object.fromEntries });
  lap("check");

  const resources = performance.getEntriesByType("resource").map((e) => ({ name: e.name, bytes: e.encodedBodySize, transfer: e.transferSize }));
  post({ type: "ready", versions, timings, resources, fonts });
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

async function run({ source, filename, width, height, scale, files, seed }) {
  py.globals.get("enter_run_folder")();                                    // a folder of its own: the file's files, saves and imports
  known = new Map();
  for (const [name, bytes] of Object.entries(files ?? {})) {               // beside the sketch: "data/photo.jpg", "helpers.py"
    const folder = name.split("/").slice(0, -1).join("/");
    if (folder) py.FS.mkdirTree(folder);
    py.FS.writeFile(name, new Uint8Array(bytes));
  }
  passedIn = new Set(Object.keys(files ?? {}));
  sendNewFiles({ record: true });                                          // what is there now is not the sketch's: only its later writes are sent
  await py.loadPackage(packagesFor(source), { messageCallback: console.log, errorCallback: console.error });   // none for most sketches
  const { Session } = py.pyimport("funground.web");
  sketchFile = filename;
  session = Session(width, height, scale, postFrame, postSound, postMicrophoneRequest, postCameraRequest);
  if (seed !== undefined) py.pyimport("funground").random_seed(seed);    // the Session's own sketch: a repeatable run (goldens)
  try {
    session.start(source, filename);
  } catch (error) {
    sendNewFiles();
    return fail(error);
  }
  sendNewFiles();                                                          // a script saves while it runs
  const [canvasWidth, canvasHeight] = session.canvas_size.toJs();
  post({ type: "started", width: canvasWidth, height: canvasHeight, running: session.running });
}

function step({ now }) {
  let running = false;
  try {
    running = session.step(now);
  } catch (error) {
    fail(error);
  }
  sendNewFiles();                                                          // f.save() writes at the end of a frame: seen by the step that ends it
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

function event({ kind, x, y, button, key, keyCode, delta }) {
  session?.push_event(kind, x, y, button ?? undefined, key ?? undefined, keyCode ?? undefined, delta ?? 0);
}

// A learner sees the traceback from their own file down, not the host's frames above it.
function fail(error) {
  const message = String(error.message ?? error);
  const first = message.indexOf(`File "${sketchFile}"`);
  const trimmed = first < 0 ? message : "Traceback (most recent call last):\n  " + message.slice(first);
  post({ type: "error", message: trimmed });
}

// ---- files the sketch wrote (S-212)

const MIME_TYPES = { png: "image/png", pdf: "application/pdf", svg: "image/svg+xml", gif: "image/gif", mp4: "video/mp4",
  jpg: "image/jpeg", jpeg: "image/jpeg", txt: "text/plain", json: "application/json", csv: "text/csv" };

// Compare the run folder's listing (name, size, modified time) with the last one: a file that is new or changed is sent to the
// page. `record` only notes what is there. funground has no hook for a save, and none is needed: a listing costs
// microseconds, and this runs after every step.
function sendNewFiles({ record = false } = {}) {
  for (const [name, size, modified] of py.globals.get("run_files")().toJs()) {
    const stamp = `${size}:${modified}`;
    if (known.get(name) === stamp) continue;
    known.set(name, stamp);
    if (record || passedIn.has(name)) continue;
    const bytes = py.FS.readFile(name);                                    // a copy, so its buffer can be transferred
    post({ type: "file", name, bytes: bytes.buffer, mime: MIME_TYPES[name.split(".").pop().toLowerCase()] ?? "application/octet-stream" }, [bytes.buffer]);
  }
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
    post({ type: "stopped" });
  }
}

const handlers = { init, run, step, event, microphone, camera, "camera-unavailable": cameraUnavailable, stop };

self.onmessage = async (e) => {
  try {
    await handlers[e.data.type](e.data);
  } catch (error) {
    fail(error);
  }
};
