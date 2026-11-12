// The funground browser runner, page side (story S-153). How a page uses it: runner/README.md.
//
//   import { createRunner } from "./runner.js";
//   const runner = await createRunner({ canvas, output });      // loads Python; resolves when it is ready
//   await runner.run(source, { filename: "sketch.py" });        // starts a sketch; frames appear on the canvas
//   runner.stop();                                              // ends it, however busy it is
//   const { tests, output, error } = await runner.check(source, { tests: [{ name, code }] });   // a learner's code and its tests (S-273)
//
// The learner's code runs in a module Web Worker (worker.js), so the page stays responsive. A worker runs one
// file only. When a run ends, or Stop terminates it, a fresh worker starts loading at once, so the next Run
// finds Python ready (or nearly).

import { createAudio } from "./audio.js";
import { createCamera } from "./camera.js";

const KEY_NAMES = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down", Enter: "enter", Escape: "escape" };
const MOUSE_BUTTONS = ["left", "center", "right"];                 // MouseEvent.button 0, 1, 2
const WHEEL_NOTCH = 100;                                          // deltaY pixels in one notch of a wheel
// With `reuse`: how long a run may take to stop before its worker is ended and a new Python started. A sketch answers
// between two frames, so a busy frame or a slow setup() needs more than a moment; a new Python costs seconds.
const STOP_WAIT_MS = 1000;
const KEEP_WAIT_MS = 10000;                                       // how long keep() waits for the sketch's answer (S-226)

/**
 * @param {object} options
 * @param {HTMLCanvasElement} options.canvas  where frames are drawn; it also receives the mouse and keyboard
 * @param {HTMLElement | ((text: string, stream: "stdout" | "stderr") => void)} [options.output]  where print() and errors go
 * @param {string | URL} [options.baseUrl]  the folder holding worker.js and runtime/ (default: next to this file)
 * @param {boolean} [options.prewarm]  start the next run's worker as soon as a run ends (default true); false starts it at the next run(), which then waits for Python to load
 * @param {(count: number) => void} [options.onFrame]  after each frame is drawn (1 is the first of the run)
 * @param {(reason: "ended" | "error" | "stopped") => void} [options.onFinish]  when a run ends, however it ends
 * @param {() => void} [options.onRestart]  with `reuse`: a run did not stop within STOP_WAIT_MS, so its worker was ended and a
 *   new one (a new Python) is loading; the next run waits for it, which takes seconds. A page can say so
 * @param {(message: object) => void} [options.onSound]  every sound command the sketch makes ({command, voice, fields, samples}), before it is played; for tests and tools
 * @param {(file: {name: string, bytes: Uint8Array, type: string}) => void} [options.onFile]  a file the sketch wrote in its folder
 *   (f.save, save_gif, a plain open() ...): new or changed since the run began (a file passed in `files` only when the sketch rewrites it). Called after the frame (or
 *   script, or stop) that wrote it, and again if the sketch writes it again. `name` is relative to the sketch's folder, `bytes` is
 *   the whole file and `type` its MIME type ("image/png", "application/pdf", "image/svg+xml", "image/gif", "video/mp4")
 * @param {string | URL} [options.pyodideUrl]  the folder Pyodide loads from (default: jsDelivr, in worker.js)
 * @param {string | URL} [options.onnxruntimeUrl]  the folder onnxruntime-web loads from, for ml.pose() and ml.hand() (default: jsDelivr at one
 *   exact version, in worker.js). It holds ort.wasm.mjs and the .wasm file beside it
 * @param {string | URL} [options.runtimeUrl]  the folder holding manifest.json and the wheels (default: runtime/ under baseUrl)
 * @param {Array<string | {name: string, url: string, sha256: string, imports?: string[]}>} [options.packages]  what learners' code may load
 *   besides Python itself (S-274, S-276). Left out is the full start (funground and its libraries, about 10 MB cold) and nothing else may be
 *   loaded. `"funground"` is funground (implicit: always installed at start, never on import; without it `run()` runs a plain Python script,
 *   about 6 MB cold). Any other string is a Pyodide package by its name in Pyodide's lock file, such as `"numpy"` or `"scikit-learn"`;
 *   what it depends on comes with it. An object is a host wheel: `{name, url, sha256, imports?}` (a wheel of `py3-none-any`, or of this
 *   Pyodide's own platform; `url` is relative to `baseUrl`; `imports` are the names a learner imports, default `[name with "-" as "_"]`).
 *   The runner checks the wheel's SHA-256 and installs it without pip or PyPI. An import of anything else fails with a sentence naming
 *   what the page does offer. See "The host's packages" in README.md
 * @param {"on import" | "at start"} [options.install]  when the listed Pyodide packages and wheels are loaded (default "on import"): just
 *   before a `run()` or `check()` whose code imports them, or all of them before the runner is ready. Heavy packages (scikit-learn) belong at start
 * @param {boolean} [options.spare]  while a sketch runs, keep the next run's worker loaded too, so that a re-run (an editor
 *   re-running on every edit) starts at once instead of waiting for Python to load; costs a second Python's memory (default false)
 * @param {boolean} [options.reuse]  run the next sketch in the same worker when the last one has ended or stops when asked
 *   (funground's Session starts each sketch afresh); a sketch that does not stop within STOP_WAIT_MS (`while True:`) still
 *   has its worker ended (D-083); default false (one worker per run, as before)
 * @param {string} [options.microphoneRefusal]  for a host that does not allow the microphone (VS Code's panel): the line a sketch
 *   that starts it gets in its output instead; the browser is not asked and the sketch hears nothing (default: none, the
 *   microphone is asked for as usual)
 * @param {string} [options.cameraRefusal]  for a host that does not allow the camera (VS Code's panel): why, in a few words; a
 *   sketch that starts the camera gets "The camera is not available: {cameraRefusal}." in its output and the browser is not asked
 * @returns {Promise<{info: object, run: Function, check: Function, stop: Function, keep: Function, running: boolean}>}
 */
