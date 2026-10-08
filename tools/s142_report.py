r"""Turn results_s142/*.json into the tables of spikes/S-142_RESULTS.md (printed as Markdown).

    C:\Projects\playground\.venv\Scripts\python.exe tools/s142_report.py > results_s142/tables.md
"""
from __future__ import annotations

import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "results_s142"
VARIANTS = [("native", "cairo"), ("chrome", "cairo", "main"), ("chrome", "cairo", "worker"),
            ("native", "canvas"), ("chrome", "canvas", "main"), ("chrome", "canvas", "worker")]
NAMES = {("native", "cairo"): "native Cairo", ("chrome", "cairo", "main"): "Chrome Cairo, page paints",
         ("chrome", "cairo", "worker"): "Chrome Cairo, worker paints", ("native", "canvas"): "native IR (encode only)",
         ("chrome", "canvas", "main"): "Chrome Canvas, page paints", ("chrome", "canvas", "worker"): "Chrome Canvas, worker paints"}


def load(path):
    p = R / path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def med(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def aggregate(cases):
    """Several repeats of one case: per phase the median of the repeats' medians (and of their p95s)."""
    cases = [c for c in cases if c]
    if not cases:
        return None
    ok = [c for c in cases if "phases" in c]
    if not ok:
        return cases[0]
    out = {"id": ok[0]["id"], "reps": len(ok), "canvas": ok[0].get("canvas"), "phases": {}}
    for k in ok[0]["phases"]:
        ss = [c["phases"][k] for c in ok if c["phases"].get(k)]
        out["phases"][k] = {"median": med([x["median"] for x in ss]), "p95": med([x["p95"] for x in ss])} if ss else None
    e = [c["phases"]["e2e"]["median"] for c in ok if c["phases"].get("e2e")]
    out["e2e_range"] = (min(e), max(e)) if e else None
    for k in ("fps", "skipped_ticks"):
        v = [c[k] for c in ok if c.get(k) is not None]
        out[k] = med(v)
    return out


def get_all():
    data = {}
    for dpr in (1, 2):
        for v in VARIANTS:
            stem = f"native-{v[1]}-{dpr}x" if v[0] == "native" else f"browser-{v[1]}-{v[2]}-{dpr}x"
            files = [stem + ".json", stem + ".r2.json", stem + ".r3.json"]
            runs = [load(x) for x in files]
            per = {}
            for d in runs:
                if d:
                    for c in d["cases"]:
                        per.setdefault(c["id"], []).append(c)
            data[(v, dpr)] = {i: aggregate(cs) for i, cs in per.items()}
    return data


def f(x, nd=1):
    return "-" if x is None else f"{x:.{nd}f}"


def mp(s, nd=1):
    """median / p95 of a stat dict (native: median/p95; browser: same keys)."""
    if not s:
        return "-"
    return f"{s['median']:.{nd}f} / {s['p95']:.{nd}f}"


def row(v, c):
    """cells for one variant of one case; keys harmonised between native and browser results."""
    if c is None:
        return ["not run"] + ["-"] * 10
    if "error" in c:
        return ["error: " + c["error"][:60]] + ["-"] * 10
    ph = c["phases"]
    if v[0] == "native":
        e2e = ph["e2e"]
        return [mp(ph["draw"]), mp(ph["other"]), mp(ph["render"]), mp(ph["encode"]), mp(ph["copy"]), "-", "-", "-", mp(e2e), "-", "-"]
    fps = c.get("fps")
    return [mp(ph["draw_py"]), mp(ph["py_other"]), mp(ph["render_cairo"]), mp(ph["encode"]), mp(ph["wasm_copy"]), mp(ph["transfer"]),
            mp(ph["parse"]), mp(ph["paint"]), mp(ph["e2e"]), f(fps), f(c.get("skipped_ticks"), 0) if fps else "-"]


def main():
    data = get_all()
    ids = []
    for d in data.values():
        for i in d:
            if i not in ids:
                ids.append(i)
    meta = {}
    for (v, dpr), d in data.items():
        for i, c in d.items():
            if c.get("canvas"):
                meta.setdefault(i, c["canvas"][:2])
            if "ops_median" in c:
                meta.setdefault(i + ":ops", c["ops_median"])
    print("## Tables per case (median / p95 in ms; fps and skipped ticks are for the 30 timed frames under rAF)\n")
    for i in ids:
        print(f"### {i}\n")
        print("| scale | route | draw() | py other | Cairo render | encode (JSON) | wasm->JS copy | message | JSON.parse | paint | end to end | fps | skipped ticks |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for dpr in (1, 2):
            for v in VARIANTS:
                c = data[(v, dpr)].get(i)
                cells = row(v, c)
                print(f"| {dpr}x | {NAMES[v]} | " + " | ".join(cells) + " |")
        print()


def e2e(c):
    return c["phases"]["e2e"]["median"] if c and "phases" in c and c["phases"].get("e2e") else None


def summary(data, ids):
    print("## Summary: end-to-end frame time, median of 3 runs (ms) and achieved fps\n")
    for dpr in (1, 2):
        print(f"### {dpr}x\n")
        print("| case | native Cairo | Chrome Cairo (page) | Chrome Cairo (worker) | native IR | Chrome Canvas (page) | Chrome Canvas (worker) | fps Cairo page / worker | fps Canvas page / worker | Cairo(page) / Canvas(page) |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        ratios = []
        for i in ids:
            cs = [data[(v, dpr)].get(i) for v in VARIANTS]
            vals = [e2e(c) for c in cs]
            fp = lambda c: "-" if not c or not c.get("fps") else f"{c['fps']:.0f}"
            r = vals[1] / vals[4] if vals[1] and vals[4] else None
            if r:
                ratios.append(r)
            print(f"| {i} | " + " | ".join(f(x) for x in vals[:3]) + f" | {f(vals[3])} | {f(vals[4])} | {f(vals[5])} | {fp(cs[1])} / {fp(cs[2])} | {fp(cs[4])} / {fp(cs[5])} | {f(r, 2)} |")
        if ratios:
            print(f"\nMean Cairo/Canvas ratio of end-to-end medians (page paints), cases both routes ran: {sum(ratios)/len(ratios):.2f} over {len(ratios)} cases.\n")
    print("### Spread of the end-to-end median across the 3 runs (min - max, ms), Chrome, page paints, 1x\n")
    print("| case | Cairo | Canvas |\n|---|---|---|")
    for i in ids:
        a, b = data[(VARIANTS[1], 1)].get(i), data[(VARIANTS[4], 1)].get(i)
        rg = lambda c: "-" if not c or not c.get("e2e_range") else f"{c['e2e_range'][0]:.1f} - {c['e2e_range'][1]:.1f}"
        print(f"| {i} | {rg(a)} | {rg(b)} |")
    print()


def first_load():
    print("## First load (cold: fresh Chrome profile for every run; Pyodide and PyPI from the real network)\n")
    print("| route / where / dpr | Pyodide load | fonttools+micropip | uharfbuzz (micropip, PyPI) | pathops | pycairo | funground+fonts fetch | import funground | boot total | first frame since navigation |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for route in ("cairo", "canvas"):
        for where in ("main", "worker"):
            for dpr in (1, 2):
                rows = [load(x) for x in (f"browser-{route}-{where}-{dpr}x.json", f"browser-{route}-{where}-{dpr}x.r2.json", f"browser-{route}-{where}-{dpr}x.r3.json")]
                rows = [r for r in rows if r and r.get("boot")]
                if not rows:
                    continue
                m = lambda k: med([r["boot"].get(k) for r in rows])
                ff = med([r.get("first_frame_ms") for r in rows])
                print(f"| {route} / {where} / {dpr}x ({len(rows)} runs) | " + " | ".join(f(m(k) / 1000 if m(k) is not None else None, 2) + " s" for k in ("load_pyodide", "load_fonttools_micropip", "micropip_uharfbuzz", "install_pathops", "install_pycairo", "fetch_funground_fonts", "import_funground", "total")) + f" | {f(ff / 1000, 2)} s |")
    print()
    r = load("browser-cairo-main-1x.json")
    cats = {}
    for e in r["boot_resources"]:
        n = e["name"]
        sz = e["encoded"] or e["transfer"]
        key = ("Pyodide core (pyodide.mjs, lock, stdlib zip, asm.wasm, asm.mjs)" if "/pyodide" in n or "python_stdlib" in n else
               "fonttools wheel" if "fonttools" in n else "micropip wheel" if "micropip" in n else
               "uharfbuzz wheel (PyPI; size not reported by the browser)" if "uharfbuzz" in n or "pypi.org" in n else
               "skia-pathops wheel" if "skia_pathops" in n else "pycairo wheel" if "pycairo" in n else
               "funground.zip" if "funground.zip" in n else "fonts (7 files, all loaded)" if "/fonts/" in n else "shim, mixer stub, fonts.json")
        cats[key] = cats.get(key, 0) + sz
    cats["uharfbuzz wheel (PyPI; size not reported by the browser)"] = 981875      # file size, from S-133 / the CI artifact
    cairo_total = sum(cats.values())
    print("Bytes downloaded at boot (encoded body sizes; localhost files are uncompressed; Pyodide's come gzip/brotli-free as reported):\n")
    print("| component | cairo route | canvas route |\n|---|---|---|")
    for k, v in cats.items():
        print(f"| {k} | {v:,} | {0 if k == 'pycairo wheel' else v:,} |")
    print(f"| **total** | **{cairo_total:,}** | **{cairo_total - cats['pycairo wheel']:,}** |\n")


if __name__ == "__main__":
    import sys
    data = get_all()
    ids = []
    for d in data.values():
        for i in d:
            if i not in ids:
                ids.append(i)
    summary(data, ids)
    first_load()
    main()
    main()
