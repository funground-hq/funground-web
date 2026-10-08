r"""Compare Canvas 2D renders (results/<case>/canvas.png) with the Cairo references (cases/<case>/ref.png).

    C:\Projects\playground\.venv\Scripts\python.exe tools/compare.py [case ...]   # default: every case in results/

Per case (written to results/compare.json and results/<case>/diff.png):
  diff_pct       percent of pixels whose RGB differs by more than 8/255 in any channel (spike 08's definition)
  mean_abs       mean absolute difference per channel, 0..255
  max_diff       largest single-channel difference
  strong_pct     percent of pixels differing by more than 64 (a clearly different colour, not just a shifted edge)
  off_edge_pct   percent of pixels that differ by more than 8 AND sit where neither image has an edge
                 (an edge = max-min of a 5x5 window above 12 in any channel, in either image)
  edges_only     off_edge_pct <= 0.2 and nothing differs by more than 64 outside an edge
  pass           diff_pct <= 3 and mean_abs <= 3 and edges_only
diff.png: grey = |difference| x 4, yellow = differs on an edge, red = differs away from any edge.
Uses Pillow only (no numpy).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

WEB = Path(__file__).resolve().parent.parent
RESULTS = Path(__import__("os").environ.get("RESULTS_DIR", WEB / "results"))
CASES = WEB / "cases"
T_DIFF, T_STRONG, T_EDGE = 8, 64, 12


def maxchan(img: Image.Image) -> Image.Image:
    r, g, b = img.split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b)


def edge_mask(img: Image.Image) -> Image.Image:
    hi, lo = img.filter(ImageFilter.MaxFilter(5)), img.filter(ImageFilter.MinFilter(5))
    return maxchan(ImageChops.subtract(hi, lo)).point(lambda v: 255 if v > T_EDGE else 0)


def count(mask: Image.Image) -> int:
    return mask.histogram()[255]


def compare(case: str) -> dict:
    ref = Image.open(CASES / case / "ref.png").convert("RGB")
    got_path = RESULTS / case / "canvas.png"
    if not got_path.exists():
        return {"case": case, "error": "no render"}
    got = Image.open(got_path).convert("RGB")
    if ref.size != got.size:
        return {"case": case, "error": f"size {got.size} vs {ref.size}"}
    n = ref.size[0] * ref.size[1]
    d = ImageChops.difference(ref, got)
    dm = maxchan(d)
    differs = dm.point(lambda v: 255 if v > T_DIFF else 0)
    strong = dm.point(lambda v: 255 if v > T_STRONG else 0)
    edges = ImageChops.lighter(edge_mask(ref), edge_mask(got))
    off = ImageChops.multiply(differs, ImageChops.invert(edges))          # 255 where differs and not an edge
    off = off.point(lambda v: 255 if v > 200 else 0)
    off_strong = ImageChops.multiply(strong, ImageChops.invert(edges)).point(lambda v: 255 if v > 200 else 0)
    hist = d.histogram()                                                  # 3 x 256 bins
    total = sum(v * c for ch in range(3) for v, c in enumerate(hist[ch * 256:(ch + 1) * 256]))
    mean_abs = total / (3 * n)
    max_diff = max(v for ch in range(3) for v in range(256) if hist[ch * 256 + v])
    res = {
        "case": case, "size": list(ref.size), "diff_pct": 100 * count(differs) / n, "mean_abs": mean_abs,
        "max_diff": max_diff, "strong_pct": 100 * count(strong) / n, "off_edge_pct": 100 * count(off) / n,
        "off_edge_strong_px": count(off_strong),
    }
    lum = lambda im: sum(i * c for i, c in enumerate(im.convert("L").histogram())) / n
    res["lum_bias"] = lum(got) - lum(ref)          # mean luminance, Canvas minus Cairo (positive: Canvas lighter)
    res["edges_only"] = res["off_edge_pct"] <= 0.2 and res["off_edge_strong_px"] == 0
    res["pass"] = res["diff_pct"] <= 3 and res["mean_abs"] <= 3 and res["edges_only"]
    # diff image
    grey = dm.point(lambda v: min(255, v * 4)).convert("RGB")
    yellow = Image.new("RGB", ref.size, (255, 220, 0))
    red = Image.new("RGB", ref.size, (255, 0, 0))
    grey = Image.composite(yellow, grey, differs)
    grey = Image.composite(red, grey, off)
    grey.save(RESULTS / case / "diff.png")
    sheet = Image.new("RGB", (ref.size[0] * 3 + 8, ref.size[1]), (128, 128, 128))
    sheet.paste(ref, (0, 0)); sheet.paste(got, (ref.size[0] + 4, 0)); sheet.paste(grey, (ref.size[0] * 2 + 8, 0))
    sheet.save(RESULTS / case / "side.png")        # Cairo | Canvas 2D | diff
    meta = RESULTS / case / "meta.json"
    if meta.exists():
        m = json.loads(meta.read_text(encoding="utf-8"))
        res.update({k: m.get(k) for k in ("ms_cold", "ms_warm", "cairo_ms", "ops", "error")})
    return res


def main() -> None:
    cases = sys.argv[1:] or sorted(p.name for p in RESULTS.iterdir() if (p / "canvas.png").exists())
    out = []
    for c in cases:
        r = compare(c)
        out.append(r)
        if "error" in r and "diff_pct" not in r:
            print(f"{c}: {r['error']}")
        else:
            print(f"{c}: diff={r['diff_pct']:.2f}% mean={r['mean_abs']:.2f} max={r['max_diff']} off_edge={r['off_edge_pct']:.3f}% "
                  f"{'PASS' if r['pass'] else 'FAIL'}")
    prev = {}
    f = RESULTS / "compare.json"
    if f.exists():
        prev = {r["case"]: r for r in json.loads(f.read_text(encoding="utf-8"))}
    prev.update({r["case"]: r for r in out})
    f.write_text(json.dumps(sorted(prev.values(), key=lambda r: r["case"]), indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