export async function createRunner({ canvas, output, baseUrl = new URL("./", import.meta.url), prewarm = true, onFrame, onFinish, onRestart, onSound, onFile, pyodideUrl, onnxruntimeUrl: onnxruntimeOption, runtimeUrl: runtimeOption, packages, install, spare = false, reuse = false, microphoneRefusal = null, cameraRefusal = null }) {
  // S-274, S-276, D-144 e: what `packages` and `install` may hold. Checked first, before anything is made.
  const hostPackages = checkedPackages(packages, install, baseUrl);
  const write = outputWriter(output);
  const context = canvas.getContext("2d");
  const audio = createAudio({
    write,
    workletUrl: new URL("microphone-worklet.js", baseUrl),
    onChunk: (samples) => { if (run) worker.worker.postMessage({ type: "microphone", samples }, [samples.buffer]); },
    microphoneRefusal,
  });
  const camera = createCamera({
    onFrame: (pixels, width, height) => { if (run) worker.worker.postMessage({ type: "camera", pixels, width, height }, [pixels.buffer]); },
    onUnavailable: (reason) => { if (run) worker.worker.postMessage({ type: "camera-unavailable", reason }); },
    cameraRefusal,
  });
  // Browsers keep a page silent until the visitor has clicked or pressed a key on it: the first of either, and Run, unlock sound.
  for (const kind of ["pointerdown", "keydown"]) window.addEventListener(kind, audio.unlock, { capture: true, passive: true });
  const workerUrl = new URL("worker.js", baseUrl);
  const workerScript = await workerScriptUrl(workerUrl);
  const runtimeUrl = new URL(runtimeOption ?? "runtime/", baseUrl).href;
  const pyodide = pyodideUrl === undefined ? undefined : new URL(pyodideUrl, baseUrl).href;
  const onnxruntime = onnxruntimeOption === undefined ? undefined : new URL(onnxruntimeOption, baseUrl).href.replace(/\/?$/, "/");
  // The models worker and its glue are started by worker.js, on the first request for a model; they come from the same place as worker.js.
  const modelsScripts = { worker: String(await workerScriptUrl(new URL("models-worker.js", baseUrl))), glue: String(await workerScriptUrl(new URL("models-glue.js", baseUrl))) };
  let worker = startWorker();            // the worker for the next run, or the run in progress
  let next = null;                       // with `spare`: the worker for the run after the one in progress
  let run = null;                        // the run in progress, or null
  let logical = { width: 0, height: 0 }; // the sketch's canvas in logical pixels
  let scale = 1;                         // backing pixels per logical pixel (devicePixelRatio when the run began)
  let frames = 0;
  let keeps = 0;                         // numbers the keep requests (S-226)
  const keeping = new Map();             // request number -> what to do with the worker's answer
  if (canvas.tabIndex < 0) canvas.tabIndex = 0;                    // a canvas takes the keyboard only if it can be focused

  let info;
  try {
    info = await worker.ready;           // a failure to load is thrown to the caller
  } catch (error) {
    worker.worker.terminate();           // with its Python (S-276: a name Pyodide does not have, a wheel refused at start)
    throw error;
  }

  // ---- workers

  function startWorker() {
    const created = new Worker(workerScript, { type: "module" });
    const slot = { worker: created, ready: null, loaded: false };
    slot.ready = new Promise((resolve, reject) => {
      created.onerror = (e) => reject(new Error(`the runner's worker failed to load: ${e.message}`));
      created.onmessage = (e) => {
        const message = e.data;
        if (message.type === "ready") { slot.loaded = true; console.debug("runner: worker ready"); resolve(message); }
        else if (message.type === "stopped") slot.stopped?.();
        else if (message.type === "error" && !slot.loaded) reject(new Error(message.message));
        else handle(message);
      };
    });
    slot.ready.catch(() => {});                                    // reported where it is awaited
    created.postMessage({ type: "init", runtimeUrl, pyodideUrl: pyodide, onnxruntimeUrl: onnxruntime, modelsScripts, packages: hostPackages, install });
    console.debug("runner: worker started");
    return slot;
  }

  // The worker is done with: end it, and take the spare or start the next unless the page asked to wait. Messages still in
  // flight from it are dropped.
  function replaceWorker() {
    worker.worker.terminate();
    worker = next ?? (prewarm ? startWorker() : null);
    next = null;
  }

  // The run is over: nothing more is drawn or played. Its worker is ended (and replaced), or with `reuse` kept for the next
  // run: a sketch that ended or failed has already been stopped by funground's Session.
  function finish(reason, { keepWorker = reuse } = {}) {
    if (!run) return;
    cancelAnimationFrame(run.animation);
    run.resolve({ ok: false });                                    // no effect when the run had started
    audio.reset();                                                 // nothing keeps playing or listening
    camera.reset();                                                // or looking
    run = null;
    if (!keepWorker) replaceWorker();
    onFinish?.(reason);
  }

  // Stop the run in progress. Without `reuse` its worker is ended at once. With `reuse` the worker is asked to stop the
  // sketch (its finish() runs); it is ended only if it does not answer in time, being busy in the sketch's own code.
  async function stopRun() {
    if (!run) return;
    if (!reuse) return finish("stopped");
    const slot = worker;
    const answered = new Promise((resolve) => { slot.stopped = () => resolve(true); });
    finish("stopped", { keepWorker: true });
    slot.worker.postMessage({ type: "stop" });
    const stopped = await Promise.race([answered, new Promise((resolve) => setTimeout(resolve, STOP_WAIT_MS, false))]);
    slot.stopped = null;
    if (!stopped && worker === slot) {
      replaceWorker();
      onRestart?.();
    }
  }

  // ---- messages from the worker

  function handle(message) {
    switch (message.type) {
      case "output": write(message.text, message.stream); break;
      case "error": write(message.message, "stderr"); finish("error"); break;
      case "frame": if (run) drawFrame(message); break;           // a stopped run's last frames are not drawn
      case "sound": if (run) { onSound?.(message); audio.command(message); } break;
      case "kept": keeping.get(message.id)?.(message); break;
      case "file": onFile?.({ name: message.name, bytes: new Uint8Array(message.bytes), type: message.mime }); break;   // even after the run ended: its last frame may have saved
      case "microphone": audio.microphoneCommand(message); break;
      case "camera": if (run) camera.command(message); break;
      case "started": started(message); break;
      case "checked": if (run?.check) { run.resolve({ tests: message.tests, output: message.output, error: message.error }); finish("ended"); } break;     // a stopped check's answer is dropped
      case "stepped": if (run) { run.waiting = false; if (!message.running) finish("ended"); } break;
    }
  }

  // The canvas's backing size is always the size of the frames funground sends: the page never works it out
  // from logical size x scale, because its rounding can differ from funground's by a pixel, and setting a
  // canvas's width or height clears it (even to the same value). So it is set here, and only on a real change.
  function drawFrame({ pixels, width, height }) {
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    context.putImageData(new ImageData(new Uint8ClampedArray(pixels), width, height), 0, 0);
    onFrame?.(++frames);
  }

  // `started` gives the sketch's logical size, after setup() (or after a script has drawn): it sets the size the
  // canvas is shown at and maps the mouse; the backing pixels come with the frames.
  function started({ width, height, running }) {
    if (!run) return;
    logical = { width, height };
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    run.resolve({ ok: true, width, height });
    if (spare && !next) next = startWorker();                     // after setup(), so the two do not compete for the first frame
    if (running) run.animation = requestAnimationFrame(tick);
    else finish("ended");
  }

  // ---- running

  async function runSketch(source, { filename = "sketch.py", files = {}, width, height, seed, stdin } = {}) {
    audio.unlock();                                                // Run is a click or a key: the moment the browser allows sound
    if (run) await stopRun();
    worker ??= startWorker();
    await worker.ready;
    scale = window.devicePixelRatio || 1;
    logical = { width: width ?? (canvas.clientWidth || 640), height: height ?? (canvas.clientHeight || 400) };
    frames = 0;
    return new Promise((resolve) => {
      run = { resolve, waiting: false, animation: 0 };
      worker.worker.postMessage({ type: "run", source, filename, width: logical.width, height: logical.height, scale, files, seed, stdin });
    });
  }

  // Check (S-273, D-141 a): run `source` as plain Python, then each test, in the same worker and under the same `reuse` rules as run().
  // `tests` is [{name, code}]. Resolves {tests: [{name, passed, message}], output, error}: `error` is the traceback when the code
  // raised (then `tests` is []). The check counts as the run in progress, so stop() ends it, which is the only way out of a test
  // that never ends: it resolves with `error` saying so.
  async function checkCode(source, { filename = "main.py", stdin, files = {}, tests = [] } = {}) {
    if (run) await stopRun();
    worker ??= startWorker();
    await worker.ready;
    return new Promise((resolve) => {
      const stopped = { tests: [], output: "", error: "The check was stopped." };
      run = { resolve: (answer) => resolve(answer.ok === false ? stopped : answer), check: true, waiting: false, animation: 0 };
      worker.worker.postMessage({ type: "check", source, filename, stdin, files, tests });
    });
  }

  // Keep this run's picture (S-226): the sketch runs f.keep(note), which writes studio/NNN.png, .py and .json, and each of
  // them reaches `onFile` as any saved file does, before the answer. Resolves { ok: true, base, files: ["studio/001.png", ...] },
  // or { ok: false, reason } when there is no run to keep (not started, stopped, ended with an error or by f.stop()) or the
  // worker does not answer. A script that has finished drawing can still be kept, and so can a sketch that called no_loop().
  function keepRun(note = "") {
    const slot = worker;
    if (!slot?.loaded) return Promise.resolve({ ok: false, reason: "The sketch is not running." });
    const id = ++keeps;
    return new Promise((resolve) => {
      const done = (answer) => { clearTimeout(timer); keeping.delete(id); resolve(answer); };
      const timer = setTimeout(() => done({ ok: false, reason: "The sketch did not answer in time." }), KEEP_WAIT_MS);
      keeping.set(id, ({ ok, base, files, reason }) => done(ok ? { ok, base, files } : { ok, reason }));
      slot.worker.postMessage({ type: "keep", id, note: String(note) });
    });
  }

  function tick(time) {
    if (!run) return;
    if (!run.waiting) {                  // one step in flight at most: a slow sketch drops display frames, never queues them
      run.waiting = true;
      camera.sendFrame();                // before the step, so the sketch's draw() sees it
      worker.worker.postMessage({ type: "step", now: time / 1000 });
    }
    run.animation = requestAnimationFrame(tick);
  }

  // ---- input, in logical pixels

  function send(kind, fields) {
    if (run) worker.worker.postMessage({ type: "event", kind, ...fields });
  }

  function position(e) {
    const box = canvas.getBoundingClientRect();
    return { x: Math.round((e.clientX - box.left) * (logical.width / box.width)), y: Math.round((e.clientY - box.top) * (logical.height / box.height)) };
  }

  canvas.addEventListener("pointerdown", (e) => {
    canvas.focus();
    try { canvas.setPointerCapture(e.pointerId); } catch { /* no live pointer to capture (a synthetic event) */ }   // a drag that leaves the canvas still arrives
    send("mouse_pressed", { ...position(e), button: MOUSE_BUTTONS[e.button] ?? "left" });
  });
  canvas.addEventListener("pointerup", (e) => send("mouse_released", { ...position(e), button: MOUSE_BUTTONS[e.button] ?? "left" }));
  canvas.addEventListener("pointermove", (e) => send(e.buttons & 7 ? "mouse_dragged" : "mouse_moved", position(e)));
  canvas.addEventListener("contextmenu", (e) => e.preventDefault());
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const notches = e.deltaMode === WheelEvent.DOM_DELTA_LINE ? e.deltaY : e.deltaY / WHEEL_NOTCH;
    send("mouse_wheel", { ...position(e), delta: notches });
  }, { passive: false });
  canvas.addEventListener("keydown", (e) => { e.preventDefault(); send("key_pressed", keyFields(e)); });
  canvas.addEventListener("keyup", (e) => { e.preventDefault(); send("key_released", keyFields(e)); });

  return {
    info,                                // what the first worker reported: library versions, load times, bytes fetched
    run: runSketch,
    check: checkCode,                    // check(source, {tests: [{name, code}], stdin, files}): the code, then each test (see checkCode)
    stop: stopRun,
    keep: keepRun,                       // keep(note): the picture, a copy of the code and a record, as files (see keepRun)
    audioState: () => audio.state(),     // sound unlocked? what each voice is doing? microphone open? (for tests and tools)
    cameraState: () => camera.state(),   // the camera open, and wanted by the sketch? (for tests and tools)
    get running() { return run !== null; },
  };
}

