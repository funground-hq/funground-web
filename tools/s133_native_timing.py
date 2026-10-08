r"""Native shaping time for the same strings the browser times (every 4th case of the corpus)."""
import json
import os
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
CORE = Path(os.environ.get("FUNGROUND_CORE", r"C:\Projects\playground-0.2"))
os.environ["FUNGROUND_HEADLESS"] = "1"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(WEB / "harness" / "s133"))
import corpus_run

cases = json.loads((WEB / "spikes" / "S-133" / "corpus.json").read_text(encoding="utf-8"))
pick = [c for i, c in enumerate(cases) if i % 4 == 0 and c["text"]]
roots = {"fonts": str(CORE / "funground" / "fonts"), "extra": str(WEB / "harness" / "s133" / "dist" / "extra")}
rep = int(sys.argv[1]) if len(sys.argv) > 1 else 3
print(json.dumps(corpus_run.timings(pick, roots, rep)))
