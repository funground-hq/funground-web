# harfbuzzjs (vendored for spike S-133)

- Package: `harfbuzzjs` 1.6.3 (npm "latest" on 8 October 2026), MIT licence (see LICENSE).
- Source: https://cdn.jsdelivr.net/npm/harfbuzzjs@1.6.3/ (files `dist/index.mjs`, `dist/harfbuzz.js`,
  `dist/harfbuzz.wasm`, `dist/index.d.mts`, `LICENSE`, `package.json`), fetched with curl, unmodified.
- Upstream: https://github.com/harfbuzz/harfbuzzjs
- Layout differs from older releases (`hb.wasm` + `hbjs.js`): 1.6.x is an ES module `index.mjs` that imports
  the Emscripten loader `harfbuzz.js`, which fetches `harfbuzz.wasm` next to itself.
- `harfbuzz-subset.wasm` (667 KB, font subsetting) is not fetched: nothing here needs it.