// S-276: `packages` and `install` as the worker takes them (wheel addresses made absolute here, because a worker started from a
// blob: URL has no folder to resolve them against). One plain sentence for each mistake.
function checkedPackages(packages, install, baseUrl) {
  if (install !== undefined && install !== "on import" && install !== "at start") {
    throw new Error('createRunner(): install must be "on import" or "at start".');
  }
  if (packages === undefined) return undefined;
  if (!Array.isArray(packages)) throw new Error('createRunner(): packages must be a list, for example ["numpy"].');
  return packages.map((entry) => {
    if (typeof entry === "string" && entry.trim() !== "") return entry;
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
      throw new Error("createRunner(): each entry of packages must be a package name or a wheel written as {name, url, sha256}.");
    }
    const { name, url, sha256, imports } = entry;
    if (typeof name !== "string" || name === "" || typeof url !== "string" || url === "" || typeof sha256 !== "string" || !/^[0-9a-f]{64}$/i.test(sha256)) {
      throw new Error(`createRunner(): the wheel ${typeof name === "string" && name ? `"${name}" ` : ""}in packages needs a name, a url and a sha256 of 64 hexadecimal characters.`);
    }
    if (imports !== undefined && !(Array.isArray(imports) && imports.every((item) => typeof item === "string" && item !== ""))) {
      throw new Error(`createRunner(): the imports of the wheel "${name}" must be a list of names.`);
    }
    return { name, url: new URL(url, baseUrl).href, sha256: sha256.toLowerCase(), ...(imports ? { imports: [...imports] } : {}) };
  });
}

// A worker must come from the page's own origin. When the runner's files are on another one (a VS Code webview loads
// them from its resource origin), the script is fetched once and started from a blob: URL, which is the page's.
async function workerScriptUrl(url) {
  if (url.origin === location.origin) return url;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`the runner's worker could not be fetched: ${response.status} ${url}`);
  return URL.createObjectURL(new Blob([await response.text()], { type: "text/javascript" }));
}

function keyFields(e) {
  const printable = e.key.length === 1;
  return { key: printable ? e.key : KEY_NAMES[e.key] ?? e.key.toLowerCase(), keyCode: e.keyCode };
}

function outputWriter(output) {
  if (typeof output === "function") return output;
  if (!output) return (text, stream) => console[stream === "stderr" ? "error" : "log"](text);
  return (text, stream) => {
    const line = document.createElement("div");
    line.className = stream;
    line.textContent = text;
    output.append(line);
    output.scrollTop = output.scrollHeight;
  };
}
