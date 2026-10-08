r"""Record every text shaping call a funground sketch makes (native desktop run, S-133).

    C:\Projects\playground\.venv\Scripts\python.exe tools/s133_record.py SKETCH.py OUT.jsonl

Runs the sketch headless for 30 frames, as the golden tests do (tests/conftest.py run_sketch), with
FontResource.shape wrapped, and appends one JSON line per distinct call: font, face, text, tracking,
features, variations, fallback. Used by tools/s133_corpus.py, one process per sketch.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CORE = Path(os.environ.get("FUNGROUND_CORE", r"C:\Projects\playground-0.2"))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["FUNGROUND_HEADLESS"] = "1"
sys.path.insert(0, str(CORE / "tests"))
sys.path.insert(0, str(CORE))


def main(sketch: str, out: str) -> None:
    out = os.path.abspath(out)
    import conftest
    from funground import typography as ty

    seen: dict = {}
    original = ty.FontResource.shape

    def shape(self, text, size, tracking=0.0, features=(), variations=(), fallback=None):
        path = os.path.abspath(self.path)
        font_dir = os.path.abspath(ty.FONT_DIR)
        font = "fonts/" + os.path.basename(path) if os.path.dirname(path) == font_dir else path
        key = (font, self.face, text, float(tracking), tuple(map(tuple, features)), tuple(map(tuple, variations)),
               None if fallback is None else tuple(fallback))
        seen.setdefault(key, None)
        return original(self, text, size, tracking, features, variations, fallback)

    ty.FontResource.shape = shape
    error = None
    try:
        conftest.reset_funground()
        os.chdir(Path(sketch).parent)
        conftest.run_sketch(Path(sketch), frames=30)
    except BaseException as exc:                              # keep what was shaped before the failure
        error = f"{type(exc).__name__}: {exc}"
    with open(out, "a", encoding="utf-8") as fh:
        for font, face, text, tracking, features, variations, fallback in seen:
            fh.write(json.dumps({"src": Path(sketch).name, "font": font, "face": face, "text": text, "tracking": tracking,
                                 "features": [list(x) for x in features], "variations": [list(x) for x in variations],
                                 "fallback": None if fallback is None else list(fallback)}, ensure_ascii=False) + "\n")
    if error:
        print(f"{Path(sketch).name}: {error}", file=sys.stderr)
    print(f"{Path(sketch).name}: {len(seen)} calls")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
