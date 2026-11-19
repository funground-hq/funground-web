# funground-web
funground in the browser: Pyodide runtime, Canvas 2D renderer for the draw-op IR, static editor

How a page uses the runner: [runner/README.md](runner/README.md).

## Releases

A page uses one numbered release of the runner, never `main` (ADR-008). A release is a folder, also given as a zip:

- the runner's scripts, exactly those [runner/files.json](runner/files.json) names;
- `runtime/`, built by `tools/build_runtime.py` from one funground commit: funground's wheels, the WebAssembly wheels
  from funground-cairo-wasm's release, svgelements and pypdf, the fonts, `models.json`, `completions.json` and the
  examples;
- the runner's `README.md` (its interface) and `LICENSE`;
- `release.json`: the version, the funground version and commit built in, the addresses of Pyodide and
  onnxruntime-web the runner loads (they are not in the release), the runner's capabilities, and every other file with
  its size and SHA-256.

This repository's checks and test sketches are not in it. A user copies the folder whole and checks every file
against `release.json`: `tools/make_release.py --check FOLDER` does that, and `tools/test_release.py FOLDER` also runs
a sketch and plain Python with the folder alone in headless Chrome (`--pyodide DIR` serves Pyodide from a
local copy instead of jsDelivr, as a host that keeps its own copy does). Releases are made by the Release workflow
(`.github/workflows/release.yml`, started by hand) as drafts; the maintainer publishes them. Notes: [RELEASES.md](RELEASES.md).

## Used by

- **The funground website** ([funground-hq.github.io](https://github.com/funground-hq/funground-hq.github.io)): Play,
  the browser editor, is put together from the runner and its `runtime/` (`tools/assemble.py`). Today it builds from
  this repository's `main`; it moves to a pinned release with its story S-269.
- **The funground extension for github.dev and VS Code** ([vscode-extension/](vscode-extension/)): it carries the
  runner's scripts and loads Python and funground from the site's `runtime/<version>/` (D-081).
- **QuestConquest**, an online learning platform, as an outside host (D-143 a): it copies one release into its own
  pages and checks every file against `release.json`. It runs learners' plain Python with `packages: []` and uses
  `run`, `stop`, `stdin` and `check`.
