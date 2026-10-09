// The funground extension for VS Code for the web (github.dev, vscode.dev) and the desktop (story S-158).
//
// "funground: Run" opens a preview panel beside the editor and runs the active Python file in it with the funground
// browser runner (../runner, copied into media/runner by build.py). The panel follows the active Python editor, runs the
// sketch again a moment after typing stops and at once on save, and shows print() and errors; an error's line is also
// marked in the editor. What the sketch reads from beside it is read through vscode.workspace.fs and handed to the run:
// the files in the data/ folder (f.load_image("data/photo.png")) and the other .py files in its folder (import helpers).
// In github.dev the files are the repository's.
//
// Safety: the sketch runs only inside the webview, which has its own origin and a strict Content Security Policy (one
// exception, D-080, at previewHtml); this file never runs sketch code. A "browser" entry point: no Node APIs.

const vscode = require("vscode");

const RUNTIME_SITE = "https://funground-hq.github.io/runtime/";   // D-081: the runtime lives in a folder per version, below this
const DATA_LIMIT = 32 * 1024 * 1024;            // bytes of data/ and helper files sent with a run; more is refused with a message

let panel = null;                               // the one preview panel
let ready = false;                              // the webview's runner has loaded Python
let current = null;                             // the document the preview shows
let timer = null;
let sent = null;                                // what the last run was made from: {document, version, helpers}, to skip a repeat
let diagnostics;
let output;

function activate(context) {
  diagnostics = vscode.languages.createDiagnosticCollection("funground");
  output = vscode.window.createOutputChannel("funground");
  context.subscriptions.push(
    diagnostics, output,
    vscode.commands.registerCommand("funground.run", () => runActive(context)),
    vscode.commands.registerCommand("funground.stop", () => panel?.webview.postMessage({ type: "stop" })),
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (panel && editor && isSketch(editor.document) && editor.document !== current) {
        current = editor.document;
        schedule(0, "editor");
      }
    }),
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (panel && e.document === current && e.contentChanges.length && setting("autoRun")) schedule(setting("autoRunDelay"), "edit");
    }),
    vscode.workspace.onDidSaveTextDocument((document) => {
      if (panel && document === current) schedule(0, "save");
    }),
  );
}

function deactivate() {}

const setting = (name) => vscode.workspace.getConfiguration("funground").get(name);
const isSketch = (document) => document.languageId === "python";

function runActive(context) {
  const editor = vscode.window.activeTextEditor;
  const document = editor && isSketch(editor.document) ? editor.document : current;
  if (!document) {
    vscode.window.showInformationMessage("Open a Python sketch first, then run it.");
    return;
  }
  current = document;
  if (!panel) openPanel(context);
  else panel.reveal(vscode.ViewColumn.Beside, true);
  schedule(0, "command");
}

async function openPanel(context) {
  const created = vscode.window.createWebviewPanel("funground.preview", "funground", { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true }, {
    enableScripts: true,
    retainContextWhenHidden: true,             // keeps Python loaded while the panel is behind another tab
    localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, "media")],
  });
  panel = created;
  ready = false;
  created.iconPath = vscode.Uri.joinPath(context.extensionUri, "media", "icon.svg");
  created.onDidDispose(() => { if (panel === created) { panel = null; ready = false; sent = null; diagnostics.clear(); } });
  created.webview.onDidReceiveMessage(received);
  const html = previewHtml(created.webview, context.extensionUri, await runtimeSite(context));
  if (panel === created) created.webview.html = html;        // not if the panel was closed while we looked for the runtime
}

// Run the current sketch after `delay` ms, unless asked again before then. `why` is "command", "save", "edit", "editor"
// (another sketch became active) or "ready"; an edit or a switch that would run exactly what is running is skipped.
function schedule(delay, why) {
  clearTimeout(timer);
  timer = setTimeout(() => sendRun(why), delay);
}

