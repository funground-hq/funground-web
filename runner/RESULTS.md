# Runner results (story S-153)

Measured on 9 October 2026 on the maintainer's Windows machine (slow, short of memory), headless Chrome with its own
temporary profile, `tools/test_runner.py` and `tools/check_on_demand.py` at funground branch `release-0.2-web`
(runtime built by `tools/build_runtime.py`). Pyodide 314.0.7 from jsDelivr, pygame-ce 2.5.7, Pillow 12.2.0.

**Noise.** The machine's own Chrome and other programs may have been running, and Pyodide came over the real
network from jsDelivr (everything else from localhost). Runs of the same thing differ by 1 to 2 s; read the
numbers as a range, not as a figure. Bytes do not vary.

## 1. Pixels against the goldens

Criterion: the runner's frame is byte-identical to the golden at 1x (frame 30 of a sketch, the first frame of a
script; the random generator is seeded with 0 as in funground's `tests/conftest.py`; the canvas is copied in the
frame callback, at exactly that frame).

| Case | Result |
|---|---|
| Session 1: 01 to 10 | 10 of 10 identical |
| text-01, paths-05, basics-03 (script), studios-03 (A4 script, 842 x 595) | 4 of 4 identical |
| images-01 | **not identical**: 50,454 of 256,000 pixels differ (largest channel difference 87) |

images-01 cause: Pyodide's pygame-ce (and its Pillow) decode a JPEG differently from the desktop build. In the same
page, `pygame.image.load` and `PIL.Image.open` agree with each other (MD5 `3bf4a6a5...`), the desktop pair agrees
with each other (MD5 `973d358e...`), and the two pairs differ; the same picture saved as PNG decodes to the same
bytes in both (`funground.imaging.decode`, MD5 `ae3903b3...`). So the runner, Cairo and the renderer are exact; only
the JPEG decoder (a different libjpeg build, probably its chroma upsampling) differs, in the edges of colour areas.
It is not fixable in the runner. Proposals for the funground session, none applied: (a) accept it and record a
web golden or a tolerance for JPEG sketches; (b) decode JPEG with a decoder that is the same everywhere (a pure-Python
or a pinned decoder; see ADR-004); (c) make the gallery's photo a PNG.

Stop, errors, a syntax error and input events also pass (`tests/out/report.json`, "scenarios").

Fractional scale, `--dpr 1.25` (no golden at that scale): all 15 cases give a frame of the golden's size times 1.25
(800 x 500; studios-03 1052 x 744 for 1052.5 x 743.75), none blank (64 to 24,283 colours). The two wipe bugs fixed
after the maintainer's hand test (canvas size from the frames only) do not recur.

## 2. First load against the S-139 budget

Criteria (S-139): first visit at most 10 s on a 10 Mb/s link (estimated from bytes); repeat visit at most 3 s.
Time to first frame = page start to the first frame of a plain sketch (Session 1 `01_first_sketch`).

Bytes (compressed, as fetched; `encodedBodySize`), a sketch that needs no pictures or sound:

| Piece | Bytes |
|---|---|
| Pyodide core (`pyodide.asm.wasm` 3.44 MB, `python_stdlib.zip` 2.51 MB, loader, lock file) | 6,237,877 |
| Pyodide packages: micropip 0.11 MB, fonttools 1.12 MB | 1,232,204 |
| C-extension wheels: pycairo 0.50 MB, uharfbuzz 0.98 MB, skia-pathops 0.17 MB | 1,651,165 |
| funground wheel (code 0.28 MB, **fonts 2.42 MB**) | 2,727,330 |
| svgelements, pypdf from PyPI (sizes from PyPI; the browser does not report them) | 533,336 |
| **Total** | **12,381,912** |
| Loaded only when a sketch needs them: pygame-ce 1.53 MB, Pillow 1.03 MB | 2,555,559 |

Time to first frame, plain sketch, three runs each way, old worker (pygame-ce and Pillow always) and new worker
(on demand), alternating:

| | Old (always) | New (on demand) |
|---|---|---|
| Cold (new profile), s | 8.9, 8.7, 8.3 | 7.7, 6.9, 7.9 |
| Warm (profile reused), s | 3.8, 3.5, 3.4 | 4.5, 3.8, 3.5 |

Other runs of the new worker: cold 9.2 to 10.3 s, warm 3.3 to 5.5 s (the machine was busier). Where a warm run goes
(s): Pyodide start 1.4 to 2.8, packages 0.2 to 0.4, wheels 0.9 to 1.4 (unpacking the funground wheel), check 0.4.
A sketch that loads a picture adds about 1.2 s cold and 0.25 s warm for pygame-ce and Pillow.

Against the budget:

