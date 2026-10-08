// S-148: Pyodide worker for the phase split (prof_shim.py) and the postMessage test.
//   boot {route, base}      Pyodide, fonttools, uharfbuzz, pathops, pycairo (both routes: the Canvas route needs it for ink), funground, Host
//   prof {id, kind, scale}  prof_shim.profile -> {type:"prof", result: <JSON text>}
//   pm {reps}               post the last frame's JSON as string, parsed object, UTF-8 buffer and a flat Float64Array (the page acks each)
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const now = () => performance.now();
const abs = () => performance.timeOrigin + performance.now();
let py = null, host = null, profShim = null, base = null, route = null, ackWaiter = null;

async function micropipInstall(url) {
  py.globals.set("_wheel_url", url);
  await py.runPythonAsync("import micropip; await micropip.install(_wheel_url, deps=False)");
}

async function boot(m) {
  route = m.route; base = m.base;
  const t0 = now();
  const { loadPyodide } = await import(PYODIDE + "pyodide.mjs");
  py = await loadPyodide({ indexURL: PYODIDE, env: { SDL_VIDEODRIVER: "dummy", SDL_AUDIODRIVER: "dummy", FUNGROUND_HEADLESS: "1" } });
  await py.loadPackage(["fonttools", "micropip"]);
  await py.runPythonAsync("import micropip; await micropip.install('uharfbuzz')");
  await micropipInstall(new URL("dist/wheels/skia_pathops-0.9.2-cp310-abi3-pyemscripten_2026_0_wasm32.whl", base).href);
  await micropipInstall(new URL("dist/wheels/pycairo-1.29.2-cp314-cp314-pyemscripten_2026_0_wasm32.whl", base).href);
  const [zip, shim, prof, mixer] = await Promise.all([
    fetch(new URL("dist/funground.zip", base)).then((r) => r.arrayBuffer()),
    fetch(new URL("shim.py", base)).then((r) => r.text()),
    fetch(new URL("../s148/prof_shim.py", base)).then((r) => r.text()),
    fetch(new URL("mixer_stub.py", base)).then((r) => r.text()),
  ]);
  py.unpackArchive(zip, "zip", { extractDir: "/src" });
  py.FS.writeFile("/src/shim.py", shim);
  py.FS.writeFile("/src/prof_shim.py", prof);
  py.FS.writeFile("/src/mixer_stub.py", mixer);
  py.FS.mkdirTree("/src/funground/fonts");
  const fonts = await (await fetch(new URL("dist/fonts.json", base))).json();
  for (const f of fonts) py.FS.writeFile("/src/funground/fonts/" + f, new Uint8Array(await (await fetch(new URL("dist/fonts/" + f, base))).arrayBuffer()));
  py.runPython("import sys; sys.path.insert(0, '/src'); import shim, prof_shim");
  host = py.pyimport("shim").Host(route);
  profShim = py.pyimport("prof_shim");
  postMessage({ type: "booted", ms: now() - t0 });
}

let pygameLoaded = false;
async function prof(m) {
  if (m.pygame && !pygameLoaded) { await py.loadPackage("pygame-ce"); py.runPython("import mixer_stub; mixer_stub.install()"); pygameLoaded = true; }
  const source = await (await fetch(new URL(`dist/sketches/${m.id}.py`, base))).text();
  const text = profShim.profile(host, m.id, m.kind, source, m.scale, route);
  postMessage({ type: "prof", id: m.id, result: text });
}

function pmWait() { return new Promise((r) => { ackWaiter = r; }); }

async function pm(m) {
  const body = profShim.LAST.get("body");
  if (!body) { postMessage({ type: "pmdone", error: "no body" }); return; }
  const obj = JSON.parse(body);
  const nOps = obj.length;
  const enc = new TextEncoder();
  const sender = { string: [], object: [], buffer: [], flat: [] };
  const bytes = { string: body.length, object: body.length, buffer: enc.encode(body).byteLength, flat: nOps * 14 * 8 };
  for (let rep = 0; rep < m.reps; rep++) {
    for (const kind of ["string", "object", "buffer", "flat"]) {
      const msg = { type: "pmmsg", kind, rep, tSent: 0 };
      const transfer = [];
      if (kind === "string") msg.payload = body;
      else if (kind === "object") msg.payload = obj;
      else if (kind === "buffer") { const u = enc.encode(body); msg.payload = u.buffer; transfer.push(u.buffer); }
      else { const f = new Float64Array(nOps * 14); for (let i = 0; i < f.length; i++) f[i] = i * 0.5; msg.payload = f.buffer; transfer.push(f.buffer); }
      const w = pmWait();
      const t = now();
      msg.tSent = abs();
      postMessage(msg, transfer);
      sender[kind].push(now() - t);
      await w;
    }
  }
  postMessage({ type: "pmdone", nOps, bytes, sender });
}

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === "boot") await boot(m);
    else if (m.type === "prof") await prof(m);
    else if (m.type === "pm") await pm(m);
    else if (m.type === "ack" && ackWaiter) { const r = ackWaiter; ackWaiter = null; r(); }
  } catch (err) {
    postMessage({ type: "error", where: m.type, message: String((err && err.stack) || err) });
  }
};