async function sendRun(why) {
  if (!panel || !ready || !current) return;
  const document = current;
  const budget = makeBudget();
  const helpers = await helperSources(document.uri, budget).catch(reportUnsent);
  const same = sent && sent.document === document && sent.version === document.version && sameTexts(sent.helpers, helpers);
  if (same && (why === "edit" || why === "editor")) return;
  sent = { document, version: document.version, helpers };
  diagnostics.delete(document.uri);
  const filename = fileName(document);
  const files = { ...(await dataFiles(document.uri, budget).catch(reportUnsent)), ...encodeTexts(helpers) };
  panel.title = `funground: ${filename}`;
  panel.webview.postMessage({ type: "run", source: document.getText(), filename, files, seed: setting("randomSeed") ?? undefined, why, at: Date.now() });
}

const fileName = (document) => document.uri.path.split("/").pop();

function reportUnsent(error) {
  output.appendLine(`files beside the sketch not sent: ${error.message}`);
  return {};
}

// A count of the bytes read for one run, shared by the data and the helper files.
function makeBudget() {
  let total = 0;
  return (bytes) => {
    total += bytes;
    if (total > DATA_LIMIT) throw new Error(`the files beside the sketch hold more than ${DATA_LIMIT >> 20} MB`);
  };
}

// Every file under data/ beside the sketch, as {"data/photo.png": Uint8Array}. github.dev reads them from the repository.
async function dataFiles(sketchUri, budget) {
  const files = {};
  async function walk(uri, prefix) {
    let entries;
    try { entries = await vscode.workspace.fs.readDirectory(uri); } catch { return; }      // no data folder
    for (const [name, type] of entries) {
      const child = vscode.Uri.joinPath(uri, name);
      if (type & vscode.FileType.Directory) await walk(child, `${prefix}${name}/`);
      else if (type & vscode.FileType.File) {
        const bytes = await vscode.workspace.fs.readFile(child);
        budget(bytes.byteLength);
        files[`${prefix}${name}`] = bytes;
      }
    }
  }
  await walk(vscode.Uri.joinPath(sketchUri, "..", "data"), "data/");
  return files;
}

// The other .py files in the sketch's folder (not its subfolders), as {"helpers.py": "text"}, so that `import helpers` works.
// A file that is open in an editor is sent as the editor has it, saved or not.
async function helperSources(sketchUri, budget) {
  const folder = vscode.Uri.joinPath(sketchUri, "..");
  const sources = {};
  for (const [name, type] of await vscode.workspace.fs.readDirectory(folder)) {
    const uri = vscode.Uri.joinPath(folder, name);
    if (!(type & vscode.FileType.File) || !name.endsWith(".py") || uri.toString() === sketchUri.toString()) continue;
    sources[name] = await readText(uri);
    budget(sources[name].length);
  }
  return sources;
}

async function readText(uri) {
  const open = vscode.workspace.textDocuments.find((document) => document.uri.toString() === uri.toString());
  return open ? open.getText() : new TextDecoder().decode(await vscode.workspace.fs.readFile(uri));
}

function encodeTexts(texts) {
  return Object.fromEntries(Object.entries(texts).map(([name, text]) => [name, new TextEncoder().encode(text)]));
}

function sameTexts(a, b) {
  const names = Object.keys(a);
  return names.length === Object.keys(b).length && names.every((name) => a[name] === b[name]);
}

function received(message) {
  switch (message.type) {
    case "ready":
      ready = true;
      output.appendLine(`Python ready in ${message.loadMs} ms (${message.runtime})`);
      schedule(0, "ready");
      break;
    case "failed":
      output.appendLine(message.message);
      vscode.window.showErrorMessage(`funground could not start Python: ${message.message}`);
      break;
    case "error":
      markError(message.text);
      break;
    case "log":
      output.appendLine(message.text);
      break;
  }
}

