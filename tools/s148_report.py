r"""S-148 tables: before (results_s142) and after (results_s148), per variant and case group, plus the profile tables.

    C:\Projects\playground\.venv\Scripts\python.exe tools/s148_report.py > results_s148/tables_ba.md
    C:\Projects\playground\.venv\Scripts\python.exe tools/s148_report.py --prof > results_s148/tables_prof.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s142_report as S                                       # noqa: E402

WEB = Path(__file__).resolve().parent.parent
HEAVY = ["projects-02_rangoli", "projects-06_kinetic_type", "text-09_text_dots", "randomness-03_noise", "sound-02_write_a_tune",
         "randomness-02_gaussian_and_choice", "studios-03_rhythm", "studios-05_text_as_geometry", "paths-06_outlines",
         "studios-06_poster_series"]
TYPICAL = ["s1-05_text", "s1-06_animation", "s1-07_bounce"]
KEYS_N = {"draw": "draw", "other": "other", "render": "render", "encode": "encode", "copy": "copy", "e2e": "e2e"}
KEYS_B = {"draw": "draw_py", "other": "py_other", "render": "render_cairo", "encode": "encode", "copy": "wasm_copy",
          "message": "transfer", "parse": "parse", "paint": "paint", "e2e": "e2e"}
COLS = ["draw", "other", "render", "encode", "copy", "message", "parse", "paint", "e2e"]


def loadall(d):
    S.R = WEB / d
    return S.get_all()


def phase(c, v, col):
    if not c or "phases" not in c:
        return None
    keys = KEYS_N if v[0] == "native" else KEYS_B
    k = keys.get(col)
    if k is None:
        return None
    s = c["phases"].get(k)
    return s["median"] if s else None


def gmean(data, v, dpr, ids, col):
    xs = [phase(data[(v, dpr)].get(i), v, col) for i in ids]
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def f(x, nd=1):
    return "-" if x is None else f"{x:.{nd}f}"


def ba(before, after):
    r = "-" if not before or after is None else f"{after / before:.2f}"
    return f"{f(before)} -> {f(after)} ({r})"


def before_after():
    old, new = loadall("results_s142"), loadall("results_s148")
    print("## Before (S-142) -> after (S-148): mean over the cases of the per-case medians, ms (ratio after / before)\n")
    print("| group | scale | route | draw() | py other | render | encode | wasm copy | message | parse | paint | end to end |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for gname, ids in (("heavy (10)", HEAVY), ("typical (3)", TYPICAL)):
        for dpr in (1, 2):
            for v in S.VARIANTS:
                if gname.startswith("typical") and v[-1] == "worker":
                    continue
                cells = [ba(gmean(old, v, dpr, ids, c), gmean(new, v, dpr, ids, c)) for c in COLS]
                print(f"| {gname} | {dpr}x | {S.NAMES[v]} | " + " | ".join(cells) + " |")
    print()
    print("## End to end per case, median of 3, ms: before -> after (ratio)\n")
    for dpr in (1, 2):
        print(f"### {dpr}x\n")
        print("| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) |")
        print("|---|---|---|---|---|---|---|")
        for i in HEAVY + TYPICAL:
            cells = [ba(phase(old[(v, dpr)].get(i), v, "e2e"), phase(new[(v, dpr)].get(i), v, "e2e")) for v in S.VARIANTS]
            print(f"| {i} | " + " | ".join(cells) + " |")
        print()
    print("## Cairo (page paints) / Canvas (page paints) end-to-end ratio, before -> after\n")
    print("| case | 1x before | 1x after | 2x before | 2x after |\n|---|---|---|---|---|")
    sums = {}
    for i in HEAVY + TYPICAL:
        row = []
        for dpr in (1, 2):
            for d in (old, new):
                a, b = phase(d[(S.VARIANTS[1], dpr)].get(i), S.VARIANTS[1], "e2e"), phase(d[(S.VARIANTS[4], dpr)].get(i), S.VARIANTS[4], "e2e")
                r = a / b if a and b else None
                row.append(f(r, 2))
                if r:
                    sums.setdefault((dpr, d is new, i in HEAVY), []).append(r)
        print(f"| {i} | " + " | ".join(row) + " |")
    print()
    for g in (True, False):
        print(f"Mean ratio {'heavy' if g else 'typical'}: " + ", ".join(
            f"{dpr}x {'after' if aft else 'before'} {sum(sums[(dpr, aft, g)]) / len(sums[(dpr, aft, g)]):.2f}" for dpr in (1, 2) for aft in (False, True)) + "\n")
    print("## Spread of the 3 repeats, end-to-end medians (min - max), page paints, 1x, after\n")
    print("| case | Cairo | Canvas |\n|---|---|---|")
    for i in HEAVY + TYPICAL:
        a, b = new[(S.VARIANTS[1], 1)].get(i), new[(S.VARIANTS[4], 1)].get(i)
        rg = lambda c: "-" if not c or not c.get("e2e_range") else f"{c['e2e_range'][0]:.1f} - {c['e2e_range'][1]:.1f}"
        print(f"| {i} | {rg(a)} | {rg(b)} |")
    print()


def _runs(names):
    out = []
    for n in names:
        p = WEB / "results_s148" / n
        if p.exists():
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def _med(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _timer(runs, cid, key):
    vals = []
    for r in runs:
        c = next((c for c in r["cases"] if c["id"] == cid), None)
        pr = c.get("prof", c) if c else None
        if pr and "timers" in pr:
            vals.append(pr["timers"].get(key))
    return _med(vals)


def _first(runs, cid):
    for r in runs:
        c = next((c for c in r["cases"] if c["id"] == cid), None)
        pr = c.get("prof", c) if c else None
        if pr and "timers" in pr:
            return pr
    return None


def prof_tables():
    ids = HEAVY
    for route in ("cairo", "canvas"):
        files = {
            ("native", "before"): [f"prof-native-before-{route}-1x.json", f"prof-native-before2-{route}-1x.json"],
            ("native", "after"): [f"prof-native-{route}-1x.json", f"prof-native2-{route}-1x.json"],
            ("pyodide", "before"): [f"prof-before-browser-{route}.json", f"prof-before2-browser-{route}.json"],
            ("pyodide", "after"): [f"prof-browser-{route}.json", f"prof-browser2-{route}.json"],
        }
        runs = {k: _runs(v) for k, v in files.items()}
        print(f"## {route} route: Python time per frame, scale 1, back to back in this session (ms, median of 20 frames; "
              f"median of {len(runs[('pyodide', 'after')])} runs per cell): before = funground of S-142, after = release-0.2-web HEAD\n")
        print("| case | draw() native before -> after | draw() Pyodide before -> after | " + ("render native | render Pyodide | " if route == "cairo" else "encode native before -> after | encode Pyodide before -> after | ") + "Pyodide / native draw (after) |")
        print("|---|---|---|---|---|---|")
        tot = {}
        for i in ids:
            cells = []
            for env in ("native", "pyodide"):
                b, a = _timer(runs[(env, "before")], i, "draw"), _timer(runs[(env, "after")], i, "draw")
                cells.append(f"{f(b)} -> {f(a)} ({f(a / b if a and b else None, 2)})")
                tot.setdefault(("draw", env), []).append((b, a))
            if route == "cairo":
                for env in ("native", "pyodide"):
                    b, a = _timer(runs[(env, "before")], i, "render"), _timer(runs[(env, "after")], i, "render")
                    cells.append(f"{f(b)} -> {f(a)}")
            else:
                for env in ("native", "pyodide"):
                    def enc(rs, which):
                        parts = [_timer(rs, i, k) for k in ("build", "extra", "dumps")]
                        return None if None in parts else parts
                    eb, ea = enc(runs[(env, "before")], 0), enc(runs[(env, "after")], 0)
                    tb = None if eb is None else eb[0] + eb[1] + eb[2]
                    ta = None if ea is None else ea[0] + ea[1] + ea[2]
                    cells.append(f"{f(tb)} -> {f(ta)}")
            dn, dp = _timer(runs[("native", "after")], i, "draw"), _timer(runs[("pyodide", "after")], i, "draw")
            cells.append(f"{f(dp / dn if dn and dp else None, 1)}x")
            print(f"| {i} | " + " | ".join(cells) + " |")
        for env in ("native", "pyodide"):
            bs = [x for x, y in tot[("draw", env)] if x is not None and y is not None]
            as_ = [y for x, y in tot[("draw", env)] if x is not None and y is not None]
            print(f"\nMean draw() {env}: {sum(bs) / len(bs):.1f} -> {sum(as_) / len(as_):.1f} ms over {len(bs)} cases")
        print()
        print(f"## {route} route, Pyodide, after: where one frame goes (ms; native after in brackets)\n")
        cols = ["step", "draw", "other"] + (["render"] if route == "cairo" else ["build", "extra", "dumps"])
        print("| case | ops | JSON bytes | " + " | ".join(cols) + " |")
        print("|---|---|---|" + "---|" * len(cols))
        for i in ids:
            pb, pn = _first(runs[("pyodide", "after")], i), _first(runs[("native", "after")], i)
            if not pb or not pn:
                print(f"| {i} | missing |")
                continue
            cells = [f"{f(_timer(runs[('pyodide', 'after')], i, k))} [{f(_timer(runs[('native', 'after')], i, k))}]" for k in cols]
            print(f"| {i} | {pb.get('ops')} | {pb.get('bytes') or '-'} | " + " | ".join(cells) + " |")
        print()
        print(f"## {route} route: cProfile of draw(), share by file, after (first run; native | Pyodide)\n")
        for i in ids:
            pb, pn = _first(runs[("pyodide", "after")], i), _first(runs[("native", "after")], i)
            if not pb or not pn or "draw_profile" not in pb:
                continue
            np_, bp_ = pn["draw_profile"], pb["draw_profile"]
            ntot, btot = np_["total_ms"], bp_["total_ms"]
            keys = list(bp_["buckets"])[:7]
            print(f"**{i}** (profiled draw {f(ntot)} ms native, {f(btot)} ms Pyodide; {np_['calls']:.0f} Python calls/frame)\n")
            print("| file | native ms | native % | Pyodide ms | Pyodide % |\n|---|---|---|---|---|")
            for k in keys:
                nv, bv = np_["buckets"].get(k), bp_["buckets"].get(k)
                print(f"| {k} | {f(nv, 2)} | {f(100 * nv / ntot if nv is not None else None, 0)} | {f(bv, 2)} | {f(100 * bv / btot, 0)} |")
            print()
        if route == "cairo":
            print("## cProfile of the Cairo render step, share by file, after (native | Pyodide)\n")
            for i in ids:
                pb, pn = _first(runs[("pyodide", "after")], i), _first(runs[("native", "after")], i)
                if not pb or not pn or "render_profile" not in pb:
                    continue
                np_, bp_ = pn["render_profile"], pb["render_profile"]
                ntot, btot = np_["total_ms"], bp_["total_ms"]
                keys = list(bp_["buckets"])[:5]
                print(f"**{i}** (profiled {f(ntot)} ms native, {f(btot)} ms Pyodide): " + "; ".join(
                    f"{k} {f(100 * (np_['buckets'].get(k) or 0) / ntot if ntot else None, 0)}% | {f(100 * bp_['buckets'][k] / btot if btot else None, 0)}%" for k in keys) + "\n")
        print()


def pm_table():
    br = (_runs(["prof-browser-canvas.json"]) or [None])[0]
    if br is None:
        return
    print("## postMessage of a frame, worker to page (ms, median of 12; latency = sent to received in the page, includes the clone/decode before onmessage)\n")
    print("| case | ops | JSON bytes | string: send / latency / page JSON.parse | object: send / latency | UTF-8 buffer (transferred): send / latency / decode+parse | flat Float64Array (transferred, 14 numbers per op): send / latency |")
    print("|---|---|---|---|---|---|---|")
    for c in br["cases"]:
        m = c.get("pm")
        if not m:
            continue
        s, o, b, fl = m["string"], m["object"], m["buffer"], m["flat"]
        print(f"| {c['id']} | {m['nOps']} | {m['bytes']['string']:,} | {f(s['sender_ms'], 2)} / {f(s['latency_ms'], 2)} / {f(s['page_decode_ms'], 2)} | "
              f"{f(o['sender_ms'], 2)} / {f(o['latency_ms'], 2)} | {f(b['sender_ms'], 2)} / {f(b['latency_ms'], 2)} / {f(b['page_decode_ms'], 2)} | {f(fl['sender_ms'], 2)} / {f(fl['latency_ms'], 2)} |")
    print()


if __name__ == "__main__":
    if "--more" in sys.argv:
        S.REPEATS = ["", ".r2", ".r3", ".r4", ".r5"]
    if "--prof" in sys.argv:
        prof_tables()
        pm_table()
    else:
        before_after()
