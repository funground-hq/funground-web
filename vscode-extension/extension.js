// The funground extension for VS Code for the web (github.dev, vscode.dev) and the desktop (story S-158).
//
// "funground: Run" opens a preview panel beside the editor and runs the active Python file in it with the funground
// browser runner (../runner, copied into media/runner by build.py). The panel follows the active Python editor, runs the
// sketch again a moment after typing stops and at once on save, and shows print() and errors; an error's line is also
// marked in the editor. What the sketch reads from beside it is read through vscode.workspace.fs and handed to the run:
// the files in the data/ folder (f.load_image("data/photo.png")) and the other .py files in its folder (import helpers).
// In github.dev the files are the repository's.
//
// It also suggests funground's names, colours and option words, and shows hints (see "Suggestions" below).
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
      if (panel && editor && isRunnable(editor.document) && editor.document !== current) {
        current = editor.document;
        schedule(0, "editor");
      }
    }),
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (panel && feedsRun(e.document) && e.contentChanges.length && setting("autoRun")) schedule(setting("autoRunDelay"), "edit");
    }),
    vscode.workspace.onDidSaveTextDocument((document) => {
      if (panel && feedsRun(document)) schedule(0, "save");
    }),
  );  return startSuggestions(context);                // a promise: activation ends when the suggestions are in place (or skipped)
}

function deactivate() {}

const setting = (name) => vscode.workspace.getConfiguration("funground").get(name);
const isSketch = (document) => document.languageId === "python";

