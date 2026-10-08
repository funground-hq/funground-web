// S-133: the text corpus in Pyodide. Loads Pyodide, fontTools, harfbuzzjs, funground and the fonts, then
// runs harness/s133/corpus_run.py over the cases the page sends. Messages in: {type:"boot"}, {type:"run", cases},
// {type:"time", cases, repeat}, {type:"dump", cases, ids}. Out: {type:"ready", phases, ...}, {type:"result", ...}, {type:"error"}.
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const now = () => performance.now();
const FONTS = ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf",
  "NotoEmoji-Regular.ttf", "NotoSansDevanagari-Regular.ttf", "NotoSansSymbols2-Regular.ttf"];
const EXTRA = ["TestVar.ttf", "DejaVuSansMono.ttf"];
let py = null, corpus = null;
const phases = {}, sizes = {};

async function boot(m) {
  const t0 = now();
  const { loadPyodide } = await import(PYODIDE + "pyodide.mjs");
  let t = now();
  py = await loadPyodide({ indexURL: PYODIDE });
  phases.load_pyodide = now() - t; t = now();
  await py.loadPackage("fonttools");
  phases.load_fonttools = now() - t; t = now();
  if (m.wheel) {                                      // the real uharfbuzz wheel from PyPI (pyemscripten), fetched by the browser
    await py.loadPackage("micropip");
    await py.runPythonAsync("import micropip; await micropip.install('uharfbuzz')");
    phases.micropip_uharfbuzz = now() - t; t = now();
  } else {
    self.hb = await import("../../vendor/harfbuzzjs/index.mjs");        // top-level await: compiles harfbuzz.wasm
    phases.load_harfbuzzjs = now() - t; t = now();
  }
  const get = async (url, bin) => { const r = await fetch(url); if (!r.ok) throw new Error(url + " " + r.status); return bin ? new Uint8Array(await r.arrayBuffer()) : r.text(); };
  const [zip, shim, runner] = await Promise.all([get("dist/funground.zip", true), get("../../shim/uharfbuzz.py"), get("corpus_run.py")]);
  sizes["funground.zip"] = zip.length; sizes["shim/uharfbuzz.py"] = shim.length;
  py.unpackArchive(zip, "zip", { extractDir: "/src" });
  if (!m.wheel) py.FS.writeFile("/src/uharfbuzz.py", shim);
  py.FS.writeFile("/src/corpus_run.py", runner);
  py.FS.writeFile("/src/stubs.py", await get("stubs.py"));
  phases.unpack = now() - t; t = now();
  py.FS.mkdirTree("/src/funground/fonts"); py.FS.mkdirTree("/src/extra");
  for (const f of FONTS) { const b = await get("dist/fonts/" + f, true); sizes[f] = b.length; py.FS.writeFile("/src/funground/fonts/" + f, b); }
  for (const f of EXTRA) { const b = await get("dist/extra/" + f, true); sizes["extra/" + f] = b.length; py.FS.writeFile("/src/extra/" + f, b); }
  phases.fetch_fonts = now() - t; t = now();
  py.runPython("import sys; sys.path.insert(0, '/src')");
  py.runPython("import stubs, uharfbuzz as hb, corpus_run; import funground.typography");
  phases.import_python = now() - t;
  phases.total = now() - t0;
  postMessage({ type: "ready", phases, sizes, hb_version: py.runPython("import uharfbuzz as hb; hb.version_string() + \" / uharfbuzz \" + hb.__version__ + \" \" + hb.__file__"), fonttools: py.runPython("import fontTools, sys; fontTools.version + \" python \" + sys.version.split()[0]") });
}

const call = (expr, cases) => {
  py.globals.set("_cases_json", JSON.stringify(cases));
  const out = py.runPython(`import json, corpus_run
_roots = {"fonts": "/src/funground/fonts", "extra": "/src/extra"}
_cases = json.loads(_cases_json)
json.dumps(${expr})`);
  return JSON.parse(out);
};

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === "boot") await boot(m);
    else if (m.type === "run") { const t = now(); const r = call("corpus_run.run_all(_cases, _roots)", m.cases); r.wall_ms = now() - t; postMessage({ type: "result", r }); }
    else if (m.type === "time") postMessage({ type: "result", r: call(`corpus_run.timings(_cases, _roots, ${m.repeat || 3})`, m.cases) });
    else if (m.type === "dump") postMessage({ type: "result", r: call(`corpus_run.dump(_cases, ${JSON.stringify(m.ids)}, _roots)`, m.cases) });
  } catch (err) {
    postMessage({ type: "error", where: m.type, message: String((err && err.stack) || err) });
  }
};
