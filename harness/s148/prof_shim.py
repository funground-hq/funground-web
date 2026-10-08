"""S-148: where the Python time of a frame goes, in Pyodide and natively (same code in both).

    import shim, prof_shim
    host = shim.Host(route)                   # shim.py of S-142, unchanged
    text = prof_shim.profile(host, case_id, kind, source, scale, route)     # JSON text

Pass 1 (timers only): per frame step, draw(), renderer (Cairo route), and for the Canvas route the encode split
into building the dicts (ir.op_to_jsonable), the extra work for Text outlines and rounded Rects, and json.dumps.
Pass 2 (cProfile, 3 to 4 times slower, so only shares mean anything): draw() alone, and the renderer alone
(Cairo route); bucketed by funground file, C builtins credited to their caller (as S-143).
A script case (f.show()) has no draw(): the profile covers the whole run.
"""
from __future__ import annotations

import cProfile
import json
import os
import pstats
import statistics
import tempfile
import time

perf = time.perf_counter
WARM, TIMED, PWARM, PFRAMES = 5, 20, 3, 8
SWARM, STIMED, PSRUNS = 1, 5, 3
LAST = {"body": None}


def _bucket(path, case):
    p = path.replace("\\", "/")
    i = p.rfind("/funground/")
    if i >= 0:
        return "funground/" + p[i + len("/funground/"):]
    if p.endswith("/" + case + ".py") or p == case + ".py":
        return "USER sketch"
    if "fontTools" in p:
        return "fontTools"
    if "pathops" in p:
        return "skia-pathops"
    if p in ("~", "") or p.startswith("<"):
        return "C/other"
    return p.rsplit("/", 1)[-1]


def _shares(prof, case, frames):
    """buckets {name: ms/frame}, top functions [(where, ms/frame, calls/frame)], total ms/frame, calls/frame."""
    st = pstats.Stats(prof)
    buckets, funcs, counts = {}, {}, {}
    total = 0.0
    calls = 0
    for key, (cc, nc, tt, ct, callers) in st.stats.items():
        f, line, name = key
        calls += nc
        total += tt
        if f == "~" and callers:                     # a C builtin: credit its time to the callers
            for ck, cv in callers.items():
                b = _bucket(ck[0], case)
                buckets[b] = buckets.get(b, 0.0) + cv[2]
            continue
        b = _bucket(f, case)
        buckets[b] = buckets.get(b, 0.0) + tt
        label = f"{b}:{line} {name}"
        funcs[label] = funcs.get(label, 0.0) + tt
        counts[label] = counts.get(label, 0) + nc
    top = sorted(funcs.items(), key=lambda kv: -kv[1])[:12]
    k = 1000.0 / frames
    return {"buckets": {b: round(v * k, 3) for b, v in sorted(buckets.items(), key=lambda kv: -kv[1])[:14]},
            "top": [(w, round(v * k, 3), round(counts[w] / frames, 1)) for w, v in top],
            "total_ms": round(total * k, 3), "calls": round(calls / frames, 1)}


def _med(xs):
    return round(statistics.median(xs), 3) if xs else None


def _encode_split(host, ops):
    """Host.encode with the time split: the dicts (op_to_jsonable), the extras (Text outlines, rounded Rect), dumps."""
    ir = host.ir
    t_build = t_extra = 0.0
    enc = []
    for op in ops:
        t = perf()
        d = ir.op_to_jsonable(op)
        t_build += perf() - t
        if type(op) is ir.Text or (type(op) is ir.Rect and op.radii):
            t = perf()
            d = host.encode(op)                      # the full Host.encode; its own op_to_jsonable is in the extra
            t_extra += perf() - t
        enc.append(d)
    t = perf()
    body = json.dumps(enc, separators=(",", ":"))
    return body, t_build * 1000, t_extra * 1000, (perf() - t) * 1000


