r"""Test the browser runner in headless Chrome (story S-153).

    C:\Projects\playground\.venv\Scripts\python.exe tools/test_runner.py --funground C:\Projects\playground-0.2 [--profile DIR] [--dpr 2]

Needs runner/runtime/ (tools/build_runtime.py). A localhost server (this script) serves the repository, counts the
bytes it sends, hands tests/runner/test.html its list of cases, and receives the page's report and the canvas
snapshots. Chrome (--headless=new, its own profile) is started and stopped by its PID; the maintainer's Chrome is never
touched. By default the profile is new and deleted afterwards (a cold start); --profile DIR keeps it, so a second
run with the same DIR measures a warm start.

Pixel check: the runner's frame (1x) must equal the golden of tests/golden byte for byte, with two stated exceptions
(TOLERANCE): a sketch that loads a JPEG (D-101 a, the browser's libjpeg decodes colour edges a little differently) and a
picture scaled up (one step at the edge of the scaled picture, measured; cause unverified). A frame outside its
tolerance fails the run. Pillow reads the PNGs.
At another scale (--dpr 1.25) there is no golden: the check is that the frame is the golden's size times the scale
(to within a pixel) and not blank.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import http.server
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from PIL import Image

CHROME = r"C:\Users\samirj\AppData\Local\Google\Chrome\Application\chrome.exe"
REPO = Path(__file__).resolve().parent.parent
FLAGS = ["--no-first-run", "--no-default-browser-check", "--disable-renderer-backgrounding",
         "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows"]
TYPES = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
         ".py": "text/plain", ".whl": "application/zip", ".jpg": "image/jpeg", ".svg": "image/svg+xml"}
FRAMES = 30                                                   # the golden frame of a sketch (tests/conftest.py run_sketch)

# How far a frame may differ from its golden, for the sketches that cannot be exact. A pixel's difference is its largest
# channel difference (0 to 255). "mean" bounds the average over all pixels, "p99" the 99th percentile, "max" every pixel.
# Measured 18 Oct 2026: images-01 (a JPEG) mean 0.57, p99 9, max 87; images-08 (a 160 x 120 GIF drawn at 480 x 360) two
# corner pixels off by 1.
TOLERANCE = {
    "jpeg": {"why": "a JPEG decodes a little differently in the browser (D-101 a, contract P4)", "mean": 1.0, "p99": 16},
    "images-08_play_a_take": {"why": "a scaled-up picture: one step at its top corners", "max": 1},
}
JPEG = re.compile(r"\.jpe?g\b", re.I)                         # a sketch that names a JPEG file loads one

# Session 1 (all with a golden) and six gallery examples: text, paths and path operations, a script with f.show(),
# pictures, marks and Grid, a clip loaded from a GIF (S-220), and a picture made see-through (S-218).
SESSION1 = [f"{n:02d}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)]
GALLERY = ["text-01_text", "paths-05_booleans", "basics-03_a_script", "images-01_load_image", "studios-03_rhythm",
           "images-08_play_a_take", "images-10_in_front_of_a_picture"]


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
    for case in cases:
        source = (runtime / "examples" / case["source"]).read_text(encoding="utf-8")
        case["tolerance"] = TOLERANCE.get(case["id"]) or (TOLERANCE["jpeg"] if JPEG.search(source) else None)
    return cases


def build_wheel(folder: Path, file: str, files: dict[str, str], requires: list[str] = ()) -> dict:
    """A tiny wheel written with zipfile (no pip, no network): the module(s) in `files`, and a .dist-info with METADATA, WHEEL and
    RECORD. The name and version come from the file name. Returns its file name and SHA-256."""
    name, version = file.split("-")[:2]
    dist = f"{name}-{version}.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n" + "".join(f"Requires-Dist: {r}\n" for r in requires)
    tag = "-".join(file.removesuffix(".whl").split("-")[-3:])
    files = {**files, f"{dist}/METADATA": metadata, f"{dist}/WHEEL": f"Wheel-Version: 1.0\nGenerator: test_runner\nRoot-Is-Purelib: true\nTag: {tag}\n"}
    record = []
    for path, text in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(text.encode()).digest()).rstrip(b"=").decode()
        record.append(f"{path},sha256={digest},{len(text.encode())}")
    files[f"{dist}/RECORD"] = "\n".join(record + [f"{dist}/RECORD,,"]) + "\n"
    with zipfile.ZipFile(folder / file, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, text in files.items():
            info = zipfile.ZipInfo(path, (2026, 11, 12, 0, 0, 0))        # a fixed date: the same bytes every build
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text)
    return {"file": file, "sha256": hashlib.sha256((folder / file).read_bytes()).hexdigest()}


def build_test_wheels(folder: Path) -> dict:
    """S-276: the host wheels the packages scenario lists, in `folder` (which the test server serves), with index.json."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    wheels = {
        "good": build_wheel(folder, "fgtest_good-0.1.0-py3-none-any.whl", {"fgtest_good/__init__.py": 'VERSION = "0.1.0"\n\n\ndef hello(name):\n    return f"hello, {name}"\n'},
                            ['pytest ; extra == "test"', "sphinx; extra == 'docs'"]),
        "badsum": build_wheel(folder, "fgtest_badsum-0.1.0-py3-none-any.whl", {"fgtest_badsum/__init__.py": "VALUE = 1\n"}),
        "pandas": build_wheel(folder, "fgtest_pandas-0.1.0-py3-none-any.whl", {"fgtest_pandas/__init__.py": "VALUE = 2\n"}, ["pandas (>=2)"]),
        "numpy": build_wheel(folder, "fgtest_numpy-0.1.0-py3-none-any.whl",
                             {"fgtest_numpy/__init__.py": "def total():\n    import numpy as np\n    return int(np.arange(4).sum())\n"}, ["numpy>=1"]),
        "tag": build_wheel(folder, "fgtest_tag-0.1.0-cp312-cp312-win_amd64.whl", {"fgtest_tag/__init__.py": "VALUE = 3\n"}),
        "two": build_wheel(folder, "fgtest_two-0.1.0-py3-none-any.whl",
                           {"fgtest_two/__init__.py": "def both():\n    import fgtest_good\n    import numpy as np\n    return fgtest_good.hello('two') + ' ' + str(int(np.arange(4).sum()))\n"},
                           ["fgtest-good", "numpy"]),
    }
    (folder / "index.json").write_text(json.dumps(wheels, indent=1), encoding="utf-8")
    return wheels


