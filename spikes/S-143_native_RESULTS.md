# S-143 (native half): where a heavy frame's time goes

**Question:** where does a heavy frame's time go in funground's own Python, before any renderer?
**Run:** 8 October 2026, CPython 3.14.7, the playground venv, funground from `playground-0.2`
(`release-0.2-web`), one process at a time, no Chrome or Pyodide. Scripts: `spikes/S-143/`
(`profile_native.py` phase timers and cProfile, `prototypes.py` patches and equality checks,
`micro.py` interleaved per-call benchmarks); raw output in `spikes/S-143/out/`.
Written by the main session from the builder's report (the subagent could not write report files).

## Answer

1. **User code is 1–7 % of `draw()`.** 93–99 % of a heavy frame's `draw()` is funground and its
   libraries: copying `GraphicsState` with `dataclasses.replace`, re-parsing colours, validating
   `Vector` numbers, pure-Python noise and path conversion. Excluding sound-02, an estimated 45–65 % of
   `draw()` is avoidable. Pyodide pays all of it at about 2.5×.
2. **Encoding a frame to JSON costs about as much as Cairo** and about a third of `draw()`: 3–12 ms for
   230–640 ops (mean 7.8 ms at scale 1 over the 8 loop examples). 70–80 % of that is building dicts in
   `op_to_jsonable`, not `json.dumps`.
3. **Text shaping is not in `draw()`.** Glyph outlines are re-transformed point by point on every frame
   inside the renderer (`TextRun.outline_ops`, no cache): 50–60 % of poster_series's Cairo time.

## Method

- The 10 heaviest examples from the cloud `bench.json`, plus Session-1 `06_animation` and `07_bounce`.
  studios-03 and studios-05 are scripts: their "frame" is the run plus the canvas flush.
- Backing scale 1 and 2, headless, `random_seed(0)`, run as `tests/conftest.py::run_sketch`. 12 timed
  frames after 3 warm-up (scripts: 5 runs after 1).
- Pass 1, timers only: `draw()`, `CairoRenderer.render`, `_render`, and encoding
  (`[op_to_jsonable(o)]` then `json.dumps`). Pass 2, cProfile (draw and render separately, bucketed by
  file, C builtins credited to the caller); cProfile slows Python 3–4×, so only shares are used.
- **Noise:** the machine was contended (Chrome running for S-142). Identical runs differed by up to
  1.5–2×; treat single numbers as ±30 %. Prototype timings are the minimum of 7 runs; micro-benchmarks
  interleave before and after.
- "User" is the sketch file's own time; library work it calls (`noise()`, `Vector`, `random`) counts as
  funground/library.

## Phase table, scale 1 (ms per frame, native)

| Example | ops | draw | user | Cairo | encode (objects + dumps) | api calls/frame |
|---|---:|---:|---:|---:|---:|---:|
| rangoli | 636 | 4.4 | 5% | 4.5 | 7.6 (5.2+2.4) | 2237 |
| kinetic_type | 633 | 35.1 | 5% | 6.4 | 9.6 (7.5+2.1) | 7599 |
| text_dots | 507 | 14.9 | 2% | 7.3 | 9.5 (7.6+1.8) | 4074 |
| noise | 419 | 15.7 | 3% | 1.8 | 7.7 (6.5+1.2) | 4340 |
| sound-02 write_a_tune | 413 | 86.9 | 1% | 5.7 | 9.4 (7.4+2.1) | 1313 |
| gaussian_and_choice | 401 | 10.0 | 4% | 4.6 | 9.3 (7.6+1.8) | 4808 |
| studios-03 rhythm (script) | 371 | 5.6 | 1% | 6.6 | 4.6 (3.7+0.9) | 267 |
| studios-05 text_as_geometry (script) | 290 | 14.0 | 0% | 4.9 | 11.8 (8.9+2.9) | 885 |
| paths-06 outlines | 249 | 12.9 | 2% | 7.8 | 6.8 (5.3+1.5) | 1544 |
| studios-06 poster_series | 229 | 6.1 | 3% | 22.8 | 2.9 (2.2+0.7) | 595 |
| session1 06_animation | 2 | 0.03 | 5% | 0.1 | 0.03 | 11 |
| session1 07_bounce | 2 | 0.02 | 7% | 0.1 | 0.04 | 10 |

