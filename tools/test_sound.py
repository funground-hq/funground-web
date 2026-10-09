r"""Test sound and the microphone in the browser runner, in headless Chrome (story S-137).

    C:\Projects\playground\.venv\Scripts\python.exe tools/test_sound.py --funground C:\Projects\playground-0.2

Needs runner/runtime/ (tools/build_runtime.py). For each sound example of the gallery:

  * the reference: this script runs the example on CPython through funground's own host API (funground.web.Session)
    for a few frames and records the sound commands it makes;
  * the browser: tests/runner/sound.html runs the same file in the runner and counts the commands that reach the
    page (the number of sounds and the frames in each), and what the page's Web Audio voices are doing.

The two must agree. Then the microphone: a sketch that listens (tests/runner/mic_sketch.py) and the gallery tuner run
against Chrome's fake microphone and must see a level above 0. A last start with Chrome's default autoplay policy
(no click is possible in a test) checks that a sound before the first gesture is skipped with one line, not an error.

Chrome is started with its own temporary profile and stopped by its PID; the maintainer's Chrome is never touched.
The first start uses --autoplay-policy=no-user-gesture-required (the test cannot click) and the fake microphone flags.
Real listening is the maintainer's job (runner/README.md, "Try the sound").
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
from pathlib import Path

CHROME = r"C:\Users\samirj\AppData\Local\Google\Chrome\Application\chrome.exe"
REPO = Path(__file__).resolve().parent.parent
FLAGS = ["--no-first-run", "--no-default-browser-check", "--disable-renderer-backgrounding",
         "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows"]
SOUND_FLAGS = ["--autoplay-policy=no-user-gesture-required", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
TYPES = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
         ".py": "text/plain", ".whl": "application/zip", ".wav": "audio/wav"}
STEPS = 12                                                    # frames of the reference run, and of the browser's wait

# Gallery examples that make sound in setup() or at the top of the file.
PLAYING = ["sound-01_visualiser", "sound-02_write_a_tune", "sound-03_sargam_over_a_drone", "music-04_hear_a_raga",
           "music-05_tala", "music-01_tap_along", "music-11_piano_roll"]


def examples(runtime: Path) -> dict:
    return {e["id"]: e for e in json.loads((runtime / "examples" / "index.json").read_text(encoding="utf-8"))}


def reference(entry: dict, funground: Path) -> list[dict]:
    """The sound commands CPython's Session makes for the example in its first frames: [{command, frames}] in order."""
    seen: list[dict] = []

    def on_sound(command, voice, fields, samples):
        seen.append({"command": command, "frames": None if samples is None else len(samples) // fields["channels"]})

    from funground.web import Session
    path = funground / "examples" / entry["source"]
    session = Session(640, 400, on_sound=on_sound)
    cwd = os.getcwd()
    os.chdir(path.parent)                                       # data files sit beside the example
    try:
        session.start("import funground\nfunground.random_seed(0)\n" + path.read_text(encoding="utf-8"), path.name)
        for n in range(STEPS):
            if not session.step(n / 60):
                break
    finally:
        os.chdir(cwd)
        session.stop()
    return seen


def summary(commands: list[dict]) -> dict:
    """What is compared: the frames in each sound that was loaded, in order, and how many plays there were."""
    return {"loads": [c["frames"] for c in commands if c["command"] == "load"],
            "plays": sum(1 for c in commands if c["command"] == "play")}


def serve(cases: list[dict], box: dict, done: threading.Event):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/cases.json":
                return self.reply(json.dumps(cases).encode(), ".json")
            target = (REPO / path.lstrip("/")).resolve()
            if REPO not in target.parents or not target.is_file():
                return self.send_error(404)
            self.reply(target.read_bytes(), target.suffix)

        def reply(self, data: bytes, suffix: str):
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            for i in range(0, len(data), 65536):
                self.wfile.write(data[i:i + 65536])
                self.wfile.flush()

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/log":
                print(f"page: {body.decode()}", file=sys.stderr, flush=True)
            else:
                box["report"] = json.loads(body)
                done.set()
            self.reply(b"ok", ".txt")

        def log_message(self, *args):
            pass

    class Server(http.server.ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            if not isinstance(sys.exc_info()[1], ConnectionError):   # Chrome closing an idle keep-alive connection is normal
                super().handle_error(request, client_address)

    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_chrome(cases: list[dict], flags: list[str], timeout: int, log_path: Path) -> dict | None:
    box: dict = {}
    done = threading.Event()
    server = serve(cases, box, done)
    profile = Path(tempfile.mkdtemp(prefix="chrome_sound_"))
    command = [CHROME, "--headless=new", "--enable-logging=stderr", f"--user-data-dir={profile}", *FLAGS, *flags,
               f"http://127.0.0.1:{server.server_port}/tests/runner/sound.html"]
    with open(log_path, "ab") as log:
        chrome = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        print(f"chrome pid {chrome.pid}: {[c['id'] for c in cases]}", file=sys.stderr, flush=True)
        try:
            finished = done.wait(timeout)
        finally:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(chrome.pid)], capture_output=True)
            server.shutdown()
            time.sleep(1)
            shutil.rmtree(profile, ignore_errors=True)
    return box["report"] if finished else None


def sent(got: dict) -> dict:
    return summary([{"command": s["command"], "frames": s["frames"]} for s in got.get("sounds", [])])


def check_playing(got: dict, expected: dict) -> list[str]:
    if "error" in got:
        return [f"error: {got['error']}"]
    problems = [f"output: {line}" for line in got["output"] if line.startswith("stderr")]
    if not got["reached"]:
        problems.append(f"only {got['frames']} frames in the time allowed")
    actual = sent(got)
    if actual["loads"] != expected["loads"]:
        problems.append(f"sounds sent {actual['loads']} but the reference made {expected['loads']}")
    if actual["plays"] < expected["plays"]:
        problems.append(f"{actual['plays']} plays but the reference made {expected['plays']}")
    if any(s["peak"] == 0 for s in got["sounds"] if s["command"] == "load"):
        problems.append("a sound is silent (all zeros)")
    if got.get("speaker_peak", 0) < 0.01:
        problems.append(f"nothing audible reached the speakers (peak {got.get('speaker_peak')})")
    if not got["audio"]["unlocked"]:
        problems.append("Web Audio is not running")
    elif not any(v["state"] == "playing" for v in got["audio"]["voices"]):
        problems.append("no voice is playing")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--funground", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=300, help="seconds per Chrome start")
    args = parser.parse_args()
    funground = args.funground.resolve()
    sys.path.insert(0, str(funground))
    os.environ["FUNGROUND_HEADLESS"] = "1"

    index = examples(REPO / "runner" / "runtime")
    out = REPO / "tests" / "out"
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "chrome_sound.log"
    log_path.write_bytes(b"")

    def case(case_id: str, **extra) -> dict:
        entry = index[case_id]
        return {"id": case_id, "url": f"/runner/runtime/examples/{entry['source']}", "files": entry["files"],
                "frames": STEPS, "wait_s": 90, **extra}

    playing = [case(i) for i in PLAYING]
    microphone = [
        {"id": "mic_sketch", "url": "/tests/runner/mic_sketch.py", "files": [], "until_output": "^stdout: level", "wait_s": 60},
        case("sound-04_tuner", until_output="^$never", wait_s=8),
    ]
    report: dict = {"playing": {}, "microphone": {}, "gesture": {}}
    failures: list[str] = []

    expected = {c["id"]: summary(reference(index[c["id"]], funground)) for c in playing}
    report["expected"] = expected

    first = run_chrome(playing + microphone, SOUND_FLAGS, args.timeout, log_path)
    if first is None or "fatal" in first:
        print("the first Chrome start failed:", None if first is None else first["fatal"])
        return 1
    report["load_timings_ms"] = first.get("ready", {}).get("timings")
    results = {r["id"]: r for r in first["cases"]}
    for c in playing:
        got = results[c["id"]]
        problems = check_playing(got, expected[c["id"]])
        report["playing"][c["id"]] = {"problems": problems, "sent": sent(got), "frames": got.get("frames"),
                                         "speaker_peak": round(got.get("speaker_peak", 0), 3)}
        failures += [f"{c['id']}: {p}" for p in problems]

    heard = results["mic_sketch"]
    levels = [line for line in heard.get("output", []) if line.startswith("stdout: level")]
    report["microphone"]["mic_sketch"] = {"levels": levels[:5], "audio": heard.get("audio"), "error": heard.get("error"),
                                          "output": heard.get("output")}
    if "error" in heard or not levels:
        failures.append("mic_sketch: no level above 0 came from the fake microphone")
    tuner = results["sound-04_tuner"]
    report["microphone"]["sound-04_tuner"] = {"output": tuner.get("output"), "audio": tuner.get("audio"), "error": tuner.get("error")}
    if "error" in tuner or any(line.startswith("stderr") for line in tuner.get("output", [])):
        failures.append(f"sound-04_tuner: {tuner.get('error') or tuner['output']}")
    elif not (tuner["audio"]["microphone"] or {}).get("listening"):
        failures.append("sound-04_tuner: the microphone is not listening")

    second = run_chrome([case("sound-02_write_a_tune", frames=5, wait_s=60)], [], args.timeout, log_path)
    if second is None or "fatal" in second:
        failures.append("the gesture start failed")
    else:
        got = second["cases"][0]
        skipped = [line for line in got.get("output", []) if "Sound is off" in line]
        report["gesture"] = {"output": got.get("output"), "audio": got.get("audio"), "error": got.get("error")}
        if "error" in got or len(skipped) != 1 or any(line.startswith("stderr") for line in got["output"]):
            failures.append(f"gesture: expected one 'Sound is off' line and no error, got {got.get('output')} {got.get('error')}")

    report["failures"] = failures
    (out / "sound_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    print("FAILED" if failures else "all passed", f"({len(failures)} problems)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