def serve(cases: list[dict], snaps: Path, box: dict, done: threading.Event, sent: dict, requests: list[str]):
    """`requests` gets one entry per request, "GET /path"; the page asks for the ones since a mark."""
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
            if "/runtime/fonts/" in path and box.get("font_mode") == "compress":      # what GitHub Pages does to a font
                self.reply(gzip.compress(data), target.suffix, headers={"Content-Encoding": "gzip"})
            elif "/runtime/fonts/" in path and box.get("font_mode") == "corrupt":     # same length, last byte changed
                self.reply(data[:-1] + bytes([data[-1] ^ 0xFF]), target.suffix)
            else:
                self.reply(data, target.suffix)

        def reply(self, data: bytes, suffix: str, status: int = 200, headers: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", TYPES.get(suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
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
            elif self.path.startswith("/fontmode"):                 # ?mode=compress, corrupt or off: how the fonts are served
                box["font_mode"] = self.path.split("mode=")[1]
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
    result = {"id": case["id"], "identical": a == g, "size": list(actual.size)}
    if a == g:
        return {**result, "differing_pixels": 0, "passed": True}
    diffs = sorted(max(abs(a[i] - g[i]), abs(a[i + 1] - g[i + 1]), abs(a[i + 2] - g[i + 2])) for i in range(0, len(a), 3))
    measured = {"mean": round(sum(diffs) / len(diffs), 3), "p99": diffs[len(diffs) * 99 // 100], "max": diffs[-1]}
    limits = case.get("tolerance") or {}
    passed = bool(limits) and all(measured[k] <= limits[k] for k in ("mean", "p99", "max") if k in limits)
    return {**result, "differing_pixels": sum(1 for d in diffs if d), **measured, "passed": passed,
            "tolerance": limits.get("why")}


def scale_check(case: dict, snaps: Path, dpr: float) -> dict:
    """At a scale other than 1: the frame has the golden's size times `dpr` (within a pixel) and has more than one colour."""
    actual, golden = Image.open(snaps / f"{case['id']}.png"), Image.open(case["golden"])
    expected = [golden.size[0] * dpr, golden.size[1] * dpr]
    close = all(abs(a - e) <= 1 for a, e in zip(actual.size, expected))
    colours = len(actual.convert("RGB").getcolors(maxcolors=1 << 24) or [])
    return {"id": case["id"], "size": list(actual.size), "expected_size": expected, "size_ok": close, "colours": colours, "blank": colours <= 1}


def check_capabilities(ready: dict | None, checks: dict[str, bool]) -> dict[str, bool]:
    """S-275: every word in `ready`'s capabilities has checks named after it (\"stdin: ...\"), and they all pass."""
    words = (ready or {}).get("capabilities") or []
    tested = {word: [ok for name, ok in checks.items() if name.startswith(word + ": ")] for word in words}
    return {"capabilities: ready lists what the runner can do, and every word has passing checks of its own": (
        bool(words) and all(results and all(results) for results in tested.values()))}


def check_packages(packages: dict) -> dict[str, bool]:
    """S-276: the host's packages. Every name starts with "packages: " (S-275: the capability word has checks of its own)."""
    checks: dict[str, bool] = {}
    has = lambda files, part: any(part in n for n in files)
    end = lambda run: run["output"][-1] if run["output"] else ""
    offers = lambda name, rest: f"ModuleNotFoundError: This page does not offer {name}. {rest}"
    numpy, sklearn = packages["numpy"], packages["sklearn"]
    checks["packages: numpy, on import, is fetched by the run that imports it and not at ready, and works"] = (
        not has(numpy["atReady"], "/numpy-")
        and numpy["numpy"]["output"] == ["45 6.0"] and numpy["numpy"]["ended"] == "ended"
        and any("/numpy-" in n and n.endswith(".whl") for n in numpy["afterRun"])
        and set(numpy["info"]["versions"]) == {"python", "pyodide"})
    checks["packages: a second run that imports numpy again works in the same worker"] = numpy["again"]["output"] == ["45 6.0"]
    checks["packages: scikit-learn, install at start, is fetched before ready, with its dependencies, and a model fits"] = (
        has(sklearn["atReady"], "/scikit_learn-") and has(sklearn["atReady"], "/scipy-") and has(sklearn["atReady"], "/numpy-")
        and sklearn["sklearn"]["output"] == ["2.0 1.0"] and sklearn["sklearn"]["ended"] == "ended")
    checks["packages: the versions of what was loaded at start are in info.versions"] = (
        {"python", "pyodide", "scikit-learn", "scipy", "numpy"} <= set(sklearn["versions"]) and sklearn["versions"]["scikit-learn"][0].isdigit())
    outside = numpy["outside"]
    checks["packages: an import outside the list gives the plain sentence, the learner's file and line, and the file stops there"] = (
        outside["ended"] == "error" and outside["output"][0] == "before" and len(outside["output"]) == 2
        and offers("pandas", "It offers: numpy.") in outside["output"][1] and 'File "main.py", line 2' in outside["output"][1]
        and "No module named" not in outside["output"][1] and "<runner>" not in outside["output"][1]
        and "micropip" not in outside["output"][1] and "loadPackage" not in outside["output"][1])
    checks["packages: an import outside the list fetches nothing, and a dotted import names its top-level package"] = (
        not has(numpy["afterOutside"], "pandas") and not has(numpy["afterOutside"], "scikit_learn")
        and offers("sklearn", "It offers: numpy.") in end(numpy["outsideDotted"]))
    checks["packages: check() gives the same sentence in its error"] = (
        numpy["checked"]["tests"] == [] and offers("pandas", "It offers: numpy.") in numpy["checked"]["error"]
        and 'File "main.py", line 1' in numpy["checked"]["error"])
    checks["packages: Python's own library and a module in the run folder are never touched"] = numpy["folder"]["output"] == ["3", "library ok"]
    checks["packages: with packages: [] only Python's own library is offered, and says so"] = (
        packages["empty"]["outside"]["ended"] == "error" and offers("numpy", "It offers Python's own library only.") in end(packages["empty"]["outside"])
        and packages["empty"]["library"]["output"] == ["2"])
    session = packages["session"]
    checks["packages: funground and numpy together: a sketch uses both, and a frame is drawn"] = (
        session["sketch"]["started"]["ok"] is True and session["sketch"]["output"] == ["6"] and session["drawn"] >= 1
        and "pycairo" in session["versions"])
    checks["packages: in the funground runner an import outside the list gives the sentence, at the top of the file and inside draw()"] = (
        session["outside"]["ended"] == "error" and offers("pandas", "It offers: funground, numpy.") in end(session["outside"])
        and 'File "main.py", line 2' in end(session["outside"])
        and session["loop"]["ended"] == "error" and offers("pandas", "It offers: funground, numpy.") in end(session["loop"])
        and 'File "main.py", line 4' in end(session["loop"])
        and not has(session["outside"]["output"] + session["loop"]["output"], "micropip"))
    wheels = packages["wheels"]
    good_file = "fgtest_good-0.1.0-py3-none-any.whl"
    checks["packages: a host wheel is fetched when a run imports it, not at ready; its checksum is right and it installs and imports"] = (
        not any("/wheels/" in r for r in wheels["requestedAtReady"]) and any(r.endswith(good_file) for r in wheels["requestedAfter"])
        and wheels["good"]["output"] == ["hello, Ada"] and wheels["good"]["ended"] == "ended")
    bad = f"Refused fgtest_badsum-0.1.0-py3-none-any.whl: its SHA-256 is {wheels['sha']['badsum']}, the host listed {'0' * 64}. It was not installed."
    checks["packages: a wheel whose checksum differs is refused with the sentence, and the run does not start"] = (
        wheels["badsum"]["ended"] == "error" and wheels["badsum"]["output"] == [bad])
    checks["packages: a wheel that requires a package the page does not offer is refused, naming it"] = (
        wheels["pandas"]["ended"] == "error"
        and wheels["pandas"]["output"] == ["fgtest-pandas needs pandas, which this page does not offer. Add it to packages."])
    checks["packages: a wheel that requires numpy installs when numpy is listed, and numpy is loaded for it"] = (
        wheels["withNumpy"]["output"] == ["6"] and wheels["withNumpy"]["ended"] == "ended")
    checks["packages: a wheel that requires another host wheel installs both"] = wheels["two"]["output"] == ["hello, two 6"]
    tag_start = "Refused fgtest_tag-0.1.0-cp312-cp312-win_amd64.whl: its tag is cp312-cp312-win_amd64, and this page takes only py3-none-any, py2.py3-none-any, cp314-cp314-pyemscripten_"
    checks["packages: a wheel built for another platform is refused, naming its file and tag"] = (
        wheels["tag"]["ended"] == "error" and len(wheels["tag"]["output"]) == 1
        and wheels["tag"]["output"][0].startswith(tag_start) and wheels["tag"]["output"][0].endswith("It was not installed."))
    checks["packages: a run after a refused wheel works in the same worker"] = wheels["unrelated"]["output"] == ["no wheel needed"]
    checks["packages: install at start installs the wheel before ready and reports its version; a wheel refused at start fails createRunner"] = (
        wheels["start"]["versions"].get("fgtest-good") == "0.1.0" and wheels["start"]["run"]["output"] == ["0.1.0"]
        and has(wheels["start"]["fetched"], good_file) and wheels["startBad"] == bad and wheels["startTag"].startswith(tag_start))
    fetched = numpy["afterOutside"] + sklearn["afterRun"] + wheels["fetched"] + wheels["start"]["fetched"]
    checks["packages: nothing is requested from pypi.org or files.pythonhosted.org, and no micropip is loaded"] = (
        not has(fetched, "pypi.org") and not has(fetched, "pythonhosted") and not has(fetched, "micropip"))
    rejected = packages["rejected"]
    checks["packages: createRunner rejects options that cannot work, each with one plain sentence"] = (
        rejected["notList"] == 'createRunner(): packages must be a list, for example ["numpy"].'
        and rejected["notEntry"] == "createRunner(): each entry of packages must be a package name or a wheel written as {name, url, sha256}."
        and rejected["noSha"] == 'createRunner(): the wheel "x" in packages needs a name, a url and a sha256 of 64 hexadecimal characters.'
        and rejected["noName"] == "createRunner(): the wheel in packages needs a name, a url and a sha256 of 64 hexadecimal characters."
        and rejected["install"] == 'createRunner(): install must be "on import" or "at start".')
    checks["packages: a name Pyodide does not have rejects createRunner, naming it"] = (
        rejected["unknown"] == '"pandsa" is not a package Pyodide has, so this page cannot offer it.')
    return checks


def check_sources(ready: dict | None) -> dict[str, bool]:
    """S-277: a full start takes svgelements and pypdf from its own runtime folder and asks PyPI for nothing."""
    names = [r["name"] for r in (ready or {}).get("resources", [])]
    from_pypi = [n for n in names if "pypi.org" in n or "pythonhosted.org" in n]
    own = [n for n in names if "/runtime/wheels/" in n and ("svgelements-" in n or "pypdf-" in n)]
    return {"run: a full start fetches nothing from PyPI, and svgelements and pypdf from its own runtime": (
        bool(names) and not from_pypi and len(own) == 2)}


def check_scenarios(scenarios: dict) -> dict[str, bool]:
    """Pass or fail for the scenarios with an exact answer: fonts on demand (S-211) and saved files (S-212)."""
    checks: dict[str, bool] = {}
    fonts = scenarios.get("fonts")
    if fonts:
        used = lambda run, name: any(r.endswith(f"/{name}.bin") and r.startswith("GET") for r in run["requests"])
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
        compressed, corrupt = fonts.get("compressed", {}), fonts.get("corrupt", {})
        checks["fonts: a host that compresses fonts still fetches only the fonts a sketch uses, and text renders"] = (
            compressed.get("ok") and not compressed.get("output") and compressed.get("inked", 0) > 50
            and used(compressed, "DejaVuSans.ttf") and not any("Noto" in r for r in compressed["requests"]))
        checks["fonts: a font whose bytes differ from the manifest gives an error naming it"] = (
            "DejaVuSans.ttf" in "".join(corrupt.get("output", [])) and "manifest" in "".join(corrupt.get("output", [])))
    script = scenarios.get("script_saves")
    if script:
        checks["files: a script's SVG and GIF are reported"] = (bool(script["svg"]) and bool(script["gif"]) and script["svg"]["type"] == "image/svg+xml"
            and script["svg"]["has_svg"] and script["gif"]["magic"] and script["gif"]["type"] == "image/gif")
    web = scenarios.get("web_fonts")
    if web:
        first, second, bad = web.get("first", {}), web.get("second", {}), web.get("unreachable", {})
        name = "fonts/DejaVuSans-Bold.ttf.bin"
        checks["web fonts: the first run downloads the address once and sends the copy and fonts/sources.json"] = bool(
            first.get("ok") and sorted(first.get("names", [])) == [name, "fonts/sources.json"]
            and first.get("sources", {}).get("DejaVuSans-Bold.ttf.bin", "").endswith("/runner/runtime/fonts/DejaVuSans-Bold.ttf.bin")
            and len(first.get("requests", [])) == 1)
        checks["web fonts: a second run given the kept files reads no network"] = bool(
            second.get("ok") and not second.get("requests") and not second.get("output"))
        checks["web fonts: an address that cannot be reached gives the plain sentence"] = (
            "could not download" in "".join(bad.get("output", [])) and "Add file" in "".join(bad.get("output", [])))
    stdin = scenarios.get("stdin")
    if stdin:
        texts = lambda run: [line["text"] for line in run["output"]]
        two = texts(stdin["two"])
        checks["stdin: two lines are read in order, each prompt is sent before its read"] = (
            two[:3] == ["Your name? ", "Age? ", "Ada is 12"] and "never" not in two)
        checks["stdin: a third input() raises the plain EOFError sentence, with no frame of the runner's"] = (
            stdin["two"]["ended"] == "error" and two[3:4] == ["third? "]
            and "EOFError: input() has no more lines to read: this run was given 2." in two[-1]
            and 'File "main.py", line 4' in two[-1] and "<runner>" not in two[-1] and "<exec>" not in two[-1])
        checks["stdin: sys.stdin.readline() reads the same lines"] = texts(stdin["readline"]) == ["'first\\n' 'second'"]
        checks["stdin: a last line without a newline is sent when the run ends, and not with the next run"] = (
            texts(stdin["partial"]) == ["a", "no newline"] and texts(stdin["next"]) == ["next run"])
        none = texts(stdin["none"])
        checks["stdin: without stdin input() shows its prompt, then one plain sentence (S-279; a reused worker forgets the lines)"] = (
            none[:2] == ["before", "Your name? "]
            and "RuntimeError: Play cannot wait for typing yet. Run this on your computer, or put the answer in the code." in none[-1]
            and "OSError" not in none[-1] and "<runner>" not in none[-1] and "<exec>" not in none[-1])
        checks["stdin: stdin that is not a list of strings gives one clear error"] = (
            stdin["bad"]["ok"] is False and any("stdin must be a list of strings" in t for t in texts(stdin["bad"])))
    check = scenarios.get("checks")
    if check:
        basic = check["basic"]
        by_name = {t["name"]: t for t in basic["tests"]}
        checks["check: every test is answered in order, one passing and one failing with its own message"] = (
            basic["error"] is None and [t["name"] for t in basic["tests"]] == ["passes", "message", "bare", "other", "sees", "changes", "unchanged"]
            and by_name["passes"] == {"name": "passes", "passed": True, "message": ""}
            and by_name["message"]["passed"] is False and by_name["message"]["message"] == "total should be 11")
        checks["check: a bare assert gives a plain sentence with its line"] = (
            by_name["bare"]["passed"] is False and by_name["bare"]["message"] == "This check failed: assert total == 11")
        checks["check: another exception gives a plain sentence"] = (
            by_name["other"]["passed"] is False and by_name["other"]["message"] == "The check raised NameError: name 'totl' is not defined")
        checks["check: a test sees the learner's function and names, output (with the input() prompt) and source"] = (
            by_name["passes"]["passed"] and by_name["sees"]["passed"] and basic["output"] == "Name? Hello, Ada\n")
        checks["check: stdin lines reach the learner's input() and nothing is streamed as output"] = (
            basic["output"].startswith("Name? Hello, Ada") and check["streamed"] == 0)
        checks["check: one test's change to a name is not seen by the next, and what a test prints is discarded"] = (
            by_name["changes"]["passed"] and by_name["unchanged"]["passed"] and "nowhere" not in basic["output"])
        raises = check["raises"]
        checks["check: learner code that raises gives error from the learner's file, with its line, and no tests"] = (
            raises["tests"] == [] and raises["output"] == "1\n" and 'File "main.py", line 3' in raises["error"]
            and "print(totl)" in raises["error"] and "NameError: name 'totl' is not defined" in raises["error"]
            and "<runner>" not in raises["error"] and "<exec>" not in raises["error"] and "run_checks" not in raises["error"])
        checks["check: a syntax error gives error with the line and no tests"] = (
            check["syntax"]["tests"] == [] and 'File "main.py", line 1' in check["syntax"]["error"]
            and "SyntaxError" in check["syntax"]["error"])
        checks["check: input() with no lines given raises in the learner's code, as a plain run does"] = (
            check["noInput"]["tests"] == [] and "RuntimeError: Play cannot wait for typing yet." in check["noInput"]["error"]
            and 'File "main.py", line 1' in check["noInput"]["error"])
        runs_out = check["runsOut"]
        checks["check: input lines running out give the plain EOFError sentence, with no frame of the runner's"] = (
            runs_out["tests"] == [] and runs_out["output"] == "A? B? "
            and "EOFError: input() has no more lines to read: this run was given 1." in runs_out["error"]
            and 'File "main.py", line 2' in runs_out["error"] and "<runner>" not in runs_out["error"])
        checks["check: tests that are not a list of {name, code} give an error and no tests"] = (
            check["badTests"]["tests"] == [] and "tests must be a list" in check["badTests"]["error"])
        after = check["after"]
        checks["check: a normal run() after a check behaves as before"] = (
            after["ok"] is True and after["ended"] == "ended" and after["output"] == ["after a check"])
    alone = scenarios.get("pyodide_alone")
    if alone:
        names = lambda resources: [r["name"] for r in resources]
        texts = lambda run: [line["text"] for line in run["output"]]
        seen = names(alone["resources"])
        wheels = ("funground-", "pycairo-", "uharfbuzz-", "skia_pathops-")
        checks["run: Pyodide alone (packages: []) fetches Python itself and no funground wheel, no C-extension wheel, no manifest.json and no font"] = (
            any(n.endswith("pyodide.asm.wasm") for n in seen)
            and not any("/runtime/" in n or "manifest.json" in n or "/wheels/" in n or "/fonts/" in n or any(w in n for w in wheels) for n in seen))
        checks["run: Pyodide alone reports its Python and Pyodide versions, and the same capabilities"] = (
            set(alone["info"]["versions"]) == {"python", "pyodide"} and alone["info"]["versions"]["python"].startswith("3.14")
            and alone["info"]["capabilities"] == ["run", "stop", "stdin", "check", "packages"])
        plain = alone["plain"]
        checks["run: Pyodide alone runs a plain script that prints, reads input lines and its files, and the run ends with the size it was given"] = (
            texts(plain) == ["Name? ", "Hello, Ada", "from a file", "no newline"] and plain["ended"] == "ended"
            and plain["started"] == {"ok": True, "width": 321, "height": 123})
        raises = texts(alone["raises"])
        checks["run: Pyodide alone trims an error to the learner's file and line"] = (
            alone["raises"]["ended"] == "error" and raises[0] == "start" and len(raises) == 2
            and raises[1].startswith('Traceback (most recent call last):\n  File "main.py", line 3')
            and "ZeroDivisionError" in raises[1] and "<runner>" not in raises[1] and "<exec>" not in raises[1])
        said = 'ModuleNotFoundError: This runner was started without funground, so "import funground" cannot work here.'
        imports, from_import = texts(alone["imports"]), texts(alone["fromImport"])
        checks["run: Pyodide alone gives a plain sentence for import funground, with the learner's file and line, and the file stops there"] = (
            alone["imports"]["ended"] == "error" and imports[0] == "before" and len(imports) == 2 and said in imports[1]
            and 'File "main.py", line 2' in imports[1] and "No module named" not in imports[1] and "<runner>" not in imports[1])
        checks["run: Pyodide alone gives the same sentence for from funground import"] = (
            alone["fromImport"]["ended"] == "error" and len(from_import) == 1 and said in from_import[0]
            and 'File "main.py", line 1' in from_import[0])
        checks["run: Pyodide alone runs the next file in the same worker after an error"] = (
            texts(alone["after"]) == ["still works"] and alone["after"]["ended"] == "ended")
        answer = {t["name"]: t for t in alone["checked"]["tests"]}
        checks["run: check() answers in Pyodide alone as in a full runner"] = (
            alone["checked"]["error"] is None and alone["checked"]["output"] == "6\n" and answer["six"] == {"name": "six", "passed": True, "message": ""}
            and answer["wrong"] == {"name": "wrong", "passed": False, "message": "no"})
        default = names(alone["default_resources"])
        checks["run: the default runner still fetches manifest.json, the funground wheel and the three C-extension wheels"] = (
            any(n.endswith("/runtime/manifest.json") for n in default)
            and all(any(f"/wheels/{w}" in n for n in default) for w in wheels))
    packages = scenarios.get("packages")
    if packages:
        checks.update(check_packages(packages))
    errors = scenarios.get("errors")
    if errors:
        said = [line["text"] for line in errors["output"]]
        checks["run: a file runs, its print() reaches the page, and its error names the learner's file and line"] = (
            errors["started"] is True and "hello 42" in said
            and any("ZeroDivisionError" in s and 'File "bad.py", line 5' in s for s in said))
    stop = scenarios.get("stop")
    if stop:
        checks["stop: stop() ends a sketch stuck in while True at once, the page stays alive, and the next run works"] = (
            stop["stop_call_ms"] < 100 and stop["frames_after_stop"] == 0 and stop["page_beats_in_1s"] >= 10
            and stop["next_run_ok"] is True)
    keeps = scenarios.get("keeps")
    if keeps:
        first, second, ended, stopped = keeps["first"], keeps["second"], keeps["ended"], keeps["stopped"]
        checks["keep: a running sketch's keep reports studio/001.png, .py and .json, each once, with the right bytes"] = (
            first.get("ok") is True and sorted(first["files"]) == ["studio/001.json", "studio/001.png", "studio/001.py"]
            and sorted(keeps["names"]) == sorted(first["files"])
            and keeps["png"]["magic"] and keeps["png"]["type"] == "image/png" and keeps["py"]["same"]
            and keeps["json"]["note"] == "I kept the gold one" and keeps["json"]["sketch"] == "keeper.py" and keeps["json"]["size"] == [120, 80])
        checks["keep: a second keep is studio/002"] = second.get("ok") is True and sorted(second["files"]) == [
            "studio/002.json", "studio/002.png", "studio/002.py"]
        checks["keep: a script that has finished drawing can still be kept"] = (
            keeps["scriptOk"] and ended.get("ok") is True and "studio/001.png" in ended["files"] and "studio/001.png" in keeps["endedNames"])
        checks["keep: a stopped sketch answers 'not running' and writes nothing"] = (
            stopped.get("ok") is False and "not running" in stopped["reason"] and not keeps["stoppedFiles"])
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
    # 900: the scenarios now load scikit-learn (S-276, about 28 MB and 20 to 50 s cold) on top of everything else; a picture batch
    # takes far less, and the limit only matters when something hangs
    parser.add_argument("--timeout", type=int, default=900, help="seconds per Chrome start")
    parser.add_argument("--no-prewarm", action="store_true", help="the runner starts a worker only when a run needs it")
    parser.add_argument("--limit", type=int, help="run only the first N cases (for debugging)")
    parser.add_argument("--skip-scenarios", action="store_true", help="only the examples")
    args = parser.parse_args()

    runtime = REPO / "runner" / "runtime"
    cases = build_cases(args.funground.resolve(), runtime)[:args.limit]
    out = REPO / "tests" / "out"
    build_test_wheels(out / "wheels")
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
    report["checks"].update(check_sources(report.get("ready")))
    if not args.skip_scenarios:
        report["checks"].update(check_capabilities(report.get("ready"), report["checks"]))
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k not in ("server_bytes", "ready", "cases")}
    summary["cases"] = [{k: c.get(k) for k in ("id", "start_ms", "frame_ms", "error")} for c in report["cases"]]
    print(json.dumps(summary, indent=1))
    failed_pixels = [p["id"] for p in report.get("pixels", []) if not p.get("passed")]
    if failed_pixels:
        print("frames outside their tolerance:", failed_pixels)
    return 1 if (report["timeouts"] or any(b["fatal"] for b in report["batches"]) or not all(report["checks"].values())
                 or failed_pixels) else 0


if __name__ == "__main__":
    sys.exit(main())
