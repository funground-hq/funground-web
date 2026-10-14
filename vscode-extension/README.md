# funground for VS Code

Runs a funground sketch in a panel beside the editor, in github.dev, vscode.dev and VS Code. It is a VS Code web
extension: it has no Node part, so it works where VS Code runs in a browser.

Run **funground: Run** (Ctrl+Enter, or the play button) on a Python file. The panel then follows the active sketch,
runs it again a moment after you stop typing and at once when you save, and shows `print()` output and errors. An
error's line is also underlined in the editor.

The panel moves to another file only if that file is a sketch it can run: one with a top-level `run()` or `show()`
call (`f.run()` animates, `f.show()` draws once). Opening a helper such as `palette.py` keeps the sketch that uses it
in the panel, and changing the helper runs that sketch again. **funground: Run** runs whatever Python file is open,
for a script that only saves a file.

## Suggestions

The extension also suggests funground's names while you type (story S-205). In github.dev and vscode.dev there is no
Python environment and Pylance reads one file only, so nothing else could. It works from `media/completions.json`,
funground's own list of names, signatures, summaries, colours and option words. `tools/build_runtime.py` copies it from
the funground checkout (as `runner/runtime/completions.json`, role `completions` in `manifest.json`) and `build.py`
copies it from there into `media/` (about 177 KB), so the suggestions always match the funground the runtime runs.

- after `f.` (the alias in `import funground as ...`): every name, with its signature, summary and a Reference link;
  bare names after `from funground import *`;
- `f.COLORS.` (colours, with a swatch), `f.CONSTANTS.` (the groups, "for text_align"), `f.CONSTANTS.ALIGN.` (words);
- inside the quotes of a colour parameter (`f.fill("`) the colour names; of an option parameter (`f.blend_mode("`) the words;
- hover on a name, and signature help after `(` and `,` with the parameter you are on.

All of it is in `extension.js` (`makeSuggestions`): VS Code for the web loads an extension's `browser` file alone, so it
cannot `require` a second file. A call is found by reading the code back from the cursor (30 lines at most), skipping
strings, comments and brackets. Limits: it only knows the names the file reaches through the `funground` import (not
`g = f`), and on a computer where Pylance has funground installed the names appear twice: set `funground.suggestions`
off there. `test/suggestions_test.mjs` tests it against a stand-in for the VS Code API (no editor needed).

## How it works

```
editor (extension.js, a web worker)                       panel (a webview: its own origin, strict policy)
 typing, 400 ms pause / save / Run  ── postMessage ──►     preview.js → runner.js
 sends: the sketch's text,                                   worker: Pyodide + funground (real Cairo,
        data/ files, other .py files beside it               HarfBuzz and Skia wheels), canvas, Web Audio
 error line  ◄──────────── traceback ──────────────────
```

