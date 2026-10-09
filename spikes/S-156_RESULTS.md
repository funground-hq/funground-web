# Spike S-156: a funground sketch beside github.dev

**Status:** done, 9 October 2026 (criteria set before any measurement, commit 6fbfb81). Branch
`claude/spike-s156-github-dev-x5szgv` of `funground-web` (the session's assigned branch; the brief named
`spike/s156-github-dev`).
Question and criteria come from funground `docs/design/Editor_Note.md` (last section, D-079 accepted as C) and the
maintainer's brief for this spike.

## Question

Can a learner edit and save a sketch in github.dev (GitHub's own web editor) and see it run on the same page?
Two ways: (1) a VS Code web extension with a preview panel running the S-153 runner; (2) github.dev framed inside
our own page.

## Criteria (set before the work)

| # | Question | Pass |
|---|---|---|
| Q1 | Can github.dev or vscode.dev be framed by another site? | Yes, or a clear no with the response header that forbids it |
| Q2 | Can a web extension's webview run the runner (Pyodide in a worker, the three C-extension wheels, a canvas, Web Audio, the microphone) under the webview's Content Security Policy? | A Session-1 sketch and a gallery example render with frames byte-identical to funground's goldens (as in S-153); a sound example produces audio buffers; the CSP needs nothing weaker than `'wasm-unsafe-eval'` (no `'unsafe-eval'`, no `'unsafe-inline'` scripts, no wildcard sources) |
| Q3 | Live update: re-run on edit (debounced) and on save, from the active file's text, with output and errors with line numbers | Under 1 s from a pause in typing to the new run's first frame, after the first load; an error's line is shown |
| Q4 | Data files: a sketch loading `data/photo.png` and a WAV from the repository (through `vscode.workspace.fs`) | Both load; the picture's pixels arrive unchanged |
| Q5 | Install path: sideload for testing, publishing for learners, how a template's `.vscode/extensions.json` recommendation appears | Documented, with the steps that are the maintainer's |
| Q6 | Size and load: the extension's size, runtime inside the extension or from a site with CORS, first-run time | Both measured (or one, with the reason), and a choice recommended |

Not a criterion here, recorded as found: the microphone (asked for "if possible").

## Answer in one paragraph

Yes, by way 1. A VS Code web extension (`vscode-extension/`, 55 KB plus the runtime) opens a panel beside the editor
and runs the unchanged S-153 runner in it: Pyodide in a worker, the real Cairo, HarfBuzz and Skia wheels, a canvas
and Web Audio. Frames are byte-identical to funground's goldens. The panel runs the sketch again about 0.4 s after the
learner stops typing, almost all of it the deliberate pause, and within 0.1 s of a save. Two things do not work as
they stand: **the microphone** (VS Code does not let a webview ask for it) and **pictures** (pygame-ce needs
`'unsafe-eval'`, which the panel's policy refuses; Pillow loads without it). Way 2, framing github.dev in our page, could not be
checked from here (Q1).

```
github.dev page (GitHub's origin)                               ┌ webview: its own origin, strict CSP ─────┐
┌ editor: sketches/bounce.py ───────────┐  text + data/ files   │  preview.js → runner.js                  │
│ typing ── 400 ms pause ──► extension.js├──── postMessage ─────►│    worker (blob:) : Pyodide + funground  │
│ Ctrl+S ─────────────────►  (web worker,│                       │    canvas · Web Audio · output           │
│ error line ◄── diagnostics   no Node)  │◄── traceback ─────────┤  (no microphone: not allowed by VS Code) │
└────────────────────────────────────────┘                      └──────────────────────────────────────────┘
Save = GitHub's commit. Sketch code never runs with the editor's rights.
```

## What was built

| Path | What |
|---|---|
| `vscode-extension/package.json`, `extension.js` | The extension: `"browser"` entry only (no Node APIs); command **funground: Run** (Ctrl+Enter, play button on Python files), **funground: Stop**; the panel follows the active Python editor, re-runs on edit (debounced, `funground.autoRunDelay`, 400 ms) and on save; `data/` beside the sketch read through `vscode.workspace.fs` (32 MB cap); an error's line becomes an editor diagnostic. Settings: `autoRun`, `autoRunDelay`, `runtimeUrl`, `randomSeed` |
| `vscode-extension/media/preview.js`, `.css` | The panel page: loads the runner, runs what the extension sends, shows output; records what it did for the tests (`window.fungroundPreview`) |
| `vscode-extension/build.py` | Standard library only. Copies the runner into `media/runner/`; puts together the runtime (Pyodide core plus micropip, fonttools, pygame-ce, Pillow, each checked against Pyodide's lock file; the four wheels from `runner/runtime/`; svgelements and pypdf from PyPI, checked against PyPI's SHA-256) inside the extension or as a site folder; writes a `.vsix` without vsce |
| `vscode-extension/test/` | `run_tests.mjs` (VS Code for the web from `@vscode/test-web`, driven by Playwright as a learner would: clicks in the Explorer, F1, typing, Ctrl+S), `compare.py` (goldens), `sketchbook/` (the sample) |
| `runner/runner.js`, `runner/worker.js` | Options the panel needs, all off by default so `demo.html` and the site behave as before: `pyodideUrl`, `runtimeUrl`; a worker started from a `blob:` URL when the runner's files are on another origin (a webview requires it); `seed`; wheels with role `dependency` installed from the runtime folder instead of PyPI; `spare` (keep the next worker loaded); **`reuse`** (below) |

**`reuse`: why re-running is fast.** Before, every run needed a new worker, so a new Python (about 6 s). The first
measured re-run on edit took 8 to 24 s. funground's `Session` already starts each sketch afresh (a new `Sketch`, a
new namespace) and `stop()` clears what it installed. So with `reuse` the page asks the worker to stop the sketch
(`stop` → `stopped`) and runs the next file in the same Python. A sketch that does not answer within 250 ms
(`while True:`) still has its worker ended. Evidence that a reused Python draws the same: in every run below,
booleans, bounce and text ran in the worker that had already run other sketches, and all were byte-identical. This
changes the runner's design ("a worker runs one file only"). Before the site uses it, funground should get a test
that two Sessions in one interpreter give the same frames as fresh ones (proposal for the funground session; not
applied there).

## How it was tested

- **VS Code for the web:** **1.141.0** built from `microsoft/vscode` (tag 1.141.0) in this sandbox: the development
  build (`--sourcesPath`) and the minified production bundle (`gulp vscode-web-min`); also the packaged
  `vscode-web` 1.91.1 from npm (July 2024) as an older reference. vscode.dev and github.dev serve the same
  workbench and webview code (`src/vs/workbench/contrib/webview/browser/pre/`); what differs is GitHub's file system
  and the Marketplace.
- `@vscode/test-web` 0.0.81 (server only), `playwright-core` 1.64.0, Chromium 141.0.7390.37 headless, Node 22.22.0 for
  the tests and 24.18.0 for building VS Code. Pyodide 314.0.7 (release tarball from GitHub), the
  funground-cairo-wasm v0.1.0-wasm wheels, the funground wheel from `release-0.2-web` a19e4c0
  (`tools/build_runtime.py`).
- **Not localhost.** VS Code's webview service worker handles requests to `localhost:<port>` and `127.0.0.1:<port>`
  specially. For a request from a worker (our `blob:` worker) it waits its 30 s timeout for an answer that never
  comes, then fetches directly (`processLocalhostRequest`). With `@vscode/test-web` on `localhost` every fetch the
  worker made waited 30 s, and Python took **216 s** to load instead of 6 s (1.141, both builds). vscode.dev,
  github.dev, the Marketplace's CDN and a runtime site are not localhost. So the measured runs serve VS Code at
  `vscode.localhost` and the runtime site at `runtime.localhost`: Chromium treats both as secure loopback names,
  and the localhost rule does not match them (`run_tests.mjs --host`). 1.91 does not have this behaviour.
- **Network:** this sandbox's policy blocks github.dev, vscode.dev, cdn.jsdelivr.net, open-vsx.org,
  marketplace.visualstudio.com, update.code.visualstudio.com and *.vscode-cdn.net. So everything was served
  locally, and no number here includes real network time. Bytes are given so transfer can be estimated.

## Results

### Q1: framing github.dev or vscode.dev: **not measured**

`curl -sI https://github.dev https://vscode.dev` from here gets the sandbox proxy's 403; the hosts are blocked.
No public record of their headers was found (research agent, sources below). **The maintainer can settle it in a
minute** on a network that reaches GitHub:

    curl -sI https://github.dev/ | grep -iE "x-frame-options|content-security-policy"
    curl -sI https://vscode.dev/ | grep -iE "x-frame-options|content-security-policy"

Pass if neither shows `X-Frame-Options` and no `frame-ancestors` excludes other sites. VS Code's own test server
sends `frame-ancestors 'none'` for downloaded builds (`@vscode/test-web` `app.js`), which suggests the products do
too. Way 2 would also leave github.dev's sign-in inside a third-party frame. Way 1 works, so Q1 decides nothing now.

### Q2: the runner in a webview: **pass** (the microphone excepted)

Frames against funground's goldens (`compare.py`, RGB byte for byte, frame 30, seed 0 via `funground.randomSeed`):

| Case | 1.141 min, bundled | 1.141 min, site | 1.141 dev build | 1.91 bundled | 1.91 site |
|---|---|---|---|---|---|
| Session 1 `01_first_sketch` | identical | identical | identical | identical | identical |
| Session 1 `07_bounce` | identical | identical | identical | identical | identical |
| gallery `paths-05_booleans` (skia-pathops) | identical | identical | identical | identical | identical |
| gallery `text-01_text` (HarfBuzz) | identical | identical | identical | identical | identical |

- **Sound:** `tune.py` (gallery sound-02) made two `load`s of 355,845 frames each, the same as S-137 measured. The
  page's `AudioContext` was unlocked (`unlocked: true`) and both voices were `playing`. Unlocking needed no click
  in the panel: VS Code's webview frame has `allow="autoplay"`, and typing or clicking in the editor counts as the
  gesture. No one has listened.
- **Microphone: not possible in a webview.** VS Code creates the webview frame with
  `allow="cross-origin-isolated; autoplay; local-network-access; clipboard-read; clipboard-write"`
  (`webviewElement.ts`, 1.141.0). Without `microphone` in that list, a cross-origin frame cannot call
  `getUserMedia`. Measured: even with Chromium's fake microphone set to allow, `listen.py` got the runner's refusal
  line and kept running at level 0. The line says "Allow it with the icon in the address bar", which is wrong in a
  panel and should get its own wording. An extension cannot change the frame. Ways round it, none tried: open the
  sketch in a browser tab on our site (`vscode.env.openExternal`), or ask VS Code to add the permission (an issue
  upstream).
- **Content Security Policy** (`extension.js`, `previewHtml`):
  `default-src 'none'; script-src 'nonce-…' <webview> [runtime site] 'wasm-unsafe-eval'; worker-src blob:;
  connect-src <webview> [runtime site]; style-src <webview>; img-src <webview> data: blob:`. No `'unsafe-eval'`, no
  inline script except the one with the nonce, no wildcard of ours (`<webview>` is VS Code's `cspSource`). That is
  enough for Pyodide, the three C-extension wheels, fonttools, Pillow and the funground wheel.
- **Except pygame-ce:** Emscripten links its side modules with `eval`, so `import pygame` fails with
  `EvalError: … 'unsafe-eval' is not an allowed source` and then `ImportError: … PyInit_base`. The C-extension wheels
  and Pillow do not do this (`pillow_check.py`: `PIL.Image loaded`, `pygame failed`). funground needs pygame-ce only
  for pictures in this runner (`imaging.py`). See Q4 and decision 1.

### Q3: live update: **pass**

Five edits each (typing a comment at the end of line 9 of `first_sketch.py`), then a save:

| | 1.141 min, bundled | 1.141 min, site | 1.91 bundled |
|---|---|---|---|
| last key → new run's first frame, ms (includes the 400 ms pause) | 378, 438, 386, 383, 415 | 437, 419, 412, 394, 427 | 396, 397, 453, 407, 392 |
| run sent → first frame, ms (the part that is not the pause) | 20, 46, 20, 17, 54 | 73, 51, 50, 28, 61 | 32, 32, 39, 48, 27 |
| Ctrl+S → first frame, ms | 68 | 94 | 32 |
| opening another sketch → its first frame, ms | 343 to 893 (tune.py 4,716: it synthesises its tune) | 222 to 850 (4,496) | 218 to 692 (4,908) |

"Last key" is read just after Playwright's last keystroke, which waits 30 ms per key, so the true figure is up to
about 30 ms larger. All are well under 1 s. Without `reuse`, the same edits took 7.3 to 24 s (1.91, first runs).
Errors: `oops.py` (`NameError` on line 10) shows the traceback from the learner's file down in the panel, and line 10
gets an error squiggle in the editor (one `.squiggly-error`). Saving in `@vscode/test-web` went to its in-memory
copy of the folder, not to disk. That is expected: in github.dev, saving is GitHub's commit.

### Q4: data files: **WAV pass; picture pass only with `'unsafe-eval'`**

- `visualiser.py` (gallery sound-01) loaded `data/tune.wav` from the workspace (132,300 frames) and played it in a
  loop.
- `photo.py` draws `data/photo.png` at its own size at (20, 20). Under the strict policy it fails at
  `f.load_image` (pygame-ce, Q2). With `'unsafe-eval'` added (test option `--csp unsafe-eval`, which patches a copy;
  the extension never asks for it) the drawn pixels equal the PNG's, byte for byte, on 1.141 and 1.91.

### Q5: install path: **documented** (the repository-carried route not yet tried)

From VS Code 1.141.0's source (`extensions.contribution.ts`, `workspaceRecommendations.ts`,
`extensionRecommendationNotificationService.ts`) and the VS Code docs (research agent):

1. **Sideload for testing: Developer: Install Extension from Location…** It is offered in VS Code for the web
   (`CONTEXT_HAS_WEB_SERVER`) and takes the URL of a folder holding the unpacked extension, served with CORS.
   **Install from VSIX… is not offered in the web** (only with a local or remote server). Serve the folder under a
   name that is not `localhost`/`127.0.0.1` (see "Not localhost"; the docs' `https://localhost:5000` would make
   every runtime fetch wait 30 s on 1.141), for example `https://funground.localhost:5000` with a mkcert
   certificate. Recent Chrome may ask to allow access to local network devices: allow it. Whether the install
   survives a reload, and whether github.dev offers the command as vscode.dev does, were not verified.
2. **Publishing for learners (the maintainer's act).** github.dev and vscode.dev install from the Visual Studio
   Marketplace (not Open VSX: that serves VSCodium, Gitpod, Theia and others; unverified that github.dev never
   uses it). Needs a publisher at marketplace.visualstudio.com/manage (the ID is permanent). Publishing is
   `vsce publish`, or uploading a `.vsix` on that page; `build.py --vsix` writes one without npm, but vsce's own
   packaging is safer for the first real publish. Global personal access tokens in Azure DevOps retire on
   1 December 2026; the docs recommend Microsoft Entra ID (`vsce publish --azure-credential`). vsce marks an
   extension web-compatible by itself when it has `browser` and no `main`, as this one does. Verified-publisher
   status needs a domain and 6 months. A first install from a new publisher shows VS Code's "trust this publisher"
   question (since 1.97). Open VSX is worth publishing to as well (an Eclipse account, its publisher agreement,
   `ovsx publish`).
3. **The template's recommendation.** `.vscode/extensions.json` `{"recommendations": ["funground-hq.funground"]}`
   makes VS Code show, the first time the repository is opened, a notification offering to install the recommended
   extensions for "this repository". The Extensions view lists it under recommendations. The id is looked up in the
   gallery, so this works only once the extension is published.
4. **Found in the source, not yet tried: an extension carried by the repository.** VS Code also recommends any
   extension folder under `.vscode/extensions/` of the opened repository, and in the web can install it into that
   workspace (`fetchWorkspaceExtensions`, `installResourceExtension`, allowed when the manifest can run on the web).
   That would need no Marketplace at all: the template would carry `.vscode/extensions/funground/` (55 KB with the
   runtime from our site). Unknowns: the trust question it shows, whether github.dev's GitHub file system serves its
   files to the webview fast enough (they would be `vscode-resource` requests, which from a worker hit the same
   service-worker path as localhost does, hence the site runtime), and that every learner's copy freezes the
   version their template had. Not tested: the test was stopped before it was written, at the maintainer's
   request. It is the next step (put the extension in the sketchbook's `.vscode/extensions/funground/`, start
   VS Code without development mode, press Install on the notification).

### Q6: size and load: **both measured**

| | Runtime in the extension | Runtime from a site (CORS) |
|---|---|---|
| Extension | 22,301,944 bytes unpacked; `.vsix` 14,989,317 bytes | 55,018 bytes |
| Runtime files | inside the extension: Pyodide part 17,365,378, wheels and manifest 4,881,548 | the same 22.2 MB on the site; 14,977,065 bytes gzip-compressed in all |
| What a plain sketch downloads | about 12.4 MB compressed (S-153; pygame-ce and Pillow only on demand) | the same |
| Python ready in the panel (1.141 min) | 5,673 ms (Pyodide 3,394, packages 395, wheels 1,190, check 647) | 5,590 ms (3,243, 412, 1,252, 629) |
| Run command → first frame | 7,934 ms | 8,022 ms |
| Webview policy | nothing extra | the site's origin in `script-src` and `connect-src` |
| An update to funground | republish the extension; learners update it | update the site; versioned paths keep old extensions working |
| Offline after install | yes | no (browser cache only) |

Local serving makes the two equal here. Over a real network they would differ by where the bytes come from (the
Marketplace's CDN or GitHub Pages), not by how many. S-153's estimate of 10 to 14 s for a first visit at 10 Mb/s
applies to both.

## Limits of this spike

- Nothing ran in real github.dev or vscode.dev (blocked here); the test host is the same workbench code with a
  local file system. GitHub's file system, the Marketplace CDN and real network times are untested.
- Chromium only (headless). Safari and Firefox were not tried; Firefox's webview frame lacks the clipboard permissions,
  irrelevant here.
- Nobody listened to the sound or looked at the panel; the screenshots in `test/out/` are local (git-ignored).
- `reuse` keeps Python state that funground does not reset: modules a sketch imports from the sketchbook would stay
  imported (not used by any sketch here), and memory is not measured. A sketch run twice in one worker gave
  identical frames in every case measured.
- `@vscode/test-web` runs the extension in development mode; Marketplace installation, publisher trust and
  workspace trust prompts were not exercised.

## Decisions for the maintainer (for the funground decision log; not applied)

**1. Pictures in the panel.** *Context:* `f.load_image` and the other picture functions use pygame-ce, which needs
`'unsafe-eval'`; without a decision, pictures fail in github.dev with an error at the line. *Options:* (a) keep
current behaviour (pictures do not work in the panel); (b) allow `'unsafe-eval'` in the panel's policy (measured:
works, pixels identical); (c) decode pictures with Pillow in funground (ADR-004's proposal; Pillow loads under the
strict policy, and would also drop pygame-ce, 1.53 MB, from the picture path). *Trade-offs:* (b) is one word and
loosens only the panel's own origin, which already runs arbitrary learner Python; but it is the one exception in
the policy, and Marketplace review may ask about it. (c) is a funground change with golden checks, and fixes the
website runner too. *Recommendation:* (c), with (b) as a stop-gap only if pictures are needed before (c) lands.
*Why:* the panel keeps a policy with no exceptions, and the same change shortens every picture sketch's load.

**2. Where the runtime comes from.** *Options:* (a) inside the extension (22 MB, works offline once installed,
updates by republishing); (b) from funground-hq.github.io with CORS (55 KB extension, one place to update, the site's
origin added to the policy); (c) both, site by default with a bundled fallback. *Recommendation:* (b), versioned
paths (`/runtime/0.2.0/`). *Why:* it measured the same; one copy to update; a repository-carried extension (Q5.4)
is only practical at 55 KB. What would change it: learners who must work offline, or a school network that blocks
GitHub Pages but not the Marketplace.

**3. How learners get it.** *Options:* (a) publish to the Visual Studio Marketplace (and Open VSX) as
`funground-hq.funground` and recommend it from the template; (b) the template carries the extension in
`.vscode/extensions/` (no publishing; to be tested first, Q5.4); (c) both. *Recommendation:* test (b) first: if
github.dev installs it with one click, it avoids a publisher account and token; publish (a) once the extension is
stable. Publishing and the publisher account are the maintainer's act.

**4. `reuse` in the runner.** Adopt it for the site and the editor too (a re-run in under 0.1 s instead of a new
Python), with a funground test that two Sessions in one interpreter match fresh ones. Decide alone in a
funground-web story once that test exists.

## Recommendation

Go with way 1. A funground web extension is the way to "edit in github.dev, see it beside": it passes Q2 (apart
from the microphone), Q3 and Q6, and Q4 for sound. Before learners use it, (1) decide pictures (decision 1),
(2) try it in real github.dev (steps below), (3) choose the install route (decision 3). The microphone needs either
a browser tab or a change in VS Code; sketches that listen should keep running on the website and the desktop for
now. Keep the one-page editor (S-151 part 2) for learners without GitHub, sharing the same runner.

## Try it in real github.dev (the maintainer, on a network that reaches GitHub)

1. Build: `C:\Projects\playground\.venv\Scripts\python.exe tools\build_runtime.py --funground C:\Projects\playground-0.2`,
   then `C:\Projects\playground\.venv\Scripts\python.exe vscode-extension\build.py` (the runtime inside; it
   downloads Pyodide's files from jsDelivr, or give `--pyodide <unpacked Pyodide 314.0.7 release>`).
2. Serve `vscode-extension\` over HTTPS with CORS under a name that is not `localhost` (for example
   `https://funground.localhost:5000` with a mkcert certificate, or any HTTPS host you control). The folder needs
   `package.json`, `extension.js` and `media/`.
3. Open a sketchbook repository in github.dev (press `.` on its GitHub page). Copy `test/sketchbook/` into a test
   repository for the same cases.
4. F1 → **Developer: Install Extension from Location…** → paste the URL → Install (allow local network access if
   Chrome asks).
5. Open `first_sketch.py`, press Ctrl+Enter (or the play button). Expect: Python ready in about 6 s plus the download,
   a red circle, then a re-run about half a second after you stop typing.
6. Try `visualiser.py` and `tune.py` (sound, after a click in the editor), `oops.py` (line 10 underlined),
   `photo.py` (fails until decision 1), `listen.py` (the refusal line). Commit a change with GitHub's Source Control
   view: that is Save.
7. Also run the two `curl -sI` lines of Q1, and report what happens at step 4 if github.dev does not offer the
   command.

## How to repeat

    cd vscode-extension/test && npm install
    python ../build.py --pyodide <Pyodide 314.0.7> [--runtime site --site <dir>]
    node run_tests.mjs --vscode static:<VS Code web build> [--runtime site:<dir>] [--csp unsafe-eval] [--host localhost] --label NAME
    python compare.py --funground <funground checkout> out/NAME

A VS Code web build: `microsoft/vscode` at tag 1.141.0 with Node 24.18.0, `npm ci`, `npm run compile`,
`npm run compile-web` (`--vscode sources:<checkout>`), or `npm run gulp vscode-web-min` (`--vscode
static:<checkout>/../vscode-web`). Workarounds needed in this sandbox, because its network blocks electronjs.org and
api.github.com: in `.npmrc` and `remote/.npmrc`, `disturl=https://nodejs.org/dist`, `target=24.18.0`,
`runtime=node` (native modules are built but unused in the web); `electron.d.ts` v43.7.7 downloaded from the
GitHub release into `.build/typings/` (its SHA-256 matches `build/checksums/electron.txt`); the ripgrep v15.0.1 musl
archive placed in `/tmp/vscode-ripgrep-cache-1.17.1/`; apt `libkrb5-dev libx11-dev libxkbfile-dev libsecret-1-dev`.
Or the npm package `vscode-web@1.91.1` (`--vscode static:<package>/dist`).

## Sources

- VS Code 1.141.0 source: `src/vs/workbench/contrib/webview/browser/webviewElement.ts` (frame `allow`),
  `…/webview/browser/pre/service-worker.js` (localhost and worker requests), `…/webview/common/webview.ts`
  (`asWebviewUri`), `…/extensions/browser/extensions.contribution.ts`, `workspaceRecommendations.ts`,
  `extensionRecommendationNotificationService.ts`, `services/extensionManagement/common/extensionManagementService.ts`.
- VS Code docs (from `microsoft/vscode-docs`): `api/extension-guides/web-extensions.md`, `webview.md`,
  `api/working-with-extensions/publishing-extension.md`, `docs/configure/extensions/extension-marketplace.md`.
- Raw numbers: `vscode-extension/test/out/<label>/report.json` (git-ignored; regenerate with the commands above).

## Who did what

Main session: design, the extension, the runner options, the test harness, every measurement and this document.
A Sonnet research agent: the docs and publishing facts in Q5 (sources above). A Sonnet agent: the VS Code
1.141.0 source build and its workarounds.