Scale 2: draw and encode the same within noise; Cairo about 1.6× (rangoli 7.9, kinetic_type 10.2,
text_dots 9.8, gaussian 9.8, paths-06 13.0, poster_series 38.9 ms). Rows in `out/*_x2.json`.

| Mean of the 8 loop examples | draw | Cairo | encode |
|---|---:|---:|---:|
| scale 1 | 23.2 | 7.6 | 7.8 |
| scale 2 | 28.0 | 12.7 | 9.3 |

(The cloud's native scale-2 draw was 18.5 ms on a faster machine; sound-02 alone adds about 11 ms to
this mean.)

**Where `draw()` goes (ms of the 23.2 scale-1 mean):** `synth.py` (all sound-02) 10.1 ·
state/colour/geometry 4.2 · `dataclasses.replace` 2.5 · `sketch.py` methods 1.6 · `noise.py` 1.1 ·
random/math 0.9 · `api.py` wrappers 0.8 · user code 0.6 · skia-pathops 0.5 · everything else < 0.2 each.
A heavy frame makes 270–7600 API calls and 12k–250k Python function calls. A Session-1 sketch costs
0.02–0.08 ms: nothing here matters for it.

## Top hotspots (paths under `funground/`)

| # | Where | What | Share of draw | Class |
|---|---|---|---|---|
| 1 | `state.py:65 with_` via `state.py:96 update` → `dataclasses._replace` | every `fill`, `stroke`, `stroke_width` copies a 30-field frozen dataclass | 10–36 % | avoidable |
| 2 | `color.py:260 parse`, `:309 _parse_str`, `:365 parse_in_mode`, `:41 __post_init__`, `:328 _component`; from `sketch.py:1207`, `:1224`, `paint.py:47` | colour re-parsed and re-validated on every call | 10–25 % | avoidable |
| 3 | `vector.py:25 _number` (`isinstance(v, numbers.Real)` through the ABC machinery), `:59`, `:103` | every `Vector` validates two numbers | ~45 % of kinetic_type | avoidable |
| 4 | `sketch.py:1253`, `:1662`, `:1670`, `:809`, `:813`; `api.py:821`, `:1507`, `:150`, `:165` | 4–5 wrapper layers per shape | 10–25 % | partly avoidable; op construction itself ≤ 3 % |
| 5 | `noise.py:60 __call__` | pure-Python Perlin | 22 % of noise | inherent |
| 6 | `synth.py:654 find_pitch` (`sum()`) | called by the sketch every frame | 93 % of sound-02 | inherent as written; numpy could replace it |
| 7 | `pathops.py:43`, `:92`, `:19` | skia-pathops conversion | 19–25 % of paths-06, rangoli | mostly inherent |
| 8 | render: `typography.py:219 outline_ops` → `geometry.py:390 transformed`, `:68 apply` | glyph outlines transformed every frame, no cache | 50–60 % of Cairo in poster_series | avoidable |
| 9 | encode: `ir.py:333 op_to_jsonable`, `_fields_to_jsonable` | the 30-field style re-serialised per op though styles are shared | 3–12 ms | avoidable |

## Prototypes (monkeypatches in `prototypes.py` only)

- **P1** cache `Color._parse_str` per string · **P2** `GraphicsState.with_` from an `attrgetter` tuple and
  the positional constructor · **P3** `vector._number` fast path for exact int/float · **P4** cache of
  scaled glyph outlines in `TextRun.outline_ops`, then translate only · **E1** style table + flat
  per-op arrays as JSON · **E2** the same with a float64 binary stream for simple shapes.
- **Correctness:** on 7 examples, for P1–P4 singly and together, every frame's ops (dataclass equality)
  and the final pixels were identical to the unpatched run. E1 and E2 decode back to equal ops.

| Call (µs, min of 25 interleaved) | before | after | patch |
|---|---:|---:|---|
| `fill("tomato")` | 11.1 | 9.9 | P1 |
| `fill("#336699")` | 14.9 | 11.8 | P1 |
| `fill(200,100,50)` | 18.7 | 10.2 | P2 |
| `stroke_width(2)` | 20.5 | 7.2 | P2 |
| `fill("tomato")` | 13.8 | 6.6 | P1+P2 |
| `Vector(1.5, 2.5)` | 2.1 | 0.31 | P3 |

