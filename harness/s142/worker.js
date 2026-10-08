// S-142: Python (Pyodide) in a module worker, either renderer, either place to paint.
//
//   boot  {route: "cairo"|"canvas", where: "main"|"worker"}   load Pyodide, packages, funground, the Host
//   case  {id, kind, scale, pygame, ink, canvas?}              load one sketch (loop: run to f.run(); script: nothing yet)
//   step  {t, events, seq, snap}                               one frame of a loop sketch
//   script {scale, seq, snap}                                  run a script sketch and deliver its frame
//
// route "cairo": real CairoRenderer (pycairo); the frame is the surface's BGRA bytes. They are copied out of the
//   wasm heap while swapping B and R (one pass over a Uint32Array), then either transferred to the page
//   (where "main": page does ImageData + putImageData) or painted here on the transferred OffscreenCanvas.
// route "canvas": IR renderer stand-in; the frame is JSON of the IR ops, drawn with renderer/ir_canvas.js, on the
//   page (where "main") or here (where "worker").
//
// All times are performance.now() in milliseconds (Chrome coarsens it to 0.1 ms).

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const now = () => performance.now();
const abs = () => performance.timeOrigin + performance.now();      // comparable between page and worker

let py = null, host = null, route = null, where = null, oc = null, octx = null, renderer = null;
let curW = 0, curH = 0, curScale = 1, curKind = "loop";
const phases = {};
let pyReady = false, pygameLoaded = false, cairoLoaded = false, base = null;

async function micropipInstall(url) {                        // a wheel file served next to the page
  py.globals.set("_wheel_url", url);
  await py.runPythonAsync("import micropip; await micropip.install(_wheel_url, deps=False)");
}

async function boot(m) {
  route = m.route; where = m.where; base = m.base;
  const t0 = now();
  const { loadPyodide } = await import(PYODIDE + "pyodide.mjs");
  phases.import_pyodide_js = now() - t0;
  let t = now();
  py = await loadPyodide({ indexURL: PYODIDE, env: { SDL_VIDEODRIVER: "dummy", SDL_AUDIODRIVER: "dummy", FUNGROUND_HEADLESS: "1" } });
  phases.load_pyodide = now() - t; t = now();
  await py.loadPackage(["fonttools", "micropip"]);                // typography.py imports fontTools at load time
  phases.load_fonttools_micropip = now() - t; t = now();
  await py.runPythonAsync("import micropip; await micropip.install('uharfbuzz')");   // PyPI wheel, as S-133
  phases.micropip_uharfbuzz = now() - t; t = now();
  await micropipInstall(new URL("dist/wheels/skia_pathops-0.9.2-cp310-abi3-pyemscripten_2026_0_wasm32.whl", base).href);
  phases.install_pathops = now() - t; t = now();
  if (route === "cairo") {
    await micropipInstall(new URL("dist/wheels/pycairo-1.29.2-cp314-cp314-pyemscripten_2026_0_wasm32.whl", base).href);
    cairoLoaded = true;
    phases.install_pycairo = now() - t; t = now();
  }
  const [zip, shim, mixer] = await Promise.all([
    fetch(new URL("dist/funground.zip", base)).then((r) => r.arrayBuffer()),
    fetch(new URL("shim.py", base)).then((r) => r.text()),
    fetch(new URL("mixer_stub.py", base)).then((r) => r.text()),
  ]);
  py.unpackArchive(zip, "zip", { extractDir: "/src" });
  py.FS.writeFile("/src/shim.py", shim);
  py.FS.writeFile("/src/mixer_stub.py", mixer);
  py.FS.mkdirTree("/src/funground/fonts");
  const fonts = await (await fetch(new URL("dist/fonts.json", base))).json();
  for (const f of fonts) py.FS.writeFile("/src/funground/fonts/" + f, new Uint8Array(await (await fetch(new URL("dist/fonts/" + f, base))).arrayBuffer()));
  phases.fetch_funground_fonts = now() - t; t = now();
  py.runPython("import sys; sys.path.insert(0, '/src'); import shim");
  host = py.pyimport("shim").Host(route);
  phases.import_funground = now() - t;
  if (route === "canvas") {
    const { IrCanvasRenderer } = await import("../../renderer/ir_canvas.js");
    self.IrCanvasRenderer = IrCanvasRenderer;
  }
  phases.total = now() - t0;
  pyReady = true;
  const res = performance.getEntriesByType("resource").map((e) => ({ name: e.name, transfer: e.transferSize, encoded: e.encodedBodySize, decoded: e.decodedBodySize }));
  postMessage({ type: "booted", phases, resources: res, memory: py._module?.HEAPU8?.length ?? null });
}