- The sketch runs only in the panel, never with the editor's rights. The runner is `../runner` (copied by `build.py`).
- Files the sketch reads from beside it are read with `vscode.workspace.fs`, so in github.dev they are the
  repository's: the files in `data/` (`f.load_image("data/photo.png")`) and the other `.py` files in the sketch's
  folder (`import helpers`; an open editor's unsaved text is used). More than 32 MB in all is not sent.
- Python stays loaded between runs (the runner's `reuse` option, D-083): a re-run takes a fraction of a second.
- The panel's policy allows `'unsafe-eval'`. This is the one exception (D-080): pictures (`f.load_image` and friends)
  use pygame-ce, whose WebAssembly modules are linked with `eval`. It is in the panel only, never the editor.

## Where Python loads from

Python (Pyodide) and funground's wheels are the runtime. The extension looks for it in this order (D-081):

1. the **`funground.runtimeUrl`** setting, if it is not empty: a folder URL holding `pyodide/` and `runtime/`, served
   with CORS;
2. a copy **inside the extension**, if the extension was built with one (`build.py --runtime bundled`, 22 MB);
3. the funground website: `https://funground-hq.github.io/runtime/<version>/`, where `<version>` is
   `fungroundRuntime` in `package.json`.

A normal copy for learners has no runtime inside (about 64 KB), so it loads from the website.

## Settings

| Setting | Default | |
|---|---|---|
| `funground.autoRun` | on | Run again after you stop typing, and on save. |
| `funground.autoRunDelay` | 400 | Milliseconds to wait after the last change. |
| `funground.runtimeUrl` | empty | Where the runtime loads from (above). |
| `funground.suggestions` | on | Suggest funground's names, colours and option words, with hover and signature hints. |
| `funground.randomSeed` | none | Seed the random numbers before each run, so every run draws the same. |

## How learners get it

From the Visual Studio Marketplace, once it is published there (D-082; publishing needs the maintainer's
publisher account). Two other routes were tried and do not work in github.dev or vscode.dev:

- **Carried by the repository** in `.vscode/extensions/funground/`: the editor offers it and installs it, but
  cannot load its code from the repository's file system ("Activating extension failed: Failed to fetch").
- **Install Extension from Location with an address on our website**: vscode.dev's own Content Security Policy
  lets the editor download an extension only from the Marketplace's servers and from `localhost`.

`build.py --template` still writes the small folder (about 60 KB, no runtime inside: it loads from the website's
`runtime/<version>/` folder) that a Marketplace package or a local install is made from.

## Publish to the Visual Studio Marketplace

The publisher is `funground-hq` (created by the maintainer). Publishing is the maintainer's act.

1. Build and package (vsce is a local devDependency in `test/`; `npm install` there once):

   ```
   C:\Projects\playground\.venv\Scripts\python.exe vscode-extension\build.py --runtime site
   cd vscode-extension
   node test\node_modules\@vscode\vsce\vsce package --readme-path LISTING.md --no-dependencies
   ```

   This writes `funground-<version>.vsix` (about 64 KB: the extension, its listing page `LISTING.md`, the
   changelog, the licence and the icon; `.vscodeignore` keeps the rest out). The listing is `LISTING.md`,
   written for learners; this README is for developers.
2. At https://marketplace.visualstudio.com/manage, choose the publisher, **New extension**, **Visual Studio
   Code**, and upload the `.vsix`. An update is **Update** on the extension's row, with a higher `version`
   in `package.json`.
3. The icon is `media/icon.png`, drawn by `make_icon.py` with funground (128 x 128).

## Try it in github.dev or vscode.dev before it is published

Serve the extension from this computer, where vscode.dev's policy allows it:

```
C:\Projects\playground\.venv\Scripts\python.exe vscode-extension\build.py --runtime site
C:\Projects\playground\.venv\Scripts\python.exe vscode-extension\serve.py
```

Then in github.dev (press `.` on a repository) or vscode.dev: **F1**, **Developer: Install Extension from
Location...**, `http://localhost:5000/`. Chrome asks whether the page may reach devices on your local network:
allow it (the panel fetches its own files from `localhost`). The browser keeps the extension; keep `serve.py`
running while you use it, since its files are read from there. Checked on 11 October 2026 in the real vscode.dev:
installs, loads Python from the website and draws the sketch.

## Build (Windows)

Needs `runner/runtime/` first (`tools/build_runtime.py`, see `../runner/README.md`). The build uses only Python's
standard library.

```
C:\Projects\playground\.venv\Scripts\python.exe vscode-extension\build.py [options]
```

| Option | Writes |
|---|---|
| (none), `--runtime bundled` | `media/runner/` with the runner's scripts and the runtime inside (git-ignored). |
| `--runtime site` | `media/runner/` with the scripts only. |
| `--site OUT` | The website's folder for this runtime: `OUT/pyodide/` and `OUT/runtime/`. The site serves it, with CORS, at `https://funground-hq.github.io/runtime/<fungroundRuntime>/`. |
| `--template OUT` | The folder a template carries (above), without the runtime. `OUT` must be new or empty. |
| `--vsix` | `funground-<version>.vsix` beside `build.py`. |
| `--pyodide DIR` | Use an unpacked Pyodide 314.0.7 instead of downloading it from jsDelivr (a `--site` folder's `pyodide/` will do). |

Every build also copies `runner/runtime/completions.json` into `media/` (git-ignored), checked against the manifest.

## Test (Windows)

Needs Node 22 and the Chrome in `C:\Users\samirj\AppData\Local\Google\Chrome\Application\`. Nothing is installed
globally and no browser is downloaded.

```
cd vscode-extension\test
npm install --ignore-scripts
node suggestions_test.mjs                      # the suggestions, against a stand-in for the VS Code API; needs media/completions.json
node run_tests.mjs --runtime bundled|site:<folder made by build.py --site>|published:<the same> [--label NAME]
C:\Projects\playground\.venv\Scripts\python.exe compare.py --funground C:\Projects\playground-0.2 out\NAME
```

`run_tests.mjs` starts VS Code for the web with `@vscode/test-web` (it downloads the stable build once into
`.vscode-test-web/`), then drives headless Chrome as a learner would. Build the extension with the same runtime
mode first (`--runtime bundled`, or `--runtime site` with `build.py --site <folder>`). `site:` points the
`funground.runtimeUrl` setting at the folder; `published:` leaves the setting empty, as for a learner, and answers
the website's address from the folder. VS Code is served at `vscode.localhost` and the
runtime site at `runtime.localhost`: the webview's service worker stalls requests to plain `localhost`. `compare.py` checks
the saved frames byte for byte against funground's golden images. The numbers: `RESULTS.md`.

## Limits

- **No microphone.** VS Code does not let a webview use it. A sketch that listens gets one line saying so and keeps
  running. Run such sketches on the funground website or on your computer.
- Chrome first. Other browsers are not tried.
- Sound needs a click or a key press in the editor first (the browser's rule); typing counts.
- The extension is not published to a marketplace. Marketplace publishing is the maintainer's act (see
  `../spikes/S-156_RESULTS.md`, Q5).
