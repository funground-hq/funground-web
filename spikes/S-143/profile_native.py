"""S-143 native half: where does a heavy frame's time go in funground's own Python?

    C:\\Projects\\playground\\.venv\\Scripts\\python.exe profile_native.py ID[,ID...] --scale 1|2 [--frames 12]

One process, sequential, native CPython only. ID is a gallery id ("projects-02_rangoli") or
"session1/06_animation". Writes out/<id>_x<scale>.json and out/<id>_x<scale>_draw.txt / _render.txt.

Phases per frame (perf_counter, no profiler running):
  draw    the sketch's draw() (user code + funground API + IR construction)
  cairo   CairoRenderer.render(frame)            (renderer only)
  render  the whole sketch._render()             (cairo + present/capture + panel)
  encode  [op_to_jsonable(o) for o in ops] + json.dumps   (the S-136 hand-over)
A second pass with cProfile (draw and render profiled separately) gives the split of draw() by file:
  user | api.py | sketch.py | state/colour/geometry | dataclass ctors | ir.py | typography | other
Builtins (C functions) are credited to the file of their caller.
"""
from __future__ import annotations

import argparse
import cProfile
import gc
import inspect
import io
import json
import os
import pstats
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT02 = r"C:\Projects\playground-0.2"
sys.path.insert(0, ROOT02)
OUT = Path(__file__).resolve().parent / "out"
now = time.perf_counter

args_ns = None


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids")
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--no-profile", action="store_true")
    return ap.parse_args()


def example_path(eid: str) -> Path:
    if eid.startswith("session1/"):
        return Path(ROOT02) / "examples" / "session1" / (eid.split("/", 1)[1] + ".py")
    cat, name = eid.split("-", 1)
    return Path(ROOT02) / "examples" / "gallery" / cat / (name + ".py")


def setup_env(scale: int):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ["FUNGROUND_HEADLESS"] = "1"
    if scale != 1:
        os.environ["FUNGROUND_BACKING_SCALE"] = str(scale)
    else:
        os.environ.pop("FUNGROUND_BACKING_SCALE", None)


def fresh_sketch():
    from funground import api
    from funground.sketch import Sketch

    sk = api.use_sketch(Sketch())
    sk.random_seed(0)
    return sk


def encode(ops):
    from funground.ir import op_to_jsonable

    t0 = now()
    objs = [op_to_jsonable(o) for o in ops]
    t1 = now()
    s = json.dumps(objs)
    t2 = now()
    return t1 - t0, t2 - t1, len(s)


def run_loop(path: Path, frames: int, warmup: int, profile: bool, install=None):
    """Run a looping sketch for warmup+frames frames. Returns dict of per-frame lists (+ profiles)."""
    import funground
    from funground import api

    sk = fresh_sketch()
    if install:
        install(sk)
    rec = {"draw": [], "cairo": [], "render": [], "enc_obj": [], "enc_dump": [], "ops": [], "bytes": []}
    prof_draw, prof_render = cProfile.Profile(), cProfile.Profile()
    renderer = sk._renderer
    orig_rr = renderer.render
    orig_render = sk._render

    def timed_rr(frame):
        t0 = now()
        orig_rr(frame)
        rec["cairo"].append(now() - t0)

    def timed_render():
        if profile:
            prof_render.enable()
        t0 = now()
        orig_render()
        rec["render"].append(now() - t0)
        if profile:
            prof_render.disable()

    renderer.render = timed_rr
    sk._render = timed_render

    source = path.read_text(encoding="utf-8")
    ns = {"__name__": "__sketch__", "__file__": str(path)}
    orig_run, orig_show = funground.run, funground.show

    def harness_run(*, fps=1000, max_frames=frames + warmup):
        g = inspect.currentframe().f_back.f_globals
        draw = g.get("draw")
        if callable(draw):
            def timed_draw():
                if profile:
                    prof_draw.enable()
                t0 = now()
                draw()
                rec["draw"].append(now() - t0)
                if profile:
                    prof_draw.disable()
                ops = sk.frame.ops
                rec["ops"].append(len(ops))
                # encode outside the timed/profiled regions
                a, b, n = encode(ops)
                rec["enc_obj"].append(a)
                rec["enc_dump"].append(b)
                rec["bytes"].append(n)
            g["draw"] = timed_draw
        api.active_sketch().run_namespace(g, fps=fps, max_frames=max_frames)

    funground.run, funground.show = harness_run, (lambda: None)
    try:
        gc.collect()
        exec(compile(source, str(path), "exec"), ns)
    finally:
        funground.run, funground.show = orig_run, orig_show
    return rec, prof_draw, prof_render, sk


