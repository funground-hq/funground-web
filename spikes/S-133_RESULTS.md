# S-133 results: fallback route, uharfbuzz's used API over harfbuzzjs in Pyodide

Question: can a small Python module with uharfbuzz's used API, implemented over harfbuzzjs (HarfBuzz compiled
to wasm, called from Pyodide through the `js` module), make `typography.py` produce the same `FillPath`
outlines in Pyodide as native uharfbuzz does on the desktop?

Short answer: yes. On a corpus of 1405 shaped strings (19,991 glyphs, 52,200 `FillPath` ops at three sizes) the
glyph ids, advances, offsets, clusters, run fonts, line advances and the `FillPath` op data are **identical**, with
no float differences at all. The three Session-1 sketches that S-136 skipped (05, 13, 14) run in the browser with
text and their last frame passes the S-135 criteria against `tests/golden`; the frames are pixel-identical to
S-135's native-IR frames (one rasteriser noise exception, below). The price is speed (shaping is 7 to 11 times
slower than native, still about 0.1 ms a string) and 0.5 MB of code plus the fonts.

## Update: the real wheel passes (read this first)

The coordinator reported that PyPI has a uharfbuzz wheel for Pyodide 314. Tried first, in the same harness
(`?wheel=1` on `text.html` and `run.html`): `micropip.install("uharfbuzz")` in the worker, no stand-in, no shim.

