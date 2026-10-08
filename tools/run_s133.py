r"""Run one S-133 page (a copy of tools/run_s136.py with a page argument and a PNG saved from the result) in headless Chrome and print/save the result JSON.

    C:\Projects\playground\.venv\Scripts\python.exe tools/run_s133.py harness/s133/text.html "x=1" [--name NAME] [--profile DIR] [--visible]

A localhost server (this script) serves the repository and receives the page's result by POST. Chrome is
one process tree per run; it is stopped by its PID when the result arrives or on timeout. Nothing is installed.
Results go to results_s136/<name>.json.
"""
from __future__ import annotations

import argparse
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

CHROME = r"C:\Users\samirj\AppData\Local\Google\Chrome\Application\chrome.exe"
WEB = Path(__file__).resolve().parent.parent
FLAGS = ["--no-first-run", "--no-default-browser-check", "--disable-renderer-backgrounding",
         "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows"]


def run(page: str, query: str, name: str, profile: str | None, visible: bool, timeout: int, extra: list[str]) -> dict:
    box: dict = {}
    done = threading.Event()

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(WEB), **k)

        def do_GET(self):
            p = (WEB / self.path.split("?")[0].lstrip("/")).resolve()
            if WEB not in p.parents or not p.is_file():
                self.send_error(404)
                return
            data = p.read_bytes()
            kind = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
                    ".py": "text/plain", ".zip": "application/zip", ".wasm": "application/wasm"}.get(p.suffix, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=3600")      # lets the "warm" run use Chrome's HTTP cache
            self.send_header("Connection", "close")
            self.end_headers()
            for i in range(0, len(data), 65536):
                self.wfile.write(data[i:i + 65536])
                self.wfile.flush()

        def do_POST(self):
            n = int(self.headers["Content-Length"])
            box["data"] = json.loads(self.rfile.read(n))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            done.set()

        def log_message(self, fmt, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/{page}?post=1&{query}"
    prof = profile or tempfile.mkdtemp(prefix="chrome_s136_")
    cmd = [CHROME, *([] if visible else ["--headless=new"]), f"--user-data-dir={prof}", *FLAGS, *extra, url]
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"chrome pid {p.pid}", file=sys.stderr)
    try:
        if not done.wait(timeout):
            raise TimeoutError(f"no result from Chrome within {timeout}s")
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        srv.shutdown()
    res = box["data"]
    res["wall_s"] = time.perf_counter() - t0
    png = res.pop("png", None)
    out = WEB / "results_s133"
    out.mkdir(exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    if png:
        import base64
        (out / f"{name}.png").write_bytes(base64.b64decode(png.split(",", 1)[1]))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("query")
    ap.add_argument("--name", default="run")
    ap.add_argument("--profile")
    ap.add_argument("--visible", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--chrome-arg", action="append", default=[])
    a = ap.parse_args()
    r = run(a.page, a.query, a.name, a.profile, a.visible, a.timeout, a.chrome_arg)
    print(json.dumps({k: v for k, v in r.items() if k != "ua"}, indent=1))
