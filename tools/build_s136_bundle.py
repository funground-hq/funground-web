r"""Build harness/s136/dist/ for the S-136 spike: the funground source as one zip, plus the sketches.

    C:\Projects\playground\.venv\Scripts\python.exe tools/build_s136_bundle.py

The zip holds funground/ from the playground-0.2 spike branch (FUNGROUND_CORE overrides the path)
without what Pyodide cannot run or the spike does not use: the SDL platform, the Cairo renderer (a
stand-in replaces it, see harness/s136/shim.py), file export, the gallery app, bundled fonts.
"""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

CORE = Path(os.environ.get("FUNGROUND_CORE", r"C:\Projects\playground-0.2"))
OUT = Path(__file__).resolve().parent.parent / "harness" / "s136" / "dist"
SKIP_DIRS = {"__pycache__", "export", "fonts"}
SKIP_FILES = {"platform/pygame_platform.py", "renderers/cairo2d.py", "gallery.py"}

HANG = '''import funground as f


def setup():
    f.size(640, 400)


def draw():
    f.background("white")
    if f.frame_count == 30:
        while True:
            pass


f.run()
'''

HANG_HB = """import time

import js
import funground as f


def setup():
    f.size(640, 400)


def draw():
    f.background("white")
    if f.frame_count == 30:
        t = time.perf_counter()
        while True:       # spins; tells the page it is alive every 5 ms
            if time.perf_counter() - t > 0.005:
                js.postMessage("hb")
                t = time.perf_counter()


f.run()
"""

STRESS = '''import math

import funground as f


def setup():
    f.size(640, 400)


def draw():
    f.background("white")
    f.no_stroke()
    for i in range(500):
        a = f.frame_count * 0.02 + i * 0.1
        f.fill(i % 255, 120, 255 - i % 255, 160)
        f.circle(320 + math.cos(a) * (i * 0.6), 200 + math.sin(a * 1.3) * (i * 0.35), 16)


f.run()
'''


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "sketches").mkdir(parents=True)
    src = CORE / "funground"
    n = size = 0
    with zipfile.ZipFile(OUT / "funground.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(CORE)
            inner = p.relative_to(src).as_posix()
            if not p.is_file() or SKIP_DIRS & set(p.relative_to(src).parts) or inner in SKIP_FILES:
                continue
            z.write(p, rel.as_posix())
            n += 1
            size += p.stat().st_size
    for p in (CORE / "examples" / "session1").glob("*.py"):
        shutil.copyfile(p, OUT / "sketches" / p.name)
    (OUT / "sketches" / "hang.py").write_text(HANG, encoding="utf-8")
    (OUT / "sketches" / "hang_hb.py").write_text(HANG_HB, encoding="utf-8")
    (OUT / "sketches" / "stress.py").write_text(STRESS, encoding="utf-8")
    print(f"{n} files, {size // 1024} KB raw, zip {(OUT / 'funground.zip').stat().st_size // 1024} KB -> {OUT}")


if __name__ == "__main__":
    main()