- Wheel: `uharfbuzz-0.56.3-cp310-abi3-pyemscripten_2026_0_wasm32.whl`, 981,875 bytes (a 984,489-byte
  `pyemscripten_2025_0` wheel is also on PyPI), https://files.pythonhosted.org/packages/b0/38/ab433adf99a79086c40cae85d2563411a6dcd6dca5832e9ede83b0a72078/uharfbuzz-0.56.3-cp310-abi3-pyemscripten_2026_0_wasm32.whl
  (index: https://pypi.org/project/uharfbuzz/0.56.3/). micropip chose it in Pyodide 314.0.7; it reports uharfbuzz 0.56.3 with **HarfBuzz 14.6.0**
  (native desktop here: uharfbuzz 0.56.2, HarfBuzz 14.5.0). `micropip` plus the install took 1.76 s (PyPI metadata and wheel, from the real internet).
- Corpus (1405 cases): **identical** to native in everything compared (glyph ids, advances, offsets, clusters, run fonts, line advances, `FillPath` SHA-256 at three sizes), same single error case (empty string) in both. Result file `results_s133/wheel_run1.json`.
- Sketches 05_text, 13_transforms, 14_paths in the browser (GL): 0.61 %, 0.74 %, 1.45 % pixels differing, mean abs 0.09, 0.15, 0.26, off-edge 0.000 %: **pass**, and
  the frames are pixel-identical to the ones made with the harfbuzzjs shim.
- Speed: shaper part 34 us a string and whole `_shape_one` 63 us (one run; same 352 strings), against native 4.6 / 15.6 us and the shim's 85 to 144 / 104 to 181 us:
  the wheel is about 2.5 times faster than the shim, about 4 times slower than native.
- Download: 982 KB wheel (a zip already) in place of the shim's 562 KB raw / 204 KB gzip (shim + harfbuzzjs); the wheel is larger because it carries the whole extension.

**So the shim is not needed.** It stays in the branch (`shim/uharfbuzz.py`, `vendor/harfbuzzjs/`, the harness's non-`wheel` path) only as a documented fallback if the
wheel is withdrawn or stops following Pyodide. Everything below this section is the shim work done before the change of plan; its identity and timing figures
are valid for the fallback. Corrections to the text below: the recommendation at the end is superseded (use the wheel; keep the corpus to re-test it);
open problem 9 is answered (a wheel exists and passes); open problems 2 and 3 (memory, other browsers) apply to the wheel too and were not tested.

Branch (nothing committed or pushed): `spike/s133-text-shim` in `C:\Projects\funground-web`, from
`spike/s136-worker-loop`. `C:\Projects\playground` and `C:\Projects\playground-0.2` were not changed (the latter
is on `spike/s136-loop`, whose `funground/` is what was tested). The funground test suite was not run.

## Pass criteria (set before the work)

| # | Criterion | Result | Verdict |
|---|---|---|---|
| C1 | `shim/uharfbuzz.py` covers every uharfbuzz name `typography.py` uses (Face, Font + scale + variations, Buffer, shape, glyph infos/positions), with the same behaviour | see "API subset" | pass |
| C2 | For the corpus, glyph ids, advances, offsets, clusters identical native vs Pyodide | 1405 of 1405 cases identical (1 case is an error in both, with the same message) | pass |
| C3 | The `FillPath` op data identical (a float difference below 1e-6 only with an explanation) | 1405 of 1405 identical at 12, 40.5 and 96 px, SHA-256 of the exact JSON (shortest round-trip floats); no float difference exists | pass |
| C4 | 05_text, 13_transforms, 14_paths in the browser: last frame against `tests/golden` within S-135's tolerance (at most 3 % pixels differing by more than 8, mean abs diff at most 3, differences on edges only) | all three pass, in both Chrome rasterisers (table below) | pass |
| C5 | Timings and sizes measured | below | done |

## What was built

| File | What |
|---|---|
| `vendor/harfbuzzjs/` | harfbuzzjs 1.6.3 as files (`index.mjs`, `harfbuzz.js`, `harfbuzz.wasm`, `index.d.mts`, `package.json`, `LICENSE` (MIT), `VENDOR.md` with version and URL), fetched with curl from `https://cdn.jsdelivr.net/npm/harfbuzzjs@1.6.3/dist/`, unmodified. |
| `shim/uharfbuzz.py` | The shim. 125 lines. |
| `harness/s133/corpus_run.py` | Runs a corpus through `funground.typography`; the same file runs natively and in Pyodide. |
| `harness/s133/text.html`, `text_worker.js`, `stubs.py` | The Pyodide side of the corpus test (module worker, as S-136). `stubs.py` stands in only for `pathops` and the Cairo renderer (needed to `import funground`); uharfbuzz is not stubbed. |
| `harness/s133/run.html`, `worker.js`, `shim.py` | Copies of S-136's harness that load harfbuzzjs, the shim and the fonts, send a Text op's shaped outlines to the page (`Host.encode`, as `tools/irenc.py` does for S-135), and stop after `frames=N` with a PNG of the canvas. |
| `tools/s133_record.py`, `s133_corpus.py`, `s133_compare.py`, `s133_native_timing.py`, `build_s133_bundle.py`, `run_s133.py` | Record shaping calls natively, build corpus and reference, compare, time, build the bundle, run a page in headless Chrome by PID. |
| `spikes/S-133/` | `corpus.json` (1405 cases), `reference.json` (native results), `recorded.jsonl` (raw shaping calls of the sketches). |

Re-run: `build_s133_bundle.py`, then `s133_corpus.py` (writes `harness/s133/dist/extra/` and the reference), then
`run_s133.py harness/s133/text.html x=1 --name N`, then `s133_compare.py results_s133/N.json`.

## The corpus

1405 cases, all through `FontResource.shape`, so also the T18 fallback (`ShapedLine` of several runs: 14 cases).

| Source | Cases | How |
|---|---|---|
| Session-1 sketches (not 11) and the gallery examples that have a golden (95 examples) | 609 | A native run of each (30 frames, as the golden tests) with `FontResource.shape` wrapped; every distinct (font, face, text, tracking, features, variations, fallback). Session-1: only 05, 13, 14 shape text. The gallery sketches that use another font file (DejaVu Sans Mono) were included; fonts outside the bundle were skipped (none). |
| T-row tests: every string constant (1 to 100 characters, no newline) in `test_text.py`, `test_text_settings.py`, `test_text_layout.py`, `test_text_path.py`, `test_fonts.py`, `test_fallback.py`, `test_formatted.py`, `test_font_info.py`, `test_pdf_text.py`, `test_svg_text.py` | 693 | DejaVu Sans with fallback (every string); a fifth of them also in Bold and in Oblique with tracking. Many are not text meant for drawing (messages, names); that is harmless. |
| Extra samples | 103 | Devanagari in Noto Sans Devanagari and through DejaVu with fallback (conjuncts, pre-base vowel, reph, nukta, marks); emoji (single, skin tone, ZWJ family, flags, keycap, VS16, tag sequences) in Noto Emoji and with fallback; Symbols 2; Latin kerning and ligatures; seven feature sets (`liga` off, `kern` off, `smcp`, `frac`, `onum`, `c2sc`); tracking; Bold, Oblique, Bold Oblique; Arabic and Hebrew (RTL, joining); Greek and Cyrillic; empty and blank strings; a variable font (`tests/fontmaker.py`'s `TestVar`, axis `wght` 100 to 900) at ten settings including out-of-range ones, and a request for an axis it lacks. |

The native reference: uharfbuzz 0.56.2 with HarfBuzz 14.5.0, fontTools 4.66.0, CPython 3.14.7. The browser: harfbuzzjs 1.6.3 with **HarfBuzz 14.6.0**,
fontTools 4.62.1, CPython 3.14.2 (Pyodide 314.0.7), headless Chrome 154.

Not a vacuous test: 52,200 ops; Devanagari strings shape to fewer glyphs than characters with non-trivial clusters
(`क्षत्रिय नमस्ते`: 15 characters, 10 glyphs, clusters 0 3 3 7 8 ...); the variable font changes advances with
the axis (400, 450, 500, 575, 600, 700, 800); an emoji family is one cluster; the fallback produces up to five runs
(`a😀b😃c`).

## Results: shaper output, native against Pyodide

| Compared | Cases | Differences |
|---|---|---|
| Glyph ids | 1405 | 0 |
| x advances | 1405 | 0 |
| x and y offsets | 1405 | 0 |
| Clusters | 1405 | 0 |
| Font of each run (fallback) | 1405 | 0 |
| Line advance (float) | 1405 | 0 |
| `FillPath` op data, SHA-256 at 12, 40.5, 96 px (path commands and floats) | 1405 x 3 | 0 |
| Case 1349 (empty string, no fallback) | 1 | same `TypeError` in both: see below |

By source: sketches 609, tests 693, extra 103; no difference in any. Three browser runs (the first with the
final shim, two later runs) all compared identical. Because both sides run the same `corpus_run.py` and
`typography.py`, the only things that can differ are HarfBuzz, the shim and fontTools.

**Floats.** No difference at all, so no explanation is needed. Why none: HarfBuzz returns integer positions (font
scale = units per em); the outline coordinates come from fontTools in pure Python in both runs, and the same IEEE
double arithmetic is applied in the same order. The fontTools versions differ (4.66.0 against 4.62.1) and made no difference to these fonts.

**A behaviour copied on purpose.** For an empty buffer uharfbuzz 0.56 returns `None` (not `[]`) from `glyph_infos`
and `glyph_positions`; `typography.py` would raise `TypeError` for `shape("")`. The shim does the same so that the behaviour is identical.
funground never shapes an empty string (`text_width` returns 0.0 first; `f.text` skips it).

## Results: the three sketches in the browser

Last frame (30 steps, the golden tests' frame) drawn by `renderer/ir_canvas.js` from the IR that Pyodide produced
(Text ops carrying their shaped outlines), compared with `tests/golden/*.png` by `tools/compare.py` (the S-135 tool;
criteria: at most 3 % of pixels differing by more than 8, mean abs difference at most 3, differences only on edges).
Two Chrome 154 rasterisers as in S-135: GL (default headless) and CPU (`--disable-gpu`).

| Sketch | GL: differing % / mean abs / max / off-edge % | CPU: differing % / mean abs / max / off-edge % | Verdict | S-135 (native IR) GL / CPU, differing % |
|---|---|---|---|---|
| 05_text | 0.61 / 0.09 / 85 / 0.000 | 0.29 / 0.05 / 58 / 0.000 | pass | 0.61 / 0.29 |
| 13_transforms | 0.74 / 0.15 / 82 / 0.000 | 0.50 / 0.10 / 54 / 0.000 | pass | 0.74 / 0.50 |
| 14_paths | 1.45 / 0.26 / 94 / 0.000 | 1.19 / 0.29 / 104 / 0.000 | pass | 1.45 / 1.19 |

The numbers equal S-135's, because the pictures do: the Pyodide frames are **pixel-identical** to S-135's canvases
(drawn from IR that was recorded natively with Cairo and uharfbuzz) in 5 of 6 cases. The sixth, 14_paths on GL,
differs in 16 pixels by one level (bounding box 496,270 to 630,284, on the edge of a clip); the same sketch on CPU is identical, and the
GL rasteriser is not bit-stable on clip edges. Text is not involved.

## API subset covered

The names `typography.py` uses (it is the only user in `funground/`), plus the three that `tests/test_svg_text.py` uses
(`hb.Face(data)`, `hb.shape(font, buf)` with no features, `buf.glyph_infos`):

| uharfbuzz | Shim |
|---|---|
| `Face(data: bytes, index=0)`, `.upem` | `hb.Blob` + `hb.Face`; the bytes are copied twice (Python to a `Uint8Array`, then into wasm memory) |
| `Font(face)`, `.scale` (get and set a pair) | `hb.Font`, `setScale` |
| `Font.set_variations({tag: value})` | `setVariations([Variation...])`; replaces all, as in uharfbuzz |
| `Buffer()`, `.add_str(text, offset, length)`, `.add_codepoints`, `.guess_segment_properties()`, `.clear_contents()` | `addCodePoints` (see below) |
| `shape(font, buffer, features=None)` with `{tag: bool/int}` or `{tag: [(start, end, value), ...]}` | `hb.shape` with `Feature` objects; a feature string such as `"liga=0"` is not supported (raises) |
| `buf.glyph_infos` (`.codepoint .cluster .mask .flags`), `buf.glyph_positions` (`.x_advance .y_advance .x_offset .y_offset`) | `getGlyphInfosAndPositions().to_py()`, read once per shape |

Not covered (nothing in funground uses it): drawing and outlines (`draw_glyph`), glyph names and extents, metrics,
`Blob`, named instances, `set_var_coords_*`, math and colour tables, `serialize`, `set_message_func`, shapers lists,
`ot` and `subset` modules. They raise `AttributeError`. `Face.collect_unicodes`, `get_axis_infos` and so on are in harfbuzzjs and could be added in a few lines each.

**Decision in the shim: code points, not UTF-16.** harfbuzzjs's `addText` feeds UTF-16, so a cluster would be an index in UTF-16 units and
an emoji such as U+1F600 would move every later cluster by one against uharfbuzz (whose `add_str` uses UTF-32).
The shim calls `addCodePoints` instead, so clusters are indices into the Python string, as natively. This was
designed, not measured against `addText` (the corpus has the cluster evidence: `a😀b😃c` has clusters 0 per run after itemising, and the emoji family
is one cluster).

**The shim needs a global.** The worker (or page) must run `self.hb = await import(".../harfbuzzjs/index.mjs")` before Python imports `uharfbuzz`
(the shim reads `js.hb`). The module does `init(await createHarfBuzz())` at load, so the import waits for the wasm to compile.

## Sizes (added download)

Raw bytes, and gzip level 9 (what a static host sends; Brotli not measured).

| File | Raw | gzip |
|---|---|---|
| `harfbuzz.wasm` | 441,359 | 178,492 |
| `index.mjs` (the JS API; 83 KB, includes everything) | 82,693 | 16,885 |
| `harfbuzz.js` (Emscripten loader) | 31,763 | 6,691 |
| `shim/uharfbuzz.py` | 5,774 | 2,087 |
| **Shaper total** | **561,589** | **204,155** |
| Fonts, needed up front: `DejaVuSans.ttf` | 757,076 | 381,615 |
| Fonts, on first use: Bold 705,684; Oblique 635,416; Bold Oblique 643,292; Noto Emoji 886,628; Noto Sans Devanagari 243,520; Noto Sans Symbols 2 671,568 | 3,786,108 (all six) | about 2,0 MB |
| All seven fonts | 4,543,184 | 2,383,000 (about) |

`harfbuzz-subset.wasm` (667 KB) is not needed and not fetched. A 4.5 MB font set was already expected in
`Web_Target_Options.md` ("DejaVu Sans up front, the rest on first use"): the three sketches here load only DejaVu Sans.
The fonts are a cost of the web target whatever the shaper is; the shaper itself adds 0.56 MB raw (0.20 MB gzipped).
For comparison a native uharfbuzz wheel for Emscripten would be a C extension of the same HarfBuzz; its size was not measured (no wheel exists).

Load time in the browser (Chrome 154, localhost, so no network; compile time included): `import` of harfbuzzjs 56 to 80 ms; the
DejaVu Sans file into the Pyodide file system 28 to 51 ms; `import funground` about 420 to 470 ms (as S-136). Boot to ready
6.1 to 7.0 s (Pyodide itself 4.8 to 5.1 s, from jsDelivr).

## Timings

The same strings (every fourth case, 352 strings with text, 4,987 glyphs, mean 14 glyphs), `FontResource._shape_one` = Buffer, add, shape, read back, build the `TextRun`,
mean microseconds per string (3 repeats in Pyodide, 5 natively; Pyodide in headless Chrome on a slow machine):

| | Native (uharfbuzz) | Pyodide (shim) run 1 | run 3 |
|---|---|---|---|
| `_shape_one` per string | 15.6 | 181 | 104 |
| The shaper part alone (Buffer, shape, read back), per string | 4.6 | 144 | 85 |
| Per glyph | 0.32 | 10.2 | 6.0 |

So the shim costs **a factor of about 7 to 11 in total** (18 to 31 for the shaper alone), about 0.1 to 0.2 ms a string. Where the
time goes was not profiled in detail. A first experiment, packing the glyphs into one `Int32Array` in a JS helper
(`new Function`) so that only one value crosses the boundary, cut the shaper part from 144 to 105 µs and the string from 181 to 132 µs in the same
session (measured once, kept out of the shim because it needs `new Function` and the run-to-run spread, 181 against 104 µs for the same code, is as large as the gain). What costs: one
conversion of each glyph row to a Python dict, two Python objects per glyph, and about ten calls across the Python/JS boundary per string.

What that means for a sketch: shaping is not cached by `FontResource`; a frame that shapes N distinct strings costs
about N x 0.1 to 0.2 ms (a sketch with 10 changing labels, 1 to 2 ms). The first frame of the three sketches took 150 to 300 ms of Python
(maximum `Sketch.step` in the 30 frames), mostly building glyph outlines with fontTools (cached afterwards); the median step is 1.2 ms
(05_text), 1.8 ms (13) and 3.0 ms (14), where S-136's text-free sketches took 0.4 to 0.8 ms.

## Differences and their causes

| Difference | Cause | Effect |
|---|---|---|
| HarfBuzz 14.6.0 (harfbuzzjs 1.6.3) against 14.5.0 (uharfbuzz 0.56.2) | The two projects release separately | None on this corpus. A shaping change between two HarfBuzz versions would show; the web build would drift from the desktop one |
| fontTools 4.62.1 against 4.66.0 | Pyodide ships its own | None on the fonts tested |
| CPython 3.14.2 against 3.14.7 | Pyodide 314.0.7 | None |
| `Buffer.glyph_infos` returns `None` for an empty buffer | copied from uharfbuzz on purpose | none, identical |
| Speed | Python in wasm, a JS call for every operation | 7 to 11 times slower than native |

## Open problems

1. **HarfBuzz versions are not tied together.** Identical now; nothing pins them. A funground release should record the HarfBuzz version of both
   builds, and the corpus (`spikes/S-133/corpus.json` with `tools/s133_compare.py`) can be re-run when either moves. It takes about 1 minute in
   the browser once the bundle is built.
2. **Not tested: memory.** harfbuzzjs has no `destroy()`; wasm objects are freed by a `FinalizationRegistry`. A long run that shapes many strings
   each frame was not measured for heap growth. Unverified.
3. **Not tested: Firefox and Safari** (out of scope, D-074: Chrome first). Chrome 154 only, one machine, headless. harfbuzzjs itself is standard wasm.
4. **Speed.** About 0.1 to 0.2 ms a string; a text-heavy animated sketch (hundreds of changing strings a frame) would feel it. Options: a
   cache of shaped lines in `FontResource` (a product change; the desktop would gain too), fewer boundary crossings (the packed-array helper, about 27 % in one
   measurement), shaping in JS and returning flat arrays.
5. **How `hb` reaches the shim.** A global set by the worker. A supported way (a small loader module, or the shim importing harfbuzzjs itself with
   `pyodide.ffi`/`js.import`) is a product decision.
6. **Fonts are separate files in the Pyodide file system.** The shim's `Face` takes bytes, as uharfbuzz; funground reads each font twice (fontTools and the shaper)
   and the shim copies the bytes twice more. About 3 x the file size of transient memory; fine for DejaVu Sans, to be watched with all seven fonts loaded.
7. **Features given as strings** (`"liga=0"`, a form uharfbuzz accepts) are not supported and raise; funground does not use them. Direction, script, language and cluster-level settings
   of the buffer are not exposed (funground uses `guess_segment_properties`).
8. **The harness changes `Host.encode`** to attach outlines to Text ops (and a path to rounded rects). The product's web renderer interface needs the same
   (`irenc.py` does it for S-135); the IR does not serialise `outlines` itself.
9. **S-134 interaction.** If Cairo-in-wasm (architecture C) works, uharfbuzz-in-wasm is still needed for shaping; the options note's "uharfbuzz wheel" and this shim are
   interchangeable behind `import uharfbuzz`. This spike did not build a wheel (the primary route of S-133) and does not say whether one can be built.

## Recommendation

Superseded by the update at the top: use the PyPI wheel (`micropip.install("uharfbuzz")`, or ship the wheel file with the site so the first load needs no PyPI),
which passed the same corpus and sketches exactly and is faster. Keep this shim only as the fallback. Keep `corpus.json` and `tools/s133_compare.py`: they decide, in about a minute,
whether a new HarfBuzz, uharfbuzz, fontTools or Pyodide changes any outline. Pin the wheel version in the web build.
