r"""Build harness/s142/dist/ for the S-142 spike.

    C:\Projects\playground\.venv\Scripts\python.exe tools/build_s142_bundle.py

Inputs (read only):
  FUNGROUND_SRC   a folder holding funground/ of the branch with the split loop (default
                  <scratch>/fg_s136, made with: git -C C:/Projects/playground-0.2 archive spike/s136-loop funground | tar -x)
  FUNGROUND_CORE  C:/Projects/playground-0.2 (examples/ and tests/golden/, unchanged by the loop branch)
  WHEELS          the CI artifact of funground-cairo-wasm run 37768002634 (pycairo, skia-pathops, uharfbuzz wheels)
Writes dist/funground.zip (funground/ with renderers/cairo2d.py, without platform/pygame_platform.py, gallery.py
and fonts/), dist/fonts/, dist/sketches/<case>.py, dist/wheels/ (pycairo, skia-pathops), dist/cases.json.
"""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path

SCRATCH = Path(r"C:\Users\samirj\AppData\Local\Temp\claude")
SRC = Path(os.environ.get("FUNGROUND_SRC", SCRATCH / "fg_s136"))
CORE = Path(os.environ.get("FUNGROUND_CORE", r"C:\Projects\playground-0.2"))
WHEELS = Path(os.environ.get("WHEELS", SCRATCH / "wheels142"))
OUT = Path(__file__).resolve().parent.parent / "harness" / "s142" / "dist"
SKIP_DIRS = {"__pycache__", "fonts"}
SKIP_FILES = {"platform/pygame_platform.py", "gallery.py"}

# The 10 heaviest gallery examples of the cloud bench (results/pyodide/bench.json "top", ops of the 30th frame)
HEAVY = [
    ("projects-02_rangoli", "loop"), ("projects-06_kinetic_type", "loop"), ("text-09_text_dots", "loop"),
    ("randomness-03_noise", "loop"), ("sound-02_write_a_tune", "loop"), ("randomness-02_gaussian_and_choice", "loop"),
    ("studios-03_rhythm", "script"), ("studios-05_text_as_geometry", "script"), ("paths-06_outlines", "loop"),
    ("studios-06_poster_series", "loop"),
]
TYPICAL = ["05_text", "06_animation", "07_bounce"]          # Session 1: text, a moving circle, a bouncing ball


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "sketches").mkdir(parents=True)
    (OUT / "fonts").mkdir()
    (OUT / "wheels").mkdir()
    src = SRC / "funground"
    n = size = 0
    with zipfile.ZipFile(OUT / "funground.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(src.rglob("*")):
            inner = p.relative_to(src).as_posix()
            if not p.is_file() or SKIP_DIRS & set(p.relative_to(src).parts) or inner in SKIP_FILES:
                continue
            z.write(p, p.relative_to(SRC).as_posix())
            n += 1
            size += p.stat().st_size
    for p in (src / "fonts").glob("*.ttf"):
        shutil.copyfile(p, OUT / "fonts" / p.name)
    (OUT / "fonts.json").write_text(json.dumps(sorted(f.name for f in (OUT / "fonts").glob("*.ttf"))), encoding="utf-8")
    for w in WHEELS.glob("*.whl"):
        if w.name.startswith(("pycairo", "skia_pathops")):
            shutil.copyfile(w, OUT / "wheels" / w.name)
    cases = []
    for cid, kind in HEAVY:
        cat, name = cid.split("-", 1)
        shutil.copyfile(CORE / "examples" / "gallery" / cat / f"{name}.py", OUT / "sketches" / f"{cid}.py")
        golden = CORE / "tests" / "golden" / "gallery" / f"{cid}.png"
        cases.append({"id": cid, "group": "heavy", "kind": kind, "golden": golden.name if golden.exists() else None,
                      "pygame": cid.startswith("sound-"),
                      "ink": cid.startswith("studios-")})          # marks measure ink with Cairo (see S-142_RESULTS)
    for name in TYPICAL:
        shutil.copyfile(CORE / "examples" / "session1" / f"{name}.py", OUT / "sketches" / f"s1-{name}.py")
        cases.append({"id": f"s1-{name}", "group": "typical", "kind": "loop", "golden": f"{name}.png", "pygame": False, "ink": False})
    (OUT / "cases.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")
    print(f"{n} files, {size // 1024} KB raw, zip {(OUT / 'funground.zip').stat().st_size // 1024} KB -> {OUT}")


if __name__ == "__main__":
    main()
