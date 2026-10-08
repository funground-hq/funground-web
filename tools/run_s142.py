r"""Run one S-142 page in headless Chrome and save its result.

    C:\Projects\playground\.venv\Scripts\python.exe tools/run_s142.py --route cairo|canvas --where main|worker [--dpr 1|2]
                                                                       [--cases a,b] [--no-check] [--name NAME]

A localhost server (this script) serves the repository, counts the bytes it sends, receives the page's result by POST
(/result) and its canvas snapshots (/snap, raw RGBA, saved as PNG in results_s142/snaps/). Chrome (--headless=new, a fresh
profile in the scratch folder) is one process tree, stopped by its PID when the result arrives or on timeout.
--dpr 2 runs Chrome with --force-device-scale-factor=2 (devicePixelRatio 2, canvas backing scale 2).
Headless Chrome has no real vsync and no GPU window; see S-142_RESULTS.md.
"""
from __future__ import annotations

import argparse
import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

CHROME = r"C:\Users\samirj\AppData\Local\Google\Chrome\Application\chrome.exe"
WEB = Path(__file__).resolve().parent.parent
SCRATCH = r"C:\Users\samirj\AppData\Local\Temp\claude"
FLAGS = ["--no-first-run", "--no-default-browser-check", "--disable-renderer-backgrounding",
         "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows"]
TYPES = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
         ".py": "text/plain", ".zip": "application/zip", ".whl": "application/zip", ".ttf": "font/ttf"}


def run(args) -> dict:
    box: dict = {}
    sent: dict[str, int] = {}
    done = threading.Event()
    snaps = WEB / "results_s142" / "snaps" / f"{args.name}"
    snaps.mkdir(parents=True, exist_ok=True)

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(WEB), **k)

        def do_GET(self):
            p = (WEB / self.path.split("?")[0].lstrip("/")).resolve()
            if WEB not in p.parents or not p.is_file():
                self.send_error(404)
                return
            data = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(p.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            sent[self.path.split("?")[0]] = sent.get(self.path.split("?")[0], 0) + len(data)
            for i in range(0, len(data), 65536):
                self.wfile.write(data[i:i + 65536])
                self.wfile.flush()

        def do_POST(self):
            n = int(self.headers["Content-Length"])
            body = self.rfile.read(n)
            u = urlparse(self.path)
            if u.path == "/snap":
                q = parse_qs(u.query)
                w, h = int(q["w"][0]), int(q["h"][0])
                Image.frombuffer("RGBA", (w, h), body, "raw", "RGBA", 0, 1).save(snaps / (q["name"][0] + ".png"))
            else:
                box["data"] = json.loads(body)
                done.set()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, fmt, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    query = f"post=1&route={args.route}&where={args.where}&check={0 if args.no_check else 1}"
    if args.cases:
        query += f"&cases={args.cases}"
    if args.reps:
        query += f"&reps={args.reps}"
    url = f"http://127.0.0.1:{srv.server_port}/harness/s142/run.html?{query}"
    prof = tempfile.mkdtemp(prefix="chrome_s142_", dir=SCRATCH)
    cmd = [CHROME, "--headless=new", f"--user-data-dir={prof}", *FLAGS]
    if args.dpr != 1:
        cmd.append(f"--force-device-scale-factor={args.dpr}")
    cmd.append(url)
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"chrome pid {p.pid}", file=sys.stderr, flush=True)
    try:
        if not done.wait(args.timeout):
            raise TimeoutError(f"no result from Chrome within {args.timeout}s")
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        srv.shutdown()
        time.sleep(1)
        shutil.rmtree(prof, ignore_errors=True)
    res = box["data"]
    res["wall_s"] = time.perf_counter() - t0
    res["server_bytes"] = sent
    out = WEB / "results_s142" / f"{args.name}.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True)
    ap.add_argument("--where", required=True)
    ap.add_argument("--dpr", type=int, default=1)
    ap.add_argument("--cases", default="")
    ap.add_argument("--reps", default="")
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--name", default="")
    ap.add_argument("--timeout", type=int, default=1500)
    a = ap.parse_args()
    a.name = a.name or f"browser-{a.route}-{a.where}-{a.dpr}x"
    r = run(a)
    print(json.dumps({k: v for k, v in r.items() if k not in ("ua", "page_resources", "boot_resources", "cases", "server_bytes")}, indent=1))
    for c in r["cases"]:
        ph = c.get("phases") or {}
        e2e = (ph.get("e2e") or {}).get("median")
        print(c["id"], c.get("error") or f"e2e median {e2e} fps {c.get('fps')}")
