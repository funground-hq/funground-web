r"""S-142 native column: the same Host (harness/s142/shim.py) and cases, run in CPython.

    C:\Projects\playground\.venv\Scripts\python.exe tools/s142_native.py --route cairo|canvas [--scale 1|2] [--cases a,b] [--out FILE]

funground comes from FUNGROUND_SRC (the playground-0.2 branch with the split loop, extracted with git archive;
the working tree of playground-0.2 has no start/step/finish yet). Loop cases: 5 warm-up steps and 30 timed steps
(the cloud bench's counts), a fake 60 Hz clock. Script cases: 1 warm-up run and 10 timed runs.
Per phase (ms): step (whole), draw (learner draw()), render (Cairo; 0 for the IR route), other (step - draw -
render), encode (IR route: op_to_jsonable + json.dumps), copy (Cairo route: one bytes() copy of the surface).
With --scale 1 the Cairo route's 30th frame is also compared with the golden (RGB, byte for byte).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
SCRATCH = Path(r"C:\Users\samirj\AppData\Local\Temp\claude")
SRC = Path(os.environ.get("FUNGROUND_SRC", SCRATCH / "fg_s136"))
CORE = Path(os.environ.get("FUNGROUND_CORE", r"C:\Projects\playground-0.2"))
DIST = WEB / "harness" / "s142" / "dist"
WARM, REPS, SWARM, SREPS = 5, 30, 1, 10


def stat(xs):
    xs = sorted(xs)
    if not xs:
        return None
    p95 = xs[min(len(xs) - 1, int(len(xs) * 0.95))]
    return {"n": len(xs), "median": round(statistics.median(xs), 3), "p95": round(p95, 3), "mean": round(statistics.fmean(xs), 3)}


def golden_rgb(case):
    from PIL import Image
    g = case.get("golden")
    if not g:
        return None
    p = CORE / "tests" / "golden" / ("gallery" if case["group"] == "heavy" else "") / g
    return Image.open(p).convert("RGB")


def bgra_to_rgb(b, w, h):
    from PIL import Image
    return Image.frombuffer("RGBA", (w, h), b, "raw", "BGRA", 0, 1).convert("RGB")


def run_case(host, case, scale):
    source = (DIST / "sketches" / f"{case['id']}.py").read_text(encoding="utf-8")
    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp(prefix="s142-"))
    if host.route == "canvas":
        host.set_ink(case.get("ink"))
    series = {k: [] for k in ("step", "draw", "render", "other", "encode", "copy", "e2e")}
    nops, pixel = [], None
    try:
        if case["kind"] == "script":
            for i in range(SWARM + SREPS):
                t0 = time.perf_counter()
                r = host.run_script(source, case["id"] + ".py", scale)
                running, step, draw, render, enc, body, n = r[:7]
                cp = 0.0
                if host.route == "cairo":
                    cp, b = host.native_copy()
                if i >= SWARM:
                    for k, v in (("step", step), ("draw", draw), ("render", render), ("other", 0.0), ("encode", enc), ("copy", cp)):
                        series[k].append(v)
                    series["e2e"].append((time.perf_counter() - t0) * 1000)
                    nops.append(n)
                if i == SWARM and host.route == "cairo" and scale == 1:
                    w, h = host.frame_size()
                    pixel = (b, w, h)
        else:
            host.load_loop(source, case["id"] + ".py", scale)
            for i in range(WARM + REPS):
                t0 = time.perf_counter()
                running, step, draw, render, enc, body, n = host.step(i * 1000.0 / 60.0)
                cp = 0.0
                if host.route == "cairo":
                    cp, b = host.native_copy()
                if i == 29 and host.route == "cairo" and scale == 1:
                    w, h = host.frame_size()
                    pixel = (b, w, h)
                if i >= WARM:
                    for k, v in (("step", step), ("draw", draw), ("render", render), ("other", step - draw - render),
                                 ("encode", enc), ("copy", cp)):
                        series[k].append(v)
                    series["e2e"].append((time.perf_counter() - t0) * 1000)
                    nops.append(n)
    finally:
        os.chdir(cwd)
    out = {"id": case["id"], "kind": case["kind"], "scale": scale, "ops_median": statistics.median(nops) if nops else None,
           "canvas": host.size()[:2], "phases": {k: stat(v) for k, v in series.items()}}
    if pixel is not None:
        g = golden_rgb(case)
        if g is None:
            out["pixels"] = "no golden"
        else:
            got = bgra_to_rgb(*pixel)
            out["pixels"] = "byte-identical" if got.size == g.size and got.tobytes() == g.tobytes() else "DIFFERENT"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True)
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--cases", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    sys.path.insert(0, str(SRC))
    sys.path.insert(0, str(WEB / "harness" / "s142"))
    import shim
    cases = json.loads((DIST / "cases.json").read_text(encoding="utf-8"))
    if a.cases:
        want = a.cases.split(",")
        cases = [c for c in cases if c["id"] in want]
    t = time.perf_counter()
    host = shim.Host(a.route)
    res = {"route": a.route, "scale": a.scale, "python": sys.version.split()[0], "import_ms": host.import_ms, "cases": []}
    for c in cases:
        try:
            r = run_case(host, c, a.scale)
        except BaseException as exc:                  # noqa: BLE001
            if isinstance(exc, KeyboardInterrupt):
                raise
            r = {"id": c["id"], "error": f"{type(exc).__name__}: {exc}"}
        res["cases"].append(r)
        ph = r.get("phases")
        print(r["id"], r.get("error") or {k: ph[k]["median"] for k in ("step", "draw", "render", "encode", "copy")}, r.get("pixels", ""), flush=True)
    res["seconds"] = time.perf_counter() - t
    out = Path(a.out) if a.out else WEB / "results_s142" / f"native-{a.route}-{int(a.scale)}x.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
