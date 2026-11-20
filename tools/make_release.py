r"""Make funground-web's release from a built runner (story S-268, ADR-008), or check one.

    C:\Projects\playground\.venv\Scripts\python.exe tools/make_release.py --version 0.1.0 [--out dist]
    C:\Projects\playground\.venv\Scripts\python.exe tools/make_release.py --check dist/funground-web-0.1.0

Needs runner/runtime/ (tools/build_runtime.py), built from a clean funground checkout. Standard library only.

A release holds the minimum a run needs, and nothing of this repository's own checks or test sketches (ADR-008):

    funground-web-<version>/
        runner.js, worker.js, ...   the runner's scripts, exactly those runner/files.json names
        runtime/                    everything tools/build_runtime.py wrote: manifest.json and every file it lists (wheels,
                                    fonts, models.json, completions.json), and examples/ with its index.json
        README.md                   runner/README.md: how a page uses the runner, which is the release's interface
        LICENSE                     this repository's licence (LGPL-2.1), which the wheels inside it are under too
        release.json                what is in the release (below)

release.json says which release this is and lists every other file in the folder, with its size and SHA-256:

    {"name": "funground-web", "version": "0.1.0", "commit": "<funground-web commit>",
     "funground": {"version": "0.2.0", "commit": "<funground commit>"},
     "uses": {"pyodide": "<address>", "onnxruntime-web": "<address>", "funground-cairo-wasm": "<release address>"},
     "capabilities": ["run", "stop", ...],
     "files": [{"path": "runner.js", "size": 12345, "sha256": "<hex>"}, ...]}

A host that uses the release (the site's Play, an outside host such as an online course, D-143 a) copies the folder whole and
checks every file against release.json, as --check does: the folder holds exactly the files listed, no more and no fewer, and
every size and SHA-256 matches. Pyodide and onnxruntime-web are not in the release: the runner loads them from the addresses
under "uses" unless the host gives its own (the runner's pyodideUrl and onnxruntimeUrl options).

Beside the folder, the zip of it (funground-web-<version>.zip, the same bytes for the same files) and a copy of release.json.
The release's notes are the section of RELEASES.md headed with its version; a version without notes is refused.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = REPO / "runner"
VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")       # 0.1.0, 0.2.0-rc.1
ZIP_TIME = (2026, 1, 1, 0, 0, 0)                                  # fixed, so the same files give the same zip
# Files of the release that are not the runner's scripts or runtime/: {path in the release: source}.
EXTRA = {"README.md": RUNNER / "README.md", "LICENSE": REPO / "LICENSE"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runner_scripts() -> list[str]:
    """runner/files.json's list, after tools/check_runner_files.py has found nothing wrong with it."""
    spec = importlib.util.spec_from_file_location("check_runner_files", Path(__file__).with_name("check_runner_files.py"))
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    found = check.problems()
    if found:
        raise SystemExit("runner/files.json is out of date:\n  " + "\n  ".join(found))
    return check.named_files()


def checked_runtime(runtime: Path) -> dict:
    """runtime/manifest.json, after every file it lists has been found with its size and SHA-256 (a stale or partly rebuilt
    runtime/ is refused), and its funground checkout was clean."""
    manifest_path = runtime / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"{manifest_path} is missing: run tools/build_runtime.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = runtime / entry["name"]
        if not path.is_file() or path.stat().st_size != entry["size"] or sha256(path) != entry["sha256"]:
            raise SystemExit(f"runtime/{entry['name']} is missing or differs from manifest.json: run tools/build_runtime.py again")
    if manifest["funground"].get("dirty"):
        raise SystemExit("runtime/ was built from a funground checkout with uncommitted changes: a release needs a clean one")
    if not (runtime / "examples" / "index.json").is_file():
        raise SystemExit("runtime/examples/index.json is missing: run tools/build_runtime.py again")
    return manifest


def funground_version(manifest: dict) -> str:
    """The version of the funground wheel built into the runtime (role "funground"): its file name says it (PEP 427)."""
    wheels = [Path(f["name"]).name for f in manifest["files"] if f["role"] == "funground"]
    if len(wheels) != 1:
        raise SystemExit(f"manifest.json should list one funground wheel, it lists {wheels}")
    return wheels[0].split("-")[1]


