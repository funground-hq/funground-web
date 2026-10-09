# funground for VS Code

Runs a funground sketch in a panel beside the editor, in github.dev, vscode.dev and VS Code. It is a VS Code web
extension: it has no Node part, so it works where VS Code runs in a browser.

Run **funground: Run** (Ctrl+Enter, or the play button) on a Python file. The panel then follows the active sketch,
runs it again a moment after you stop typing and at once when you save, and shows `print()` output and errors. An
error's line is also underlined in the editor.

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

A normal copy for learners has no runtime inside (55 KB), so it loads from the website.

## Settings

| Setting | Default | |
|---|---|---|
| `funground.autoRun` | on | Run again after you stop typing, and on save. |
| `funground.autoRunDelay` | 400 | Milliseconds to wait after the last change. |
| `funground.runtimeUrl` | empty | Where the runtime loads from (above). |
| `funground.randomSeed` | none | Seed the random numbers before each run, so every run draws the same. |

## How learners get it

For now the extension is carried by a sketchbook template, in `.vscode/extensions/funground/` (D-082); VS Code offers
to install an extension it finds there. The template copies exactly the folder `build.py --template` writes:

```
package.json
extension.js
media/icon.svg
media/preview.js
media/preview.css
media/runner/runner.js
media/runner/worker.js
media/runner/audio.js
media/runner/microphone-worklet.js
```

That is about 60 KB. No runtime is inside, so it loads from the website's `runtime/<version>/` folder.

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

## Test (Windows)

Needs Node 22 and the Chrome in `C:\Users\samirj\AppData\Local\Google\Chrome\Application\`. Nothing is installed
globally and no browser is downloaded.

```
cd vscode-extension\test
npm install --ignore-scripts
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
