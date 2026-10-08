r"""Render a batch of cases in headless Chrome and save the PNGs.

    C:\Projects\playground\.venv\Scripts\python.exe tools/run_chrome.py [--out results] case1 case2 ...

A tiny localhost server (this script) serves the repo and receives the results by POST; Chrome is a
single headless process per batch and is killed when the results arrive (or on timeout). Real time
(no virtual-time budget), so the harness's performance.now() timings mean something. Nothing is installed.
"""
from __future__ import annotations

import base64
import http.server
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

CHROME = r"C:\Users\samirj\AppData\Local\Google\Chrome\Application\chrome.exe"
WEB = Path(__file__).resolve().parent.parent


def render(cases: list[str], out: Path, timeout: int = int(__import__("os").environ.get("CHROME_TIMEOUT", "300")), warm: int = 7, extra=()) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    box: dict = {}
    done = threading.Event()

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(WEB), **k)

        def do_GET(self):                          # whole file in one write: the streaming default stalls on 1 MB bodies
            p = (WEB / self.path.split("?")[0].lstrip("/")).resolve()
            if WEB not in p.parents or not p.is_file():
                self.send_error(404); return
            data = p.read_bytes()
            kind = {".html": "text/html", ".js": "text/javascript", ".json": "application/json"}.get(p.suffix, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", kind); self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close"); self.end_headers()
            for i in range(0, len(data), 65536):
                self.wfile.write(data[i:i + 65536]); self.wfile.flush()

        def do_POST(self):
            n = int(self.headers["Content-Length"])
            box["data"] = json.loads(self.rfile.read(n))
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
            done.set()

        def log_message(self, fmt, *a):
            if __import__('os').environ.get('CHROME_LOG'):
                print(fmt % a, file=sys.stderr)

    http.server.ThreadingHTTPServer.request_queue_size = 256
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/harness/index.html?post=1&warm={warm}&cases=" + ",".join(cases)
    profile = tempfile.mkdtemp(prefix="chrome_s135_")
    extra = [*extra, *__import__("os").environ.get("CHROME_EXTRA", "").split()]
    cmd = [CHROME, "--headless=new", f"--user-data-dir={profile}", "--no-first-run",
           "--no-default-browser-check", *extra, url]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not done.wait(timeout):
            raise TimeoutError("no result from Chrome within %ss" % timeout)
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        srv.shutdown()
    meta = box["data"]
    for r in meta:
        d = out / r["case"]
        d.mkdir(parents=True, exist_ok=True)
        png = r.pop("png", None)
        if png:
            (d / "canvas.png").write_bytes(base64.b64decode(png.split(",", 1)[1]))
        (d / "meta.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    return meta


if __name__ == "__main__":
    args = sys.argv[1:]
    out = WEB / "results"
    if args[:1] == ["--out"]:
        out, args = Path(args[1]), args[2:]
    for r in render(args, out):
        print(r["case"], r.get("error", "").split("\n")[0] or f"cold={r['ms_cold']:.1f} warm={r['ms_warm']:.2f}")