- **First visit, 10 Mb/s: not met on this estimate.** 12.4 MB is 9.9 s of transfer at 1.25 MB/s, before about 4 s of
  start-up that only partly overlaps it: about 10 to 14 s. Loading pygame-ce and Pillow on demand saves 2.56 MB
  (2.0 s of transfer; 1.1 s measured here, where the network is faster).
- **Repeat visit, 3 s: not met on this machine** (3.3 to 5.5 s); the bytes come from the cache, the time is
  Pyodide's start-up and unpacking, which a faster machine shortens. Unmeasured: how a real site with long cache
  headers and compression behaves; `tools/test_runner.py`'s server sends neither.
- Largest levers left, none applied: the bundled fonts (2.42 MB of the funground wheel, unpacked on every start),
  fonttools (1.12 MB), and Pyodide's core (6.2 MB, fixed).

## 3. pygame-ce on demand

funground imports pygame only in `imaging.py` (pictures: `load_image`, `get`, `load_pixels`, `update_pixels`,
`filter`, `Picture.resize`, `Picture.mask`, and `tint` through the renderer), `sound.py` and
`microphone_input.py` (sound), and in `platform/pygame_platform.py` (the desktop window, never used here).
Every other sketch runs without it. `runner/worker.js` now loads it (with Pillow, for the picture group) only when
the file calls one of those functions. `tools/check_on_demand.py` fails if a public funground function imports
`imaging`, `sound`, `sound_views` or `microphone_input` and is not listed. Needs no funground change.

Proposal (not applied; it changes funground): if `imaging` decoded with Pillow instead of pygame-ce (ADR-004), pictures
would need Pillow only (1.03 MB) and pygame-ce (1.53 MB) would be needed for sound only, which is S-137.

## How to repeat

    C:\Projects\playground\.venv\Scripts\python.exe tools/build_runtime.py --funground C:\Projects\playground-0.2
    C:\Projects\playground\.venv\Scripts\python.exe tools/test_runner.py --funground C:\Projects\playground-0.2
    C:\Projects\playground\.venv\Scripts\python.exe tools/test_runner.py --funground C:\Projects\playground-0.2 --dpr 1.25 --skip-scenarios
    C:\Projects\playground\.venv\Scripts\python.exe tools/test_runner.py --funground C:\Projects\playground-0.2 --limit 1 --skip-scenarios [--profile DIR]
    C:\Projects\playground\.venv\Scripts\python.exe tools/check_on_demand.py --funground C:\Projects\playground-0.2

The last-but-one is the first-load run (twice with the same `--profile` for a warm one); `report.json` has
`first_frame_ms`, the per-stage timings in `ready.timings` and the fetched bytes in `ready.resources`.

## 4. Sound and the microphone (story S-137)

Measured on 9 October 2026, same machine and Chrome as above; `tools/test_sound.py` (Chrome with
`--autoplay-policy=no-user-gesture-required`, `--use-fake-device-for-media-stream`, `--use-fake-ui-for-media-stream`,
own temporary profile).

- **Samples.** For 7 gallery examples (sound-01, 02, 03, music-01, 04, 05, 11) the sounds the page received match what
  CPython's `Session` made for the same file: the same count and the same frames in each (for example sound-02:
  355,845 frames, twice), and at least as many plays. The unit tests (`tests/test_web_sound.py` in funground) go
  further: the float samples the host receives equal pygame's 16-bit samples divided by 32768, for tone, square tone,
  melody, sargam melody, raga drone and mix.
- **Audible.** A tap on the speakers (an AnalyserNode on the destination) saw a peak of 0.50 to 0.68 for each of the 7
  examples, and a voice was playing at the end of each.
- **Microphone.** With Chrome's fake microphone, a sketch that only listens saw `level()` rise to 0.55 and `pitch()` of
  about 400 Hz (the fake device's beep) within seconds; the gallery tuner ran with the microphone listening and no
  error.
- **Before a gesture.** With Chrome's default autoplay policy and no click, sound-02 ran with one output line ("Sound is
  off until you click or press a key...") and no error.
- **Download saved.** pygame-ce (1.53 MB compressed, section 3) is no longer loaded for a sketch that plays sound or
  uses the microphone: 1.53 MB less to fetch. Section 3 measured about 1.2 s cold for pygame-ce and Pillow together, so
  that is an upper bound on the time saved (pygame-ce alone was not timed). The funground wheel grew by about 5 KB
  (2,727,330 to 2,732,325 bytes). A sketch that calls `f.spectrogram` still loads both packages (it makes a picture).
- **Not measured:** latency from a call to the sound at the ear; a real microphone; any browser but Chrome; listening
  quality. Those are the maintainer's (README, "Try the sound").

How to repeat: `tools/build_runtime.py --funground <checkout> --offline`, then `tools/test_sound.py --funground <checkout>`.