def worker_constant(name: str) -> str | list[str]:
    """A constant of runner/worker.js (PYODIDE, ONNXRUNTIME, CAPABILITIES), read from its source: the release says what the
    runner it holds uses and can do, from the file itself."""
    source = (RUNNER / "worker.js").read_text(encoding="utf-8")
    match = re.search(rf"^const {name} = (.+?);", source, re.M)
    if not match:
        raise SystemExit(f"runner/worker.js has no const {name}")
    return json.loads(match.group(1).replace("'", '"'))


def git_commit() -> str:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout.strip()
    if git("status", "--porcelain", "--untracked-files=no", "--", "runner", "LICENSE"):
        raise SystemExit("runner/ or LICENSE has uncommitted changes: a release is made from a commit")
    return git("rev-parse", "HEAD")


def release_notes(version: str) -> str:
    """The section of RELEASES.md headed "## <version>", without its heading."""
    text = (REPO / "RELEASES.md").read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match or not match.group(1).strip():
        raise SystemExit(f"RELEASES.md has no notes for {version}: write them under a heading '## {version}' first")
    return match.group(1).strip() + "\n"


def listing(folder: Path) -> list[dict]:
    """Every file under `folder` except release.json, in a fixed order, with its size and SHA-256."""
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.relative_to(folder).as_posix() != "release.json")
    return [{"path": p.relative_to(folder).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)} for p in files]


def check(folder: Path) -> list[str]:
    """What is wrong with a release folder, one sentence each; empty when it holds exactly what its release.json lists."""
    listed = json.loads((folder / "release.json").read_text(encoding="utf-8"))["files"]
    found = {f["path"]: f for f in listing(folder)}
    problems = []
    for entry in listed:
        there = found.pop(entry["path"], None)
        if there is None:
            problems.append(f"{entry['path']} is listed in release.json but missing")
        elif (there["size"], there["sha256"]) != (entry["size"], entry["sha256"]):
            problems.append(f"{entry['path']} differs from release.json (size or SHA-256)")
    problems += [f"{path} is in the folder but not listed in release.json" for path in sorted(found)]
    return problems


def write_zip(folder: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(f"{folder.name}/{path.relative_to(folder).as_posix()}", ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def make(version: str, out: Path) -> Path:
    if not VERSION.match(version):
        raise SystemExit(f"{version!r} is not a version like 0.1.0 or 0.2.0-rc.1")
    scripts = runner_scripts()
    runtime = RUNNER / "runtime"
    manifest = checked_runtime(runtime)
    notes = release_notes(version)
    commit = git_commit()

    folder = out / f"funground-web-{version}"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for name in scripts:
        shutil.copyfile(RUNNER / name, folder / name)
    shutil.copytree(runtime, folder / "runtime")
    for name, source in EXTRA.items():
        shutil.copyfile(source, folder / name)

    release = {
        "name": "funground-web",
        "version": version,
        "commit": commit,
        "funground": {"version": funground_version(manifest), "commit": manifest["funground"]["commit"]},
        "uses": {"pyodide": worker_constant("PYODIDE"), "onnxruntime-web": worker_constant("ONNXRUNTIME"),
                 "funground-cairo-wasm": manifest["release"]},
        "capabilities": worker_constant("CAPABILITIES"),
        "files": listing(folder),
    }
    (folder / "release.json").write_text(json.dumps(release, indent=1) + "\n", encoding="utf-8")
    problems = check(folder)
    if problems:
        raise SystemExit("the release folder does not match its release.json:\n  " + "\n  ".join(problems))
    write_zip(folder, out / f"{folder.name}.zip")
    shutil.copyfile(folder / "release.json", out / "release.json")
    (out / "notes.md").write_text(notes, encoding="utf-8")
    size = sum(f["size"] for f in release["files"])
    print(f"{folder.name}: {len(release['files'])} files, {size / 1e6:.1f} MB, funground {release['funground']['version']} "
          f"({release['funground']['commit'][:7]}); {out / (folder.name + '.zip')}")
    return folder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--version", help="the release's version, like 0.1.0")
    group.add_argument("--check", type=Path, metavar="FOLDER", help="check a release folder against its release.json")
    parser.add_argument("--out", type=Path, default=REPO / "dist", help="where the release is written (default: dist/)")
    args = parser.parse_args()
    if args.check:
        problems = check(args.check)
        for line in problems:
            print(line, file=sys.stderr)
        if problems:
            raise SystemExit(f"{args.check} does not match its release.json ({len(problems)} problem{'s' if len(problems) > 1 else ''})")
        print(f"{args.check}: every file matches release.json, and nothing else is there")
    else:
        make(args.version, args.out.resolve())


if __name__ == "__main__":
    main()
