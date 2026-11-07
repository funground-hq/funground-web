r"""Check that runner/files.json names every script the runner loads.

    C:\Projects\playground\.venv\Scripts\python.exe tools/check_runner_files.py

A site that serves the runner copies the scripts that runner/files.json names, and runtime/. If a script loads one
that is not named, the site does not have it, and Python cannot start in Play. That happened on 7 Nov 2026:
models-worker.js and models-glue.js were added, and the site's own list did not have them, so every sketch stopped
with a 404. This check fails, before anything is published, when:

  * a named file is missing from runner/;
  * a script in runner/ is not named;
  * a named script refers to a script beside it ("./audio.js", new URL("models-worker.js", ...)) that is not named.

A reference is a quoted file name ending in .js or .mjs with no folder in it, so a module loaded from a CDN folder
(pyodideUrl + "pyodide.mjs") is counted too and must be left out by EXTERNAL. tools/build_runtime.py runs this
first. Standard library only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = REPO / "runner"
LIST = RUNNER / "files.json"
# A quoted script name with no folder: "audio.js", './audio.js', `models-glue.js`.
REFERENCE = re.compile(r"""["'`](?:\./)?([A-Za-z0-9_.-]+\.m?js)["'`]""")
# Loaded from their own folders, not from the runner: Pyodide (worker.js, pyodideUrl + "pyodide.mjs") and onnxruntime-web
# (models-worker.js, settings.onnxruntimeUrl + "ort.wasm.mjs").
EXTERNAL = {"pyodide.mjs", "ort.wasm.mjs"}


def named_files(runner: Path = RUNNER) -> list[str]:
    """The scripts runner/files.json names, in its order."""
    return json.loads((runner / "files.json").read_text(encoding="utf-8"))["files"]


def problems(runner: Path = RUNNER) -> list[str]:
    """What is wrong with the list, one sentence each; empty when it is right."""
    named = named_files(runner)
    found = []
    for name in named:
        if not (runner / name).is_file():
            found.append(f"files.json names {name}, which is not in runner/")
    for path in sorted(runner.glob("*.*js")):
        if path.name not in named:
            found.append(f"runner/{path.name} is not in files.json: a site serving the runner would leave it out")
    for name in named:
        path = runner / name
        if not path.is_file():
            continue
        for used in sorted(set(REFERENCE.findall(path.read_text(encoding="utf-8"))) - EXTERNAL):
            if used not in named:
                found.append(f"{name} loads {used}, which is not in files.json")
    return found


def main() -> None:
    found = problems()
    for line in found:
        print(line, file=sys.stderr)
    if found:
        raise SystemExit(f"runner/files.json is out of date ({len(found)} problem{'s' if len(found) > 1 else ''})")
    print(f"runner/files.json names all {len(named_files())} of the runner's scripts")


if __name__ == "__main__":
    main()
