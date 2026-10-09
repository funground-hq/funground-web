// Headless test of the funground VS Code web extension (story S-158).
//
//   node run_tests.mjs [--runtime bundled | site:<folder made by build.py --site> | published:<the same>] [--label NAME] [--chromium PATH]
//                      [--vscode sources:<VS Code checkout, compiled>] [--port N] [--host NAME]
//
// Starts VS Code for the web with @vscode/test-web (it downloads the stable web build once into .vscode-test-web/ and
// reuses it), with this extension in development mode and a copy of sketchbook/ as the workspace. Then it drives headless
// Chrome with Playwright as a learner would: open a sketch (a click in the Explorer), run "funground: Run" (F1), type,
// save. It reads what the preview panel did from its page (window.fungroundPreview, media/preview.js) and writes
// out/<label>/report.json and the frames as raw RGBA, which compare.py checks against funground's goldens.
// Runtime "bundled" needs an extension built with the runtime inside (build.py). "site:<folder>" serves build.py --site's
// folder from a second local origin with CORS, as the website would, and points the extension's funground.runtimeUrl
// setting at it. "published:<folder>" leaves the setting empty, so the extension looks for the website's folder for its
// version, and answers that URL from the folder. For both, build the extension with --runtime site: nothing can then be
// read from inside it.

import { spawn } from "node:child_process";
import { cpSync, mkdirSync, rmSync, writeFileSync, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, join, resolve, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXTENSION = resolve(HERE, "..");
const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, arg, i, all) => (arg.startsWith("--") ? [...pairs, [arg.slice(2), all[i + 1]]] : pairs), []));
const runtime = args.runtime ?? "bundled";
const label = args.label ?? runtime.split(":")[0];
const OUT = join(HERE, "out", label);
const VSCODE_PORT = Number(args.port ?? 3000);
const SITE_PORT = VSCODE_PORT + 100;
const CHROME = args.chromium ?? "C:/Users/samirj/AppData/Local/Google/Chrome/Application/chrome.exe";
const LIVE_EDITS = 5;
// VS Code's webview service worker treats a request to localhost specially: from the runner's worker it waits 30 s for an
// answer that never comes, then fetches directly (src/vs/workbench/contrib/webview/browser/pre/service-worker.js,
// processLocalhostRequest, which matches "localhost" and "127.0.0.1" exactly). Real hosts (vscode.dev, github.dev, a
// Marketplace CDN, a runtime site) are not localhost, so by default the test serves both origins under subdomains of
// localhost, which Chromium resolves to the loopback address and treats as secure, and which that rule does not match.
// --host localhost shows the difference.
const HOST = args.host ?? "vscode.localhost";
const SITE_HOST = HOST === "localhost" ? "127.0.0.1" : "runtime.localhost";

