r"""Test ml.pose(), ml.hand(), ml.person(), ml.words() and ml.sound() in the browser runner, in headless Chrome (stories S-232, S-233, S-234, S-250).

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

The person (S-233) is a mask, not points. tests/runner/models_person_sketch.py cuts the person out of standing_woman_640.jpg and prints
the picture's alpha plane (one byte for each pixel). The two planes must agree: the mean absolute difference at most ALPHA_MEAN_BOUND
(3 of 255) and at most ALPHA_SHARE_BOUND (1 percent) of the pixels differing by more than ALPHA_SHARE_LEVEL (32). The bounds were set
before the first measurement. Python's share of the work in a page (the 256 x 256 mask stretched over 640 x 480 and applied, which
funground does in Cairo, in C) is timed in the browser and must take at most MASK_TIME_BOUND_MS (15 ms).

The words (S-234) are a phrase of sound, not a picture. tests/runner/models_words_sketch.py hears ml/tests/data/tts.wav (one
recording of a spoken sentence, 7 s) as ml.words(sound.load("tts.wav")) and prints the text and the score; on the desktop that
runs funground-ml's _whisper.py (numpy and onnxruntime), in the browser the models worker does the same sums in JavaScript. The
test passes when the two texts are the same, ignoring capitals; the difference of the two scores is reported, not bounded (a
score is the mean probability of the pieces chosen, and the browser's arithmetic is not bit for bit the desktop's). The sketch then
asks for the same recording again, and the time of that answer (the model already loaded) is the real-time factor. What this does
not test: a real microphone (headless Chrome has only its fake one, which plays a beep), the PhraseCutter on a live stream and the
microphone's own sample rate (the recording is sent whole, at the sound engine's rate).

The sound names (S-250) are a window of sound, not a picture. tests/runner/models_sound_sketch.py names three recordings
(ml/tests/data: tts.wav, whistle.wav and clapping.wav) as ml.sound(sound.load(name)) and prints for each the name, the score and the
names of the next guesses; on the desktop that runs funground-ml's _yamnet.py (numpy and onnxruntime), in the browser the models worker
does the same sums in JavaScript and sends the 521 scores back; the choosing of names is the same Python in both. The test passes when
the name and the names of the next guesses are the same for every recording; the largest difference of a score is reported, not
bounded (the browser's arithmetic is not bit for bit the desktop's). It also fails if the page got a recording at 16 kHz (the
resampling, which every microphone needs, would not have been tested). The sketch asks for the first recording again; the time of that
answer (the model already loaded) is the real-time factor. One more case, "sound microphone", runs ml.sound(mic) on Chrome's fake
microphone (a beep every second) and needs answers to come; its names are reported, not compared (the fake sound is not a recording we
can play the desktop). What this does not test: a real microphone.
The recordings go through sound.load() (S-259), so this also checks that a file read in a page has the desktop's samples: the files are
at 16 kHz, and the sound model tells the two apart when they differ.

Cases, run in one Chrome (one temporary profile, so Cache Storage carries over from case to case):

  * pose, hand: empty cache. One line "Downloading the {task} model, {n} MB, once. After that the browser keeps a copy.", the
    files fetched once each, only from the model site and the CDN, the points compared with the desktop's.
  * pose from the copy: the model site is switched off. No line, no request to it, the same points.
  * camera: ml.pose and ml.hand on Chrome's fake camera. Answers arrive, one answer per frame, and the sketch has loaded no
    numpy, Pillow or onnxruntime.
  * no connection and no copy: one plain sentence, once, and the sketch goes on.
  * a file with the wrong bytes: one sentence about the checksum, and the file is not kept.
  * person: the mask of the photograph, compared with the desktop's (one model file, one download line).
  * mask time: the milliseconds Python needs in the page to turn the mask into the person's picture at 640 x 480.
  * words: the recording's words (three files, one download line), compared with the desktop's; then from the copy (no request to
    the model site, no line, the same words), and the real-time factor.
  * sound: the three recordings' names (one file, one download line), compared with the desktop's; then from the copy (no request to the
    model site, no line, the same names), and the real-time factor; then the fake microphone.
  * speed: answers a second for each task on this machine, with a new picture every frame.

The model site is answered from ml/tests/.models by tools/chrome_page.mjs (the real files, with the real site's headers); --live
sends the two downloads to huggingface.co instead (about 26 MB). Chrome is started and ended by Playwright, with its own
profile; the maintainer's Chrome is never touched.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sound import REPO, serve                           # the same local server as the other tools

NODE = os.environ.get("NODE", r"C:\sw\nodejs\node.exe")
FAKE = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
SKETCHES = REPO / "tests" / "runner"
TOLERANCE_PX = 5.0
PHOTOS = {"pose": "gandhi_london_rain.jpg", "hand": "standing_woman_640.jpg", "person": "standing_woman_640.jpg", "words": "tts.wav"}
SIZE_MB = {"pose": 18, "hand": 8, "person": 1, "words": 42, "sound": 16}
FILES = {"pose": 2, "hand": 2, "person": 1, "words": 3, "sound": 1}          # model files a task downloads
ALPHA_MEAN_BOUND = 3.0                               # grey levels (of 255): the mean absolute difference of the two alpha planes
ALPHA_SHARE_LEVEL = 32                               # a pixel counts as different when its alpha differs by more than this ...
ALPHA_SHARE_BOUND = 0.01                             # ... and at most this share of the pixels may count
MASK_TIME_BOUND_MS = 15.0                            # Python's share of ml.person in a page, for 640 x 480
DOWNLOAD_LINE = "Downloading the {task} model, {mb} MB, once. After that the browser keeps a copy."
SOUND_CLIPS = ("tts.wav", "whistle.wav", "clapping.wav")      # in ml/tests/data
ORT_FOLDER = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/"


# ---- the desktop's numbers

def sketch_text(name: str, task: str) -> str:
    heading = f'SOUND = "{PHOTOS[task]}"\n' if task == "words" else f'TASK = "{task}"\nPHOTO = "{PHOTOS[task]}"\n'
    return heading + (SKETCHES / name).read_text(encoding="utf-8")


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


def parse_json_line(lines: list[str], word: str) -> dict | None:
    """The object a sketch printed after "word ", or None when it printed "word none" or nothing."""
    for line in lines:
        match = re.search(rf"^{word} (\{{.*\}})", line)
        if match:
            return json.loads(match.group(1))
    return None


def desktop_words(ml_python: str, funground: Path, hf_dir: Path) -> dict:
    """Run the words sketch on the desktop (python sketch.py, headless: funground-ml's _whisper.py) and return what it printed."""
    task = "words"
    with tempfile.TemporaryDirectory(prefix="models_desktop_") as folder:
        folder = Path(folder)
        (folder / "sketch.py").write_text(sketch_text("models_words_sketch.py", task) + "\nf.run()\n", encoding="utf-8")
        (folder / PHOTOS[task]).write_bytes((funground / "ml" / "tests" / "data" / PHOTOS[task]).read_bytes())
        env = dict(os.environ, FUNGROUND_HEADLESS="1", FUNGROUND_ML_MODELS=str(hf_dir))
        done = subprocess.run([ml_python, "sketch.py"], cwd=folder, env=env, capture_output=True, text=True, timeout=600)
    found = parse_json_line(done.stdout.splitlines(), "words")
    if found is None:
        raise SystemExit(f"the desktop heard no words (exit {done.returncode}): {done.stdout[-500:]} {done.stderr[-800:]}")
    return found


def compare_words(desktop: dict, play: dict) -> dict:
    """The two texts, whether they are the same ignoring capitals, and the scores with their difference."""
    return {"same": desktop["text"].lower() == play["text"].lower(), "text_desktop": desktop["text"], "text_play": play["text"],
            "score_desktop": desktop["score"], "score_play": play["score"], "score_difference": round(abs(desktop["score"] - play["score"]), 4)}


def parse_alpha(lines: list[str]) -> dict | None:
    """The {"width", "height", "plane"} a sketch printed after "alpha ", or None when it printed "alpha none" or nothing."""
    for line in lines:
        match = re.search(r"alpha (\{.*\})", line)
        if match:
            return json.loads(match.group(1))
    return None


def alpha_plane(found: dict) -> bytes:
    plane = zlib.decompress(base64.b64decode(found["plane"]))
    if len(plane) != found["width"] * found["height"]:
        raise SystemExit(f"an alpha plane of {found['width']} x {found['height']} has {len(plane)} bytes")
    return plane


def desktop_alpha(ml_python: str, funground: Path, hf_dir: Path) -> dict:
    """Run the person sketch on the desktop (python sketch.py, headless, onnxruntime) and return the alpha it printed."""
    task = "person"
    with tempfile.TemporaryDirectory(prefix="models_desktop_") as folder:
        folder = Path(folder)
        (folder / "sketch.py").write_text(sketch_text("models_person_sketch.py", task) + "\nf.run()\n", encoding="utf-8")
        (folder / PHOTOS[task]).write_bytes((funground / "ml" / "tests" / "data" / PHOTOS[task]).read_bytes())
        env = dict(os.environ, FUNGROUND_HEADLESS="1", FUNGROUND_ML_MODELS=str(hf_dir))
        done = subprocess.run([ml_python, "sketch.py"], cwd=folder, env=env, capture_output=True, text=True, timeout=600)
    found = parse_alpha(done.stdout.splitlines())
    if found is None:
        raise SystemExit(f"the desktop made no person (exit {done.returncode}): {done.stdout[-500:]} {done.stderr[-800:]}")
    return found


def sound_text(name: str) -> str:
    return f"SOUNDS = {list(SOUND_CLIPS)!r}\n" + (SKETCHES / name).read_text(encoding="utf-8")


def parse_sounds(lines: list[str]) -> list[dict]:
    """The objects a sketch printed after "sound ", one for each recording that was named."""
    found = []
    for line in lines:
        match = re.match(r"^sound (\{.*\})", line)
        if match:
            found.append(json.loads(match.group(1)))
    return found


def desktop_sound(ml_python: str, funground: Path, hf_dir: Path) -> list[dict]:
    """Run the sound sketch on the desktop (python sketch.py, headless: funground-ml's _yamnet.py) and return what it printed."""
    with tempfile.TemporaryDirectory(prefix="models_desktop_") as folder:
        folder = Path(folder)
        (folder / "sketch.py").write_text(sound_text("models_sound_sketch.py") + "\nf.run()\n", encoding="utf-8")
        for clip in SOUND_CLIPS:
            (folder / clip).write_bytes((funground / "ml" / "tests" / "data" / clip).read_bytes())
        env = dict(os.environ, FUNGROUND_HEADLESS="1", FUNGROUND_ML_MODELS=str(hf_dir))
        done = subprocess.run([ml_python, "sketch.py"], cwd=folder, env=env, capture_output=True, text=True, timeout=600)
    found = parse_sounds(done.stdout.splitlines())
    if len(found) != len(SOUND_CLIPS):
        raise SystemExit(f"the desktop named {len(found)} of {len(SOUND_CLIPS)} sounds (exit {done.returncode}): {done.stdout[-500:]} {done.stderr[-800:]}")
    return found


def compare_sound(desktop: list[dict], play: list[dict]) -> dict:
    """For each recording: the names on both sides, whether the name and the next names are the same, and the score difference."""
    rows, worst = [], 0.0
    by_clip = {row["clip"]: row for row in play}
    for row in desktop:
        other = by_clip.get(row["clip"])
        if other is None:
            rows.append({"clip": row["clip"], "same": False, "names_desktop": [row["name"]] + [g["name"] for g in row["next"]], "names_play": None})
            continue
        names_desktop = [row["name"]] + [g["name"] for g in row["next"]]
        names_play = [other["name"]] + [g["name"] for g in other["next"]]
        scores_desktop = [row["score"]] + [g["score"] for g in row["next"]]
        scores_play = [other["score"]] + [g["score"] for g in other["next"]]
        difference = max(abs(a - b) for a, b in zip(scores_desktop, scores_play))
        worst = max(worst, difference)
        rows.append({"clip": row["clip"], "same": names_desktop == names_play, "names_desktop": names_desktop, "names_play": names_play,
                     "score_desktop": row["score"], "score_play": other["score"], "max_score_difference": round(difference, 4),
                     "rate": other["rate"]})
    return {"clips": rows, "max_score_difference": round(worst, 4)}


def compare_alpha(desktop: dict, play: dict) -> dict:
    """How far apart two alpha planes are: the mean absolute difference (0..255), the share of pixels that differ by more than
    ALPHA_SHARE_LEVEL, the largest difference, and the share of each plane that is mostly the person (alpha over 127)."""
    if (desktop["width"], desktop["height"]) != (play["width"], play["height"]):
        return {"problem": f"the planes have different sizes: {desktop['width']} x {desktop['height']} and {play['width']} x {play['height']}"}
    a, b = alpha_plane(desktop), alpha_plane(play)
    differences = [abs(x - y) for x, y in zip(a, b)]
    count = len(differences)
    return {"mean_abs": round(sum(differences) / count, 4), "share_over_32": round(sum(d > ALPHA_SHARE_LEVEL for d in differences) / count, 5),
            "max": max(differences), "person_share_desktop": round(sum(v > 127 for v in a) / count, 4),
            "person_share_play": round(sum(v > 127 for v in b) / count, 4)}


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

    def sound_case(case_id: str, data: Path, **extra) -> dict:
        files = {clip: base64.b64encode((data / clip).read_bytes()).decode() for clip in SOUND_CLIPS}
        return {"id": case_id, "source": sound_text("models_sound_sketch.py"), "files": files, "until_output": "^speed ", "wait_s": 300, **extra}

    points = "^points "
    return [
        case("pose", "models_sketch.py", "pose", points, clear_cache=True),
        case("hand", "models_sketch.py", "hand", points),
        case("pose from the copy", "models_sketch.py", "pose", points, hf="offline"),
        case("person", "models_person_sketch.py", "person", "^alpha "),
        case("mask time", "models_mask_time_sketch.py", "person", "^mask to person", files=False),
        case("camera", "models_camera_sketch.py", "pose", "^loaded", files=False),
        case("words", "models_words_sketch.py", "words", "^speed ", wait_s=300, clear_cache=True),
        case("words from the copy", "models_words_sketch.py", "words", "^speed ", wait_s=300, hf="offline"),
        sound_case("sound", data, clear_cache=True),
        sound_case("sound from the copy", data, hf="offline"),
        {"id": "sound microphone", "source": (SKETCHES / "models_microphone_sketch.py").read_text(encoding="utf-8"), "files": {},
         "until_output": "^microphone ", "wait_s": 120, "hf": "offline"},
        case("no connection and no copy", "models_sketch.py", "pose", "could not download", hf="offline", clear_cache=True),
        case("wrong bytes", "models_sketch.py", "pose", "checksum", hf="corrupt", clear_cache=True),
        case("speed, pose", "models_speed_sketch.py", "pose", "^speed", wait_s=300, clear_cache=True),
        case("speed, hand", "models_speed_sketch.py", "hand", "^speed", wait_s=300),
        case("speed, person", "models_speed_sketch.py", "person", "^speed", wait_s=300),
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
    if len(asked) != FILES[task] or any(r["status"] != 200 for r in asked):
        out.append(f"expected {FILES[task]} good requests to the model site, got {asked}")
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


def problems_person(result: dict, desktop: dict) -> tuple[list[str], dict]:
    out = [f"error: {result['error']}"] if "error" in result else []
    out += stderr_problems(result)
    lines = stdout_lines(result)
    line = DOWNLOAD_LINE.format(task="person", mb=SIZE_MB["person"])
    if lines.count(line) != 1:
        out.append(f"expected the line {line!r} exactly once, got {[l for l in lines if 'Downloading' in l]}")
    asked = model_requests(result)
    if len(asked) != FILES["person"] or any(r["status"] != 200 for r in asked):
        out.append(f"expected {FILES['person']} good request to the model site, got {asked}")
    found = parse_alpha(lines)
    if found is None:
        out.append("no person picture was made in the browser")
        return out, {}
    numbers = compare_alpha(desktop, found)
    if "problem" in numbers:
        out.append(numbers["problem"])
    else:
        if numbers["mean_abs"] > ALPHA_MEAN_BOUND:
            out.append(f"the person's alpha differs from the desktop's by {numbers['mean_abs']} on average (the limit is {ALPHA_MEAN_BOUND})")
        if numbers["share_over_32"] > ALPHA_SHARE_BOUND:
            out.append(f"{numbers['share_over_32']:.2%} of the person's pixels differ by more than {ALPHA_SHARE_LEVEL} (the limit is {ALPHA_SHARE_BOUND:.0%})")
        if numbers["person_share_desktop"] < 0.1:
            out.append("the desktop's mask has hardly a person in it: the test photograph is wrong or the model failed")
    return out, numbers


def problems_words(result: dict, desktop: dict, copy: bool) -> tuple[list[str], dict]:
    out = [f"error: {result['error']}"] if "error" in result else []
    out += stderr_problems(result)
    lines = stdout_lines(result)
    downloads = [l for l in lines if "Downloading" in l]
    asked = model_requests(result)
    if copy:
        if downloads:
            out.append("the copy was not used: it downloaded again")
        if asked:
            out.append(f"the model site was asked although a copy was kept: {asked}")
    else:
        line = DOWNLOAD_LINE.format(task="words", mb=SIZE_MB["words"])
        if lines.count(line) != 1:
            out.append(f"expected the line {line!r} exactly once, got {downloads}")
        if len(asked) != FILES["words"] or any(r["status"] != 200 for r in asked):
            out.append(f"expected {FILES['words']} good requests to the model site, got {asked}")
    found = parse_json_line(lines, "words")
    if found is None:
        out.append(f"no words were heard in the browser: {lines[-3:]}")
        return out, {}
    if found["rate"] == 16000:
        out.append("the phrase reached the page at 16 kHz, so its resampling, which every microphone needs, was not tested")
    numbers = compare_words(desktop, found)
    if not numbers["same"]:
        out.append(f"the words differ: the desktop heard {desktop['text']!r}, Play heard {found['text']!r}")
    speed = parse_json_line(lines, "speed")
    if speed is None:
        out.append("the second answer never came")
    else:
        numbers["answer_seconds"] = speed["seconds"]
        numbers["recording_seconds"] = speed["recording"]
        numbers["real_time_factor"] = round(speed["seconds"] / speed["recording"], 3)
    numbers["first_wait_seconds"] = found["wait"]
    return out, numbers


def problems_sound(result: dict, desktop: list[dict], copy: bool) -> tuple[list[str], dict]:
    out = [f"error: {result['error']}"] if "error" in result else []
    out += stderr_problems(result)
    lines = stdout_lines(result)
    downloads = [l for l in lines if "Downloading" in l]
    asked = model_requests(result)
    if copy:
        if downloads:
            out.append("the copy was not used: it downloaded again")
        if asked:
            out.append(f"the model site was asked although a copy was kept: {asked}")
    else:
        line = DOWNLOAD_LINE.format(task="sound", mb=SIZE_MB["sound"])
        if lines.count(line) != 1:
            out.append(f"expected the line {line!r} exactly once, got {downloads}")
        if len(asked) != FILES["sound"] or any(r["status"] != 200 for r in asked):
            out.append(f"expected {FILES['sound']} good request to the model site, got {asked}")
    found = parse_sounds(lines)
    if len(found) != len(SOUND_CLIPS):
        out.append(f"Play named {len(found)} of {len(SOUND_CLIPS)} sounds: {lines[-4:]}")
    numbers = compare_sound(desktop, found)
    for row in numbers["clips"]:
        if not row["same"]:
            out.append(f"{row['clip']}: the names differ: desktop {row.get('names_desktop')}, Play {row.get('names_play')}")
        elif row["rate"] == 16000:
            out.append(f"{row['clip']} reached the page at 16 kHz, so its resampling, which every microphone needs, was not tested")
    speed = parse_json_line(lines, "speed")
    if speed is None:
        out.append("the second answer never came")
    else:
        numbers["answer_seconds"] = speed["seconds"]
        numbers["recording_seconds"] = speed["recording"]
        numbers["real_time_factor"] = round(speed["seconds"] / speed["recording"], 3)
    numbers["first_waits_seconds"] = [row["wait"] for row in found]
    return out, numbers


def problems_microphone(result: dict) -> tuple[list[str], dict]:
    out = [f"error: {result['error']}"] if "error" in result else []
    out += stderr_problems(result)
    found = parse_json_line(stdout_lines(result), "microphone")
    if found is None:
        return out + ["the sketch printed no microphone line"], {}
    if not found["answers"]:
        out.append("no sound was named from the fake microphone in 60 s")
    elif found["rate"] == 16000:
        out.append("the microphone ran at 16 kHz, so its resampling was not tested")
    return out, found


def mask_time_of(result: dict) -> tuple[list[str], str]:
    out = [f"error: {result['error']}"] if "error" in result else []
    out += stderr_problems(result)
    for line in stdout_lines(result):
        match = re.match(r"mask to person ([\d.]+) ms median, ([\d.]+) ms slowest", line)
        if match:
            if float(match.group(1)) > MASK_TIME_BOUND_MS:
                out.append(f"Python needs {match.group(1)} ms to turn the mask into the person's picture (the limit is {MASK_TIME_BOUND_MS})")
            return out, f"{match.group(1)} ms median, {match.group(2)} ms slowest"
    return out + [f"no time was printed: {stdout_lines(result)[-3:]}"], "none"


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

def kept_names(funground: Path) -> list[str]:
    """``--hf-alias`` arguments for models whose copy has another name than the file in the repository (funground-ml's table
    says so: ``kept_as``), read from ml/funground_ml/_models.py, the one place the table is written down."""
    spec = importlib.util.spec_from_file_location("_funground_ml_models", funground / "ml" / "funground_ml" / "_models.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module                          # the dataclasses in it look themselves up here
    spec.loader.exec_module(module)
    return [f"{model.file}={model.local_name}" for model in module.MODELS.values() if model.local_name != model.file]


def run_page(cases_list: list[dict], hf_dir: Path, live: bool, timeout: int, aliases: list[str]) -> dict:
    box: dict = {}
    done = threading.Event()
    server = serve(cases_list, box, done)
    command = [NODE, str(REPO / "tools" / "chrome_page.mjs"), "--url", f"http://127.0.0.1:{server.server_port}/tests/runner/models.html",
               "--hf-dir", str(hf_dir), "--timeout", str(timeout)]
    for alias in aliases:
        command += ["--hf-alias", alias]
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
    desktop_person = desktop_alpha(args.ml_python, args.funground, hf_dir)
    print("desktop person:", f"{desktop_person['width']} x {desktop_person['height']}", flush=True)

    desktop_heard = desktop_words(args.ml_python, args.funground, hf_dir)
    print("desktop words:", desktop_heard, flush=True)

    desktop_named = desktop_sound(args.ml_python, args.funground, hf_dir)
    print("desktop sound:", [(row["clip"], row["name"], [g["name"] for g in row["next"]]) for row in desktop_named], flush=True)

    wanted = [c for c in cases(args.funground / "ml" / "tests" / "data") if not (args.skip_speed and c["id"].startswith("speed"))
              and (args.only is None or args.only in c["id"])]
    if args.live:
        for c in wanted:
            if c["id"] in ("pose", "hand", "person", "words", "sound"):
                c["hf"] = "live"
    report = run_page(wanted, hf_dir, args.live, args.timeout, kept_names(args.funground))
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
    if "person" in results:
        found, summary["person"] = problems_person(results["person"], desktop_person)
        check("person", found)
    for case_id, copy in (("words", False), ("words from the copy", True)):
        if case_id in results:
            found, summary[case_id] = problems_words(results[case_id], desktop_heard, copy)
            check(case_id, found)
    for case_id, copy in (("sound", False), ("sound from the copy", True)):
        if case_id in results:
            found, summary[case_id] = problems_sound(results[case_id], desktop_named, copy)
            check(case_id, found)
    if "sound microphone" in results:
        found, summary["sound microphone"] = problems_microphone(results["sound microphone"])
        check("sound microphone", found)
    if "mask time" in results:
        found, summary["mask time"] = mask_time_of(results["mask time"])
        check("mask time", found)
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
    for task in ("pose", "hand", "person"):
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
    (out / "models_report.json").write_text(json.dumps({"summary": summary, "report": report, "desktop": desktop, "desktop_words": desktop_heard, "desktop_sound": desktop_named,
                                                        "desktop_person": {k: v for k, v in desktop_person.items() if k != "plane"}}, indent=1),
                                            encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print("FAILED" if summary["failures"] else "all passed", f"({len(summary['failures'])} problems)")
    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
