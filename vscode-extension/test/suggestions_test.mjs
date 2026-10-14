// Test of the extension's suggestions (story S-205) against a stand-in for the VS Code API: no editor, no browser.
//
//   node suggestions_test.mjs
//
// Loads ../extension.js with a fake "vscode" module, runs activate(), and calls the registered completion, hover and
// signature providers on small fake documents. The data is ../media/completions.json (build.py copies it there). This
// proves the logic; the real editor is the maintainer's check (github.dev, story S-205's acceptance).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXTENSION = resolve(HERE, "..");
const require = createRequire(import.meta.url);
const Module = require("node:module");

// ---- the stand-in

const registered = [];
let versions = 0;                                  // every fake document is a new edit of the same file
const settings = {};
class Position { constructor(line, character) { this.line = line; this.character = character; } }
class Range { constructor(start, end) { this.start = start; this.end = end; } }
class MarkdownString {
  constructor(value = "") { this.value = value; }
  appendCodeblock(code, language) { this.value += `\n\`\`\`${language}\n${code}\n\`\`\`\n`; return this; }
  appendMarkdown(text) { this.value += text; return this; }
}
const disposable = () => ({ dispose() {} });
const vscode = {
  Uri: { joinPath: (base, ...parts) => join(base, ...parts) },
  workspace: {
    fs: { readFile: async (path) => readFileSync(path) },
    getConfiguration: () => ({ get: (name) => settings[name] }),
    onDidChangeTextDocument: disposable, onDidSaveTextDocument: disposable,
  },
  window: { createOutputChannel: () => ({ appendLine() {}, dispose() {} }), onDidChangeActiveTextEditor: disposable },
  commands: { registerCommand: disposable },
  languages: {
    createDiagnosticCollection: () => ({ dispose() {} }),
    registerCompletionItemProvider: (selector, provider, ...triggers) => (registered.push({ kind: "completion", provider, triggers, selector }), disposable()),
    registerHoverProvider: (selector, provider) => (registered.push({ kind: "hover", provider, selector }), disposable()),
    registerSignatureHelpProvider: (selector, provider, metadata) => (registered.push({ kind: "signature", provider, metadata, selector }), disposable()),
  },
  CompletionItem: class { constructor(label, kind) { this.label = label; this.kind = kind; } },
  CompletionItemKind: new Proxy({}, { get: (_, name) => name }),
  CompletionTriggerKind: { Invoke: 0, TriggerCharacter: 1 },
  SnippetString: class { constructor(value) { this.value = value; } },
  MarkdownString, Position, Range,
  Hover: class { constructor(contents, range) { this.contents = contents; this.range = range; } },
  SignatureHelp: class {},
  SignatureInformation: class { constructor(label, documentation) { this.label = label; this.documentation = documentation; } },
  ParameterInformation: class { constructor(label) { this.label = label; } },
};
const original = Module._load;
Module._load = (request, ...rest) => (request === "vscode" ? vscode : original(request, ...rest));
const extension = require(join(EXTENSION, "extension.js"));

// A document of `lines`; the cursor is where "|" is in the last line (or the end of it).
function documentOf(...lines) {
  const text = lines.join("\n");
  const wordAt = (position) => {
    const line = lines[position.line];
    let a = position.character, b = position.character;
    while (a > 0 && /\w/.test(line[a - 1])) a--;
    while (b < line.length && /\w/.test(line[b])) b++;
    return a === b ? undefined : new Range(new Position(position.line, a), new Position(position.line, b));
  };
  return {
    uri: { toString: () => "file:///sketch.py" }, version: ++versions,
    getText(range) {
      if (!range) return text;
      const upto = lines.slice(range.start.line, range.end.line + 1);
      const last = upto.length - 1;
      upto[last] = upto[last].slice(0, range.end.character);
      upto[0] = upto[0].slice(range.start.character);
      return upto.join("\n");
    },
    lineAt: (line) => ({ text: lines[typeof line === "number" ? line : line.line] }),
    getWordRangeAtPosition: wordAt,
  };
}
const endOf = (document, lines) => new Position(lines.length - 1, lines[lines.length - 1].length);

// ---- start the extension

const output = [];
const context = { subscriptions: [], extensionUri: EXTENSION };
await extension.activate(context);
const providers = Object.fromEntries(registered.map((r) => [r.kind, r]));
const header = "import funground as f";

