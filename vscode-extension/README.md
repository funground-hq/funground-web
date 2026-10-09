# funground for VS Code (spike S-156)

Runs a funground sketch in a panel beside the editor, in github.dev, vscode.dev and VS Code. Run
**funground: Run** (or Ctrl+Enter, or the play button) on a Python file. The panel then follows the active
sketch, runs it again a moment after you stop typing and at once when you save, and shows `print()` output
and errors. An error's line is also underlined in the editor. Files in `data/` beside the sketch load
from the repository.

Status: a spike. Results, limits and how to try it: `../spikes/S-156_RESULTS.md`.

- Build: `python vscode-extension/build.py [--runtime bundled|site] [--pyodide DIR] [--site OUT] [--vsix]`
  (needs `runner/runtime/` from `tools/build_runtime.py`).
- Test: `cd vscode-extension/test && npm install && node run_tests.mjs --vscode static:<VS Code web build>`,
  then `python compare.py --funground <checkout> out/<label>`.
- Settings: `funground.autoRun`, `funground.autoRunDelay`, `funground.runtimeUrl` (empty: the copy inside
  the extension), `funground.randomSeed`.
- Known limits: the microphone (VS Code's webview frame does not allow it); pictures need pygame-ce, which
  the panel's Content Security Policy blocks unless it allows `'unsafe-eval'`.