const report = { label, host: HOST, runtime, chrome: CHROME, started: new Date().toISOString(), steps: [], cases: {}, live: [], errors: [] };
const log = (...parts) => { const line = parts.join(" "); console.log(line); report.steps.push(line); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- the workspace: a fresh copy of the sketchbook (Save writes to it)

rmSync(OUT, { recursive: true, force: true });
mkdirSync(join(OUT, "frames"), { recursive: true });
const workspace = join(OUT, "sketchbook");
cpSync(join(HERE, "sketchbook"), workspace, { recursive: true });

// ---- the runtime site (a second origin, with CORS, as GitHub Pages serves one)

const TYPES = { ".mjs": "text/javascript", ".js": "text/javascript", ".json": "application/json", ".wasm": "application/wasm", ".zip": "application/zip", ".whl": "application/zip" };
let siteBytes = 0;
let site = null;
const published = runtime.startsWith("published:");     // no setting: the extension's default, the website's folder (routed to the local copy)
if (runtime.startsWith("site:") || published) {
  const root = resolve(runtime.slice(runtime.indexOf(":") + 1));
  site = createServer((request, response) => {
    const path = join(root, decodeURIComponent(new URL(request.url, "http://x").pathname));
    if (!path.startsWith(root) || !existsSync(path) || !statSync(path).isFile()) { response.writeHead(404, { "Access-Control-Allow-Origin": "*" }); response.end(); return; }
    const data = readFileSync(path);
    siteBytes += data.length;
    response.writeHead(200, { "Content-Type": TYPES[extname(path)] ?? "application/octet-stream", "Access-Control-Allow-Origin": "*", "Cache-Control": "max-age=600" });
    response.end(data);
  }).listen(SITE_PORT, "127.0.0.1");
  if (!published) {
    const settings = JSON.parse(readFileSync(join(workspace, ".vscode", "settings.json"), "utf8"));
    settings["funground.runtimeUrl"] = `http://${SITE_HOST}:${SITE_PORT}/`;
    writeFileSync(join(workspace, ".vscode", "settings.json"), JSON.stringify(settings, null, 2));
  }
}

// ---- VS Code for the web

const DATA_DIR = join(HERE, ".vscode-test-web");                              // the downloaded build is kept here (git-ignored)
const serverArgs = ["--browserType", "none", "--port", String(VSCODE_PORT), `--extensionDevelopmentPath=${EXTENSION}`, "--testRunnerDataDir", DATA_DIR];
const [kind, where] = (args.vscode ?? "stable").split(/:(.*)/s);
if (kind === "sources") serverArgs.push("--sourcesPath", resolve(where));
else if (kind === "stable") serverArgs.push("--quality", "stable");
else throw new Error("--vscode sources:<path> (the default is the stable web build)");
serverArgs.push(workspace);
const server = spawn(process.execPath, [join(HERE, "node_modules", "@vscode", "test-web", "out", "server", "index.js"), ...serverArgs], { stdio: ["ignore", "pipe", "pipe"] });
process.on("exit", () => server.kill());                                            // never leave the server behind
server.stdout.on("data", (d) => process.stdout.write(`[server] ${d}`));
server.stderr.on("data", (d) => process.stdout.write(`[server] ${d}`));
for (let i = 0; i < 240; i++) {                                                // the first run downloads VS Code
  try { if ((await fetch(`http://localhost:${VSCODE_PORT}/`)).ok) break; } catch { /* not yet */ }
  await sleep(500);
}

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: [
    "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",   // a microphone that says yes, if asked
  ],
});
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
// "local-network-access": Chrome 142 and later asks before a page reaches a loopback address from another origin (VS Code's
// extension host and webview frames are subdomains of vscode.localhost); headless Chrome cannot ask, so it is given.
await context.grantPermissions(["microphone", "local-network-access"]);
const page = await context.newPage();
// The extension host's own iframe (not the preview panel) allows scripts and requests only to https: and to http://localhost:*, so on
// vscode.localhost it cannot load its worker. The page that lists those sources is served with one more: our host name.
// Nothing about the extension or its panel's policy is touched.
await context.route(/webWorkerExtensionHostIframe\.html/, async (route) => {
  const html = await (await fetch(`http://localhost:${VSCODE_PORT}${new URL(route.request().url()).pathname}`)).text();
  await route.fulfill({ contentType: "text/html", body: html.replaceAll("http://localhost:*", `http://localhost:* http://${HOST}:*`) });
});
if (published) {
  // https://funground-hq.github.io/runtime/<fungroundRuntime>/ answered from the local copy, with the CORS header GitHub Pages sends
  const folder = `/runtime/${JSON.parse(readFileSync(join(EXTENSION, "package.json"), "utf8")).fungroundRuntime}`;
  await context.route(`https://funground-hq.github.io${folder}/**`, async (route) => {
    const local = await fetch(`http://127.0.0.1:${SITE_PORT}${new URL(route.request().url()).pathname.slice(folder.length)}`);
    const headers = { "Access-Control-Allow-Origin": "*", "Content-Type": local.headers.get("content-type") ?? "application/octet-stream" };
    await route.fulfill({ status: local.status, headers, body: Buffer.from(await local.arrayBuffer()) });
  });
}
const consoleLines = [];
page.on("console", (m) => { if (/runner|funground|Refused|CSP|Content Security|worker/i.test(m.text())) consoleLines.push(`${m.type()}: ${m.text()}`.slice(0, 500)); });
const requests = [];
page.on("requestfinished", async (request) => {
  const url = request.url();
  if (!/pyodide|wheels|runtime|runner|manifest/.test(url)) return;
  const sizes = await request.sizes().catch(() => null);
  requests.push({ url: url.replace(/^.*?(\/media\/|:\d+\/)/, "$1"), bytes: sizes?.responseBodySize ?? null });
});