// The panel follows the active editor only to a sketch it can run: a file with a top-level run() or show() call
// (`f.run()` for a sketch that animates, `f.show()` for a script that draws once). A helper such as palette.py has
// neither, so opening it to change a colour leaves the sketch that uses it in the panel. The Run command (Ctrl+Enter)
// still runs whatever Python file is open, for a script that only saves a file.
const RUNNABLE = /^(?:[A-Za-z_]\w*\.)?(?:run|show)\s*\(/m;
const isRunnable = (document) => isSketch(document) && RUNNABLE.test(document.getText());

// A change to the sketch in the panel, or to a .py file beside it (a helper it may import), runs the sketch again.
function feedsRun(document) {
  if (!current) return false;
  if (document === current) return true;
  const folder = (uri) => uri.path.slice(0, uri.path.lastIndexOf("/"));
  return isSketch(document) && document.uri.scheme === current.uri.scheme && folder(document.uri) === folder(current.uri);
}

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

// ---- Suggestions (story S-205, from spike 13, route B)
//
// In github.dev and vscode.dev there is no Python environment, and Pylance reads one file only, so nothing there knows what
// funground offers. This extension supplies it from media/completions.json: funground's own list of its names, signatures,
// summaries, colours and option words, copied in by build.py from the funground the runtime runs (so the two always match).
// What it offers: names after `f.` (and bare, after `from funground import *`); the colours inside `f.COLORS.` and the
// words inside `f.CONSTANTS.` and `f.CONSTANTS.GROUP.`; colour names inside the quotes of a colour parameter
// (f.fill("...")) and option words inside the quotes of an option parameter (f.blend_mode("...")); hover; signature help.
// This is one file on purpose: VS Code for the web loads an extension's "browser" file alone, so it cannot require a sibling.

const DOCS = "https://funground-hq.github.io/";                 // an entry's `url` is "reference/API.md#fn-circle"
const KIND = { function: "Function", class: "Class", value: "Variable", namespace: "Module" };
const SCAN_LINES = 30;                                           // how far back a call can start, for signature help and quotes

async function startSuggestions(context) {
  let data;
  try {
    const bytes = await vscode.workspace.fs.readFile(vscode.Uri.joinPath(context.extensionUri, "media", "completions.json"));
    data = JSON.parse(new TextDecoder().decode(bytes));
  } catch (error) {
    output.appendLine(`suggestions not available: ${error.message}`);
    return;
  }
  registerSuggestions(context, data);
  output.appendLine(`suggestions for funground ${data.version}: ${data.names.length} names, ${data.colors.length} colours`);
}

function registerSuggestions(context, data) {
  const s = makeSuggestions(data);
  const enabled = () => setting("suggestions") !== false;
  const python = { language: "python" };
  context.subscriptions.push(
    vscode.languages.registerCompletionItemProvider(python, { provideCompletionItems: (d, p, t, c) => (enabled() ? s.complete(d, p, c) : undefined) }, ".", '"', "'"),
    vscode.languages.registerHoverProvider(python, { provideHover: (d, p) => (enabled() ? s.hover(d, p) : undefined) }),
    vscode.languages.registerSignatureHelpProvider(python, { provideSignatureHelp: (d, p) => (enabled() ? s.signature(d, p) : undefined) }, { triggerCharacters: ["(", ","], retriggerCharacters: [","] }),
  );
}

// The logic, apart from registering it, so a test can call it with a stand-in for the editor.
function makeSuggestions(data) {
  const byName = new Map(data.names.map((n) => [n.name, n]));
  const colorParams = new Map();                                  // "fill" -> Set("color")
  for (const { function: fn, parameter } of data.color_params) {
    if (!colorParams.has(fn)) colorParams.set(fn, new Set());
    colorParams.get(fn).add(parameter);
  }
  const markdown = (text) => text.replace(/``([^`]+)``/g, "`$1`");                         // the summaries use reST double backticks
  const link = (n) => `[Reference](${DOCS}${n.url.replace(".md#", "/#")})`;
  const kindOf = (n) => vscode.CompletionItemKind[KIND[n.kind] ?? "Function"];
  const imports = new Map();                                      // document uri -> {version, alias, star}

  // How this file imports funground: `import funground as f` gives "f"; `from funground import *` allows bare names.
  function importsOf(document) {
    const key = document.uri?.toString() ?? "";
    const known = imports.get(key);
    if (known && known.version === document.version) return known;
    const text = document.getText();
    const alias = /^\s*import\s+funground\s+as\s+(\w+)/m.exec(text)?.[1] ?? (/^\s*import\s+funground\s*$/m.test(text) ? "funground" : null);
    const found = { version: document.version, alias, star: /^\s*from\s+funground\s+import\s+\*/m.test(text) };
    imports.set(key, found);
    return found;
  }

  // The code before the cursor (a few lines of it), read once for strings, comments and open calls.
  function scanBefore(document, position) {
    const from = new vscode.Position(Math.max(0, position.line - SCAN_LINES), 0);
    return scan(document.getText(new vscode.Range(from, position)));
  }

  // The funground entry for a call's name, or null: `f.circle(` with the alias, or `circle(` after a star import.
  function entryOf(chain, { alias, star }) {
    if (!chain) return null;
    const name = chain.length === 2 && chain[0] === alias ? chain[1] : chain.length === 1 && star ? chain[0] : null;
    return name ? byName.get(name) ?? null : null;
  }

  const colorItem = (name, value, hex) => {
    const item = new vscode.CompletionItem(name, vscode.CompletionItemKind.Color);
    item.detail = value === undefined ? hex : `"${value}"  ${hex}`;
    item.documentation = hex;                                     // a colour string as the documentation is what shows the swatch
    return item;
  };

  // The meaning of an option word, from the functions that take the group.
  const meaningOf = (word, functions) => {
    for (const fn of functions) {
      for (const options of Object.values(byName.get(fn)?.options ?? {})) {
        const found = options.find((o) => o.word === word);
        if (found) return found.meaning;
      }
    }
    return undefined;
  };

  function complete(document, position, context) {
    const here = scanBefore(document, position);
    if (here.comment) return undefined;
    const line = document.lineAt(position.line).text;
    const before = line.slice(0, position.character);
    const imported = importsOf(document);
    if (here.string) return completeInString(here, imported);

    const dotted = /([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.(\w*)$/.exec(before);
    if (dotted) return completeAfterDot(dotted[1].split("."), imported, line.slice(position.character));
    const bare = /(?:^|[^\w.])(\w*)$/.exec(before);
    const typed = bare?.[1] ?? "";
    const invoked = context?.triggerKind === vscode.CompletionTriggerKind?.Invoke;
    if (!imported.star || !bare || (!typed && !invoked) || /\b(?:def|class|import|from)\s+\w*$/.test(before)) return undefined;
    return data.names.filter((n) => n.star).map((n) => nameItem(n, line.slice(position.character)));
  }

  function nameItem(n, after) {
    const item = new vscode.CompletionItem(n.name, kindOf(n));
    item.detail = n.kind === "function" || n.kind === "class" ? n.signature : n.kind === "value" ? `${n.name}: ${n.detail}` : n.detail;
    item.documentation = new vscode.MarkdownString(`${markdown(n.summary)}\n\n${link(n)}`);
    if (n.kind === "function" && !after.startsWith("(")) {
      item.insertText = new vscode.SnippetString(`${n.name}($0)`);
      item.command = { command: "editor.action.triggerParameterHints", title: "Parameter hints" };
    }
    return item;
  }

  function completeAfterDot(chain, { alias, star }, after) {
    let rest;
    if (alias && chain[0] === alias) rest = chain.slice(1);
    else if (star && (chain[0] === "COLORS" || chain[0] === "CONSTANTS")) rest = chain;
    else return undefined;
    if (rest.length === 0) return data.names.map((n) => nameItem(n, after));
    const space = byName.get(rest[0]);
    if (space?.kind !== "namespace") return undefined;
    if (rest[0] === "COLORS" && rest.length === 1) return space.members.map((m) => colorItem(m.name, m.value, m.hex));
    if (rest[0] === "CONSTANTS" && rest.length === 1) {
      return space.members.map((g) => {
        const item = new vscode.CompletionItem(g.name, vscode.CompletionItemKind.Enum);
        item.detail = `for ${g.used_by.join(", ")}`;
        return item;
      });
    }
    if (rest[0] === "CONSTANTS" && rest.length === 2) {
      const group = space.members.find((g) => g.name === rest[1]);
      return group?.members.map((m) => {
        const item = new vscode.CompletionItem(m.name, vscode.CompletionItemKind.EnumMember);
        item.detail = `"${m.value}"`;
        const meaning = meaningOf(m.value, group.used_by);
        if (meaning) item.documentation = new vscode.MarkdownString(markdown(meaning));
        return item;
      });
    }
    return undefined;
  }

  // Inside the quotes of an argument: colour names for a colour parameter, option words for an option parameter.
  function completeInString(here, imported) {
    const frame = here.stack[here.stack.length - 1];
    const entry = frame?.open === "(" ? entryOf(frame.callee, imported) : null;
    if (!entry) return undefined;
    const param = parameterAt(entry, frame, here.text.slice(frame.argStart, here.string.start));
    const items = [];
    if (colorParams.get(entry.name)?.has(param)) for (const c of data.colors) items.push(colorItem(c.name, undefined, c.hex));
    for (const o of entry.options?.[param] ?? []) {
      const item = new vscode.CompletionItem(o.word, vscode.CompletionItemKind.EnumMember);
      item.documentation = new vscode.MarkdownString(markdown(o.meaning));
      items.push(item);
    }
    return items.length ? items : undefined;
  }

  const bareName = (parameter) => parameter.replace(/^\*+/, "").split("=")[0].trim();

  // The parameter an argument belongs to: the name before `=`, else its place in the call.
  function parameterAt(entry, frame, argText) {
    const keyword = /^\s*([A-Za-z_]\w*)\s*=\s*$/.exec(argText);
    return keyword ? keyword[1] : parameters(entry).map(bareName)[frame.commas];
  }

  function hover(document, position) {
    const range = document.getWordRangeAtPosition(position);
    if (!range) return undefined;
    const imported = importsOf(document);
    const line = document.lineAt(position.line).text;
    const lead = line.slice(0, range.start.character);
    const qualified = imported.alias && lead.endsWith(`${imported.alias}.`);
    const bare = imported.star && !/\.\s*$/.test(lead);
    const n = byName.get(document.getText(range));
    if (!n || !(qualified || bare)) return undefined;
    const text = new vscode.MarkdownString().appendCodeblock(n.kind === "value" ? `${n.name}: ${n.detail}` : n.signature, "python");
    text.appendMarkdown(`\n${markdown(n.summary)}\n\n${link(n)}`);
    return new vscode.Hover(text, range);
  }

  function signature(document, position) {
    const here = scanBefore(document, position);
    if (here.comment || here.string) return undefined;
    const frame = here.stack[here.stack.length - 1];
    const entry = frame?.open === "(" ? entryOf(frame.callee, importsOf(document)) : null;
    if (!entry || (entry.kind !== "function" && entry.kind !== "class")) return undefined;
    const info = new vscode.SignatureInformation(entry.signature, markdown(entry.summary));
    const names = parameters(entry);
    info.parameters = names.map((p) => new vscode.ParameterInformation(p));
    const keyword = /^\s*([A-Za-z_]\w*)\s*=/.exec(here.text.slice(frame.argStart));
    const named = keyword ? names.findIndex((p) => bareName(p) === keyword[1]) : -1;
    const help = new vscode.SignatureHelp();
    help.signatures = [info];
    help.activeSignature = 0;
    help.activeParameter = Math.max(0, named >= 0 ? named : Math.min(frame.commas, names.length - 1));
    return help;
  }

  return { complete, hover, signature };
}

// The parameters of an entry's signature, "circle(x, y, diameter)" -> ["x", "y", "diameter"], splitting only at top-level commas.
function parameters(entry) {
  const inner = entry.signature.slice(entry.signature.indexOf("(") + 1, entry.signature.lastIndexOf(")"));
  const out = [];
  let depth = 0;
  let from = 0;
  for (let i = 0; i < inner.length; i++) {
    if ("([{".includes(inner[i])) depth++;
    else if (")]}".includes(inner[i])) depth--;
    else if (inner[i] === "," && depth === 0) { out.push(inner.slice(from, i).trim()); from = i + 1; }
  }
  out.push(inner.slice(from).trim());
  return out.filter(Boolean);
}

// Read Python text from its start to the cursor. Returns the open brackets (innermost last, each with the call's dotted name,
// how many commas it has seen, and where its current argument began), and whether the end is inside a string or a comment.
function scan(text) {
  const stack = [];
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === "#") {
      const end = text.indexOf("\n", i);
      if (end < 0) return { stack, text, comment: true };
      i = end + 1;
    } else if (c === '"' || c === "'") {
      const quote = text.startsWith(c.repeat(3), i) ? c.repeat(3) : c;
      let j = i + quote.length;
      for (; j < text.length; j++) {
        if (text[j] === "\\") j++;
        else if (text.startsWith(quote, j) || (quote.length === 1 && text[j] === "\n")) break;
      }
      if (j >= text.length) return { stack, text, string: { quote, start: i } };
      i = text[j] === "\n" ? j : j + quote.length;
    } else {
      if (c === "(" || c === "[" || c === "{") stack.push({ open: c, callee: c === "(" ? calleeBefore(text, i) : null, commas: 0, argStart: i + 1 });
      else if (c === ")" || c === "]" || c === "}") stack.pop();
      else if (c === "," && stack.length) { stack[stack.length - 1].commas++; stack[stack.length - 1].argStart = i + 1; }
      i++;
    }
  }
  return { stack, text };
}

// The dotted name just before a "(" as a list (["f", "circle"]), or null after `def` or `class`.
function calleeBefore(text, at) {
  const head = text.slice(Math.max(0, at - 200), at);
  const m = /([A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*)\s*$/.exec(head);
  if (!m || /\b(?:def|class)\s+$/.test(head.slice(0, m.index))) return null;
  return m[1].split(".").map((part) => part.trim());
}

module.exports = { activate, deactivate, makeSuggestions };
