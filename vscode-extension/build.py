r"""Assemble the funground VS Code extension (spike S-156) from this repository's runner.

    C:\Projects\playground\.venv\Scripts\python.exe vscode-extension/build.py [--runtime bundled|site] [--pyodide DIR] [--site OUT] [--vsix]

Needs runner/runtime/ (tools/build_runtime.py). Standard library only; nothing is installed. It writes:

    media/runner/            runner.js, worker.js, audio.js, microphone-worklet.js, copied from ../runner (git-ignored)
    media/runner/runtime/    with --runtime bundled (default): manifest.json and the wheels the worker installs, plus
                             svgelements and pypdf (role "dependency"), so nothing is fetched from PyPI
    media/runner/pyodide/    with --runtime bundled: the part of Pyodide the runner uses (core, standard library, and
                             micropip, fonttools, pygame-ce, Pillow), from --pyodide DIR (an unpacked Pyodide release) or
                             from jsDelivr
    --site OUT               the same pyodide/ and runtime/ folders under OUT, for a site that serves them with CORS
                             (the extension's "funground.runtimeUrl" setting points at OUT's URL)
    --vsix                   funground-<version>.vsix beside this file (a zip in the format vsce writes)

With --runtime site, media/runner/ holds only the runner's four scripts and the extension loads the rest from the site.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RUNNER_FILES = ("runner.js", "worker.js", "audio.js", "microphone-worklet.js")
PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/"
PYODIDE_CORE = ("pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
PYODIDE_PACKAGES = ("micropip", "fonttools", "pygame-ce", "pillow")        # worker.js: PYODIDE_PACKAGES and ON_DEMAND
DEPENDENCIES = {                                                             # funground's pure-Python dependencies, from PyPI
    "svgelements": "1.9.6",
    "pypdf": "6.20.0",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def copy_pyodide(out: Path, source: Path | None) -> list[str]:
    """Pyodide's core and the four packages, each checked against the lock file's SHA-256."""
    out.mkdir(parents=True, exist_ok=True)
    read = (lambda name: (source / name).read_bytes()) if source else (lambda name: fetch(PYODIDE_URL + name))
    lock_bytes = read("pyodide-lock.json")
    lock = json.loads(lock_bytes)
    names = list(PYODIDE_CORE)
    wanted = list(PYODIDE_PACKAGES)
    while wanted:                                                            # the packages and what they depend on
        package = lock["packages"][wanted.pop()]
        if package["file_name"] not in names:
            names.append(package["file_name"])
            wanted += package["depends"]
    hashes = {p["file_name"]: p["sha256"] for p in lock["packages"].values()}
    for name in names:
        data = lock_bytes if name == "pyodide-lock.json" else read(name)
        if name in hashes and sha256(data) != hashes[name]:
            raise SystemExit(f"{name}: SHA-256 does not match pyodide-lock.json")
        (out / name).write_bytes(data)
    return names


def copy_runtime(out: Path) -> None:
    """runner/runtime's manifest and wheels, plus the pure-Python dependencies (role "dependency") from PyPI."""
    source = REPO / "runner" / "runtime"
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    (out / "wheels").mkdir(parents=True, exist_ok=True)
    for entry in manifest["files"]:
        data = (source / entry["name"]).read_bytes()
        if sha256(data) != entry["sha256"]:
            raise SystemExit(f"{entry['name']}: SHA-256 does not match runner/runtime/manifest.json (run tools/build_runtime.py)")
        (out / entry["name"]).write_bytes(data)
    for name, version in DEPENDENCIES.items():
        release = json.loads(fetch(f"https://pypi.org/pypi/{name}/{version}/json"))
        wheel = next(f for f in release["urls"] if f["packagetype"] == "bdist_wheel" and f["filename"].endswith("-none-any.whl"))
        target = out / "wheels" / wheel["filename"]
        if not (target.exists() and sha256(target.read_bytes()) == wheel["digests"]["sha256"]):
            target.write_bytes(fetch(wheel["url"]))
        data = target.read_bytes()
        if sha256(data) != wheel["digests"]["sha256"]:
            raise SystemExit(f"{wheel['filename']}: SHA-256 does not match PyPI")
        manifest["files"].append({"name": f"wheels/{wheel['filename']}", "role": "dependency", "size": len(data), "sha256": sha256(data)})
    manifest.pop("examples", None)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def write_vsix(extension: Path) -> Path:
    """A .vsix: the extension's files under extension/, with the two XML files vsce adds."""
    package = json.loads((extension / "package.json").read_text(encoding="utf-8"))
    target = extension / f"{package['name']}-{package['version']}.vsix"
    files = ["package.json", "extension.js", "README.md", *(p.relative_to(extension).as_posix() for p in sorted((extension / "media").rglob("*")) if p.is_file())]
    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{package['name']}" Version="{package['version']}" Publisher="{package['publisher']}" />
    <DisplayName>{package['displayName']}</DisplayName>
    <Description xml:space="preserve">{package['description']}</Description>
    <Categories>{",".join(package['categories'])}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{package['engines']['vscode']}" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="web" />
    </Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code" /></Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
  </Assets>
</PackageManifest>
"""
    types = sorted({Path(f).suffix.lstrip(".") for f in files} | {"vsixmanifest"})
    mime = {"json": "application/json", "js": "application/javascript", "mjs": "application/javascript", "md": "text/markdown",
            "css": "text/css", "svg": "image/svg+xml", "wasm": "application/wasm", "vsixmanifest": "text/xml"}
    content_types = ('<?xml version="1.0" encoding="utf-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     + "".join(f'<Default Extension=".{t}" ContentType="{mime.get(t, "application/octet-stream")}"/>' for t in types) + "</Types>")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("extension.vsixmanifest", manifest)
        z.writestr("[Content_Types].xml", content_types)
        for name in files:
            z.write(extension / name, f"extension/{name}")
    return target


def folder_size(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime", choices=("bundled", "site"), default="bundled")
    parser.add_argument("--pyodide", type=Path, help="an unpacked Pyodide 314.0.7 release (default: download from jsDelivr)")
    parser.add_argument("--site", type=Path, help="also write pyodide/ and runtime/ under this folder, for a CORS site")
    parser.add_argument("--vsix", action="store_true")
    args = parser.parse_args()
    if not (REPO / "runner" / "runtime" / "manifest.json").exists():
        sys.exit("runner/runtime/ is missing: run tools/build_runtime.py first")

    runner = HERE / "media" / "runner"
    shutil.rmtree(runner, ignore_errors=True)
    runner.mkdir(parents=True)
    for name in RUNNER_FILES:
        shutil.copy2(REPO / "runner" / name, runner / name)
    targets = ([runner] if args.runtime == "bundled" else []) + ([args.site.resolve()] if args.site else [])
    for target in targets:
        copy_pyodide(target / "pyodide", args.pyodide)
        copy_runtime(target / "runtime")
        print(f"{target}: pyodide/ {folder_size(target / 'pyodide'):,} bytes, runtime/ {folder_size(target / 'runtime'):,} bytes")
    print(f"extension folder: {folder_size(HERE / 'media') + sum((HERE / n).stat().st_size for n in ('package.json', 'extension.js')):,} bytes")
    if args.vsix:
        vsix = write_vsix(HERE)
        print(f"{vsix.name}: {vsix.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
