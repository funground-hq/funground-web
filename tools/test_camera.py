r"""Test the camera in the browser runner, in headless Chrome (story S-172).

    C:\Projects\playground\.venv\Scripts\python.exe tools/test_camera.py

Needs runner/runtime/ (tools/build_runtime.py) built from a funground with the camera (the camera library, Session.push_camera).
Three cases, each in its own runner (tests/runner/camera.html):

  * live: Chrome's fake camera (a moving test pattern) feeds tests/runner/camera_sketch.py, which prints a pixel of each
    frame, records half a second and saves it as clip.gif. Frames must arrive and not be black, the GIF must reach the
    page, the camera must be open while the sketch runs and closed after Stop.
  * refused: Chrome refuses the camera. The sketch must get one line, "The camera is not available: it was not
    allowed...", no error, and never a frame.
  * host refusal: the runner is made with cameraRefusal (as VS Code's panel is). The same sketch gets that reason in one
    line, and the browser is never asked.

  * fit (S-311, --only-fit): Chrome's fake camera plays a portrait picture written at test time (tests/out/portrait.y4m, a
    white circle in the middle). Asked for 160 x 120, fit "stretch" must squash the circle (today's picture) and "cover" must
    keep it round, both at 160 x 120 (tests/runner/camera_fit.html uses createCamera alone, one Chrome start).

Chrome is started with its own temporary profile and stopped by its PID; the maintainer's Chrome and camera are never
touched (the fake device replaces every camera). Real use is the maintainer's job, on the live site.
"""
from __future__ import annotations

import argparse
import base64
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


PORTRAIT = (240, 320)               # a phone held upright: taller than wide
ASKED = (160, 120)                  # what the page asks for in the fit test (a landscape sketch)


def write_portrait_y4m(path: Path, frames: int = 5) -> None:
    """A small portrait Y4M video: a white circle (diameter 160) in the middle of black, a few frames of the same picture."""
    width, height = PORTRAIT
    luma = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            inside = (x + 0.5 - width / 2) ** 2 + (y + 0.5 - height / 2) ** 2 <= 80 ** 2
            luma[y * width + x] = 235 if inside else 16
    chroma = bytes([128]) * (width * height // 4)
    frame = b"FRAME\n" + bytes(luma) + chroma + chroma
    path.write_bytes(f"YUV4MPEG2 W{width} H{height} F10:1 Ip A1:1 C420jpeg\n".encode() + frame * frames)


def bright_box(frame: dict | None) -> tuple[int, int]:
    """The width and height of the box around the bright pixels of a frame the page posted (0, 0 for none)."""
    if not frame:
        return (0, 0)
    width, height, rgba = frame["width"], frame["height"], base64.b64decode(frame["base64"])
    xs, ys = [], []
    for y in range(height):
        for x in range(width):
            if rgba[(y * width + x) * 4] > 128:
                xs.append(x)
                ys.append(y)
    return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1) if xs else (0, 0)


def problems_fit(got: dict) -> list[str]:
    if "fatal" in got:
        return [f"page: {got['fatal']}"]
    problems = []
    boxes = {}
    for fit, result in got["fits"].items():
        frame = result["frame"]
        if not frame:
            problems.append(f"{fit}: no frame ({result['unavailable']})")
            continue
        if (frame["width"], frame["height"]) != ASKED:
            problems.append(f"{fit}: the frame is {frame['width']} x {frame['height']}, not {ASKED}")
        boxes[fit] = bright_box(frame)
        state = result["state"] or {}
        if state.get("fit") != fit or not state.get("open") or not state.get("label"):
            problems.append(f"{fit}: state() does not describe the open camera: {state}")
        settings = state.get("settings", {})
        if not settings.get("height", 0) > settings.get("width", 1):
            problems.append(f"{fit}: the track settings are not portrait: {settings}")
        if "capabilities" not in state:
            problems.append(f"{fit}: state() has no capabilities")
    if "stretch" in boxes:
        w, h = boxes["stretch"]
        if not (w > 1.4 * h and h > 20):                                  # 107 wide, 60 tall when squashed
            problems.append(f"stretch: the circle should be squashed (wider than tall) but its box is {w} x {h}")
    if "cover" in boxes:
        w, h = boxes["cover"]
        if not (abs(w - h) <= 3 and w > 80):                              # 107 by 107 when round
            problems.append(f"cover: the circle should be round but its box is {w} x {h}")
    return problems


def fit_main(out: Path, log_path: Path, report: dict, failures: list[str]) -> None:
    video = out / "portrait.y4m"
    write_portrait_y4m(video)
    got = run_chrome([{"id": "fit"}], FAKE + [f"--use-file-for-fake-video-capture={video}"], 300, log_path, page="camera_fit.html")
    if got is None:
        failures.append("fit: the Chrome start failed or timed out")
        return
    report["fit"] = {fit: {**{k: v for k, v in r.items() if k != "frame"}, "box": bright_box(r["frame"])}
                     for fit, r in got.get("fits", {}).items()}
    failures += [f"fit: {p}" for p in problems_fit(got)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-fit", action="store_true", help="only the fit test (S-311), one Chrome start")
    args = parser.parse_args()
    out = REPO / "tests" / "out"
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "chrome_camera.log"
    log_path.write_bytes(b"")
    report: dict = {}
    failures: list[str] = []

    if args.only_fit:
        fit_main(out, log_path, report, failures)
        print(json.dumps(report, indent=1))
        print("FAILED" if failures else "all passed", f"({len(failures)} problems)")
        print("\n".join(failures))
        return 1 if failures else 0

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

    fit_main(out, log_path, report, failures)

    report["failures"] = failures
    (out / "camera_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    print("FAILED" if failures else "all passed", f"({len(failures)} problems)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
