r"""Fill runner/runtime/ with what the browser runner loads from its own origin (story S-153).

    C:\Projects\playground\.venv\Scripts\python.exe tools/build_runtime.py --funground C:\Projects\playground-0.2

Standard library only; nothing is installed. It writes, under runner/runtime/ (git-ignored):

    wheels/        the three C-extension wheels (pycairo, uharfbuzz, skia-pathops) downloaded from the
                   funground-cairo-wasm release and checked against that release's SHA256SUMS.txt,
                   and the funground wheel built from the checkout given by --funground
    examples/      the checkout's gallery and Session 1 examples, with an index.json, for demo.html
    manifest.json  every file with its role, size and SHA-256; worker.js installs the wheels it lists

Why the files are copied here and not fetched from GitHub by the page: a release download carries no
CORS header, so a browser page cannot read it.

The funground wheel is a zip written by this script, following the wheel format (PEP 427, PEP 566),
because the venv has no build backend (setuptools is not installed, and building in an isolated
environment would install it). What goes in is read from the checkout's pyproject.toml, so the two
cannot drift: the same packages, the same package-data patterns, the same metadata. One difference, on
purpose: the gallery examples and their pictures (packages funground.examples and
funground.gallery_images, 4 MB) are left out. A page does not need them to run a sketch, and the site
fetches examples one at a time (see EXAMPLES below).
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RELEASE = "https://github.com/funground-hq/funground-cairo-wasm/releases/download/v0.1.0-wasm/"
C_WHEELS = ("pycairo", "uharfbuzz", "skia_pathops")            # name prefixes of the wheels in that release
ZIP_TIME = (2026, 1, 1, 0, 0, 0)                               # fixed, so the same source gives the same wheel
EXAMPLE_FOLDERS = ("gallery", "session1")                      # under <funground>/examples/


# ---- downloads

def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_c_wheels(out: Path) -> list[Path]:
    """The release's three wheels, each checked against SHA256SUMS.txt. An existing file with the right hash is kept."""
    sums = {}
    for line in fetch(RELEASE + "SHA256SUMS.txt").decode().splitlines():
        digest, _, name = line.strip().partition(" *")
        if name:
            sums[name] = digest
    found = []
    for prefix in C_WHEELS:
        names = [n for n in sums if n.startswith(prefix + "-")]
        if len(names) != 1:
            raise SystemExit(f"SHA256SUMS.txt should list exactly one {prefix} wheel, it lists {names}")
        name = names[0]
        target = out / name
        if not (target.exists() and sha256(target.read_bytes()) == sums[name]):
            print(f"downloading {name}")
            target.write_bytes(fetch(RELEASE + name))
        if sha256(target.read_bytes()) != sums[name]:
            target.unlink()
            raise SystemExit(f"{name}: SHA-256 does not match SHA256SUMS.txt")
        found.append(target)
    return found


def keep_c_wheels(out: Path, manifest: Path) -> list[Path]:
    """Offline: the C-extension wheels already in `out`, each checked against the SHA-256 the last build recorded."""
    recorded = {Path(f["name"]).name: f["sha256"] for f in json.loads(manifest.read_text(encoding="utf-8"))["files"] if f["role"] == "c-extension"}
    if not recorded:
        raise SystemExit("--offline needs an earlier build: runner/runtime/manifest.json lists no C-extension wheels")
    found = []
    for name, digest in recorded.items():
        target = out / name
        if not target.exists() or sha256(target.read_bytes()) != digest:
            raise SystemExit(f"{name} is missing or differs from manifest.json: build once without --offline")
        found.append(target)
    return found


# ---- the funground wheel

def package_files(root: Path, project: dict) -> list[Path]:
    """The files setuptools would put in the wheel, from the checkout's own configuration, in a fixed order."""
    setuptools = project["tool"]["setuptools"]
    mapped = set(setuptools.get("package-dir", {}))                    # packages built from other folders: left out
    patterns = setuptools.get("package-data", {}).get("funground", [])
    files = set()
    for package in setuptools["packages"]:
        if package in mapped:
            continue
        folder = root / package.replace(".", "/")
        files.update(p for p in folder.glob("*.py"))
        if package == "funground":
            for pattern in patterns:
                files.update(p for p in folder.glob(pattern) if p.is_file())
    return sorted(files)