async function loadCase(m) {
  const t0 = now();
  const extra = {};
  if (m.pygame && !pygameLoaded) {
    const t = now();
    await py.loadPackage("pygame-ce");
    py.runPython("import mixer_stub; mixer_stub.install()");
    pygameLoaded = true; extra.pygame_ms = now() - t;
  }
  if (route === "canvas") {
    if (m.ink && !cairoLoaded) {                                  // marks measure ink with Cairo
      const t = now();
      await micropipInstall(new URL("dist/wheels/pycairo-1.29.2-cp314-cp314-pyemscripten_2026_0_wasm32.whl", base).href);
      cairoLoaded = true; extra.pycairo_ms = now() - t;
    }
    host.set_ink(!!m.ink);
  }
  const source = await (await fetch(new URL(`dist/sketches/${m.id}.py`, base))).text();
  curKind = m.kind; curScale = m.scale;
  py.runPython("import os, tempfile; os.chdir(tempfile.mkdtemp())");
  let size = null;
  if (m.kind === "loop") {
    const r = host.load_loop(source, m.id + ".py", m.scale);
    size = r.toJs(); r.destroy();
  } else {
    self.scriptSource = source; self.scriptName = m.id + ".py";
  }
  oc = m.canvas || null; octx = null; renderer = null;
  postMessage({ type: "loaded", id: m.id, size: size ? size.slice(0, 3) : null, ms: now() - t0, extra });
}

// Prepare the painting side once the size is known (loop: after load; script: after the first run)
function prepare(w, h, scale) {
  curW = Math.round(w * scale); curH = Math.round(h * scale);
  if (where === "worker" && oc) {
    oc.width = curW; oc.height = curH;
    if (route === "cairo") octx = oc.getContext("2d");
    else renderer = new IrCanvasRenderer(oc, { width: w, height: h, scale, getBlob: () => null });
  }
}

function swizzle(mv, w, h) {
  const buf = mv.getBuffer("u8");
  const n = w * h;
  const d = buf.data;
  const out = new Uint32Array(n);
  if (d.byteOffset % 4 === 0) {
    const src = new Uint32Array(d.buffer, d.byteOffset, n);
    for (let i = 0; i < n; i++) { const v = src[i]; out[i] = (v & 0xFF00FF00) | ((v & 0xFF) << 16) | ((v >>> 16) & 0xFF); }
  } else {
    const o8 = new Uint8Array(out.buffer);
    for (let i = 0; i < n * 4; i += 4) { o8[i] = d[i + 2]; o8[i + 1] = d[i + 1]; o8[i + 2] = d[i]; o8[i + 3] = d[i + 3]; }
  }
  buf.release();
  return out;
}

// Turn the Host's list into the message for the page; paint here when where === "worker".
function deliver(r, tIn, extraMsg) {
  const [running, stepMs, drawMs, renderMs, encMs, body, nOps] = r.slice(0, 7);
  const out = { type: "frame", running, py: { step: stepMs, draw: drawMs, render: renderMs, other: stepMs - drawMs - renderMs, encode: encMs }, nOps, tIn, ...extraMsg };
  const transfer = [];
  if (route === "cairo") {
    const mv = host.frame_view();
    const wh = host.frame_size().toJs();
    const t = now();
    const px = swizzle(mv, wh[0], wh[1]);
    mv.destroy();
    out.wcopyMs = now() - t;
    out.w = wh[0]; out.h = wh[1];
    if (where === "worker") {
      if (!octx) throw new Error("worker canvas was not prepared");
      const t2 = now();
      octx.putImageData(new ImageData(new Uint8ClampedArray(px.buffer), wh[0], wh[1]), 0, 0);
      out.paintMs = now() - t2;
      if (extraMsg.snap) out.snapBuf = octx.getImageData(0, 0, wh[0], wh[1]).data.buffer;
    } else {
      out.pixels = px.buffer; transfer.push(px.buffer);
    }
  } else {
    if (where === "worker") {
      let t = now();
      const ops = JSON.parse(body);
      out.parseMs = now() - t; t = now();
      renderer.drawFrame(ops);
      out.paintMs = now() - t;
      if (extraMsg.snap) out.snapBuf = oc.getContext("2d").getImageData(0, 0, curW, curH).data.buffer;
    } else out.ops = body;
  }
  if (out.snapBuf) transfer.push(out.snapBuf);
  out.tSent = abs();
  postMessage(out, transfer);
}

function step(m) {
  const tIn = abs();
  const r = host.step(m.t, m.events).toJs();
  deliver(r, tIn, { seq: m.seq, snap: m.snap, consumed: m.maxEventSeq });
}

function script(m) {
  const tIn = abs();
  const r = host.run_script(self.scriptSource, self.scriptName, m.scale).toJs();
  const size = r.slice(7, 10);
  if (m.prepare) prepare(size[0], size[1], size[2]);
  deliver(r, tIn, { seq: m.seq, snap: m.snap, size });
}

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === "boot") await boot(m);
    else if (m.type === "case") { await loadCase(m); if (m.kind === "loop") { /* size known to page after "loaded" */ } }
    else if (m.type === "prepare") { prepare(m.w, m.h, m.scale); postMessage({ type: "prepared" }); }
    else if (m.type === "step") step(m);
    else if (m.type === "script") script(m);
  } catch (err) {
    postMessage({ type: "error", where: m.type, message: String((err && err.stack) || err) });
  }
};
