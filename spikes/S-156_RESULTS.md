# Spike S-156: a funground sketch beside github.dev

**Status:** criteria set 9 October 2026, before any measurement; results below are filled in as measured.
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

How it is tested: `@vscode/test-web` serves VS Code for the web (the same workbench and webview code as vscode.dev and
github.dev, with a local file system in place of GitHub's) and the extension in development mode; Playwright drives
headless Chromium as a learner would (Ctrl+P to open a sketch, F1 "funground: Run", typing, Ctrl+S). The final check
in real github.dev is the maintainer's (steps at the end).
