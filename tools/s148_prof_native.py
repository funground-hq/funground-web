r"""S-148 native profile: the phase split and cProfile shares of the heavy cases, in CPython.

    C:\Projects\playground\.venv\Scripts\python.exe tools/s148_prof_native.py --route cairo|canvas [--scale 1]

Same code as in Pyodide (harness/s148/prof_shim.py). Writes results_s148/prof-native-<route>-<scale>x.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
SCRATCH = Path(r"C:\Users\samirj\AppData\Local\Temp\claude")
SRC = Path(os.environ.get("FUNGROUND_SRC", SCRATCH / "fg_s148"))
DIST = WEB / "harness" / "s142" / "dist"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True)
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    sys.path.insert(0, str(SRC))
    sys.path.insert(0, str(WEB / "harness" / "s142"))
    sys.path.insert(0, str(WEB / "harness" / "s148"))
    import shim
    import prof_shim
    host = shim.Host(a.route)
    cases = [c for c in json.loads((DIST / "cases.json").read_text(encoding="utf-8")) if c["group"] == "heavy"]
    res = {"route": a.route, "scale": a.scale, "python": sys.version.split()[0], "cases": []}
    for c in cases:
        source = (DIST / "sketches" / f"{c['id']}.py").read_text(encoding="utf-8")
        try:
            r = json.loads(prof_shim.profile(host, c["id"], c["kind"], source, a.scale, a.route))
        except BaseException as exc:                  # noqa: BLE001
            if isinstance(exc, KeyboardInterrupt):
                raise
            r = {"id": c["id"], "error": f"{type(exc).__name__}: {exc}"}
        res["cases"].append(r)
        print(r["id"], r.get("error") or r["timers"], flush=True)
    out = WEB / "results_s148" / f"prof-native{a.tag}-{a.route}-{int(a.scale)}x.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
