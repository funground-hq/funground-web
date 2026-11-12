r"""Print the entry a host lists in createRunner({packages}) for one wheel (story S-276).

    C:\Projects\playground\.venv\Scripts\python.exe tools/wheel_entry.py PATH_OR_URL [--url ADDRESS]

PATH_OR_URL is a wheel on disk or at an http(s) address. The entry is JSON: {"name", "url", "sha256", "imports"}.
  name     from the file name, as written there with "_" changed to "-" (seaborn-0.13.2-py3-none-any.whl gives "seaborn")
  url      the address the page will fetch it from: --url if given, else PATH_OR_URL (a path stays a path, so edit it or pass --url)
  sha256   of the file's bytes: the runner refuses the wheel if what it fetches differs
  imports  the names a learner imports: top_level.txt of the wheel's .dist-info, or else its top-level folders and modules

It reads the wheel and runs none of it. Python's standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path


def read(source: str) -> tuple[str, bytes]:
    """The wheel's file name and bytes, from a path or an http(s) address."""
    if re.match(r"https?://", source):
        with urllib.request.urlopen(source, timeout=60) as response:       # nosec: the maintainer named this address
            return Path(source.split("?")[0].split("#")[0]).name, response.read()
    path = Path(source)
    return path.name, path.read_bytes()


def top_level(archive: zipfile.ZipFile) -> list[str]:
    """top_level.txt when the wheel has one, else the top-level folders with an __init__.py and the top-level .py files."""
    names = archive.namelist()
    for name in names:
        if name.endswith(".dist-info/top_level.txt") and name.count("/") == 1:
            return [line.strip() for line in archive.read(name).decode("utf-8").splitlines() if line.strip()]
    found: list[str] = []
    for name in names:
        parts = name.split("/")
        if parts[0].endswith((".dist-info", ".data")):
            continue
        top = parts[0][:-3] if len(parts) == 1 and parts[0].endswith(".py") else parts[0] if len(parts) > 1 and parts[1] == "__init__.py" else None
        if top and top not in found:
            found.append(top)
    return found


def entry(source: str, url: str | None = None) -> dict:
    file, data = read(source)
    if not file.endswith(".whl"):
        raise SystemExit(f"{file} is not a .whl file.")
    try:
        imports = top_level(zipfile.ZipFile(io.BytesIO(data)))
    except zipfile.BadZipFile:
        raise SystemExit(f"{file} is not a wheel (it is not a zip file).") from None
    name = file.split("-")[0].replace("_", "-")
    return {"name": name, "url": url or source, "sha256": hashlib.sha256(data).hexdigest(), "imports": imports or [name.replace("-", "_")]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("wheel", help="a wheel on disk, or its http(s) address")
    parser.add_argument("--url", help="the address the page will fetch it from (default: the wheel's own)")
    args = parser.parse_args()
    print(json.dumps(entry(args.wheel, args.url), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
