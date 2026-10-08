"""S-143 prototypes: small monkeypatches measured before/after, native only. Nothing in playground-0.2 is edited.

    C:\\Projects\\playground\\.venv\\Scripts\\python.exe prototypes.py ID[,ID...] [--frames 15]

Patches (each reversible):
  P1 colour   cache Color._parse_str per string (Color is immutable, so sharing is safe)
  P2 state    GraphicsState.with_ without dataclasses.replace (attrgetter + positional constructor)
  P3 number   vector._number fast path for int/float (avoids the numbers.Real ABC check)
  P4 glyphs   TextRun.outline_ops: cache each glyph outline scaled and flipped per (font, gid, location, scale),
              then only translate (the per-frame Transform.then/apply work disappears)
Encoding variants (E1 table+JSON arrays, E2 table+float64 binary) are timed on the final frame's ops and
decoded back and compared with the original ops.

Correctness: the ops of every frame and the final captured pixels of the patched run must equal the baseline's.
"""
from __future__ import annotations

import argparse
import array
import json
import operator
import os
import statistics
import sys
import tempfile
import time
from numbers import Real

sys.argv_saved = list(sys.argv)
import profile_native as pn  # noqa: E402  (also puts playground-0.2 first on sys.path)

now = time.perf_counter


# ---------------------------------------------------------------- patches
class Patch:
    def __init__(self, name, apply, revert):
        self.name, self.apply, self.revert = name, apply, revert


def make_patches():
    import importlib
    fcolor, fstate, fvector, ftypo = (importlib.import_module("funground." + n) for n in ("color", "state", "vector", "typography"))
    from funground import ir
    from funground.geometry import Path

    # P1
    C = fcolor.Color
    orig_ps = C.__dict__["_parse_str"]
    cache: dict[str, object] = {}
    raw = orig_ps.__func__

    def cached_parse_str(cls, text):
        c = cache.get(text)
        if c is None:
            c = cache[text] = raw(cls, text)      # errors are not cached (they raise)
        return c

    p1 = Patch("P1 colour cache",
               lambda: setattr(C, "_parse_str", classmethod(cached_parse_str)),
               lambda: setattr(C, "_parse_str", orig_ps))

    # P2
    G = fstate.GraphicsState
    orig_with = G.with_
    names = tuple(G.__dataclass_fields__)
    getter = operator.attrgetter(*names)
    index = {n: i for i, n in enumerate(names)}

    def fast_with(self, **changes):
        vals = list(getter(self))
        try:
            for k, v in changes.items():
                vals[index[k]] = v
        except KeyError as e:
            raise TypeError(f"GraphicsState has no field {e.args[0]!r}") from None
        return G(*vals)

    p2 = Patch("P2 state with_", lambda: setattr(G, "with_", fast_with), lambda: setattr(G, "with_", orig_with))

    # P3
    orig_num = fvector._number

    def fast_number(v, what):
        t = type(v)
        if t is float:
            return v
        if t is int:
            return float(v)
        return orig_num(v, what)

    p3 = Patch("P3 vector._number", lambda: setattr(fvector, "_number", fast_number),
               lambda: setattr(fvector, "_number", orig_num))

    # P4
    TR = ftypo.TextRun
    orig_outline_ops = TR.outline_ops
    gcache: dict = {}

    def fast_outline_ops(self, x, y, color):
        s = self.scale
        baseline = y + self.font.ascent * s
        pen_x = x
        ops = []
        fid = id(self.font)
        loc = self.location
        try:
            hash(loc)
            key_loc = loc
        except TypeError:
            return orig_outline_ops(self, x, y, color)
        for g in self.glyphs:
            key = (fid, g.gid, key_loc, s)
            scaled = gcache.get(key)
            if scaled is None:
                outline = self.font.outline(g.gid, self.location)
                scaled = False if outline.is_empty else outline.transformed(ftypo.Transform.scaling(s, -s))
                gcache[key] = (scaled, outline)
                scaled = gcache[key]
            sc, _ = scaled if isinstance(scaled, tuple) else (scaled, None)
            if sc:
                tx = pen_x + g.x_offset * s
                ty = baseline - g.y_offset * s
                segs = tuple((seg[0], *((px + tx, py + ty) for px, py in seg[1:])) for seg in sc.segments)
                ops.append(ir.FillPath(Path(segs), color))
            pen_x += g.x_advance * s + self.tracking
        return ops

    p4 = Patch("P4 glyph cache", lambda: setattr(TR, "outline_ops", fast_outline_ops),
               lambda: setattr(TR, "outline_ops", orig_outline_ops))
    return [p1, p2, p3, p4]


