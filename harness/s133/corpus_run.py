"""S-133: run a text corpus through funground.typography and report what it produced.

The same file runs natively (desktop, uharfbuzz) and in Pyodide (shim/uharfbuzz.py over harfbuzzjs), so
the two results differ only through the shaper (and fontTools, if its version differs). A case is

    {"font": "fonts/DejaVuSans.ttf" | "extra/TestVar.ttf", "face": 0, "text": "...", "tracking": 0,
     "features": [["liga", false]], "variations": [["wght", 700]], "fallback": null | []}

`font` is under roots["fonts"] (funground/fonts) or roots["extra"] (other fonts the corpus brought).
Per case the result holds every shaped glyph (gid, advance, x offset, y offset, cluster), the advance
at 20 px, and for each size a SHA-256 of the JSON of the FillPath ops (`ir.op_to_jsonable`), the number
of ops and of path commands. `dump(case_ids)` gives the full ops for a few cases (to look at a mismatch).
"""
from __future__ import annotations

import hashlib
import json
import os
import time

SIZES = (12.0, 40.5, 96.0)
perf = time.perf_counter

_fonts: dict = {}


def _resource(case, roots):
    from funground import typography as ty

    sub, _, name = case["font"].partition("/")
    path = os.path.join(roots[sub], name)
    key = (path, case.get("face", 0))
    if key not in _fonts:
        _fonts[key] = ty.FontResource(path, case.get("face", 0))
    return _fonts[key]


def _shape(case, roots, size=20.0):
    res = _resource(case, roots)
    fallback = case.get("fallback")
    return res.shape(case["text"], size, float(case.get("tracking", 0)),
                     tuple((t, v) for t, v in case.get("features", ())),
                     tuple((t, v) for t, v in case.get("variations", ())),
                     None if fallback is None else tuple(fallback))


def _runs(line):
    return list(getattr(line, "runs", None) or (line,))


def _glyphs(run):
    return [[g.gid, g.x_advance, g.x_offset, g.y_offset, g.cluster] for g in run.glyphs]


def _ops(line, size):
    from funground import ir
    from funground.color import Color

    return [ir.op_to_jsonable(op) for op in line.outline_ops(10.0, 20.0, Color(0, 0, 0, 255))]


def run_case(case, roots):
    line = _shape(case, roots)
    out = {"runs": [{"font": os.path.basename(r.font.path), "glyphs": _glyphs(r)} for r in _runs(line)],
           "advance": line.advance, "ops": {}}
    for size in SIZES:
        sized = _shape(case, roots, size)
        ops = _ops(sized, size)
        blob = json.dumps(ops, separators=(",", ":"))
        out["ops"][repr(size)] = [hashlib.sha256(blob.encode()).hexdigest(), len(ops), blob.count('"')]
    return out


def run_all(cases, roots):
    t = perf()
    results = []
    for i, c in enumerate(cases):
        try:
            results.append(run_case(c, roots))
        except Exception as exc:                           # a case that fails is a result, not a crash
            results.append({"error": f"{type(exc).__name__}: {exc}"})
    return {"results": results, "seconds": perf() - t}


def dump(cases, ids, roots, size=20.0):
    return {i: _ops(_shape(cases[i], roots, size), size) for i in ids}


def hb_version():
    import uharfbuzz as hb

    return getattr(hb, "version_string", lambda: "?")(), getattr(hb, "__version__", "shim")


def timings(cases, roots, repeat=5):
    """Mean microseconds per string: `_shape_one` as a whole, and the shaper alone (Buffer, shape, read back)."""
    import uharfbuzz as hb

    one = hb_only = 0.0
    glyphs = 0
    for c in cases:
        res = _resource(c, roots)
        loc = res.location(tuple((t, v) for t, v in c.get("variations", ())))
        feats = tuple((t, v) for t, v in c.get("features", ()))
        font = res._at(loc)[0]
        text = c["text"]
        res._shape_one(text, 20.0, 0.0, feats, tuple((t, v) for t, v in c.get("variations", ())))     # warm
        t0 = perf()
        for _ in range(repeat):
            run = res._shape_one(text, 20.0, 0.0, feats, tuple((t, v) for t, v in c.get("variations", ())))
        t1 = perf()
        for _ in range(repeat):
            buf = hb.Buffer()
            buf.add_str(text)
            buf.guess_segment_properties()
            hb.shape(font, buf, {"kern": True, "liga": True, **dict(feats)})
            list(zip(buf.glyph_infos, buf.glyph_positions))
        t2 = perf()
        one += (t1 - t0) / repeat
        hb_only += (t2 - t1) / repeat
        glyphs += len(run.glyphs)
    n = len(cases)
    return {"strings": n, "glyphs": glyphs, "shape_one_us": 1e6 * one / n, "hb_only_us": 1e6 * hb_only / n,
            "hb_only_us_per_glyph": 1e6 * hb_only / max(glyphs, 1)}
