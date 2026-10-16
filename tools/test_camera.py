r"""Test the camera in the browser runner, in headless Chrome (story S-172).

    C:\Projects\playground\.venv\Scripts\python.exe tools/test_camera.py

Needs runner/runtime/ (tools/build_runtime.py) built from a funground with the camera (f.camera, Session.push_camera).
Three cases, each in its own runner (tests/runner/camera.html):

  * live: Chrome's fake camera (a moving test pattern) feeds tests/runner/camera_sketch.py, which prints a pixel of each
    frame, records half a second and saves it as clip.gif. Frames must arrive and not be black, the GIF must reach the
    page, the camera must be open while the sketch runs and closed after Stop.
  * refused: Chrome refuses the camera. The sketch must get one line, "The camera is not available: it was not
    allowed...", no error, and never a frame.
  * host refusal: the runner is made with cameraRefusal (as VS Code's panel is). The same sketch gets that reason in one
    line, and the browser is never asked.

Chrome is started with its own temporary profile and stopped by its PID; the maintainer's Chrome and camera are never
touched (the fake device replaces every camera). Real use is the maintainer's job, on the live site.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sound import REPO, run_chrome                      # the same server and Chrome start as the sound test

FAKE = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
REFUSE = ["--use-fake-device-for-media-stream", "--deny-permission-prompts"]
SKETCH = "/tests/runner/camera_sketch.py"
HOST_REASON = "VS Code's panel cannot use the camera. Run the sketch on the website or on your computer"


def case(case_id: str, until: str, **extra) -> dict:
    return {"id": case_id, "url": SKETCH, "until_output": until, "wait_s": 120, **extra}


def problems_live(got: dict) -> list[str]:
    problems = [f"error: {got['error']}"] if "error" in got else []
    frames = [line for line in got["output"] if line.startswith("stdout: frame")]
    if not frames:
        problems.append(f"no frame reached the sketch: {got['output'][-5:]}")
    elif all(line == "stdout: frame 0 0 0" for line in frames):
        problems.append("every frame is black")
    if not any(line.startswith("stdout: saved") for line in got["output"]):
        problems.append("the clip was not saved")
    gifs = [f for f in got["files"] if f["name"] == "clip.gif"]
    if not gifs or not gifs[0]["head"].startswith("GIF8") or gifs[0]["type"] != "image/gif":
        problems.append(f"clip.gif did not reach the page as a GIF: {got['files']}")
    if not (got.get("camera_while_running") or {}).get("open"):
        problems.append(f"the camera was not open while the sketch ran: {got.get('camera_while_running')}")
    if got.get("camera_after_stop") is not None:
        problems.append(f"the camera is still open after Stop: {got['camera_after_stop']}")
    problems += [f"output: {line}" for line in got["output"] if line.startswith("stderr")]
    return problems


def problems_refused(got: dict, reason: str) -> list[str]:
    problems = [f"error: {got['error']}"] if "error" in got else []
    lines = [line for line in got["output"] if "The camera is not available" in line]
    if len(lines) != 1 or reason not in lines[0]:
        problems.append(f"expected one line with {reason!r}, got {lines}")
    if any(line.startswith("stdout: frame") for line in got["output"]):
        problems.append("a frame arrived although the camera was refused")
    problems += [f"output: {line}" for line in got["output"] if line.startswith("stderr")]
    return problems


def main() -> int:
    out = REPO / "tests" / "out"
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "chrome_camera.log"
    log_path.write_bytes(b"")
    report: dict = {}
    failures: list[str] = []

    first = run_chrome([case("live", "^saved"), case("host refusal", "not available", refusal=HOST_REASON)],
                       FAKE, 600, log_path, page="camera.html")
    if first is None or "fatal" in first:
        print("the first Chrome start failed:", None if first is None else first["fatal"])
        return 1
    results = {r["id"]: r for r in first["cases"]}
    report["live"] = results["live"]
    failures += [f"live: {p}" for p in problems_live(results["live"])]
    report["host refusal"] = results["host refusal"]
    failures += [f"host refusal: {p}" for p in problems_refused(results["host refusal"], "VS Code's panel cannot use the camera")]

    second = run_chrome([case("refused", "not available")], REFUSE, 300, log_path, page="camera.html")
    if second is None or "fatal" in second:
        failures.append("the refusing Chrome start failed")
    else:
        report["refused"] = second["cases"][0]
        failures += [f"refused: {p}" for p in problems_refused(second["cases"][0], "it was not allowed")]

    report["failures"] = failures
    (out / "camera_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    print("FAILED" if failures else "all passed", f"({len(failures)} problems)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