// An error's traceback names the sketch and a line: mark that line in the document the run was made from, which is not
// always the one now showing (the learner may have moved to another file while the run was starting).
function markError(text) {
  if (!sent) return;
  const document = sent.document;
  const filename = fileName(document);
  const lines = [...text.matchAll(/File "([^"]+)", line (\d+)/g)].filter((m) => m[1] === filename);
  if (!lines.length) return;
  const line = Math.max(0, Number(lines[lines.length - 1][2]) - 1);
  const last = text.trim().split("\n").pop();
  const range = document.lineAt(Math.min(line, document.lineCount - 1)).range;
  diagnostics.set(document.uri, [new vscode.Diagnostic(range, last, vscode.DiagnosticSeverity.Error)]);
}

// Where Python and funground load from, in this order (D-081):
//   1. the funground.runtimeUrl setting, when it is not empty;
//   2. the copy inside the extension, when it has one (a build made with `build.py --runtime bundled`): returns null;
//   3. the website's folder for the runtime version this extension was made for (package.json, "fungroundRuntime").
// A site is returned as a URL that ends in "/" and holds pyodide/ and runtime/.
async function runtimeSite(context) {
  const chosen = setting("runtimeUrl").trim();
  if (chosen) return new URL(chosen.endsWith("/") ? chosen : chosen + "/");
  if (await hasBundledRuntime(context)) return null;
  return new URL(`${context.extension.packageJSON.fungroundRuntime}/`, RUNTIME_SITE);
}

// Does the extension hold the runtime? The manifest is read, not just looked for: in VS Code for the web, workspace.fs.stat
// answers "yes" for any path under an extension's own (http) location, found by the tests when the runtime was missing.
async function hasBundledRuntime(context) {
  const manifest = vscode.Uri.joinPath(context.extensionUri, "media", "runner", "runtime", "manifest.json");
  try {
    JSON.parse(new TextDecoder().decode(await vscode.workspace.fs.readFile(manifest)));
    return true;
  } catch {
    return false;
  }
}

function previewHtml(webview, extensionUri, site) {
  const media = (...path) => webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, "media", ...path));
  const nonce = [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, "0")).join("");
  const sources = [webview.cspSource, site?.origin].filter(Boolean).join(" ");
  // What the panel may do. Scripts: this page's one inline module (by nonce), the runner and Python from the extension (or
  // the runtime site); WebAssembly compiled from bytes ('wasm-unsafe-eval'). Workers only from blob: (the runner starts
  // its worker from one). Network: the extension's files and the runtime site, nothing else.
  // 'unsafe-eval' is D-080's one exception, in this panel only: pygame-ce's WebAssembly side modules are linked with eval(),
  // and funground draws pictures with pygame-ce (f.load_image). The panel already runs the learner's own Python, in its own
  // origin, with no network but ours.
  const csp = [
    "default-src 'none'",
    `script-src 'nonce-${nonce}' ${sources} 'wasm-unsafe-eval' 'unsafe-eval'`,
    "worker-src blob:",
    `connect-src ${sources}`,
    `style-src ${webview.cspSource}`,
    `img-src ${webview.cspSource} data: blob:`,
  ].join("; ");
  const folder = (...path) => `${media(...path)}/`;                          // a folder's URL, ending in "/"
  const config = {
    runner: folder("runner"),
    pyodide: site ? new URL("pyodide/", site).href : folder("runner", "pyodide"),
    runtime: site ? new URL("runtime/", site).href : folder("runner", "runtime"),
    where: site ? site.href : "inside the extension",
  };
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${media("preview.css")}">
<title>funground</title>
</head>
<body>
<div id="bar"><button id="run" title="Run (Ctrl+Enter)">Run</button><button id="stop" title="Stop">Stop</button><span id="status">Loading Python…</span></div>
<div id="stage"><canvas id="canvas" width="640" height="400"></canvas></div>
<pre id="output" aria-live="polite"></pre>
<script type="module" nonce="${nonce}">
import { start } from "${media("preview.js")}";
start(${JSON.stringify(config)});
</script>
</body>
</html>`;
}

module.exports = { activate, deactivate };