def metadata(project: dict) -> str:
    meta = project["project"]
    lines = ["Metadata-Version: 2.4", f"Name: {meta['name']}", f"Version: {meta['version']}",
             f"Summary: {meta['description']}", f"License-Expression: {meta['license']}",
             f"Requires-Python: {meta['requires-python']}"]
    lines += [f"Author: {a['name']}" for a in meta.get("authors", [])]
    lines += [f"Classifier: {c}" for c in meta.get("classifiers", [])]
    lines += [f"Requires-Dist: {d}" for d in meta.get("dependencies", [])]
    for extra, requirements in meta.get("optional-dependencies", {}).items():
        lines.append(f"Provides-Extra: {extra}")
        lines += [f'Requires-Dist: {r}; extra == "{extra}"' for r in requirements]
    return "\n".join(lines) + "\n"


def record_line(path: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{path},sha256={digest},{len(data)}"


def build_funground_wheel(root: Path, out: Path) -> Path:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    name, version = project["project"]["name"], project["project"]["version"]
    dist_info = f"{name}-{version}.dist-info"
    entries: dict[str, bytes] = {p.relative_to(root).as_posix(): p.read_bytes() for p in package_files(root, project)}
    for licence in ("LICENSE", "THIRD_PARTY_LICENSES.md"):
        entries[f"{dist_info}/licenses/{licence}"] = (root / licence).read_bytes()
    entries[f"{dist_info}/METADATA"] = metadata(project).encode()
    entries[f"{dist_info}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: funground-web tools/build_runtime.py\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    record = [record_line(path, data) for path, data in entries.items()] + [f"{dist_info}/RECORD,,"]
    entries[f"{dist_info}/RECORD"] = ("\n".join(record) + "\n").encode()
    target = out / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as wheel:
        for path, data in entries.items():
            info = zipfile.ZipInfo(path, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            wheel.writestr(info, data)
    return target


def git_state(root: Path) -> dict:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()
    return {"branch": git("branch", "--show-current"), "commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}


# ---- the examples

def example_entry(path: Path, examples_root: Path) -> dict:
    """One index row: id, title (first docstring line), source path, and the data files its code names."""
    source = path.read_text(encoding="utf-8")
    docstring = ast.get_docstring(ast.parse(source)) or path.stem
    names = re.findall(r"""["']([^"'\n]+)["']""", source)
    files = sorted({n for n in names if (path.parent / n).is_file() and (path.parent / n) != path})
    relative = path.relative_to(examples_root)
    return {"id": f"{relative.parts[-2]}-{path.stem}", "title": docstring.splitlines()[0],
            "source": relative.as_posix(), "files": files}


def copy_examples(root: Path, out: Path) -> int:
    """Copy the example folders (the .py files and the data they name) and write index.json."""
    examples_root = root / "examples"
    index = []
    for folder in EXAMPLE_FOLDERS:
        for path in sorted((examples_root / folder).rglob("*.py")):
            if "data" in path.parts or "fonts" in path.parts:
                continue                                         # helper scripts beside the data, not examples
            entry = example_entry(path, examples_root)
            for target in [entry["source"]] + [f"{Path(entry['source']).parent.as_posix()}/{n}" for n in entry["files"]]:
                (out / target).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(examples_root / target, out / target)
            index.append(entry)
    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return len(index)


# ---- main

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--funground", required=True, type=Path, help="a funground checkout (the branch to run in the browser)")
    parser.add_argument("--out", type=Path, default=REPO / "runner" / "runtime", help="default: runner/runtime")
    parser.add_argument("--offline", action="store_true",
                        help="do not download: keep the C-extension wheels already in the output folder (checked against manifest.json)")
    args = parser.parse_args()
    started = time.time()
    root, out = args.funground.resolve(), args.out.resolve()
    wheels, examples = out / "wheels", out / "examples"
    wheels.mkdir(parents=True, exist_ok=True)
    if examples.exists():
        shutil.rmtree(examples)
    examples.mkdir()
    for old in wheels.glob("funground-*.whl"):
        old.unlink()

    c_wheels = keep_c_wheels(wheels, out / "manifest.json") if args.offline else download_c_wheels(wheels)
    fg_wheel = build_funground_wheel(root, wheels)
    count = copy_examples(root, examples)

    files = [{"name": f"wheels/{w.name}", "role": "c-extension", "size": w.stat().st_size, "sha256": sha256(w.read_bytes())} for w in c_wheels]
    files.append({"name": f"wheels/{fg_wheel.name}", "role": "funground", "size": fg_wheel.stat().st_size, "sha256": sha256(fg_wheel.read_bytes())})
    manifest = {"funground": git_state(root), "release": RELEASE, "files": files, "examples": count}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    for f in files:
        print(f"{f['size']:>9,}  {f['name']}")
    print(f"{count} examples; {time.time() - started:.1f} s; manifest at {out / 'manifest.json'}")


if __name__ == "__main__":
    sys.exit(main())