| Whole frame, scale 1, ms (min of 7) | draw before | draw P1–P4 | Cairo before | Cairo P4 |
|---|---:|---:|---:|---:|
| noise | 20.9 | 13.4 | 2.4 | — |
| text_dots | 17.0 | 10.0 | 8.3 | 5.8 |
| poster_series | 6.2 | 3.2 | 25.9 | **12.1** |
| rangoli | 7.5 | 5.9 | 6.7 | — |
| paths-06 | 11.0 | 7.7 | 6.8 | 4.7 |
| gaussian | ~6–8 | ~4–5.7 | 2.8 | — |
| kinetic_type | 38 | too noisy | | |

| Encoding the final frame (ms, size) | baseline | E1 table + JSON | E2 table + binary |
|---|---|---|---|
| gaussian (401 ops) | 5.4, 69 kB | 4.0, 53 kB | 4.4, 49 kB |
| noise (419) | 6.3, 69 kB | 5.2, 51 kB | 4.6, 60 kB |
| text_dots (507) | 8.3, 122 kB | 6.3, 102 kB | 6.1, 98 kB |
| kinetic_type (633) | 18.3, 136 kB | 12.9, 111 kB | 15.8, 93 kB |
| poster_series (229) | 1.4, 22 kB | 0.8, 14 kB | 0.8, 18 kB |
| rangoli (636) | 9.5, 150 kB | 3.4, 79 kB | 4.7, 80 kB |
| paths-06 (249) | 3.6, 57 kB | 3.0, 48 kB | 3.4, 52 kB |

Sharing styles cuts bytes 20–47 % and time 15–60 %. Binary is not clearly better than flat JSON: the
remaining cost is Python reading each op's attributes. A large gain needs fewer Python steps per op
(record flat tuples as the sketch calls are made). JS-side decode time not measured.

## Ranked recommendations

Native gains from the shares and prototypes above; Pyodide gains assume 2.5× on Python, 2.0× on Cairo,
and are **unverified**.

1. **State copy without `dataclasses.replace`** (P2, `state.py:65`), or skip when unchanged: 1–4 ms native
   (10–30 % of draw); Pyodide ~2.5–10 ms. Tiny; keep the error for an unknown field.
2. **Bounded cache for string colours, fast path for int tuples** (`color.py`): 0.5–3 ms; Pyodide
   ~1.5–7 ms. Tiny.
3. **Glyph-outline cache** (`typography.py:219`): up to 13 ms in poster_series, 2–3 ms in text_dots and
   paths-06; about 2× that in Pyodide. Identical pixels; helps Cairo, PDF/SVG and the desktop.
4. **Cheaper IR hand-over:** share styles (E1) now, then record flat tuples so `op_to_jsonable` never
   runs: 2–6 ms native (30–60 %); Pyodide ~5–15 ms. Needs a decoder in `ir_canvas.js` and a format
   version.
5. **`Vector._number` fast path** (`vector.py:25`; same checks in `marks.py:168`, `surface.py:48`): up to
   15 ms native (~45 % of kinetic_type). Tiny.
6. **Shorten the per-shape wrapper chain:** 0.5–2 ms per 400 shapes; Pyodide 1–5 ms. Moderate; touches
   the API plumbing, so a design decision.
7. **numpy for `find_pitch`** (`synth.py:654`): sound-02 from 87 ms to likely < 5 ms. Sound sketches only;
   needs a tolerance check.

Items 1, 2, 3 and 5 are cheap and behaviour-preserving: roughly 30–50 % off the draw mean, about
8–20 ms of the cloud's 46 ms in Pyodide. That alone does not reach a 12 ms browser frame for the
heaviest examples; that also needs items 4 and 6, or fewer and larger ops (an estimate, not measured).

## Open questions for the Pyodide half

1. Do these shares hold in Pyodide (`dataclasses.replace`, ABC `isinstance`, attribute access)?
2. Cost of `json.dumps`, `JSON.parse` and the canvas replay for each encoding.
3. `postMessage` cost: object array vs transferred `Float64Array`.
4. Does first-frame cost (imports, fonts, cold caches) matter more than steady state?
5. Does a bounded colour cache behave across `f.run()` re-runs in one interpreter?
6. Text on the web path stays as outlines (`fillText` breaks the T-rows and is excluded by the options
   note), so the glyph-outline cache (item 3) matters there too.
