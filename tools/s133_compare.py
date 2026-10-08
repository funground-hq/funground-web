r"""Compare the browser run of the S-133 corpus with the native reference.

    C:\Projects\playground\.venv\Scripts\python.exe tools/s133_compare.py [results_s133/NAME.json]

Per case: glyph ids, advances, offsets and clusters of every run, the advance, and the SHA-256 / op count of the
FillPath ops at each size. Prints totals per source (sketch / tests / extra) and the first differences.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
OUT = WEB / "spikes" / "S-133"
name = sys.argv[1] if len(sys.argv) > 1 else str(WEB / "results_s133" / "text_run1.json")
corpus = json.loads((OUT / "corpus.json").read_text(encoding="utf-8"))
ref = json.loads((OUT / "reference.json").read_text(encoding="utf-8"))
got = json.loads(Path(name).read_text(encoding="utf-8"))["run"]
print("native harfbuzz", ref["hb"], "| native run", round(ref["seconds"], 1), "s | browser run", round(got["seconds"], 1), "s")
kinds = ("glyph ids", "advances", "offsets", "clusters", "run fonts", "advance", "ops hash", "errors")
total, bad = Counter(), defaultdict(list)
for c, r, g in zip(corpus, ref["results"], got["results"]):
    src = "tests" if c["src"].startswith("tests") else "extra" if c["src"].startswith("extra") else "sketch"
    total[src] += 1
    if "error" in r or "error" in g:
        if r.get("error") != g.get("error"):
            bad[("errors", src)].append((c["id"], r.get("error"), g.get("error")))
        continue
    rr, gr = r["runs"], g["runs"]
    if [x["font"] for x in rr] != [x["font"] for x in gr]:
        bad[("run fonts", src)].append((c["id"], c["text"][:40])); continue
    for a, b in zip(rr, gr):
        A, B = a["glyphs"], b["glyphs"]
        if len(A) != len(B) or [x[0] for x in A] != [x[0] for x in B]:
            bad[("glyph ids", src)].append((c["id"], c["text"][:40], len(A), len(B))); break
        for k, kind in ((1, "advances"), (2, "offsets"), (3, "offsets"), (4, "clusters")):
            if [x[k] for x in A] != [x[k] for x in B]:
                bad[(kind, src)].append((c["id"], c["text"][:40])); break
    if r["advance"] != g["advance"]:
        bad[("advance", src)].append((c["id"], r["advance"], g["advance"]))
    if r["ops"] != g["ops"]:
        bad[("ops hash", src)].append((c["id"], c["text"][:40], c["font"]))
print("cases:", dict(total), "total", sum(total.values()))
if not bad:
    print("ALL IDENTICAL")
for (kind, src), items in sorted(bad.items()):
    print(f"DIFF {kind} [{src}]: {len(items)}  e.g. {items[:3]}")
