# funground VS Code extension: test results (story S-158)

Measured on 9 and 10 October 2026, on the maintainer's Windows machine (slow, little memory). Raw numbers:
`test/out/<label>/report.json` (git-ignored). The spike's results are in `../spikes/S-156_RESULTS.md`.

## Environment

| | |
|---|---|
| OS | Windows 11 Home |
| Browser | Chrome 154.0.8037.99, headless, its own temporary profile (`playwright-core` 1.64.0 with `executablePath`) |
| VS Code for the web | 1.141.0 stable (commit 2a59476c), downloaded once by `@vscode/test-web` 0.0.81 (54 MB) into `test/.vscode-test-web/` |
| Node | 22.14.0 |
| Python / funground wheel | Pyodide 314.0.7; funground `release-0.2-web` 17a5e51 (S-157), pycairo, uharfbuzz, skia-pathops from `funground-cairo-wasm` v0.1.0-wasm |
| Hosts | VS Code at `vscode.localhost:3000`, the runtime site at `runtime.localhost:3100` |

Chrome on Windows resolves `*.localhost` to the loopback address without any setting. Served over plain `http`, VS Code's
own extension-host frame needs one thing from the test (below).

## The three runtime modes

Each ran the same cases in one go: `node run_tests.mjs --runtime <mode> --label <mode>`, then `compare.py`.

- `bundled`: the runtime inside the extension (22,352,514 bytes unpacked), nothing fetched from a site.
- `site`: the extension built with `--runtime site` (61,844 bytes), `funground.runtimeUrl` set to
  `http://runtime.localhost:3100/`, which serves `build.py --site` output with CORS (22.3 MB served).
- `published`: the same small extension and no setting, as a learner has it. The extension looks for
  `https://funground-hq.github.io/runtime/0.2-dev/`; the test answers that address from the same folder (the site is not
  published yet, so this checks the address, the version field and the policy, not GitHub Pages).

| Case | bundled | site | published |
|---|---|---|---|
| `first_sketch` against golden (frame 30, seed 0) | identical | identical | identical |
| `bounce` against golden | identical | identical | identical |
| `paths-05_booleans` against golden | identical | identical | identical |
| `text-01_text` against golden | identical | identical | identical |
| `photo.py`: drawn pixels equal the PNG, under the real policy | equal | equal | equal |
| `tune.py`: two `load`s of 355,845 frames, both voices playing | pass | pass | pass |
| `visualiser.py`: loads `data/tune.wav` (132,300 frames), playing | pass | pass | pass |
| `listen.py`: shows the microphone line, runs 30+ frames, microphone never opened | pass | pass | pass |
| `oops.py`: error line 10 marked in the editor (Problems view: `[Ln 10, Col 1]`) | pass | pass | pass |
| `uses_helper.py`: imports `helpers.py`; after an unsaved edit of `helpers.py` it prints the new value | 2 | 2 | 2 |

Timings, milliseconds:

| | bundled | site | published |
|---|---|---|---|
| Python ready in the panel (cold) | 4,205 | 4,158 | 4,351 |
| ... of which Pyodide / packages / wheels / check | 2,390 / 460 / 984 / 336 | 2,393 / 491 / 902 / 334 | 2,448 / 515 / 1,011 / 343 |
| Run command to first frame | 6,362 | 6,404 | 6,557 |
| Opening another sketch to its first frame: bounce, text, booleans | 177, 183, 378 | 174, 165, 393 | 179, 199, 430 |
| Same, `photo.py` (loads pygame-ce and Pillow) / `tune.py` (it makes its tune) | 563 / 2,611 | 544 / 3,053 | 584 / 3,041 |
| Last key to new run's first frame, 5 edits (400 ms pause included) | 383, 382, 382, 364, 435 | 378, 402, 402, 364, 379 | 382, 374, 382, 378, 396 |
| Run sent to first frame, 5 edits (the part that is not the pause) | 17, 25, 25, 9, 52 | 12, 32, 25, 9, 14 | 26, 26, 26, 14, 15 |
| Ctrl+S to first frame | 29 | 24 | 30 |

"Last key" is read just after Playwright's last keystroke, which waits 30 ms per key, so the true figure is up to about
30 ms larger. All edits are under the 1 s goal. Local serving: no real network time is in any figure.

Not measured: real github.dev or vscode.dev, a real network, other browsers.

## The runner (`tools/test_runner.py --funground C:\Projects\playground-0.2 --skip-scenarios`, no `--limit`)

15 cases in headless Chrome. 14 are byte-identical to the goldens at 1x. `images-01_load_image` differs in 50,454 pixels:
Pyodide's JPEG decoder differs from the desktop one, as before this story (see `../runner/README.md`). `runner/demo.html` still
behaves as it did: every new option is off by default.

## What failed on the way, and why

- **The extension host did not start on `vscode.localhost`.** VS Code's extension-host frame (`webWorkerExtensionHostIframe.html`,
  not our panel) allows scripts and requests only to `https:` and `http://localhost:*`. The test serves that one page with
  `http://vscode.localhost:*` added (a Playwright route in `run_tests.mjs`, commented). The extension's own page policy is not touched.
  Chrome also needs the `local-network-access` permission granted for headless runs (the test grants it).
- **`workspace.fs.stat` cannot tell whether the runtime is bundled.** In VS Code for the web it answers "yes" for any path
  under the extension's own location, even a missing file (the first `published` run took the missing bundled copy and failed
  to load Pyodide). The extension reads `media/runner/runtime/manifest.json` instead (`hasBundledRuntime`).
- **The runtime wheel was older than S-157.** `runner/runtime/` held the funground wheel from a19e4c0, whose `Session.stop()`
  did not forget helper modules, so an edited `helpers.py` printed the old value. After `tools/build_runtime.py --offline`
  (17a5e51) it printed the new one. Anyone testing helpers needs a wheel from S-157 or later.
- **Saving in `@vscode/test-web` does not reach the disk** (as in the spike): "file on disk changed" is false. In github.dev a
  save is GitHub's commit.

## How to repeat

```
C:\Projects\playground\.venv\Scripts\python.exe vscode-extension\build.py --runtime site --site vscode-extension\test\out\runtime-site
cd vscode-extension\test
npm install --ignore-scripts
node run_tests.mjs --runtime site:out/runtime-site --label site
C:\Projects\playground\.venv\Scripts\python.exe compare.py --funground C:\Projects\playground-0.2 out\site
```

For `bundled`: `build.py --runtime bundled --pyodide vscode-extension\test\out\runtime-site\pyodide`, then
`node run_tests.mjs --runtime bundled`. For `published`: build with `--runtime site`, then `--runtime published:out/runtime-site`.
