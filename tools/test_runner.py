r"""Test the browser runner in headless Chrome (story S-153).

    C:\Projects\playground\.venv\Scripts\python.exe tools/test_runner.py --funground C:\Projects\playground-0.2 [--profile DIR] [--dpr 2]

Needs runner/runtime/ (tools/build_runtime.py). A localhost server (this script) serves the repository, counts the
bytes it sends, hands tests/runner/test.html its list of cases, and receives the page's report and the canvas
snapshots. Chrome (--headless=new, its own profile) is started and stopped by its PID; the maintainer's Chrome is never
touched. By default the profile is new and deleted afterwards (a cold start); --profile DIR keeps it, so a second
run with the same DIR measures a warm start.

Pixel check: the runner's frame (1x) must equal the golden of tests/golden byte for byte. Pillow reads the PNGs.
At another scale (--dpr 1.25) there is no golden: the check is that the frame is the golden's size times the scale
(to within a pixel) and not blank.
"""
from __future__ import annotations

import argparse
import http.server
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image

CHROME = r"C:\Users\samirj\AppData\Local\Google\Chrome\Application\chrome.exe"
REPO = Path(__file__).resolve().parent.parent
FLAGS = ["--no-first-run", "--no-default-browser-check", "--disable-renderer-backgrounding",
         "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows"]
TYPES = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
         ".py": "text/plain", ".whl": "application/zip", ".jpg": "image/jpeg", ".svg": "image/svg+xml"}
FRAMES = 30                                                   # the golden frame of a sketch (tests/conftest.py run_sketch)

