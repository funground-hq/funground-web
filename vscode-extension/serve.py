r"""Serve the funground extension on this computer, to install it in github.dev or vscode.dev for testing.

    C:\Projects\playground\.venv\Scripts\python.exe vscode-extension\serve.py [--port 5000]

Then, in github.dev or vscode.dev: F1, "Developer: Install Extension from Location...", and the address this
prints (http://localhost:5000/). Keep this running while you install; the extension is then kept by the browser.

Why localhost: vscode.dev's own Content Security Policy lets the editor download an extension only from the
Marketplace's servers and from localhost, so an address on our website is refused (decision D-082). Learners
will get the extension from the Marketplace; this is for the maintainer's tests until then.

Serves the extension's own files only (package.json, extension.js, media/), with the CORS header the editor
needs. Run `build.py --runtime site` first, so that media/runner/ holds the runner. Standard library only.
"""
from __future__ import annotations

import argparse
import http.server
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVED = ("package.json", "extension.js", "media/")
TYPES = {".json": "application/json", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def reply(self, code: int, body: bytes, kind: str = "text/plain") -> None:
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        # vscode.dev's panel is cross-origin isolated (COEP): without this a file from another origin is blocked.
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:
        name = self.path.split("?")[0].lstrip("/")
        target = (HERE / name).resolve()
        allowed = any(name == s or (s.endswith("/") and name.startswith(s)) for s in SERVED)
        if not allowed or HERE not in target.parents or not target.is_file():
            self.reply(404, b"not found")
            return
        self.reply(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))

    do_HEAD = do_GET

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        print(f"  {self.command} {self.path} {args[1] if len(args) > 1 else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    if not (HERE / "media" / "runner" / "runner.js").is_file():
        raise SystemExit("media/runner/ is missing: run build.py --runtime site first")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Install from: http://localhost:{args.port}/   (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
