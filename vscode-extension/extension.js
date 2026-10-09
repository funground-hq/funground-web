// The funground extension for VS Code for the web (github.dev, vscode.dev) and the desktop (story S-156, spike).
//
// "funground: Run" opens a preview panel beside the editor and runs the active Python file in it with the funground
// browser runner (../runner, copied into media/runner by build.py). The panel follows the active Python editor, runs the
// sketch again a moment after typing stops and at once on save, and shows print() and errors; an error's line is also
// marked in the editor. Files in the data/ folder beside the sketch are read through vscode.workspace.fs and handed to
// the run, so f.load_image("data/photo.png") works in github.dev, where the files are the repository's.
//
// Safety: the sketch runs only inside the webview, which has its own origin and a strict Content Security Policy; this
// file never runs sketch code. A "browser" entry point: no Node APIs.

const vscode = require("vscode");

const DATA_LIMIT = 32 * 1024 * 1024;            // bytes of data/ files sent with a run; more is refused with a message

let panel = null;                               // the one preview panel
let ready = false;                              // the webview's runner has loaded Python
let current = null;                             // the document the preview shows
let timer = null;
let sent = null;                                // what the last run was made from: {uri, version}, to skip a repeat
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

function openPanel(context) {
  panel = vscode.window.createWebviewPanel("funground.preview", "funground", { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true }, {
    enableScripts: true,
    retainContextWhenHidden: true,             // keeps Python loaded while the panel is behind another tab
    localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, "media")],
  });
  ready = false;
  panel.iconPath = vscode.Uri.joinPath(context.extensionUri, "media", "icon.svg");
  panel.webview.html = previewHtml(panel.webview, context.extensionUri);
  panel.webview.onDidReceiveMessage(received);
  panel.onDidDispose(() => { panel = null; ready = false; sent = null; diagnostics.clear(); });
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
  const same = sent && sent.uri === document.uri.toString() && sent.version === document.version;
  if (same && (why === "edit" || why === "editor")) return;
  sent = { uri: document.uri.toString(), version: document.version };
  diagnostics.delete(document.uri);
  const filename = document.uri.path.split("/").pop();
  const files = await dataFiles(document.uri);
  panel.title = `funground: ${filename}`;
  panel.webview.postMessage({ type: "run", source: document.getText(), filename, files, seed: setting("randomSeed") ?? undefined, why, at: Date.now() });
}

// Every file under data/ beside the sketch, as {"data/photo.png": Uint8Array}. github.dev reads them from the repository.
async function dataFiles(sketchUri) {
  const folder = vscode.Uri.joinPath(sketchUri, "..", "data");
  const files = {};
  let total = 0;
  async function walk(uri, prefix) {
    let entries;
    try { entries = await vscode.workspace.fs.readDirectory(uri); } catch { return; }      // no data folder
    for (const [name, type] of entries) {
      const child = vscode.Uri.joinPath(uri, name);
      if (type & vscode.FileType.Directory) await walk(child, `${prefix}${name}/`);
      else if (type & vscode.FileType.File) {
        const bytes = await vscode.workspace.fs.readFile(child);
        total += bytes.byteLength;
        if (total > DATA_LIMIT) throw new Error(`the data folder holds more than ${DATA_LIMIT >> 20} MB`);
        files[`${prefix}${name}`] = bytes;
      }
    }
  }
  try {
    await walk(folder, "data/");
  } catch (error) {
    output.appendLine(`data/ not sent: ${error.message}`);
    return {};
  }
  return files;
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

// An error's traceback names the sketch and a line: mark that line in the editor.
function markError(text) {
  if (!current) return;
  const filename = current.uri.path.split("/").pop();
  const lines = [...text.matchAll(/File "([^"]+)", line (\d+)/g)].filter((m) => m[1] === filename);
  if (!lines.length) return;
  const line = Math.max(0, Number(lines[lines.length - 1][2]) - 1);
  const last = text.trim().split("\n").pop();
  const range = current.lineAt(Math.min(line, current.lineCount - 1)).range;
  diagnostics.set(current.uri, [new vscode.Diagnostic(range, last, vscode.DiagnosticSeverity.Error)]);
}

function previewHtml(webview, extensionUri) {
  const media = (...path) => webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, "media", ...path));
  const runtimeSite = setting("runtimeUrl").trim();
  const site = runtimeSite ? new URL(runtimeSite.endsWith("/") ? runtimeSite : runtimeSite + "/") : null;
  const nonce = [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, "0")).join("");
  const sources = [webview.cspSource, site?.origin].filter(Boolean).join(" ");
  // What the panel may do. Scripts: this page's one inline module (by nonce), the runner and Python from the extension (or
  // the runtime site); WebAssembly compiled from bytes ('wasm-unsafe-eval', not 'unsafe-eval'). Workers only from blob:
  // (the runner starts its worker from one). Network: the extension's files and the runtime site, nothing else.
  const csp = [
    "default-src 'none'",
    `script-src 'nonce-${nonce}' ${sources} 'wasm-unsafe-eval'`,
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