def run_script(path: Path, frames: int, warmup: int, profile: bool, install=None):
    """A top-level script (no f.run): the 'frame' is exec + canvas flush. Repeated a few times."""
    import funground
    from funground import api

    rec = {"draw": [], "cairo": [], "render": [], "enc_obj": [], "enc_dump": [], "ops": [], "bytes": []}
    prof_draw, prof_render = cProfile.Profile(), cProfile.Profile()
    source = path.read_text(encoding="utf-8")
    reps = min(frames, 5)
    for i in range(reps + 1):
        sk = fresh_sketch()
        if install:
            install(sk)
        renderer = sk._renderer
        orig_rr = renderer.render
        cairo_t = []

        def timed_rr(frame, orig_rr=orig_rr, cairo_t=cairo_t):
            t0 = now()
            orig_rr(frame)
            cairo_t.append(now() - t0)

        renderer.render = timed_rr
        ns = {"__name__": "__sketch__", "__file__": str(path)}
        orig_show = funground.show
        funground.show = lambda: None
        prof = i > 0 and profile
        gc.collect()
        try:
            if prof:
                prof_draw.enable()
            t0 = now()
            exec(compile(source, str(path), "exec"), ns)
            t_draw = now() - t0
            if prof:
                prof_draw.disable()
        finally:
            funground.show = orig_show
        if prof:
            prof_render.enable()
        t0 = now()
        sk._script_flush()
        t_render = now() - t0
        if prof:
            prof_render.disable()
        ops = sk.frame.ops
        a, b, n = encode(ops)
        if i > 0:
            rec["draw"].append(t_draw)
            rec["render"].append(t_render)
            rec["cairo"].append(sum(cairo_t))
            rec["enc_obj"].append(a)
            rec["enc_dump"].append(b)
            rec["ops"].append(len(ops))
            rec["bytes"].append(n)
    return rec, prof_draw, prof_render, sk


# ---- profile bucketing -------------------------------------------------------------------------
def bucket_of(filename: str, user_file: str) -> str:
    f = filename.replace("\\", "/")
    if f == user_file.replace("\\", "/"):
        return "user"
    if "/funground/" in f:
        base = f.rsplit("/", 1)[1]
        if base == "api.py":
            return "api.py"
        if base == "sketch.py":
            return "sketch.py"
        if base in ("state.py", "color.py", "paint.py", "geometry.py", "vector.py", "_colornames.py"):
            return "state/colour/geometry"
        if base == "ir.py":
            return "ir.py"
        if base in ("typography.py", "formatted.py", "fonts.py"):
            return "typography"
        if base == "cairo2d.py":
            return "cairo2d.py"
        return "funground other (" + base + ")"
    if f.endswith("/dataclasses.py"):
        return "dataclasses.replace (state copy)"
    if filename == "<string>":
        return "dataclass-generated (<string>)"
    if f.startswith("~") or filename == "~":
        return "builtin"
    return "stdlib/3rd-party (random, math, ...)"


def bucket_profile(prof: cProfile.Profile, user_file: str):
    st = pstats.Stats(prof)
    totals: dict[str, float] = {}
    ncalls = {"api.py": 0}
    for (fn, line, name), (cc, nc, tt, ct, callers) in st.stats.items():
        if fn == "~" and name in ("<method 'disable' of '_lsprof.Profiler' objects>", "<method 'enable' of '_lsprof.Profiler' objects>"):
            continue  # the profiler's own switch
        if fn == "~":  # builtin: credit to caller buckets
            for (cfn, cl, cn), (ccc, cnc, ctt, cct) in callers.items():
                b = bucket_of(cfn, user_file)
                totals[b] = totals.get(b, 0.0) + ctt
        else:
            b = bucket_of(fn, user_file)
            totals[b] = totals.get(b, 0.0) + tt
            if b == "api.py":
                ncalls["api.py"] += nc
    return totals, ncalls, st.total_calls, st.total_tt


