r"""Compare the canvas snapshots of the S-142 runs (results_s148/snaps/<run>/<route>-<where>-<case>.png) with the goldens.

    C:\Projects\playground\.venv\Scripts\python.exe tools/s142_pixels.py [run ...]      # default: every run with snapshots

Each snapshot is the canvas read back (getImageData) after the 30th frame (a script: after its run), at devicePixelRatio 1.
Per snapshot: byte-identical to the golden (RGB), or S-135's measures (compare.py): percent of pixels differing by more than 8,
mean absolute difference, max difference, differences away from edges; "pass" = S-135's tolerance (<= 3 % of pixels, mean <= 3,
edges only). Writes results_s148/pixels.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare as C                      # noqa: E402  (S-135's helpers)

WEB = Path(__file__).resolve().parent.parent
CORE = Path(r"C:\Projects\playground-0.2")
SNAPS = WEB / "results_s148" / "snaps"


def golden_for(case: str) -> Path | None:
    if case.startswith("s1-"):
        p = CORE / "tests" / "golden" / (case[3:] + ".png")
    else:
        p = CORE / "tests" / "golden" / "gallery" / (case + ".png")
    return p if p.exists() else None


def measure(ref: Image.Image, got: Image.Image) -> dict:
    n = ref.size[0] * ref.size[1]
    d = ImageChops.difference(ref, got)
    dm = C.maxchan(d)
    differs = dm.point(lambda v: 255 if v > C.T_DIFF else 0)
    strong = dm.point(lambda v: 255 if v > C.T_STRONG else 0)
    edges = ImageChops.lighter(C.edge_mask(ref), C.edge_mask(got))
    off = ImageChops.multiply(differs, ImageChops.invert(edges)).point(lambda v: 255 if v > 200 else 0)
    off_strong = ImageChops.multiply(strong, ImageChops.invert(edges)).point(lambda v: 255 if v > 200 else 0)
    hist = d.histogram()
    total = sum(v * c for ch in range(3) for v, c in enumerate(hist[ch * 256:(ch + 1) * 256]))
    r = {"diff_pct": 100 * C.count(differs) / n, "mean_abs": total / (3 * n),
         "max_diff": max((v for ch in range(3) for v in range(256) if hist[ch * 256 + v]), default=0),
         "off_edge_pct": 100 * C.count(off) / n, "off_edge_strong_px": C.count(off_strong)}
    r["pass"] = r["diff_pct"] <= 3 and r["mean_abs"] <= 3 and r["off_edge_pct"] <= 0.2 and r["off_edge_strong_px"] == 0
    return r


def main() -> None:
    runs = sys.argv[1:] or sorted(p.name for p in SNAPS.iterdir() if p.is_dir())
    out = {}
    for run in runs:
        for png in sorted((SNAPS / run).glob("*.png")):
            name = png.stem                            # <route>-<where>-<case>
            route, where, case = name.split("-", 2)
            g = golden_for(case)
            if g is None:
                out[f"{run}/{name}"] = {"error": "no golden"}
                continue
            ref, got = Image.open(g).convert("RGB"), Image.open(png).convert("RGB")
            if ref.size != got.size:
                out[f"{run}/{name}"] = {"error": f"size {got.size} vs golden {ref.size}"}
                continue
            r = {"identical": ref.tobytes() == got.tobytes()}
            if not r["identical"]:
                r.update(measure(ref, got))
            r["route"], r["where"], r["case"], r["run"] = route, where, case, run
            out[f"{run}/{name}"] = r
            print(f"{run:28s} {case:36s} " + ("byte-identical" if r["identical"] else
                  f"diff={r['diff_pct']:.2f}% mean={r['mean_abs']:.2f} max={r['max_diff']} off_edge={r['off_edge_pct']:.3f}% {'PASS' if r['pass'] else 'FAIL'}"))
    (WEB / "results_s148" / "pixels.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
