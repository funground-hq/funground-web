// The funground browser runner, page side (story S-153). How a page uses it: runner/README.md.
//
//   import { createRunner } from "./runner.js";
//   const runner = await createRunner({ canvas, output });      // loads Python; resolves when it is ready
//   await runner.run(source, { filename: "sketch.py" });        // starts a sketch; frames appear on the canvas
//   runner.stop();                                              // ends it, however busy it is
//
// The learner's code runs in a module Web Worker (worker.js), so the page stays responsive. A worker runs one
// file only. When a run ends, or Stop terminates it, a fresh worker starts loading at once, so the next Run
// finds Python ready (or nearly).

import { createAudio } from "./audio.js";

const KEY_NAMES = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down", Enter: "enter", Escape: "escape" };
const MOUSE_BUTTONS = ["left", "center", "right"];                 // MouseEvent.button 0, 1, 2
const WHEEL_NOTCH = 100;                                          // deltaY pixels in one notch of a wheel

/**
 * @param {object} options
 * @param {HTMLCanvasElement} options.canvas  where frames are drawn; it also receives the mouse and keyboard
 * @param {HTMLElement | ((text: string, stream: "stdout" | "stderr") => void)} [options.output]  where print() and errors go
 * @param {string | URL} [options.baseUrl]  the folder holding worker.js and runtime/ (default: next to this file)
 * @param {boolean} [options.prewarm]  start the next run's worker as soon as a run ends (default true); false starts it at the next run(), which then waits for Python to load
 * @param {(count: number) => void} [options.onFrame]  after each frame is drawn (1 is the first of the run)
 * @param {(reason: "ended" | "error" | "stopped") => void} [options.onFinish]  when a run ends, however it ends
 * @param {(message: object) => void} [options.onSound]  every sound command the sketch makes ({command, voice, fields, samples}), before it is played; for tests and tools
 * @returns {Promise<{info: object, run: Function, stop: Function, running: boolean}>}
 */
export async function createRunner({ canvas, output, baseUrl = new URL("./", import.meta.url), prewarm = true, onFrame, onFinish, onSound }) {
  const write = outputWriter(output);
  const context = canvas.getContext("2d");
  const audio = createAudio({
    write,
    workletUrl: new URL("microphone-worklet.js", baseUrl),
    onChunk: (samples) => { if (run) worker.worker.postMessage({ type: "microphone", samples }, [samples.buffer]); },
  });
  // Browsers keep a page silent until the visitor has clicked or pressed a key on it: the first of either, and Run, unlock sound.
  for (const kind of ["pointerdown", "keydown"]) window.addEventListener(kind, audio.unlock, { capture: true, passive: true });
  const workerUrl = new URL("worker.js", baseUrl);
  const runtimeUrl = new URL("runtime/", baseUrl).href;
  let worker = startWorker();            // the worker for the next run, or the run in progress
  let run = null;                        // the run in progress, or null
  let logical = { width: 0, height: 0 }; // the sketch's canvas in logical pixels
  let scale = 1;                         // backing pixels per logical pixel (devicePixelRatio when the run began)
  let frames = 0;
  if (canvas.tabIndex < 0) canvas.tabIndex = 0;                    // a canvas takes the keyboard only if it can be focused

  const info = await worker.ready;       // a failure to load is thrown to the caller

  // ---- workers

  function startWorker() {
    const created = new Worker(workerUrl, { type: "module" });
    const slot = { worker: created, ready: null, loaded: false };
    slot.ready = new Promise((resolve, reject) => {
      created.onerror = (e) => reject(new Error(`the runner's worker failed to load: ${e.message}`));
      created.onmessage = (e) => {
        const message = e.data;
        if (message.type === "ready") { slot.loaded = true; console.debug("runner: worker ready"); resolve(message); }
        else if (message.type === "error" && !slot.loaded) reject(new Error(message.message));
        else handle(message);
      };
    });
    slot.ready.catch(() => {});                                    // reported where it is awaited
    created.postMessage({ type: "init", runtimeUrl });
    console.debug("runner: worker started");
    return slot;
  }

  // The worker is done with: end it, and start the next unless the page asked to wait. Messages still in flight from it are dropped.
  function replaceWorker() {
    worker.worker.terminate();
    worker = prewarm ? startWorker() : null;
  }

  function finish(reason) {
    if (!run) return;
    cancelAnimationFrame(run.animation);
    run.resolve({ ok: false });                                    // no effect when the run had started
    audio.reset();                                                 // nothing keeps playing or listening
    run = null;
    replaceWorker();
    onFinish?.(reason);
  }

  // ---- messages from the worker

  function handle(message) {
    switch (message.type) {
      case "output": write(message.text, message.stream); break;
      case "error": write(message.message, "stderr"); finish("error"); break;
      case "frame": drawFrame(message); break;
      case "sound": onSound?.(message); audio.command(message); break;
      case "microphone": audio.microphoneCommand(message); break;
      case "started": started(message); break;
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
    if (running) run.animation = requestAnimationFrame(tick);
    else finish("ended");
  }

  // ---- running

  async function runSketch(source, { filename = "sketch.py", files = {}, width, height } = {}) {
    audio.unlock();                                                // Run is a click or a key: the moment the browser allows sound
    if (run) finish("stopped");
    worker ??= startWorker();
    await worker.ready;
    scale = window.devicePixelRatio || 1;
    logical = { width: width ?? (canvas.clientWidth || 640), height: height ?? (canvas.clientHeight || 400) };
    frames = 0;
    return new Promise((resolve) => {
      run = { resolve, waiting: false, animation: 0 };
      worker.worker.postMessage({ type: "run", source, filename, width: logical.width, height: logical.height, scale, files });
    });
  }

  function tick(time) {
    if (!run) return;
    if (!run.waiting) {                  // one step in flight at most: a slow sketch drops display frames, never queues them
      run.waiting = true;
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
    stop: () => finish("stopped"),
    audioState: () => audio.state(),     // sound unlocked? what each voice is doing? microphone open? (for tests and tools)
    get running() { return run !== null; },
  };
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