# ---------------------------------------------------------------- encodings
def enc_baseline(ops):
    from funground.ir import op_to_jsonable
    return json.dumps([op_to_jsonable(o) for o in ops])


SIMPLE = {}


def _setup_simple():
    from funground import ir
    SIMPLE.update({ir.Circle: (1, ("x", "y", "diameter")), ir.Ellipse: (2, ("x", "y", "width", "height")),
                   ir.Line: (3, ("x1", "y1", "x2", "y2")), ir.Point: (4, ("x", "y")),
                   ir.Rect: (5, ("x", "y", "width", "height"))})
    GETTERS.update({cls: operator.attrgetter(*spec[1]) for cls, spec in SIMPLE.items()})
    return ir


GETTERS = {}


def enc_table_json(ops):
    """E1: styles once in a table (by identity), simple ops as flat arrays [code, style, nums...]."""
    from funground.ir import op_to_jsonable, _fields_to_jsonable
    styles, sidx, out = [], {}, []
    for o in ops:
        spec = SIMPLE.get(type(o))
        if spec is not None and not (type(o).__name__ == "Rect" and o.radii):
            st = o.style
            i = sidx.get(id(st))
            if i is None:
                i = sidx[id(st)] = len(styles)
                styles.append(_fields_to_jsonable(st))
            out.append([spec[0], i, *GETTERS[type(o)](o)])
        else:
            out.append(op_to_jsonable(o))
    return json.dumps({"styles": styles, "ops": out})


def enc_table_binary(ops):
    """E2: styles table as JSON, simple ops as float64 records in one array, other ops as JSON strings."""
    from funground.ir import op_to_jsonable, _fields_to_jsonable
    styles, sidx, others = [], {}, []
    buf = array.array("d")
    ext = buf.extend
    for o in ops:
        spec = SIMPLE.get(type(o))
        if spec is not None and not (type(o).__name__ == "Rect" and o.radii):
            st = o.style
            i = sidx.get(id(st))
            if i is None:
                i = sidx[id(st)] = len(styles)
                styles.append(_fields_to_jsonable(st))
            ext((spec[0], i, *GETTERS[type(o)](o)))
        else:
            ext((0, len(others)))
            others.append(op_to_jsonable(o))
    header = json.dumps({"styles": styles, "others": others}).encode()
    return len(header).to_bytes(4, "little") + header + buf.tobytes()


def dec_table_binary(blob):
    from funground import ir
    from funground.ir import op_from_jsonable, _state_from_jsonable
    n = int.from_bytes(blob[:4], "little")
    head = json.loads(blob[4:4 + n])
    styles = [_state_from_jsonable(s) for s in head["styles"]]
    others = head["others"]
    a = array.array("d")
    a.frombytes(blob[4 + n:])
    cls_of = {1: ir.Circle, 2: ir.Ellipse, 3: ir.Line, 4: ir.Point, 5: ir.Rect}
    width = {1: 3, 2: 4, 3: 4, 4: 2, 5: 4}
    out, i = [], 0
    while i < len(a):
        code = int(a[i])
        if code == 0:
            out.append(op_from_jsonable(others[int(a[i + 1])]))
            i += 2
        else:
            w = width[code]
            vals = list(a[i + 2:i + 2 + w])
            out.append(cls_of[code](*vals, styles[int(a[i + 1])]))
            i += 2 + w
    return out


