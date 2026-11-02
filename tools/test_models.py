r"""Test ml.pose() and ml.hand() in the browser runner, in headless Chrome (story S-232).

    C:\Projects\playground\.venv\Scripts\python.exe tools/test_models.py --ml-python <python with funground-ml> [--funground C:\Projects\playground] [--live]

Needs runner/runtime/ built by tools/build_runtime.py from a funground with the models (the funground-ml wheel, models.json),
Node, and playwright-core (tools/chrome_page.mjs says where). --ml-python is a Python that has funground and funground-ml
installed with onnxruntime (the desktop's half): it makes the numbers the browser's are compared with.

The same sketch (tests/runner/models_sketch.py) runs on both. On the desktop it runs with onnxruntime on the two test photographs
of funground-ml (ml/tests/data: a body in gandhi_london_rain.jpg, a hand in standing_woman_640.jpg), and prints every point. In
the browser it runs in the runner, which passes the same picture to onnxruntime-web in the models worker and brings the answer
back; the sketch prints every point too. The test passes when a body and a hand are found in both and every point is within
5 px of the desktop's (S-231 measured 4.65 px for the body and 2.17 px for the hand with another resampling; the crop here is
the same as Pillow's, so the difference is much smaller).

Cases, run in one Chrome (one temporary profile, so Cache Storage carries over from case to case):

  * pose, hand: empty cache. One line "Downloading the {task} model, {n} MB, once. After that the browser keeps a copy.", the
    files fetched once each, only from the model site and the CDN, the points compared with the desktop's.
  * pose from the copy: the model site is switched off. No line, no request to it, the same points.
  * camera: ml.pose and ml.hand on Chrome's fake camera. Answers arrive, one answer per frame, and the sketch has loaded no
    numpy, Pillow or onnxruntime.
  * no connection and no copy: one plain sentence, once, and the sketch goes on.
  * a file with the wrong bytes: one sentence about the checksum, and the file is not kept.
  * speed: answers a second for each task on this machine, with a new picture every frame.

The model site is answered from ml/tests/.models by tools/chrome_page.mjs (the real files, with the real site's headers); --live
sends the two downloads to huggingface.co instead (about 26 MB). Chrome is started and ended by Playwright, with its own
profile; the maintainer's Chrome is never touched.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sound import REPO, serve                           # the same local server as the other tools

NODE = os.environ.get("NODE", r"C:\sw\nodejs\node.exe")
FAKE = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
SKETCHES = REPO / "tests" / "runner"
TOLERANCE_PX = 5.0
PHOTOS = {"pose": "gandhi_london_rain.jpg", "hand": "standing_woman_640.jpg"}
SIZE_MB = {"pose": 18, "hand": 8}
DOWNLOAD_LINE = "Downloading the {task} model, {mb} MB, once. After that the browser keeps a copy."
ORT_FOLDER = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/"


# ---- the desktop's numbers

def sketch_text(name: str, task: str) -> str:
    return f'TASK = "{task}"\nPHOTO = "{PHOTOS[task]}"\n' + (SKETCHES / name).read_text(encoding="utf-8")


def parse_points(lines: list[str]) -> dict | None:
    """The {"score", "points"} a sketch printed after "points ", or None when it printed "points none" or nothing."""
    for line in lines:
        match = re.search(r"points (\{.*\})", line)
        if match:
            return json.loads(match.group(1))
    return None


def desktop_points(ml_python: str, funground: Path, hf_dir: Path, task: str) -> dict:
    """Run the sketch on the desktop (python sketch.py, headless, onnxruntime) and return the points it printed."""
    with tempfile.TemporaryDirectory(prefix="models_desktop_") as folder:
        folder = Path(folder)
        (folder / "sketch.py").write_text(sketch_text("models_sketch.py", task) + "\nf.run()\n", encoding="utf-8")
        (folder / PHOTOS[task]).write_bytes((funground / "ml" / "tests" / "data" / PHOTOS[task]).read_bytes())
        env = dict(os.environ, FUNGROUND_HEADLESS="1", FUNGROUND_ML_MODELS=str(hf_dir))
        done = subprocess.run([ml_python, "sketch.py"], cwd=folder, env=env, capture_output=True, text=True, timeout=600)
    found = parse_points(done.stdout.splitlines())
    if found is None:
        raise SystemExit(f"the desktop found no {task} (exit {done.returncode}): {done.stdout[-500:]} {done.stderr[-800:]}")
    return found


def compare(task: str, desktop: dict, play: dict) -> dict:
    """The distance in pixels between each point of the two, by name: the largest, the mean and where the largest is."""
    names = list(desktop["points"])
    if sorted(names) != sorted(play["points"]):
        return {"problem": "the two have different point names"}
    distances = {n: math.dist(desktop["points"][n], play["points"][n]) for n in names}
    worst = max(distances, key=distances.get)
    return {"points": len(names), "max_px": round(distances[worst], 3), "worst": worst,
            "mean_px": round(sum(distances.values()) / len(names), 3),
            "score_desktop": desktop["score"], "score_play": play["score"]}


# ---- the cases

def cases(data: Path) -> list[dict]:
    """The cases in the order they run; each page run starts with the cache of the one before it."""
    def case(case_id: str, sketch: str, task: str, until: str, wait_s: int = 240, files: bool = True, **extra) -> dict:
        photo = {PHOTOS[task]: base64.b64encode((data / PHOTOS[task]).read_bytes()).decode()} if files else {}
        return {"id": case_id, "source": sketch_text(sketch, task), "files": photo, "until_output": until, "wait_s": wait_s, **extra}

    points = "^points "
    return [
        case("pose", "models_sketch.py", "pose", points, clear_cache=True),
        case("hand", "models_sketch.py", "hand", points),
        case("pose from the copy", "models_sketch.py", "pose", points, hf="offline"),
        case("camera", "models_camera_sketch.py", "pose", "^loaded", files=False),
        case("no connection and no copy", "models_sketch.py", "pose", "could not download", hf="offline", clear_cache=True),
        case("wrong bytes", "models_sketch.py", "pose", "checksum", hf="corrupt", clear_cache=True),
        case("speed, pose", "models_speed_sketch.py", "pose", "^speed", wait_s=300, clear_cache=True),
        case("speed, hand", "models_speed_sketch.py", "hand", "^speed", wait_s=300),
    ]


def stdout_lines(result: dict) -> list[str]:
    return [line[len("stdout: "):] for line in result.get("output", []) if line.startswith("stdout: ")]


def hosts(result: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for request in result.get("requests", []):
        host = re.match(r"https://([^/]+)/", request["url"]).group(1)
        counts[host] = counts.get(host, 0) + 1
    return counts


def model_requests(result: dict) -> list[dict]:
    return [r for r in result.get("requests", []) if r["url"].startswith("https://huggingface.co/")]


def stderr_problems(result: dict) -> list[str]:
    return [f"output: {line}" for line in result.get("output", []) if line.startswith("stderr")]


def problems_download(result: dict, task: str, desktop: dict) -> tuple[list[str], dict]:
    out = [f"error: {result['error']}"] if "error" in result else []
    out += stderr_problems(result)
    lines = stdout_lines(result)
    line = DOWNLOAD_LINE.format(task=task, mb=SIZE_MB[task])
    if lines.count(line) != 1:
        out.append(f"expected the line {line!r} exactly once, got {[l for l in lines if 'Downloading' in l]}")
    asked = model_requests(result)
    if len(asked) != 2 or any(r["status"] != 200 for r in asked):
        out.append(f"expected two good requests to the model site, got {asked}")
    found = parse_points(lines)
    if found is None:
        out.append(f"no {task} was found in the browser")
        return out, {}
    numbers = compare(task, desktop, found)
    if "problem" in numbers:
        out.append(numbers["problem"])
    elif numbers["max_px"] > TOLERANCE_PX:
        out.append(f"the {task} differs from the desktop's by {numbers['max_px']} px at {numbers['worst']} (the limit is {TOLERANCE_PX})")
    return out, numbers


def problems_copy(result: dict, desktop: dict) -> tuple[list[str], dict]:
    out = [f"error: {result['error']}"] if "error" in result else []
    out += stderr_problems(result)
    lines = stdout_lines(result)
    if any("Downloading" in line for line in lines):
        out.append("the copy was not used: it downloaded again")
    if model_requests(result):
        out.append(f"the model site was asked although a copy was kept: {model_requests(result)}")
    found = parse_points(lines)
    if found is None:
        out.append("no body was found from the kept copy")
        return out, {}
    numbers = compare("pose", desktop, found)
    if numbers.get("max_px", 0) > TOLERANCE_PX:
        out.append(f"differs from the desktop's by {numbers['max_px']} px")
    return out, numbers


def problems_camera(result: dict) -> list[str]:
    out = [f"error: {result['error']}"] if "error" in result else []
    out += stderr_problems(result)
    lines = stdout_lines(result)
    answers = [l for l in lines if l.startswith("answers ")]
    if not answers:
        out.append(f"no answers arrived for the camera: {lines[-5:]}")
    if "loaded []" not in lines:
        out.append(f"the sketch loaded libraries a page does not need: {[l for l in lines if l.startswith('loaded')]}")
    if model_requests(result):
        out.append("the model site was asked although the copies were kept")
    return out


def problems_sentence(result: dict, expected: re.Pattern, what: str) -> list[str]:
    out = [f"error: {result['error']}"] if "error" in result else []
    sentences = [l for l in stdout_lines(result) if expected.search(l)]
    if len(sentences) != 1:
        out.append(f"expected one sentence about {what}, got {sentences} from {result.get('output', [])[-6:]}")
    if any(line.startswith("stdout: points") for line in result.get("output", [])) and "points none" not in " ".join(stdout_lines(result)):
        out.append("a body was found without the model files")
    if result.get("cache", 0) != 0:
        out.append(f"something was kept in the cache: {result['cache']}")
    return out


def speed_of(result: dict) -> tuple[list[str], str]:
    out = [f"error: {result['error']}"] if "error" in result else []
    out += stderr_problems(result)
    for line in stdout_lines(result):
        match = re.match(r"speed ([\d.]+) answers a second, ([\d.]+) frames a second", line)
        if match:
            return out, f"{match.group(1)} answers a second ({match.group(2)} frames a second)"
    return out + [f"no speed was printed: {stdout_lines(result)[-3:]}"], "none"


# ---- Chrome

def run_page(cases_list: list[dict], hf_dir: Path, live: bool, timeout: int) -> dict:
    box: dict = {}
    done = threading.Event()
    server = serve(cases_list, box, done)
    command = [NODE, str(REPO / "tools" / "chrome_page.mjs"), "--url", f"http://127.0.0.1:{server.server_port}/tests/runner/models.html",
               "--hf-dir", str(hf_dir), "--timeout", str(timeout)]
    for flag in FAKE:
        command += ["--flag", flag]
    node = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"node pid {node.pid}: {[c['id'] for c in cases_list]}", file=sys.stderr, flush=True)
    try:
        finished = done.wait(timeout)
    finally:
        try:
            node.stdin.close()                                 # chrome_page.mjs closes Chrome and exits when its input ends
            node.wait(30)
        except Exception:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(node.pid)], capture_output=True)
        server.shutdown()
        time.sleep(1)
    if not finished:
        return {"fatal": f"no report within {timeout} s; node said: {node.stderr.read()[-800:] if node.stderr else ''}"}
    return box["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--funground", type=Path, default=Path(r"C:\Projects\playground"))
    parser.add_argument("--ml-python", required=True, help="a Python with funground, funground-ml and onnxruntime")
    parser.add_argument("--live", action="store_true", help="download the pose and hand models from huggingface.co for real")
    parser.add_argument("--skip-speed", action="store_true")
    parser.add_argument("--only", help="run only the cases whose names contain this text (a case may need the cache of an earlier one)")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    hf_dir = args.funground / "ml" / "tests" / ".models"
    out = REPO / "tests" / "out"
    out.mkdir(parents=True, exist_ok=True)

    desktop = {task: desktop_points(args.ml_python, args.funground, hf_dir, task) for task in ("pose", "hand")}
    print("desktop:", {task: f"score {found['score']}, {len(found['points'])} points" for task, found in desktop.items()}, flush=True)

    wanted = [c for c in cases(args.funground / "ml" / "tests" / "data") if not (args.skip_speed and c["id"].startswith("speed"))
              and (args.only is None or args.only in c["id"])]
    if args.live:
        for c in wanted:
            if c["id"] in ("pose", "hand"):
                c["hf"] = "live"
    report = run_page(wanted, hf_dir, args.live, args.timeout)
    results = {r["id"]: r for r in report.get("cases", [])}
    failures: list[str] = []
    summary: dict = {}
    if "fatal" in report:
        failures.append(f"fatal: {report['fatal']}")

    def check(case_id: str, found: list[str]):
        failures.extend(f"{case_id}: {p}" for p in found)

    if "pose" in results:
        found, summary["pose"] = problems_download(results["pose"], "pose", desktop["pose"])
        check("pose", found)
    if "hand" in results:
        found, summary["hand"] = problems_download(results["hand"], "hand", desktop["hand"])
        check("hand", found)
    if "pose from the copy" in results:
        found, summary["pose from the copy"] = problems_copy(results["pose from the copy"], desktop["pose"])
        check("pose from the copy", found)
    if "camera" in results:
        check("camera", problems_camera(results["camera"]))
    if "no connection and no copy" in results:
        sentence = re.compile(r"^ml\.pose\(\): could not download the pose detector from huggingface\.co \(.+\)\. "
                              r"Run the sketch once while online; after that the browser keeps a copy\.$")
        check("no connection and no copy", problems_sentence(results["no connection and no copy"], sentence, "no connection"))
    if "wrong bytes" in results:
        sentence = re.compile(r"^ml\.pose\(\): the file downloaded for the pose detector is not the one funground expects \(its checksum is different\)")
        check("wrong bytes", problems_sentence(results["wrong bytes"], sentence, "the checksum"))
    speeds = {}
    for task in ("pose", "hand"):
        if f"speed, {task}" in results:
            found, speeds[task] = speed_of(results[f"speed, {task}"])
            check(f"speed, {task}", found)
    for c in report.get("cases", []):
        if "error" in c:
            failures.append(f"{c['id']}: {c['error']}")
    hosts_seen = {c["id"]: hosts(c) for c in report.get("cases", [])}

    summary["speed"] = speeds
    summary["hosts"] = hosts_seen
    summary["failures"] = sorted(set(failures))
    (out / "models_report.json").write_text(json.dumps({"summary": summary, "report": report, "desktop": desktop}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print("FAILED" if summary["failures"] else "all passed", f"({len(summary['failures'])} problems)")
    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
