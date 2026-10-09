// The funground browser runner, worker side (story S-153, docs/design/Web_Runner_Note.md in funground).
//
// A module worker that runs one learner's file with Pyodide and funground's host API (funground.web.Session).
// The page drives it; every message has a `type`.
//
//   page -> worker
//     init   {runtimeUrl?, pyodideUrl?}     load Pyodide and install everything; answers `ready`
//     run    {source, filename, width, height, scale, files, seed?}   start the file; answers `started`
//     step   {now}                          one display frame, `now` in seconds; answers `stepped`
//     event  {kind, x, y, button, key, keyCode, delta}   one input event (funground's InputEvent vocabulary)
//     microphone {samples}                  a Float32Array of mono samples (-1 to 1, 44 100 Hz) the microphone heard
//     stop                                  end the run (the sketch's finish() runs), so the worker can run another file;
//                                           answers `stopped`. Used by runner.js's `reuse` option (spike S-156)
//
//   worker -> page
//     ready    {versions, timings, resources}   everything is installed and checked
//     started  {width, height, running}         the file ran; the canvas size it asked for (logical pixels)
//     frame    {pixels, width, height}          RGBA bytes (physical pixels); the ArrayBuffer is transferred
//     stepped  {running}                        the step is done; false when the sketch has ended
//     output   {stream, text}                   one line of print() ("stdout") or of an error ("stderr")
//     error    {message}                        the file or the setup failed (message is a Python traceback)
//     sound    {command, voice, fields, samples} a sound command for Web Audio (funground/platform/browser_audio.py has the
//                                               list); `samples` is a Float32Array whose buffer is transferred, for "load" only
//     microphone {command}                      "start", "stop" or "close": the sketch wants the microphone listened to or let go
//     stopped  {}                               the run asked to stop has ended; the worker is ready for another `run`
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
// desktop's microphone code fills, so level(), pitch() and the rest are unchanged.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const PYODIDE_PACKAGES = ["micropip", "fonttools"];     // from the Pyodide distribution, for every run

// Packages only some sketches need, loaded by run() when the file calls one of the functions listed (a call is a
// name followed by "(", so `f.get(x, y)` counts and `get` alone does not). Python imports cannot wait for a
// download, so the decision is made from the source before it runs; a function missing here fails with "No module
// named 'pygame'", which tools/check_on_demand.py catches. Why each group needs its packages:
//   pictures: funground.imaging decodes and changes pictures with pygame-ce; Pillow does its filters faster.
//   sound:    none. Under the runner funground plays through the page (see Sound above), so no sound function needs
//             pygame-ce. `spectrogram` is a picture (it makes one with load_pixels), so it is in the first group.
const ON_DEMAND = [
  { packages: ["pygame-ce", "pillow"], calls: ["load_image", "get", "load_pixels", "update_pixels", "filter", "resize", "mask", "tint", "spectrogram"] },
];

function packagesFor(source) {
  const wanted = new Set();
  for (const { packages, calls } of ON_DEMAND) {
    if (new RegExp(String.raw`\b(${calls.join("|")})\s*\(`).test(source)) packages.forEach((name) => wanted.add(name));
  }
  return [...wanted];
}

let py = null;
let session = null;
let sketchFile = "sketch.py";

const post = (message, transfer = []) => postMessage(message, transfer);
const output = (stream) => (text) => post({ type: "output", stream, text });

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
  lap("wheels");

  py.runPython(PYTHON_GLUE);
  const versions = py.globals.get("check_real_libraries")().toJs({ dict_converter: Object.fromEntries });
  lap("check");

  const resources = performance.getEntriesByType("resource").map((e) => ({ name: e.name, bytes: e.encodedBodySize, transfer: e.transferSize }));
  post({ type: "ready", versions, timings, resources });
}

// Python side of the worker: two small functions, kept here so that this file is the whole worker.
const PYTHON_GLUE = `
import importlib
from array import array

def push_microphone(session, chunk):
    """Hand a Float32Array from the page to the session as an array of floats (to_bytes copies it once)."""
    samples = array("f")
    samples.frombytes(chunk.to_bytes())
    session.push_microphone(samples)

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
  py.runPython("import os, tempfile; os.chdir(tempfile.mkdtemp())");       // a folder of its own for what the file saves
  for (const [name, bytes] of Object.entries(files ?? {})) {               // data the file reads, beside it ("data/photo.jpg")
    const folder = name.split("/").slice(0, -1).join("/");
    if (folder) py.FS.mkdirTree(folder);
    py.FS.writeFile(name, new Uint8Array(bytes));
  }
  await py.loadPackage(packagesFor(source), { messageCallback: console.log, errorCallback: console.error });   // none for most sketches
  if (seed !== undefined) py.pyimport("funground").random_seed(seed);    // a repeatable run (tests compare with goldens)
  const { Session } = py.pyimport("funground.web");
  sketchFile = filename;
  session = Session(width, height, scale, postFrame, postSound, postMicrophoneRequest);
  try {
    session.start(source, filename);
  } catch (error) {
    return fail(error);
  }
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
  post({ type: "stepped", running });
}

function microphone({ samples }) {
  if (session) py.globals.get("push_microphone")(session, samples);
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

// ---- messages

function stop() {
  try {
    session?.stop();
  } catch (error) {
    fail(error);                                                           // an error in the sketch's finish()
  } finally {
    session = null;
    post({ type: "stopped" });
  }
}

const handlers = { init, run, step, event, microphone, stop };

self.onmessage = async (e) => {
  try {
    await handlers[e.data.type](e.data);
  } catch (error) {
    fail(error);
  }
};