class _Prof:
    """A cProfile.Profile that can be swapped for a fresh one (after warm-up)."""
    def __init__(self):
        self.p = cProfile.Profile()
        self.on = False

    def reset(self):
        self.p = cProfile.Profile()

    def enter(self):
        if self.on:
            return False
        self.on = True
        self.p.enable()
        return True

    def leave(self):
        self.p.disable()
        self.on = False


def profile(host, case, kind, source, scale, route):
    os.chdir(tempfile.mkdtemp(prefix="s148-"))
    out = {"id": case, "kind": kind, "route": route, "scale": scale}
    if route == "canvas":
        host.set_ink(case.startswith("studios-"))
    if kind == "script":
        return json.dumps(_profile_script(host, case, source, scale, route, out))
    host.load_loop(source, case + ".py", scale)
    series = {k: [] for k in ("step", "draw", "render", "build", "extra", "dumps")}
    nops, nbytes = [], []
    for i in range(WARM + TIMED):
        _running, step, draw, render, _e, _b, n = host.step(i * 1000.0 / 60.0)
        if i >= WARM:
            series["step"].append(step)
            series["draw"].append(draw)
            series["render"].append(render)
            nops.append(n)
            if route == "canvas":
                body, b, e, d = _encode_split(host, host.platform.ops)
                series["build"].append(b)
                series["extra"].append(e)
                series["dumps"].append(d)
                nbytes.append(len(body))
                LAST["body"] = body
    out["ops"] = _med(nops)
    out["bytes"] = _med(nbytes)
    out["timers"] = {k: _med(v) for k, v in series.items() if v}
    out["timers"]["other"] = round(out["timers"]["step"] - out["timers"]["draw"] - out["timers"]["render"], 3)
    # pass 2: cProfile of draw() and of the renderer, separately
    host.load_loop(source, case + ".py", scale)
    pd, pr = _Prof(), _Prof()
    sk = host.sketch
    orig_draw = sk._draw_fn

    def pdraw():
        pd.enter()
        try:
            orig_draw()
        finally:
            pd.leave()

    sk._draw_fn = pdraw
    if route == "cairo":
        ren = sk._renderer
        for name in ("render", "draw_batch", "begin_frame", "end_frame", "pixels"):
            def wrap(fn):
                def w(*a, **k):
                    mine = pr.enter()
                    try:
                        return fn(*a, **k)
                    finally:
                        if mine:
                            pr.leave()
                return w
            setattr(ren, name, wrap(getattr(ren, name)))
    for i in range(PWARM):
        host.step(i * 1000.0 / 60.0)
    pd.reset()
    pr.reset()
    for i in range(PFRAMES):
        host.step((PWARM + i) * 1000.0 / 60.0)
    out["draw_profile"] = _shares(pd.p, case, PFRAMES)
    if route == "cairo":
        out["render_profile"] = _shares(pr.p, case, PFRAMES)
    return json.dumps(out)


def _profile_script(host, case, source, scale, route, out):
    series = {k: [] for k in ("step", "draw", "render", "build", "extra", "dumps")}
    for i in range(SWARM + STIMED):
        r = host.run_script(source, case + ".py", scale)
        _running, step, draw, render, _e, _b, n = r[:7]
        if i >= SWARM:
            series["step"].append(step)
            series["draw"].append(draw)
            series["render"].append(render)
            out["ops"] = n
            if route == "canvas":
                body, b, e, d = _encode_split(host, list(host.sketch.frame.ops))
                series["build"].append(b)
                series["extra"].append(e)
                series["dumps"].append(d)
                LAST["body"] = body
                out["bytes"] = len(body)
    out["timers"] = {k: _med(v) for k, v in series.items() if v}
    out["timers"]["other"] = 0.0
    p = cProfile.Profile()
    p.enable()
    for _ in range(PSRUNS):
        host.run_script(source, case + ".py", scale)
    p.disable()
    out["draw_profile"] = _shares(p, case, PSRUNS)
    out["note"] = "script: the profile covers the whole run (draw and render together)"
    return out
