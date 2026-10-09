r"""Check the frames run_tests.mjs saved against funground's goldens (spike S-156).

    C:\Projects\playground\.venv\Scripts\python.exe vscode-extension/test/compare.py --funground C:\Projects\playground-0.2 out/<label>

A golden case passes when the frame is byte-identical to the golden (RGB, as tools/test_runner.py compares). The picture
case passes when the drawn picture's pixels equal the PNG's, at the place the sketch draws it (20, 20). Writes the
results into the report's "pixels" and prints them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

PICTURE_AT = (20, 20)                      # where test/sketchbook/photo.py draws data/photo.png, at its own size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--funground", required=True, type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    report_path = args.out / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = {}
    for case_id, case in report["cases"].items():
        raw = args.out / "frames" / f"{case_id}.rgba"
        if not raw.exists():
            continue
        frame = Image.frombuffer("RGBA", (case["width"], case["height"]), raw.read_bytes(), "raw", "RGBA", 0, 1).convert("RGB")
        if case.get("golden"):
            golden = Image.open(args.funground / case["golden"]).convert("RGB")
            if frame.size != golden.size:
                results[case_id] = {"identical": False, "why": f"size {frame.size} vs golden {golden.size}"}
                continue
            a, g = frame.tobytes(), golden.tobytes()
            differing = sum(1 for i in range(0, len(a), 3) if a[i:i + 3] != g[i:i + 3]) if a != g else 0
            results[case_id] = {"identical": a == g, "differing_pixels": differing, "size": list(frame.size), "golden": case["golden"]}
        elif case.get("picture"):
            picture = Image.open(args.out / "sketchbook" / case["picture"]).convert("RGB")
            x, y = PICTURE_AT
            drawn = frame.crop((x, y, x + picture.width, y + picture.height))
            results[case_id] = {"identical": drawn.tobytes() == picture.tobytes(), "size": list(picture.size), "picture": case["picture"]}
    report["pixels"] = results
    report_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
