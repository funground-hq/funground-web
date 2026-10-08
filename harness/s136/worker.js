// S-136: Python (Pyodide) in a module worker. The page drives it frame by frame (D-074, L1).
//
// Messages in:  {type:"boot", sketch, canvas?}   load Pyodide and funground, run the file up to f.run()
//               {type:"step", t, events, seq}   one frame: t is the page's rAF timestamp (ms)
//               {type:"finish"}
// Messages out: {type:"ready", phases, size}
//               {type:"frame", seq, running, py: {step, encode}, tSent, ops?, c0x, drawMs?}
//               {type:"error", where, message}
//
// If boot carries an OffscreenCanvas, the worker draws the frame itself (canvas=worker) and sends no ops.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const now = () => performance.now();
const abs = () => performance.timeOrigin + performance.now();      // comparable between page and worker

let py = null, host = null, renderer = null, canvas = null;
const phases = {};

async function boot(m) {
  const t0 = now();
  const { loadPyodide } = await import(PYODIDE + "pyodide.mjs");
  phases.import_pyodide_js = now() - t0;
  let t = now();
  py = await loadPyodide({ indexURL: PYODIDE });
  phases.load_pyodide = now() - t; t = now();
  await py.loadPackage("fonttools");                  // typography.py imports fontTools at load time
  phases.load_fonttools = now() - t; t = now();
  const [zip, shim, src] = await Promise.all([
    fetch("dist/funground.zip").then((r) => r.arrayBuffer()),
    fetch("shim.py").then((r) => r.text()),
    fetch(`dist/sketches/${m.sketch}.py`).then((r) => r.text()),
  ]);
  phases.fetch_funground = now() - t; t = now();
  py.unpackArchive(zip, "zip", { extractDir: "/src" });
  py.FS.writeFile("/src/shim.py", shim);
  phases.unpack = now() - t; t = now();
  py.runPython("import sys; sys.path.insert(0, '/src'); import shim");
  const Host = py.pyimport("shim").Host;
  host = Host(src, m.sketch + ".py");
  phases.import_funground_py = host.import_ms;
  phases.run_to_f_run_py = host.run_top_level();      // exec the file: f.run() -> start() -> setup()
  phases.python_total = now() - t;
  const size = host.size().toJs();
  if (m.canvas) {
    canvas = m.canvas;
    const { IrCanvasRenderer } = await import("../../renderer/ir_canvas.js");
    renderer = new IrCanvasRenderer(canvas, { width: size[0], height: size[1], scale: size[2], getBlob: () => null });
  }
  phases.total = now() - t0;
  postMessage({ type: "ready", phases, size });
}

function step(m) {
  const r = host.step(m.t, m.events);
  const [running, stepMs, encMs, json] = r.toJs();
  r.destroy();
  const out = { type: "frame", seq: m.seq, running, py: { step: stepMs, encode: encMs }, consumed: m.maxEventSeq };
  if (renderer) {
    const t = now();
    const ops = JSON.parse(json);
    out.parseMs = now() - t;
    const t2 = now();
    renderer.drawFrame(ops);
    out.drawMs = now() - t2;
    out.c0x = firstCircleX(ops);
  } else {
    out.ops = json;
  }
  out.tSent = abs();
  postMessage(out);
}

const firstCircleX = (ops) => { for (const o of ops) if (o.op === "Circle") return o.x; return null; };

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === "boot") await boot(m);
    else if (m.type === "step") step(m);
    else if (m.type === "finish") { host.finish(); postMessage({ type: "finished" }); }
  } catch (err) {
    postMessage({ type: "error", where: m.type, message: String((err && err.stack) || err) });
  }
};