# Session 1 (all with a golden) and five gallery examples: text, paths and path operations, a script with f.show(),
# pictures, marks and Grid.
SESSION1 = [f"{n:02d}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)]
GALLERY = ["text-01_text", "paths-05_booleans", "basics-03_a_script", "images-01_load_image", "studios-03_rhythm"]


def build_cases(funground: Path, runtime: Path) -> list[dict]:
    index = {e["id"]: e for e in json.loads((runtime / "examples" / "index.json").read_text(encoding="utf-8"))}
    cases = []
    for number in SESSION1:
        entry = next(e for i, e in index.items() if i.startswith("session1-" + number))
        golden = funground / "tests" / "golden" / (Path(entry["source"]).stem + ".png")
        cases.append({**entry, "golden": str(golden), "frames": FRAMES})
    for case_id in GALLERY:
        entry = index[case_id]
        source = (runtime / "examples" / entry["source"]).read_text(encoding="utf-8")
        is_script = not re.search(r"^f\.run\(", source, re.M)
        cases.append({**entry, "golden": str(funground / "tests" / "golden" / "gallery" / f"{case_id}.png"),
                      "frames": 1 if is_script else FRAMES})
    return cases


def serve(cases: list[dict], snaps: Path, box: dict, done: threading.Event, sent: dict, requests: list[str]):
    """`requests` gets one entry per request, "GET /path" or "HEAD /path"; the page asks for the ones since a mark."""
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"                           # keep-alive: a closed connection can cut a large body short

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/cases.json":
                self.reply(json.dumps(cases).encode(), ".json")
                return
            if path == "/requests.json":                         # the requests since the last "mark" entry, then a new mark
                since = next((i for i in range(len(requests) - 1, -1, -1) if requests[i].startswith("MARK")), -1)
                self.reply(json.dumps(requests[since + 1:]).encode(), ".json")
                return
            requests.append(f"GET {path}")
            target = (REPO / path.lstrip("/")).resolve()
            if REPO not in target.parents or not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            sent[path] = sent.get(path, 0) + len(data)
            span = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
            if span:                                              # a lazy file (fonts, S-211) reads in ranges
                first = int(span[1])
                last = min(int(span[2] or len(data) - 1), len(data) - 1)
                self.reply(data[first:last + 1], target.suffix, 206, {"Content-Range": f"bytes {first}-{last}/{len(data)}"})
            else:
                self.reply(data, target.suffix)

        def do_HEAD(self):
            path = self.path.split("?")[0]
            requests.append(f"HEAD {path}")
            target = (REPO / path.lstrip("/")).resolve()
            if REPO not in target.parents or not target.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(target.stat().st_size + (1 if box.get("bad_fonts") and "/runtime/fonts/" in path else 0)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def reply(self, data: bytes, suffix: str, status: int = 200, headers: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", TYPES.get(suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges", "bytes")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            for i in range(0, len(data), 65536):                # the default single write stalls on large bodies here
                self.wfile.write(data[i:i + 65536])
                self.wfile.flush()

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.path.startswith("/snap"):
                query = dict(p.split("=") for p in self.path.split("?")[1].split("&"))
                Image.frombuffer("RGBA", (int(query["w"]), int(query["h"])), body, "raw", "RGBA", 0, 1).save(snaps / f"{query['id']}.png")
            elif self.path.startswith("/fontmode"):                 # ?bad=1: HEAD for a font claims one byte too many
                box["bad_fonts"] = self.path.endswith("bad=1")
            elif self.path == "/mark":
                requests.append("MARK")
            elif self.path == "/log":
                print(f"page: {body.decode()}", file=sys.stderr, flush=True)
            else:
                box["report"] = json.loads(body)
                done.set()
            self.reply(b"ok", ".txt")                             # with a length: on keep-alive a bodiless reply never ends

        def log_message(self, *args):
            pass

    class Server(http.server.ThreadingHTTPServer):
        request_queue_size = 128

        def handle_error(self, request, client_address):
            if not isinstance(sys.exc_info()[1], ConnectionError):   # Chrome closing an idle keep-alive connection is normal
                super().handle_error(request, client_address)

    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def pixel_check(case: dict, snaps: Path) -> dict:
    actual, golden = Image.open(snaps / f"{case['id']}.png"), Image.open(case["golden"])
    if actual.size != golden.size:
        return {"id": case["id"], "identical": False, "why": f"size {actual.size} vs golden {golden.size}"}
    a, g = actual.convert("RGB").tobytes(), golden.convert("RGB").tobytes()
    differing = sum(1 for i in range(0, len(a), 3) if a[i:i + 3] != g[i:i + 3]) if a != g else 0
    return {"id": case["id"], "identical": a == g, "differing_pixels": differing, "size": list(actual.size)}


def scale_check(case: dict, snaps: Path, dpr: float) -> dict:
    """At a scale other than 1: the frame has the golden's size times `dpr` (within a pixel) and has more than one colour."""
    actual, golden = Image.open(snaps / f"{case['id']}.png"), Image.open(case["golden"])
    expected = [golden.size[0] * dpr, golden.size[1] * dpr]
    close = all(abs(a - e) <= 1 for a, e in zip(actual.size, expected))
    colours = len(actual.convert("RGB").getcolors(maxcolors=1 << 24) or [])
    return {"id": case["id"], "size": list(actual.size), "expected_size": expected, "size_ok": close, "colours": colours, "blank": colours <= 1}


def check_scenarios(scenarios: dict) -> dict[str, bool]:
    """Pass or fail for the scenarios with an exact answer: fonts on demand (S-211) and saved files (S-212)."""
    checks: dict[str, bool] = {}
    fonts = scenarios.get("fonts")
    if fonts:
        used = lambda run, name: any(r.endswith(f"/{name}.bin") and r.startswith("GET") for r in run["requests"])
        # only GETs count: each worker's start-up probes one font with a HEAD (worker.js installFonts), whenever it happens to start
        checks["fonts: a sketch with no text fetches no font file"] = fonts["no_text"]["ok"] and not any(r.startswith("GET") for r in fonts["no_text"]["requests"])
        checks["fonts: text fetches DejaVuSans and no other font"] = (fonts["hello"]["ok"] and used(fonts["hello"], "DejaVuSans.ttf")
            and not any("Noto" in r for r in fonts["hello"]["requests"]))
        checks["fonts: emoji and Devanagari fetch their Noto fonts"] = (fonts["rich"]["ok"] and used(fonts["rich"], "NotoEmoji-Regular.ttf")
            and used(fonts["rich"], "NotoSansDevanagari-Regular.ttf"))
        every = fonts["every_font"]
        checks["fonts: every bundled font in the manifest is readable at its size"] = (len(fonts["manifest_fonts"]) >= 7
            and every["sizes"] == every["expected"])
    saves = scenarios.get("saves")
    if saves:
        checks["files: out.png and out.pdf are each reported once, with their magic bytes"] = (
            sorted(saves["names"]) == ["out.pdf", "out.png"] and bool(saves["png"]) and bool(saves["pdf"])
            and saves["png"]["magic"] and saves["png"]["type"] == "image/png"
            and saves["pdf"]["magic"] and saves["pdf"]["type"] == "application/pdf")
    if fonts:
        eager = fonts.get("eager", {})
        checks["fonts: the first runner takes the lazy way"] = fonts.get("mode") == "lazy"
        checks["fonts: a host with a wrong Content-Length gets the eager way, and text still renders"] = (
            eager.get("mode") == "eager" and eager.get("ok") and not eager.get("output") and eager.get("inked", 0) > 50)
    script = scenarios.get("script_saves")
    if script:
        checks["files: a script's SVG and GIF are reported"] = (bool(script["svg"]) and bool(script["gif"]) and script["svg"]["type"] == "image/svg+xml"
            and script["svg"]["has_svg"] and script["gif"]["magic"] and script["gif"]["type"] == "image/gif")
    return checks


BATCH = 3            # cases per Chrome start: a long chain of worker boots in one page stalled on this machine (see the README)


def run_batch(cases: list[dict], scenarios: bool, args, snaps: Path, sent: dict, log_path: Path) -> dict | None:
    """One Chrome start: its page runs these cases (and the scenarios if asked) and posts one report; None on timeout."""
    box: dict = {}
    done = threading.Event()
    server = serve(cases, snaps, box, done, sent, [])
    profile = args.profile or Path(tempfile.mkdtemp(prefix="chrome_runner_"))
    query = f"?scenarios={int(scenarios)}&prewarm={0 if args.no_prewarm else 1}"
    command = [CHROME, "--headless=new", "--enable-logging=stderr", f"--user-data-dir={profile}", *FLAGS]
    if args.dpr != 1:
        command.append(f"--force-device-scale-factor={args.dpr}")
    command.append(f"http://127.0.0.1:{server.server_port}/tests/runner/test.html{query}")
    with open(log_path, "ab") as log:                         # the page's console and crashes
        chrome = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        print(f"chrome pid {chrome.pid}: {[c['id'] for c in cases]}{' + scenarios' if scenarios else ''}", file=sys.stderr, flush=True)
        try:
            finished = done.wait(args.timeout)
        finally:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(chrome.pid)], capture_output=True)
            server.shutdown()
            time.sleep(1)
            if not args.profile:
                shutil.rmtree(profile, ignore_errors=True)
    return box["report"] if finished else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--funground", required=True, type=Path)
    parser.add_argument("--profile", type=Path, help="keep and reuse this Chrome profile (a second run is a warm start)")
    parser.add_argument("--dpr", type=float, default=1, help="device scale factor (the byte-for-byte pixel check is for 1)")
    parser.add_argument("--timeout", type=int, default=240, help="seconds per Chrome start")
    parser.add_argument("--no-prewarm", action="store_true", help="the runner starts a worker only when a run needs it")
    parser.add_argument("--limit", type=int, help="run only the first N cases (for debugging)")
    parser.add_argument("--skip-scenarios", action="store_true", help="only the examples")
    args = parser.parse_args()

    runtime = REPO / "runner" / "runtime"
    cases = build_cases(args.funground.resolve(), runtime)[:args.limit]
    out = REPO / "tests" / "out"
    snaps = out / "snaps"
    shutil.rmtree(snaps, ignore_errors=True)
    snaps.mkdir(parents=True)
    log_path = out / "chrome.log"
    log_path.write_bytes(b"")
    sent: dict = {}
    started = time.perf_counter()

    batches = [(cases[i:i + BATCH], False) for i in range(0, len(cases), BATCH)]
    if not args.skip_scenarios:
        batches.append(([], True))
    report: dict = {"cases": [], "scenarios": {}, "batches": [], "timeouts": []}
    for batch, scenarios in batches:
        result = run_batch(batch, scenarios, args, snaps, sent, log_path)
        if result is None:
            report["timeouts"].append([c["id"] for c in batch] or "scenarios")
            continue
        report["cases"] += result.get("cases", [])
        report["scenarios"].update(result.get("scenarios", {}))
        report["batches"].append({k: result.get(k) for k in ("first_load_ms", "first_frame_ms", "fatal")})
        report.setdefault("ready", result.get("ready"))
    report["wall_s"] = round(time.perf_counter() - started, 1)
    report["server_bytes"] = sent
    taken = [c for c in cases if (snaps / f"{c['id']}.png").exists()]
    if args.dpr == 1:
        report["pixels"] = [pixel_check(c, snaps) for c in taken]
    else:
        report["scaled"] = [scale_check(c, snaps, args.dpr) for c in taken]
    report["checks"] = check_scenarios(report["scenarios"])
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k not in ("server_bytes", "ready", "cases")}
    summary["cases"] = [{k: c.get(k) for k in ("id", "start_ms", "frame_ms", "error")} for c in report["cases"]]
    print(json.dumps(summary, indent=1))
    return 1 if report["timeouts"] or any(b["fatal"] for b in report["batches"]) or not all(report["checks"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
