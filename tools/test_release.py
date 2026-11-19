r"""Run a sketch with a release folder alone, in headless Chrome (story S-268).

    C:\Projects\playground\.venv\Scripts\python.exe tools/test_release.py dist/funground-web-0.1.0 [--chrome PATH] [--pyodide DIR]

The check a host makes before it takes a release: tools/make_release.py --check first (the folder holds exactly what
release.json lists), then a page that is not part of the release uses it as an outside host would, from /release/ on a
localhost server that serves the folder and nothing else of this repository. Pyodide comes from its address in release.json
("uses"), as on a visitor's machine, or with --pyodide DIR from that folder (served at /pyodide/ and given to the runner as
pyodideUrl, as a host that keeps its own copy of Pyodide does; vscode-extension/build.py --runtime bundled makes one). The page:

  * runs a funground sketch (the runner as Play starts it) and reads a pixel of its picture;
  * starts a second runner with Pyodide alone (packages: []), checks `ready` lists run, stop, stdin and check, runs a plain
    script with input lines, sends a check with one passing and one failing test, and stops a `while True:` loop.

It fails if any of that goes wrong, or if the page asked /release/ for a file release.json does not list (a file the
release lacks). Chrome is started with a profile of its own and ended by this script. Standard library only.
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from make_release import check  # noqa: E402

CHROMES = [
    r"C:\Users\samirj\AppData\Local\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
]
FLAGS = ["--headless=new", "--no-first-run", "--no-default-browser-check", "--disable-renderer-backgrounding",
         "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows"]
TYPES = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
         ".py": "text/plain", ".whl": "application/zip", ".md": "text/plain", ".wasm": "application/wasm", ".zip": "application/zip"}
TIMEOUT = 300                                                   # seconds for the whole page: two cold Python starts

PAGE = r"""<!doctype html>
<meta charset="utf-8">
<title>release check</title>
<canvas id="canvas" width="120" height="80"></canvas>
<script type="module">
import { createRunner } from "/release/runner.js";
const pyodideUrl = PYODIDE_URL;                                          // null: the runner's default (jsDelivr)
const where = { baseUrl: new URL("/release/", location.href), ...(pyodideUrl ? { pyodideUrl } : {}) };
const results = [];
const note = (name, passed, detail = "") => {
  results.push({ name, passed: Boolean(passed), detail: String(detail) });
  fetch("/progress", { method: "POST", body: name });                     // so a page that hangs shows how far it got
};
const report = () => fetch("/report", { method: "POST", body: JSON.stringify(results) });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
try {
  // 1. The runner as Play starts it: funground and its libraries.
  let printed = "";
  const canvas = document.getElementById("canvas");
  const play = await createRunner({ canvas, output: (text) => { printed += text; }, ...where, prewarm: false });
  note("funground runner ready", play.info?.versions?.pycairo, JSON.stringify(play.info?.versions));
  const started = await play.run("import funground as f\nf.size(120, 80)\nf.background('red')\nprint('drawn')\nf.show()\n", { filename: "sketch.py" });
  await sleep(300);
  const pixel = canvas.getContext("2d").getImageData(Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 1, 1).data;
  note("funground sketch runs", started.ok, JSON.stringify(started));
  note("funground sketch draws red", pixel[0] > 200 && pixel[1] < 60 && pixel[2] < 60, Array.from(pixel).join(","));
  note("funground sketch prints", printed.includes("drawn"), printed);

  // 2. Pyodide alone, as an outside host that runs plain Python starts it (S-274), with stdin, check and stop.
  let out = "";
  const plain = await createRunner({ canvas: document.createElement("canvas"), output: (text) => { out += text; }, ...where, packages: [], prewarm: true });
  const words = plain.info?.capabilities ?? [];
  note("plain runner lists run, stop, stdin, check", ["run", "stop", "stdin", "check"].every((w) => words.includes(w)), words.join(","));
  await plain.run("name = input('Name? ')\nprint('hello', name)\n", { filename: "main.py", stdin: ["Ada"] });
  await sleep(200);
  note("plain script reads its input line", out.includes("Name? hello Ada"), out);
  const answer = await plain.check("def double(x):\n    return 2 * x\n", { tests: [
    { name: "two", code: "assert double(2) == 4" },
    { name: "five", code: "assert double(2) == 5, 'double(2) should be 5'" },
  ] });
  note("check answers both tests", answer.tests?.length === 2 && answer.tests[0].passed && !answer.tests[1].passed
       && answer.tests[1].message.includes("double(2) should be 5"), JSON.stringify(answer));
  // Without `reuse`, every run gets a new Python, so this one waits for it to load; stop() before the run has started does
  // nothing (it is not running yet), so the page waits until it is.
  const looping = plain.run("while True:\n    pass\n", { filename: "loop.py" });
  for (let i = 0; i < 600 && !plain.running; i++) await sleep(100);
  await sleep(300);
  const before = performance.now();
  await plain.stop();
  await looping;
  note("stop ends a while True loop", !plain.running, `${Math.round(performance.now() - before)} ms`);
  out = "";
  await plain.run("print('after stop')\n", { filename: "after.py" });
  await sleep(200);
  note("a run after stop works", out.includes("after stop"), out);
} catch (error) {
  note("the page ran to the end", false, error.stack ?? error);
}
await report();
</script>
"""


def find_chrome(given: str | None) -> str:
    for candidate in ([given] if given else []) + [os.environ.get("CHROME")] + CHROMES:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("Chrome not found: give --chrome PATH")


def serve(folder: Path, listed: set[str], pyodide: Path | None) -> tuple[http.server.ThreadingHTTPServer, dict]:
    page = PAGE.replace("PYODIDE_URL", '"/pyodide/"' if pyodide else "null").encode()
    state = {"report": None, "requests": [], "unlisted": []}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
            state["requests"].append(path)
            if path in ("/", "/index.html"):
                return self.send(200, page, "text/html")
            if pyodide and path.startswith("/pyodide/"):
                file = (pyodide / path[len("/pyodide/"):]).resolve()
                if not file.is_relative_to(pyodide) or not file.is_file():
                    return self.send(404, b"", "text/plain")
                return self.send(200, file.read_bytes(), TYPES.get(file.suffix, "application/octet-stream"))
            if path.startswith("/release/"):
                relative = path[len("/release/"):]
                file = (folder / relative).resolve()
                if relative not in listed or not file.is_relative_to(folder) or not file.is_file():
                    state["unlisted"].append(relative)
                    return self.send(404, b"not in the release", "text/plain")
                return self.send(200, file.read_bytes(), TYPES.get(file.suffix, "application/octet-stream"))
            return self.send(404, b"", "text/plain")

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/report":
                state["report"] = json.loads(body)
            elif self.path == "/progress":
                print(f"  ... {body.decode()}", flush=True)
            self.send(204, b"", "text/plain")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("folder", type=Path, help="a release folder made by tools/make_release.py")
    parser.add_argument("--pyodide", type=Path, help="serve Pyodide from this folder instead of its address in release.json")
    parser.add_argument("--chrome", help="Chrome's executable (default: found in the usual places, or $CHROME)")
    args = parser.parse_args()
    folder = args.folder.resolve()
    problems = check(folder)
    if problems:
        raise SystemExit("the folder does not match its release.json:\n  " + "\n  ".join(problems))
    release = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    listed = {f["path"] for f in release["files"]} | {"release.json"}
    print(f"{folder.name}: {len(release['files'])} files match release.json")

    server, state = serve(folder, listed, args.pyodide.resolve() if args.pyodide else None)
    profile = Path(tempfile.mkdtemp(prefix="fg-release-chrome-"))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    chrome = subprocess.Popen([find_chrome(args.chrome), *FLAGS, f"--user-data-dir={profile}", url],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ended = False
    try:
        deadline = time.time() + TIMEOUT
        while state["report"] is None and time.time() < deadline and chrome.poll() is None:
            time.sleep(0.5)
        ended = chrome.poll() is not None
    finally:
        chrome.terminate()
        try:
            chrome.wait(10)
        except subprocess.TimeoutExpired:
            chrome.kill()
        server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    if state["report"] is None:
        raise SystemExit(f"the page did not report within {TIMEOUT} s (Chrome {'ended by itself' if ended else 'was stopped'}); the last file it asked for: {state['requests'][-1:]}")
    failed = 0
    for result in state["report"]:
        failed += not result["passed"]
        print(f"{'ok  ' if result['passed'] else 'FAIL'}  {result['name']}: {result['detail'][:160]}")
    asked = sorted({p[len('/release/'):] for p in state["requests"] if p.startswith("/release/")})
    print(f"the page fetched {len(asked)} files of the release")
    for name in state["unlisted"]:
        failed += 1
        print(f"FAIL  the page asked for {name}, which the release does not hold")
    if failed:
        raise SystemExit(f"{failed} check{'s' if failed > 1 else ''} failed")
    print("the release runs a sketch and plain Python on its own")


if __name__ == "__main__":
    main()
