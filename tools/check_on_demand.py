r"""Check that runner/worker.js loads pygame-ce for every function that needs it (story S-153).

    C:\Projects\playground\.venv\Scripts\python.exe tools/check_on_demand.py --funground C:\Projects\playground-0.2

The worker loads pygame-ce only when a sketch calls a function listed in its ON_DEMAND table, because a Python
import cannot wait for a download. The table must therefore name every public function that, inside its body,
imports a funground module that imports pygame (`imaging`). This script finds those functions in the checkout by
reading its source (no import, so no pygame is needed) and fails if one is missing from the table. Sound and the
microphone need no pygame under the runner (S-137: funground plays through the page), so `sound`, `sound_views` and
`microphone_input` are not on the list; tests/test_web_sound.py in funground checks that a Session imports no
pygame. Two names reach `imaging` indirectly and are in the table by hand: `tint` (from the renderer) and
`spectrogram` (which makes its picture with load_pixels).
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
USES_PYGAME = {"imaging"}                                  # funground modules that import pygame under the runner


def functions_needing_pygame(package: Path) -> dict[str, str]:
    """Public function or method name -> the file that holds it, for each one importing a pygame module in its body."""
    found: dict[str, str] = {}
    for path in sorted(package.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.ImportFrom) and imported_modules(inner) & USES_PYGAME:
                    found[node.name] = path.relative_to(package).as_posix()
    return found


def imported_modules(node: ast.ImportFrom) -> set[str]:
    """`from . import sound` imports sound; `from .imaging import x` imports imaging."""
    if node.level and node.module is None:
        return {alias.name for alias in node.names}
    return {node.module.split(".")[-1]} if node.module else set()


def listed_calls(worker: Path) -> set[str]:
    """The names in the `calls: [...]` lists of worker.js."""
    text = worker.read_text(encoding="utf-8")
    lists = re.findall(r"calls:\s*\[(.*?)\]", text, re.S)
    return {name for items in lists for name in re.findall(r'"([A-Za-z_0-9]+)"', items)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--funground", required=True, type=Path, help="a funground checkout")
    args = parser.parse_args()
    needed = functions_needing_pygame(args.funground / "funground")
    listed = listed_calls(REPO / "runner" / "worker.js")
    missing = {name: where for name, where in needed.items() if name not in listed}
    for name, where in sorted(missing.items()):
        print(f"missing from ON_DEMAND in worker.js: {name} ({where})")
    print(f"{len(needed)} functions need pygame; {len(listed)} names listed; {len(missing)} missing")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