def dec_table_json(text):
    from funground import ir
    from funground.ir import op_from_jsonable, _state_from_jsonable
    d = json.loads(text)
    styles = [_state_from_jsonable(s) for s in d["styles"]]
    cls_of = {1: ir.Circle, 2: ir.Ellipse, 3: ir.Line, 4: ir.Point, 5: ir.Rect}
    out = []
    for r in d["ops"]:
        if isinstance(r, list):
            out.append(cls_of[r[0]](*r[2:], styles[r[1]]))
        else:
            out.append(op_from_jsonable(r))
    return out


def bench(fn, arg, reps=25):
    ts = []
    for _ in range(reps):
        t0 = now()
        r = fn(arg)
        ts.append(now() - t0)
    return round(min(ts) * 1000, 3), r


# ---------------------------------------------------------------- runs
def run_variant(path, frames, warmup, repeats=7):
    best = None
    for _ in range(repeats):
        r = run_variant1(path, frames, warmup)
        if best is None:
            best = r
        else:
            best[0].update({k: min(best[0][k], r[0][k]) for k in best[0]})   # min of per-run means, per phase
    return best


def run_variant1(path, frames, warmup):
    """Run the sketch; return mean ms per phase, per-frame ops list, final pixels, last ops."""
    frame_ops = []

    def install(sk):
        orig = sk._render

        def r():
            frame_ops.append(sk.last_ops)
            orig()
        sk._render = r

    rec, _, _, sk = pn.run_loop(path, frames, warmup, False, install=install)
    s = slice(warmup, None)
    ms = {k: round(statistics.fmean(rec[k][s]) * 1000, 3) for k in ("draw", "cairo", "render")}
    return ms, frame_ops, sk.last_frame, sk.last_ops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids")
    ap.add_argument("--frames", type=int, default=15)
    ap.add_argument("--warmup", type=int, default=3)
    a = ap.parse_args()
    pn.setup_env(1)
    import funground
    assert funground.__file__.startswith(pn.ROOT02)
    _setup_simple()
    patches = make_patches()
    results = []
    for eid in a.ids.split(","):
        path = pn.example_path(eid)
        scratch = tempfile.mkdtemp(prefix="fg-s143p-")
        start = os.getcwd()
        os.chdir(scratch)
        row = {"id": eid, "variants": {}}
        try:
            base_ms, base_ops, base_px, last_ops = run_variant(path, a.frames, a.warmup)
            row["variants"]["baseline"] = {"ms": base_ms, "ops_equal": True, "pixels_equal": True}
            plans = [[p] for p in patches] + [list(patches)]
            for plan in plans:
                for p in plan:
                    p.apply()
                try:
                    ms, ops, px, _ = run_variant(path, a.frames, a.warmup)
                finally:
                    for p in reversed(plan):
                        p.revert()
                name = "ALL" if len(plan) > 1 else plan[0].name
                row["variants"][name] = {"ms": ms, "ops_equal": ops == base_ops, "pixels_equal": px == base_px}
            # encodings on the final frame
            e0, s0 = bench(enc_baseline, last_ops)
            e1, s1 = bench(enc_table_json, last_ops)
            e2, s2 = bench(enc_table_binary, last_ops)
            d1 = dec_table_json(s1)
            d2 = dec_table_binary(s2)
            row["encode"] = {"ops": len(last_ops),
                             "baseline_ms": e0, "baseline_bytes": len(s0),
                             "E1_table_json_ms": e1, "E1_bytes": len(s1), "E1_roundtrip_equal": d1 == list(last_ops),
                             "E2_table_binary_ms": e2, "E2_bytes": len(s2), "E2_roundtrip_equal": d2 == list(last_ops)}
        finally:
            os.chdir(start)
        results.append(row)
        print(json.dumps(row), flush=True)
    out = pn.OUT / "prototypes.json"
    old = json.loads(out.read_text()) if out.exists() else []
    ids = {r["id"] for r in results}
    out.write_text(json.dumps([r for r in old if r["id"] not in ids] + results, indent=1))


if __name__ == "__main__":
    main()
