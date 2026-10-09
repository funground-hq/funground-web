// The funground preview panel (inside a VS Code webview). The extension sends `run` messages with the sketch's text and
// its data/ files; this page runs them with the funground browser runner and reports back. See ../extension.js.

const vscode = acquireVsCodeApi();
const SNAPSHOT_FRAME = 30;                       // the frame funground's goldens show (tests/conftest.py)

// What the page has done, for the extension's tests (test/run_tests.mjs reads it from the page). Changes nothing.
const record = { ready: null, runs: [] };
window.fungroundPreview = record;

export async function start({ runner: runnerBase, pyodide, runtime, where }) {
  const canvas = document.getElementById("canvas");
  const outputBox = document.getElementById("output");
  const status = document.getElementById("status");
  let active = null;                             // the record of the run on the canvas
  let pending = null;                            // a run asked for while another was starting: only the latest is kept
  let starting = false;
  let last = null;                               // the last sketch sent, for the panel's Run button

  function write(text, stream) {
    const line = document.createElement("div");
    line.className = stream;
    line.textContent = text;
    outputBox.append(line);
    outputBox.scrollTop = outputBox.scrollHeight;
    if (active) active.output.push([stream, text]);
  }

  const began = performance.now();
  let runner;
  try {
    const { createRunner } = await import(new URL("runner.js", runnerBase).href);
    runner = await createRunner({
      canvas, baseUrl: runnerBase, pyodideUrl: pyodide, runtimeUrl: runtime, reuse: true,
      output: (text, stream) => {
        write(text, stream);
        if (stream === "stderr" && text.includes("Traceback")) vscode.postMessage({ type: "error", text });
      },
      onFrame: (count) => {
        if (!active) return;
        if (count === 1) { active.firstFrameMs = Math.round(performance.now() - active.t0); active.firstFrameAt = Date.now(); status.textContent = `Running ${active.filename}`; }
        if (count === 1 || count === SNAPSHOT_FRAME) active.snapshots[count] = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height);
        active.frames = count;
      },
      onFinish: (reason) => { if (active) { active.finished = reason; status.textContent = reason === "error" ? "Stopped: error" : "Stopped"; } },
      onSound: (message) => { if (active) active.sounds.push({ command: message.command, voice: message.voice, frames: message.samples ? message.samples.length / 2 : 0 }); },
    });
  } catch (error) {
    status.textContent = "Python did not load";
    write(String(error.message ?? error), "stderr");
    vscode.postMessage({ type: "failed", message: String(error.message ?? error) });
    return;
  }
  record.audioState = () => runner.audioState();
  record.ready = { loadMs: Math.round(performance.now() - began), info: runner.info, where };
  status.textContent = "Ready";
  vscode.postMessage({ type: "ready", loadMs: record.ready.loadMs, runtime: where });

  async function run(message) {
    last = message;
    if (starting) { pending = message; return; }
    starting = true;
    outputBox.textContent = "";
    status.textContent = `Starting ${message.filename}`;
    active = { filename: message.filename, why: message.why, sentAt: message.at, t0: performance.now(), frames: 0, snapshots: {}, sounds: [], output: [], finished: null };
    record.runs.push(active);
    try {
      const result = await runner.run(message.source, { filename: message.filename, files: message.files, seed: message.seed });
      active.ok = result.ok;
      active.startMs = Math.round(performance.now() - active.t0);
    } finally {
      starting = false;
    }
    if (pending) { const next = pending; pending = null; run(next); }
  }

  window.addEventListener("message", (event) => {
    const message = event.data;
    if (message.type === "run") run(message);
    else if (message.type === "stop") runner.stop();
  });
  document.getElementById("run").addEventListener("click", () => { if (last) run(last); });
  document.getElementById("stop").addEventListener("click", () => runner.stop());
}
