r"""Build harness/s133/dist/ for the S-133 spike: the funground source as one zip, the bundled fonts as
plain files (fetched one by one by the worker, so the sizes can be read), and the Session-1 sketches.

    C:\Projects\playground\.venv\Scripts\python.exe tools/build_s133_bundle.py

Like tools/build_s136_bundle.py (same exclusions) except that fonts/ stays out of the zip. The shim
(shim/uharfbuzz.py) and harfbuzzjs (vendor/harfbuzzjs/) are served from where they are in the repository.
tools/s133_corpus.py puts the extra test fonts in dist/extra/ (this script keeps them).
"""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

CORE = Path(os.environ.get("FUNGROUND_CORE", r"C:\Projects\playground-0.2"))
OUT = Path(__file__).resolve().parent.parent / "harness" / "s133" / "dist"
SKIP_DIRS = {"__pycache__", "export", "fonts"}
SKIP_FILES = {"platform/pygame_platform.py", "renderers/cairo2d.py", "gallery.py"}


def main() -> None:
    for sub in ("funground.zip", "fonts", "sketches"):
        p = OUT / sub
        shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
    (OUT / "sketches").mkdir(parents=True, exist_ok=True)
    (OUT / "fonts").mkdir(exist_ok=True)
    src = CORE / "funground"
    n = size = 0
    with zipfile.ZipFile(OUT / "funground.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(src.rglob("*")):
            inner = p.relative_to(src).as_posix()
            if not p.is_file() or SKIP_DIRS & set(p.relative_to(src).parts) or inner in SKIP_FILES:
                continue
            z.write(p, p.relative_to(CORE).as_posix())
            n += 1
            size += p.stat().st_size
    for p in (src / "fonts").glob("*.ttf"):
        shutil.copyfile(p, OUT / "fonts" / p.name)
    for p in (CORE / "examples" / "session1").glob("*.py"):
        shutil.copyfile(p, OUT / "sketches" / p.name)
    print(f"{n} files, {size // 1024} KB raw, zip {(OUT / 'funground.zip').stat().st_size // 1024} KB -> {OUT}")


if __name__ == "__main__":
    main()
