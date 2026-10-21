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

**Decided (D-101 a, 18 Oct 2026):** accepted. `tools/test_runner.py` compares a sketch that names a JPEG with a
tolerance (mean difference at most 1, 99th percentile at most 16; measured 0.57 and 9), every other sketch exactly, and a
frame outside its tolerance now fails the run. images-08 (a 160 x 120 GIF drawn at 480 x 360) differs by 1 in two corner
pixels, measured; it has its own tolerance of one step, cause unverified (perhaps pixman's scaling with and without SIMD).

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

## 5. Fonts on demand (story S-211) and saved files (story S-212)

Measured on 15 October 2026, same machine, funground at branch `sprint-27` (`C:\Projects\playground`), runtime built with
`tools/build_runtime.py --funground C:\Projects\playground --offline`. Sizes are bytes from the manifest and the built files.

### How funground finds its fonts

`funground/typography.py` has `FONT_DIR`, the `fonts/` folder beside the module, and `DEFAULT_FONT` (`DejaVuSans.ttf`) in it.
`FontResource(path)` opens a font with `TTFont(path)` and `open(path, "rb")` (the HarfBuzz face is made from all the bytes). The
four DejaVu styles are opened by name from `FONT_DIR` (`_registry`, line 764); the three Noto fallbacks (emoji, symbols,
Devanagari) are opened by `_bundled(name)` the first time `_itemise` needs a character the earlier fonts lack. So every bundled
font is opened at one moment: the first time a sketch draws text that needs it. Text is drawn from many places, not only
`f.text`: `api`, `controls`, `marks`, `formatted`, `exploring`, `sound`, and the PDF/SVG text exporters all import
`typography`. funground does not copy the fonts anywhere; it reads `FONT_DIR`.

### The options

| | (a) a package group, like `ON_DEMAND` | (b) a lazy file at the path funground opens | (c) fonts as a second wheel |
|---|---|---|---|
| How | wheel without fonts; `worker.js` fetches them before the run when the source "uses text" | wheel without fonts; each font is an Emscripten lazy file in `FONT_DIR`: the browser fetches it, with a synchronous request in the worker, the first time Python opens it | a `funground-fonts` wheel installed when the source uses text |
| Decides from | the source text: a name list | what funground really opens | the source text: a name list |
| Complete? | only if the list is: any public name that reaches `typography` (dozens in `api.py`, and the ones that draw text without being asked: labels, page numbers, controls) must be on it. A missing one is a crash with `FileNotFoundError`, the `apply_filter` bug again | by construction: if Python opens it, it is fetched | as (a) |
| Fonts fetched | all of them, or the list's choice | only the ones opened (DejaVu Sans for plain text; a Noto font only for its characters) | all of them |
| Change to funground | none | none (the folder and file names are the ones funground reads) | none |
| Cost | list to keep in step; `check_on_demand.py` would grow a typography walker | needs a server that answers HEAD (and ideally Range); one more request per font; no hash check at read time | as (a), plus a wheel |

**Recommendation: (b).** It cannot be incomplete, because there is no list: the manifest lists the files of `funground/fonts/`
(read from the folder at build time), and funground decides which it opens. It fetches the least: a plain-text sketch fetches
one font (757,076 bytes), an emoji sketch adds the emoji font only when an emoji is drawn. It needs no change to funground.
It is idiomatic Emscripten (`FS.createLazyFile`), about ten lines in `worker.js` (`addLazyFonts`).

Details that matter:

- The fonts are served as `fonts/<name>.ttf.bin`. A lazy file takes its length from a `HEAD` request and its content from the
  `GET` (in ranges when the server says `Accept-Ranges: bytes`); a host that compresses `font/ttf` on the way would make the
  two disagree. `.bin` is `application/octet-stream`, which static hosts leave alone. The price: a font travels uncompressed
  (DejaVu Sans 757,076 bytes; 381,603 deflated). Measured with plain `zlib` level 9, all seven fonts deflate to 2,383,154 bytes.
- Fail-safe: a lazy file trusts the host. `worker.js` probes one font with `HEAD`; if it is not ok, its `Content-Length` is not the
  manifest size, or it has a `Content-Encoding`, all fonts are fetched at start-up instead, checked (size and SHA-256) and
  written to the same paths (`runner.info.fonts` is `"eager"`). Cross-origin only the safelisted `Content-Length` is readable, which
  is enough: a compressed font has another length. Tested by serving a wrong `Content-Length` for one scenario.
- `HEAD` and `GET` are two requests per font.
- A font is cached in memory for the life of the worker; a reused worker (`reuse`) does not fetch it again.

**Superseded (D-114 b, decided 18 Oct 2026, built 21 Oct).** On GitHub Pages the probe always failed (Pages compresses the
fonts), so Play fetched all seven fonts at start-up. Now there is one way on every host: funground has a private hook
(`typography._ensure_bundled`, called where every bundled font is opened) and the Session takes `fetch_font` and the manifest's
`fonts`. The worker passes a synchronous `XMLHttpRequest` (allowed in a worker; the browser undoes the compression); funground
checks size and SHA-256 and writes the font to its folder, once per worker. No `HEAD`, no ranges, no lazy files, no eager
path. `runner.info.fonts` is `"on open"`. Tested (`tools/test_runner.py`, 21 Oct): a no-text sketch fetches no font; text
fetches DejaVu Sans only; a server that gzips the fonts, as Pages does, still fetches only what a sketch uses and the text
renders; a font with one changed byte gives an error naming it. Start-up time on the live site: to be measured after deploy.
- Integrity: the manifest has each font's SHA-256 (the build writes it), but a lazy file is read by Emscripten, so the runner
  does not check it when it reads.

### Numbers

| | Bytes |
|---|---|
| funground wheel, with fonts (as before) | 2,877,437 |
| funground wheel, without fonts | 458,698 |
| **Saved on every first load** | **2,418,739** (the fonts, deflated, in the wheel) |
| Plain-text sketch fetches | 757,076 (`DejaVuSans.ttf`), at the moment text is drawn |
| Emoji and Devanagari text adds | 886,628 + 671,568 (symbols are tried too) + 243,520 |
| Sum of all seven fonts, raw | 4,543,184 |

The first load for a sketch with no text is the earlier 12,381,912 bytes (S-153; the funground wheel has grown since, so the
comparison is on the wheel alone) minus 2.42 MB: about **10.1 MB** instead of 12.5 MB, 19 per cent less, 1.9 s of transfer at
10 Mb/s. A sketch with text costs about 10.9 MB, still 1.6 MB under the budget measured before. Unpacking the wheel also takes
less time, because 4.5 MB of fonts are no longer written into the file system on every start. Not measured here: seconds. The
test machine's timings vary by 1 to 2 s (section 2), more than the saving in time.

### Tests (`tools/test_runner.py`, scenario "fonts on demand")

The server logs every request. Each sketch runs in a fresh worker. Checks, all in `report.json` under `checks`:

1. a sketch that draws only a circle makes no request under `runtime/fonts/` (no `HEAD`, no `GET`);
2. a sketch that draws `Hello` fetches `DejaVuSans.ttf` and no Noto font;
3. a sketch that draws an emoji and Devanagari fetches `NotoEmoji-Regular` and `NotoSansDevanagari-Regular`;
4. a script lists `FONT_DIR` and reads every `.ttf` in it: each of the manifest's fonts is there at its manifest size. This is
   the completeness test: whatever `build_runtime.py` finds in `funground/fonts/` must be readable by funground.

`text-01_text` and the other gallery cases still match their goldens byte for byte, so text, `text_box` and the rest draw the
same. The SVG/PDF text exporters read the same files and are covered by funground's own tests; a browser run of them is
not part of these cases.

### Files the sketch saves (S-212)

After each step, after a script's last line, and after `stop`'s `finish()`, the worker lists the run's folder (name, size,
modified time) and sends each file that is new or changed since the last listing, except the names in `files`. No hook in
funground is needed (a listing takes microseconds). Checks: a loop sketch that calls `f.save("out.png")` and `f.save("out.pdf")`
gives two `onFile` calls, once each (the loop goes on for 0.7 s afterwards), with `\x89PNG\r\n\x1a\n` and `%PDF-` at the start
and the types `image/png` and `application/pdf`; a script's `f.save("pic.svg")` and `f.save("pic.gif")` arrive as `image/svg+xml`
(containing `<svg`) and `image/gif` (`GIF8`). A GIF needs Pillow, which was not loaded for a source that only says `.gif`:
`worker.js` now loads it for `save_gif(` and for a `.gif` in the source (it found no other way to know the file name). An MP4
needs ffmpeg and cannot be made in a browser: funground raises its own "cannot find ffmpeg" error.

Limits: without `reuse`, `stop()` ends the worker at once, so only files seen after earlier steps arrive (a `finish()` that
saves does not run); with `reuse`, the worker finishes the sketch and lists the folder once more. A save that changes a file
twice between two listings is seen once.