function complete(lines, trigger) {
  const document = documentOf(...lines);
  return providers.completion.provider.provideCompletionItems(document, endOf(document, lines), null, trigger);
}
const labels = (items) => items.map((i) => i.label);
let count = 0;
function test(name, body) {
  body();
  count++;
  console.log(`ok  ${name}`);
}

// ---- tests

test("providers are registered for Python, with trigger characters", () => {
  assert.deepEqual(registered.map((r) => r.kind), ["completion", "hover", "signature"]);
  assert.deepEqual(providers.completion.triggers, [".", '"', "'"]);
  assert.deepEqual(providers.signature.metadata.triggerCharacters, ["(", ","]);
  assert.equal(providers.completion.selector.language, "python");
});

test("f. lists the names with signatures, summaries and a link", () => {
  const items = complete([header, "f."]);
  assert.ok(items.length > 190, `only ${items.length} names`);
  const circle = items.find((i) => i.label === "circle");
  assert.equal(circle.detail, "circle(x, y, diameter)");
  assert.match(circle.documentation.value, /Draw a circle/);
  assert.match(circle.documentation.value, /\(https:\/\/funground-hq\.github\.io\/reference\/API\/#fn-circle\)/);
  assert.equal(circle.insertText.value, "circle($0)");
  assert.equal(items.find((i) => i.label === "width").detail, "width: int");
  assert.ok(items.some((i) => i.label === "COLORS" && i.detail === "665 colours"));
});

test("f.ci keeps the names (the editor filters them); another alias works", () => {
  assert.ok(complete([header, "f.ci"]).some((i) => i.label === "circle"));
  assert.ok(complete(["import funground as fg", "fg."]).some((i) => i.label === "circle"));
  assert.equal(complete([header, "g."]), undefined, "g is not the alias");
  assert.equal(complete(["import math", "math."]), undefined, "no funground import");
});

test("no insert of brackets when they are already typed", () => {
  const document = documentOf(header, "f.(1, 2, 3)");
  const items = providers.completion.provider.provideCompletionItems(document, new Position(1, 2));
  assert.equal(items.find((i) => i.label === "circle").insertText, undefined);
});

test("bare names after from funground import *, only the starred ones", () => {
  const items = complete(["from funground import *", "circ"]);
  assert.ok(items.some((i) => i.label === "circle"));
  assert.ok(items.length >= 190);
  assert.equal(complete(["from funground import *", ""], { triggerKind: 1 }), undefined, "nothing typed yet");
  assert.ok(complete(["from funground import *", ""], { triggerKind: 0 }).length > 0, "Ctrl+Space lists them");
  assert.equal(complete(["from funground import *", "x = foo.ci"]), undefined);
  assert.equal(complete(["from funground import *", "def ci"]), undefined);
  assert.equal(complete([header, "circ"]), undefined, "not in the star style");
});

test("f.COLORS. lists colours with their value and hex, as colour items", () => {
  const items = complete([header, "f.COLORS."]);
  const tomato = items.find((i) => i.label === "TOMATO");
  assert.equal(tomato.kind, "Color");
  assert.equal(tomato.detail, '"tomato"  #ff6347');
  assert.equal(tomato.documentation, "#ff6347");
  assert.equal(items.length, 665);
  assert.ok(complete(["from funground import *", "COLORS.TOM"]).some((i) => i.label === "TOMATO"));
});

test("f.CONSTANTS. lists the groups, f.CONSTANTS.ALIGN. its words with meaning", () => {
  const groups = complete([header, "f.CONSTANTS."]);
  assert.equal(groups.length, 18);
  assert.match(groups.find((i) => i.label === "ALIGN").detail, /^for .*text_align/);
  const words = complete([header, "f.CONSTANTS.ALIGN."]);
  const center = words.find((i) => i.label === "CENTER");
  assert.equal(center.detail, '"center"');
  assert.ok(center.documentation.value.length > 5, "has a meaning");
  assert.equal(complete([header, "f.CONSTANTS.NOPE."]), undefined);
});

test('f.fill(" offers the colour names; so does a keyword argument', () => {
  const items = complete([header, 'f.fill("re']);
  assert.equal(items.length, 665);
  assert.ok(items.some((i) => i.label === "red" && i.detail === "#ff0000"));
  assert.equal(items.find((i) => i.label === "red").kind, "Color");
  assert.equal(complete([header, 'f.fill(color="']).length, 665);
  assert.equal(complete([header, "f.fill('"]).length, 665);
  assert.equal(complete([header, 'f.lerp_color("red", "']).length, 665, "second colour parameter");
  assert.equal(complete([header, 'f.circle(f.random(1, 2), f.stroke("']).length, 665, "innermost call");
  assert.equal(complete([header, 'f.circle(10, "']), undefined, "not a colour parameter");
  assert.equal(complete([header, 'f.fill(f.circle("']), undefined, "the innermost call decides");
  assert.equal(complete([header, 'print("']), undefined);
  assert.equal(complete([header, 'f.fill(', '   "']).length, 665, "a call over two lines");
});

test('f.blend_mode(" offers the modes with meanings', () => {
  const items = complete([header, 'f.blend_mode("']);
  assert.deepEqual(labels(items).slice(0, 3), ["normal", "multiply", "screen"]);
  assert.match(items[1].documentation.value, /darker/);
  assert.equal(items[0].kind, "EnumMember");
  assert.equal(complete([header, 'f.blend_mode(mode="mu']).length, items.length);
});

test("nothing inside comments, or for names in strings", () => {
  assert.equal(complete([header, "# f."]), undefined);
  assert.equal(complete([header, 'x = "f.']), undefined);
  assert.ok(complete([header, "# a note", "f."]).length > 0, "the next line is code again");
});

test("hover on circle: signature, summary and Reference link", () => {
  const lines = [header, "f.circle(1, 2, 3)"];
  const hover = providers.hover.provider.provideHover(documentOf(...lines), new Position(1, 4));
  assert.match(hover.contents.value, /circle\(x, y, diameter\)/);
  assert.match(hover.contents.value, /Draw a circle/);
  assert.match(hover.contents.value, /https:\/\/funground-hq\.github\.io\/reference\/API\/#fn-circle/);
  const other = providers.hover.provider.provideHover(documentOf(header, "g.circle(1, 2, 3)"), new Position(1, 4));
  assert.equal(other, undefined, "not funground's alias");
  const star = providers.hover.provider.provideHover(documentOf("from funground import *", "circle(1, 2, 3)"), new Position(1, 2));
  assert.match(star.contents.value, /Draw a circle/);
  const live = providers.hover.provider.provideHover(documentOf(header, "x = f.width"), new Position(1, 8));
  assert.match(live.contents.value, /width: int/);
});

test("signature help on ( and , with the active parameter", () => {
  const help = (...lines) => {
    const document = documentOf(...lines);
    return providers.signature.provider.provideSignatureHelp(document, endOf(document, lines));
  };
  let h = help(header, "f.circle(");
  assert.equal(h.signatures[0].label, "circle(x, y, diameter)");
  assert.deepEqual(h.signatures[0].parameters.map((p) => p.label), ["x", "y", "diameter"]);
  assert.equal(h.activeParameter, 0);
  assert.equal(help(header, "f.circle(10, ").activeParameter, 1);
  assert.equal(help(header, "f.circle(10, f.random(1, 2), ").activeParameter, 2, "a nested call is skipped");
  assert.equal(help(header, "f.circle(10, 20, 30, 40, ").activeParameter, 2, "stays on the last");
  assert.equal(help(header, "f.circle(10, diameter=").activeParameter, 2, "a keyword argument");
  assert.equal(help(header, "f.fill(255, ").signatures[0].label, "fill(color, *more)");
  assert.equal(help(header, "f.circle(1, 2, 3)"), undefined, "the call is closed");
  assert.equal(help(header, "g.circle("), undefined);
  assert.equal(help(header, "def circle("), undefined);
  assert.equal(help(header, "f.circle(", "   10, ").activeParameter, 1, "over two lines");
  assert.equal(help(header, "f.circle(10, [1, 2], ").activeParameter, 2, "commas in a list do not count");
});

test("the funground.suggestions setting turns everything off", () => {
  settings.suggestions = false;
  try {
    const document = documentOf(header, "f.");
    assert.equal(providers.completion.provider.provideCompletionItems(document, endOf(document, [header, "f."])), undefined);
    assert.equal(providers.hover.provider.provideHover(documentOf(header, "f.circle(1, 2, 3)"), new Position(1, 4)), undefined);
  } finally {
    delete settings.suggestions;
  }
});

console.log(`${count} tests passed`);