try {
  const t0 = Date.now();
  await page.goto(`http://${HOST}:${VSCODE_PORT}/`, { timeout: 180000 });
  await page.waitForSelector(".monaco-workbench", { timeout: 120000 });
  await sleep(4000);                                                            // the extension host and the explorer settle
  report.vscodeVersion = await page.evaluate(() => document.querySelector("meta[name=version]")?.content ?? null);
  log(`workbench up in ${Date.now() - t0} ms`);
  const openFile = async (name) => {                                         // a click in the Explorer, as a learner would
    await page.locator(`.explorer-folders-view .monaco-list-row[aria-label="${name}"]`).dblclick();
    await page.waitForFunction((n) => document.querySelector(".tab.active")?.textContent?.includes(n), name, { timeout: 20000 });
    await sleep(300);
  };
  const command = async (title) => {
    await page.keyboard.press("F1");
    await sleep(400);
    await page.keyboard.type(title, { delay: 10 });
    await sleep(600);
    await page.keyboard.press("Enter");
  };
  const previewFrame = async (timeout = 180000) => {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      for (const frame of page.frames()) {
        try { if (await frame.evaluate(() => typeof window.fungroundPreview === "object")) return frame; } catch { /* detached */ }
      }
      await sleep(250);
    }
    throw new Error("the preview panel did not appear");
  };
  const state = (frame) => frame.evaluate(() => {
    const r = window.fungroundPreview;
    return { ready: r.ready, runs: r.runs.map((x) => ({ filename: x.filename, why: x.why, frames: x.frames, ok: x.ok, startMs: x.startMs, firstFrameMs: x.firstFrameMs, firstFrameAt: x.firstFrameAt, sentAt: x.sentAt, finished: x.finished, sounds: x.sounds.length, output: x.output })) };
  });
  const waitFor = async (frame, test, what, timeout = 120000) => {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      const s = await state(frame);
      if (test(s)) return s;
      await sleep(100);
    }
    throw new Error(`timed out waiting for ${what}`);
  };
  const saveFrame = async (frame, id, runIndex, frameNumber) => {
    const data = await frame.evaluate(([i, n]) => {
      const image = window.fungroundPreview.runs[i].snapshots[n];
      if (!image) return null;
      let binary = "";
      for (let k = 0; k < image.data.length; k += 0x8000) binary += String.fromCharCode(...image.data.subarray(k, k + 0x8000));
      return { width: image.width, height: image.height, base64: btoa(binary) };
    }, [runIndex, frameNumber]);
    if (!data) throw new Error(`${id}: no snapshot at frame ${frameNumber}`);
    writeFileSync(join(OUT, "frames", `${id}.rgba`), Buffer.from(data.base64, "base64"));
    return { width: data.width, height: data.height, frame: frameNumber };
  };

  // The Problems view lists the error the extension marked, with its line ("[Ln 10, Col 1]").
  const problemLines = async () => {
    await page.keyboard.press("Control+Shift+M");
    await sleep(1500);
    return page.evaluate(() => [...document.querySelectorAll(".markers-panel .monaco-list-row")].map((row) => row.textContent));
  };

  // uses_helper.py imports helpers.py. Open helpers.py, change its value without saving, come back: the run must use it.
  const helperEdit = async (frame) => {
    const printed = (run) => run.output.map(([, text]) => text).find((text) => text.startsWith("helper value")) ?? null;
    const first = printed((await state(frame)).runs.at(-1));
    await openFile("helpers.py");
    await page.keyboard.press("Control+A");
    await page.keyboard.type("VALUE = 2");
    await sleep(800);
    const typed = await page.evaluate(() => document.querySelector(".monaco-editor .view-lines")?.textContent);
    const before = (await state(frame)).runs.length;
    await openFile("uses_helper.py");
    const s = await waitFor(frame, (x) => x.runs.length > before && x.runs.at(-1).filename === "uses_helper.py" && x.runs.at(-1).frames >= 3, "uses_helper.py again");
    return { helperBefore: first, helperEditor: typed, helperAfter: printed(s.runs.at(-1)), helperRuns: s.runs.slice(-5).map((r) => [r.filename, r.why, r.frames, r.output]) };
  };

  // 1. first load: open a sketch, run the command, wait for Python and the first frame.
  await openFile("first_sketch.py");
  const tRun = Date.now();
  await command("funground: Run");
  const frame = await previewFrame();
  log(`panel page found ${Date.now() - tRun} ms after the command`);
  let s = await waitFor(frame, (x) => x.ready && x.runs.length && x.runs[0].frames >= 30, "the first sketch's frame 30", 240000);
  report.firstLoad = { commandToReadyMs: s.ready.loadMs, panelLoadMs: s.ready.loadMs, commandToFirstFrameMs: s.runs[0].firstFrameAt - tRun, timings: s.ready.info.timings, versions: s.ready.info.versions, where: s.ready.where };
  log(`Python ready (panel's own count) ${s.ready.loadMs} ms; command to first frame ${report.firstLoad.commandToFirstFrameMs} ms`);
  report.cases.first_sketch = { ...(await saveFrame(frame, "first_sketch", 0, 30)), golden: "tests/golden/01_first_sketch.png", output: s.runs[0].output };

  // 2. the sketches that follow the active editor: each opened file runs by itself.
  const cases = [
    { file: "booleans.py", id: "booleans", golden: "tests/golden/gallery/paths-05_booleans.png" },
    { file: "bounce.py", id: "bounce", golden: "tests/golden/07_bounce.png" },
    { file: "text.py", id: "text", golden: "tests/golden/gallery/text-01_text.png" },
    { file: "photo.py", id: "photo", picture: "data/photo.png" },
    { file: "visualiser.py", id: "visualiser", sound: true },
    { file: "tune.py", id: "tune", sound: true },
    { file: "listen.py", id: "listen", microphone: true },
    { file: "oops.py", id: "oops", error: true },
    { file: "uses_helper.py", id: "uses_helper", helper: true },
  ];
  for (const c of cases) try {
    const before = (await state(frame)).runs.length;
    const tOpen = Date.now();
    await openFile(c.file);
    s = await waitFor(frame, (x) => x.runs.length > before && x.runs.at(-1).filename === c.file && (x.runs.at(-1).frames >= 30 || ["ended", "error"].includes(x.runs.at(-1).finished)), `${c.file} running`);
    const index = s.runs.length - 1;
    const run = s.runs[index];
    const entry = { file: c.file, openToFirstFrameMs: run.firstFrameAt ? run.firstFrameAt - tOpen : null, frames: run.frames, finished: run.finished, output: run.output };
    if (c.golden || c.picture) {
      const scriptFrame = run.frames >= 30 ? 30 : 1;
      Object.assign(entry, await saveFrame(frame, c.id, index, scriptFrame), { golden: c.golden, picture: c.picture });
    }
    if (c.sound) {
      await sleep(1500);
      Object.assign(entry, await frame.evaluate((i) => ({ sounds: window.fungroundPreview.runs[i].sounds, audio: window.fungroundPreview.audioState?.() ?? null }), index));
    }
    if (c.microphone) { await sleep(3000); entry.output = (await state(frame)).runs[index].output; entry.audio = await frame.evaluate(() => window.fungroundPreview.audioState?.() ?? null); }
    if (c.error) {
      await sleep(1500);
      entry.markers = await page.evaluate(() => document.querySelectorAll(".monaco-editor .squiggly-error").length);
      entry.problems = await problemLines();
    }
    if (c.helper) Object.assign(entry, await helperEdit(frame));
    report.cases[c.id] = entry;
    log(`${c.file}: frames ${run.frames}, finished ${run.finished}, first frame ${entry.openToFirstFrameMs} ms after opening`);
  } catch (error) {
    const last = (await state(frame)).runs.at(-1);
    report.cases[c.id] = { file: c.file, failed: String(error.message ?? error), lastRun: last };
    report.errors.push(`${c.file}: ${error.message ?? error}`);
    log(`${c.file}: FAILED ${error.message ?? error}; last run ${JSON.stringify(last).slice(0, 600)}`);
  }

  // 3. live update: type in first_sketch.py and measure from the last key to the new run's first frame; then save.
  await openFile("first_sketch.py");
  await waitFor(frame, (x) => x.runs.at(-1).filename === "first_sketch.py" && x.runs.at(-1).frames >= 3, "first_sketch again");
  await page.keyboard.press("Control+G");
  await sleep(300);
  await page.keyboard.type("9");
  await page.keyboard.press("Enter");
  await page.keyboard.press("End");
  for (let i = 0; i < LIVE_EDITS; i++) {
    const before = (await state(frame)).runs.length;
    await page.keyboard.type(`  # edit ${i}`, { delay: 30 });
    const lastKey = await page.evaluate(() => Date.now());
    s = await waitFor(frame, (x) => x.runs.length > before && x.runs.at(-1).firstFrameAt, `the run after edit ${i}`, 30000);
    const run = s.runs.at(-1);
    report.live.push({ edit: i, lastKeyToFirstFrameMs: run.firstFrameAt - lastKey, sentToFirstFrameMs: run.firstFrameAt - run.sentAt, runs: s.runs.length - before });
    log(`edit ${i}: last key to first frame ${run.firstFrameAt - lastKey} ms (debounce ${400} ms included)`);
    await sleep(1500);
    for (let k = 0; k < 9 + String(i).length; k++) await page.keyboard.press("Backspace");
    await sleep(1500);
  }
  const beforeSave = (await state(frame)).runs.length;
  await page.keyboard.type("  # saved", { delay: 30 });
  await page.keyboard.press("Control+S");
  const saveAt = await page.evaluate(() => Date.now());
  s = await waitFor(frame, (x) => x.runs.length > beforeSave && x.runs.at(-1).firstFrameAt && x.runs.at(-1).firstFrameAt > saveAt - 50, "the run after saving", 30000);
  report.save = { saveToFirstFrameMs: s.runs.at(-1).firstFrameAt - saveAt, savedFile: readFileSync(join(workspace, "first_sketch.py"), "utf8").includes("# saved") };
  log(`save: to first frame ${report.save.saveToFirstFrameMs} ms; file on disk changed: ${report.save.savedFile}`);

  // 4. memory, as Chromium counts it for the panel's page (both workers included only if the browser reports them).
  report.memory = await frame.evaluate(() => performance.memory ? { usedJSHeapSize: performance.memory.usedJSHeapSize } : null);
  await page.screenshot({ path: join(OUT, "workbench.png") });
} catch (error) {
  report.errors.push(String(error.stack ?? error));
  console.error(error);
  await page.screenshot({ path: join(OUT, "failure.png") }).catch(() => {});
} finally {
  report.requests = requests;
  report.siteBytes = siteBytes;
  report.console = consoleLines.slice(0, 200);
  writeFileSync(join(OUT, "report.json"), JSON.stringify(report, null, 1));
  await browser.close();
  server.kill();
  site?.close();
  console.log(`report: ${join(OUT, "report.json")}`);
  process.exit(report.errors.length ? 1 : 0);
}
