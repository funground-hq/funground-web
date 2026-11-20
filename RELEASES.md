# funground-web releases

One section per release, newest first (ADR-008). Each says what changed for a page that uses the runner, and which
funground it was built with. `tools/make_release.py` takes a release's notes from its section and refuses a version
without one. The release workflow (`.github/workflows/release.yml`) makes a draft; nothing is published until the
maintainer publishes it.

## 0.1.0 (20 November 2026)

The first release: the runner as Play and the github.dev extension use it on 19 November 2026.

- What a release holds: the runner's scripts (`runner/files.json`), `runtime/` (funground's wheels, the WebAssembly
  wheels from funground-cairo-wasm, svgelements and pypdf, the fonts, `models.json`, `completions.json` and the
  examples), the runner's `README.md`, `LICENSE`, and `release.json`, which lists every other file with its size and
  SHA-256 and names the funground version built in.
- What the runner can do (`ready`'s `capabilities`): `run`, `stop`, `stdin`, `check`, `packages`.
- Since there were no releases before: input lines for `input()` (S-272), a check message (S-273), the capability
  list (S-275), a runner started without funground (S-274), the host's packages (S-276), no requests to PyPI
  (S-277), `input()` without lines says Play cannot wait for typing yet (S-279), `onModel` (S-307).
- Not in the release: Pyodide and onnxruntime-web (the runner loads them from the addresses in `release.json`,
  `uses`, unless the host gives its own), and this repository's checks and test sketches.
