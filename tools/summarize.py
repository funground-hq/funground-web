r"""Build the tables of RESULTS.md from results/ and results_cpu/ (compare.json) and cases/*/ir.json.

    C:\Projects\playground\.venv\Scripts\python.exe tools/summarize.py   # writes results/tables.md
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
OPS = ["Clear", "Circle", "Ellipse", "Rect", "Line", "Point", "Text", "Save", "Restore", "Concat", "ClipPath", "ResetClip",
       "FillPath", "StrokePath", "SetAntialias", "ResetMatrix", "Image", "Pixels", "BeginGroup", "EndGroup"]
DEDICATED = {"Clear": "syn-clear", "Circle": "syn-shapes", "Ellipse": "syn-shapes", "Rect": "syn-shapes", "Line": "syn-shapes",
             "Point": "syn-shapes", "Text": "syn-text", "Save": "syn-transforms", "Restore": "syn-transforms", "Concat": "syn-transforms",
             "ClipPath": "syn-clip", "ResetClip": "syn-clip", "FillPath": "syn-fillpath", "StrokePath": "syn-strokes",
             "SetAntialias": "syn-antialias", "ResetMatrix": "syn-transforms", "Image": "syn-images", "Pixels": "syn-pixels / syn-pixels-2x",
             "BeginGroup": "syn-groups", "EndGroup": "syn-groups"}


def load(d: str) -> dict:
    return {r["case"]: r for r in json.loads((WEB / d / "compare.json").read_text(encoding="utf-8"))}


def case_ops(case: str) -> set[str]:
    doc = json.loads((WEB / "cases" / case / "ir.json").read_text(encoding="utf-8"))
    ops = {o["op"] for s in doc["steps"] for o in s.get("ops", ())} | {o["op"] for o in (doc.get("overlay") or ())}
    return ops


def fmt(r: dict | None) -> str:
    if not r or "diff_pct" not in r:
        return "| - | - | - | - | - "
    return f"| {r['diff_pct']:.2f} | {r['mean_abs']:.2f} | {r['max_diff']} | {r['off_edge_pct']:.3f} | {'pass' if r['pass'] else '**FAIL**'} "


def main() -> None:
    gl, cpu = load("results"), load("results_cpu")
    manifest = {m["case"]: m for m in json.loads((WEB / "cases" / "manifest.json").read_text(encoding="utf-8")) if "case" in m}
    cases = sorted(gl, key=lambda c: (c.startswith("syn-"), c))
    ops_of = {c: case_ops(c) for c in cases}
    out = []
    out.append("### Per case\n")
    out.append("Differing % = pixels with any channel off by more than 8 (of 255). Mean = mean absolute difference per channel. "
               "Max = largest single-channel difference. Off-edge % = differing pixels away from any edge. "
               "ms = the final frame replayed on a warm renderer (7 runs, median, includes a pixel read-back so the work is flushed); "
               "Cairo = pycairo replay of the same frame.\n")
    out.append("| Case | Size | Ops (last frame) | GL: diff % | mean | max | off-edge % | result | CPU: diff % | mean | max | off-edge % | result | ms GL | ms CPU | Cairo ms |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in cases:
        g, p = gl[c], cpu.get(c)
        size = "x".join(map(str, g.get("size", [])))
        nops = manifest.get(c, {}).get("frame_ops") or json.loads((WEB / "cases" / c / "ir.json").read_text(encoding="utf-8")).get("final_frame_ops", "")
        scale = "" if not manifest.get(c) and not c.endswith("2x") and c != "syn-hidpi" else ""
        out.append(f"| {c} | {size} | {nops} {fmt(g)}{fmt(p)}| {g.get('ms_warm', 0):.1f} | {(p or {}).get('ms_warm', 0):.1f} | {g.get('cairo_ms', 0):.2f} |")
    out.append("")
    out.append("### Per op type\n")
    out.append("Cases = how many of the 63 cases contain the op. Pass counts are for GL / CPU raster (see 'Two Chrome rasterisers'). "
               "Worst = highest differing-pixel percentage among the cases that contain it (every such case also contains other ops).\n")
    out.append("| Op type | Cases | Pass GL | Pass CPU | Worst diff % (GL / CPU) | Dedicated case |")
    out.append("|---|---|---|---|---|---|")
    for op in OPS:
        cs = [c for c in cases if op in ops_of[c]]
        pg = sum(1 for c in cs if gl[c].get("pass")); pc = sum(1 for c in cs if cpu.get(c, {}).get("pass"))
        wg = max(gl[c]["diff_pct"] for c in cs); wc = max(cpu[c]["diff_pct"] for c in cs)
        out.append(f"| {op} | {len(cs)} | {pg}/{len(cs)} | {pc}/{len(cs)} | {wg:.2f} / {wc:.2f} | {DEDICATED[op]} |")
    out.append("")
    real = [c for c in cases if not c.startswith("syn-")]
    for name, d in (("GL", gl), ("CPU", cpu)):
        w = [d[c]["ms_warm"] for c in real]
        out.append(f"- {name}: real cases (n={len(real)}) warm ms/frame: median {statistics.median(w):.2f}, mean {statistics.mean(w):.2f}, "
                   f"max {max(w):.1f} ({max(real, key=lambda c: d[c]['ms_warm'])})")
    cw = [gl[c]["cairo_ms"] for c in real]
    out.append(f"- Cairo (pycairo) real cases: median {statistics.median(cw):.2f}, mean {statistics.mean(cw):.2f}, max {max(cw):.1f}")
    for name, d in (("GL", gl), ("CPU", cpu)):
        n = len(d)
        out.append(f"- {name}: {sum(1 for r in d.values() if r.get('pass'))}/{n} cases pass; "
                   f"{sum(1 for r in d.values() if r.get('diff_pct', 0) <= 3)} within 3 % differing; "
                   f"mean abs diff max {max(r['mean_abs'] for r in d.values()):.2f}; "
                   f"edges_only in {sum(1 for r in d.values() if r.get('edges_only'))}/{n}")
    (WEB / "results" / "tables.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
