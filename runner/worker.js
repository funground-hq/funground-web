// The funground browser runner, worker side (story S-153, docs/design/Web_Runner_Note.md in funground).
//
// A module worker that runs one learner's file with Pyodide and funground's host API (funground.web.Session).
// The page drives it; every message has a `type`.
//
//   page -> worker
//     init   {runtimeUrl?}                  load Pyodide and install everything; answers `ready`
//     run    {source, filename, width, height, scale, files}   start the file; answers `started`
//     step   {now}                          one display frame, `now` in seconds; answers `stepped`
//     event  {kind, x, y, button, key, keyCode, delta}   one input event (funground's InputEvent vocabulary)
//
//   worker -> page
//     ready    {versions, timings, resources}   everything is installed and checked
//     started  {width, height, running}         the file ran; the canvas size it asked for (logical pixels)
//     frame    {pixels, width, height}          RGBA bytes (physical pixels); the ArrayBuffer is transferred
//     stepped  {running}                        the step is done; false when the sketch has ended
//     output   {stream, text}                   one line of print() ("stdout") or of an error ("stderr")
//     error    {message}                        the file or the setup failed (message is a Python traceback)
//
// There is no `stop` message: the page stops a run by terminating the worker, the only way to end a sketch that
// never returns (`while True:`). A sketch that ends by itself finishes normally and says `stepped {running: false}`.
//
// Frames. funground hands over each finished frame as the Cairo surface's bytes (BGRA, premultiplied) in a view
// valid only during the call. We copy it once, into a fresh buffer, converting to the RGBA, straight-alpha bytes
// that ImageData wants, and transfer that buffer. Converting here, not on the page, keeps the page's thread free,
// and the copy has to happen anyway because the view dies when the call returns.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const PYODIDE_PACKAGES = ["micropip", "fonttools", "pygame-ce", "pillow"];     // from the Pyodide distribution
// pygame-ce decodes pictures (funground.imaging) and pillow filters and GIFs. svgelements and pypdf are pure
// Python: micropip fetches them from PyPI as dependencies of the funground wheel.

let py = null;
let session = null;
let sketchFile = "sketch.py";

const post = (message, transfer = []) => postMessage(message, transfer);
const output = (stream) => (text) => post({ type: "output", stream, text });

// ---- setup

async function init({ runtimeUrl }) {
  const runtime = new URL(runtimeUrl ?? "runtime/", import.meta.url);
  const timings = {};
  let t = performance.now();
  const lap = (name) => { timings[name] = Math.round(performance.now() - t); t = performance.now(); console.debug(`runner: ${name} ${timings[name]} ms`); };

  const { loadPyodide } = await import(PYODIDE + "pyodide.mjs");
  py = await loadPyodide({
    indexURL: PYODIDE,
    stdout: output("stdout"),
    stderr: output("stderr"),
    env: { SDL_VIDEODRIVER: "dummy", SDL_AUDIODRIVER: "dummy", FUNGROUND_HEADLESS: "1" },
  });
  lap("pyodide");

  const manifest = await (await fetch(new URL("manifest.json", runtime))).json();
  const wheelUrls = (role) => manifest.files.filter((f) => f.role === role).map((f) => new URL(f.name, runtime).href);
  await py.loadPackage(PYODIDE_PACKAGES, { messageCallback: console.log, errorCallback: console.error });   // not the learner's output
  lap("packages");

  // The C-extension wheels first, then funground, whose dependencies (pycairo, uharfbuzz and skia-pathops among them) are then met.
  py.globals.set("c_wheels", wheelUrls("c-extension"));
  py.globals.set("funground_wheel", wheelUrls("funground")[0]);
  await py.runPythonAsync(`
import micropip
await micropip.install(list(c_wheels), deps=False)
await micropip.install(funground_wheel)
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

async function run({ source, filename, width, height, scale, files }) {
  py.runPython("import os, tempfile; os.chdir(tempfile.mkdtemp())");       // a folder of its own for what the file saves
  for (const [name, bytes] of Object.entries(files ?? {})) {               // data the file reads, beside it ("data/photo.jpg")
    const folder = name.split("/").slice(0, -1).join("/");
    if (folder) py.FS.mkdirTree(folder);
    py.FS.writeFile(name, new Uint8Array(bytes));
  }
  const { Session } = py.pyimport("funground.web");
  sketchFile = filename;
  session = Session(width, height, scale, postFrame);
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

// ---- messages

const handlers = { init, run, step, event };

self.onmessage = async (e) => {
  try {
    await handlers[e.data.type](e.data);
  } catch (error) {
    fail(error);
  }
};