def dump_stats(prof, path: Path, title: str, n_frames: int):
    s = io.StringIO()
    s.write(title + "\n\n")
    st = pstats.Stats(prof, stream=s).strip_dirs()
    s.write("--- sorted by tottime (top 30) ---\n")
    st.sort_stats("tottime").print_stats(30)
    s.write("\n--- sorted by cumulative (top 30) ---\n")
    st.sort_stats("cumulative").print_stats(30)
    path.write_text(s.getvalue(), encoding="utf-8")


def stat(xs):
    ms = [x * 1000 for x in xs]
    return round(statistics.fmean(ms), 3) if ms else None


def main():
    a = parse()
    setup_env(a.scale)
    import funground

    print("funground.__file__ =", funground.__file__, flush=True)
    assert funground.__file__.startswith(ROOT02), funground.__file__
    OUT.mkdir(exist_ok=True)
    for eid in a.ids.split(","):
        path = example_path(eid)
        src = path.read_text(encoding="utf-8")
        is_loop = "f.run(" in src or "funground.run(" in src
        tag = eid.replace("/", "_") + f"_x{a.scale}"
        scratch = tempfile.mkdtemp(prefix="fg-s143-")
        start = os.getcwd()
        os.chdir(scratch)
        try:
            runner = run_loop if is_loop else run_script
            # pass 1: timers only
            rec, _, _, sk = runner(path, a.frames, a.warmup, False)
            skip = a.warmup if is_loop else 0
            r = {k: v[skip:] for k, v in rec.items()}
            res = {"id": eid, "scale": a.scale, "mode": "loop" if is_loop else "script",
                   "frames_timed": len(r["draw"]),
                   "canvas": [sk.width, sk.height],
                   "ms": {k: stat(r[k]) for k in ("draw", "cairo", "render", "enc_obj", "enc_dump")},
                   "ops": round(statistics.fmean(r["ops"]), 1) if r["ops"] else None,
                   "json_bytes": round(statistics.fmean(r["bytes"])) if r["bytes"] else None}
            res["ms"]["encode"] = round(res["ms"]["enc_obj"] + res["ms"]["enc_dump"], 3)
            res["ms"]["present_other"] = round(res["ms"]["render"] - res["ms"]["cairo"], 3)
            # pass 2: profiles
            if not a.no_profile:
                rec2, pd, pr, _ = runner(path, a.frames, a.warmup, True)
                nfr = len(rec2["draw"]) - (a.warmup if is_loop else 0)
                # the profile covers all frames incl. warm-up
                nfr_all = len(rec2["draw"])
                bd, ncd, tcd, ttd = bucket_profile(pd, str(path))
                br, ncr, tcr, ttr = bucket_profile(pr, str(path))
                res["profile"] = {
                    "frames_profiled": nfr_all,
                    "draw_bucket_ms_per_frame": {k: round(v * 1000 / nfr_all, 3) for k, v in sorted(bd.items(), key=lambda kv: -kv[1])},
                    "draw_profiled_total_ms_per_frame": round(ttd * 1000 / nfr_all, 3),
                    "api_py_calls_per_frame": round(ncd["api.py"] / nfr_all, 1),
                    "function_calls_per_frame_draw": round(tcd / nfr_all, 1),
                    "render_bucket_ms_per_frame": {k: round(v * 1000 / nfr_all, 3) for k, v in sorted(br.items(), key=lambda kv: -kv[1])},
                    "render_profiled_total_ms_per_frame": round(ttr * 1000 / nfr_all, 3),
                    "function_calls_per_frame_render": round(tcr / nfr_all, 1),
                }
                dump_stats(pd, OUT / f"{tag}_draw.txt", f"{eid} x{a.scale}: draw() profile, {nfr_all} frames", nfr_all)
                dump_stats(pr, OUT / f"{tag}_render.txt", f"{eid} x{a.scale}: _render() profile, {nfr_all} frames", nfr_all)
            (OUT / f"{tag}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
            print(json.dumps({k: res[k] for k in ("id", "scale", "ops", "ms")}), flush=True)
        finally:
            os.chdir(start)
            try:
                import pygame
                if pygame.get_init():
                    pygame.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
