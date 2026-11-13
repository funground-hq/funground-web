"""Serve this repository on http://localhost:8000, for runner/demo.html and trying the runner by hand.

    C:\\Projects\\playground\\.venv\\Scripts\\python.exe tools/serve.py [--port 8000]

Why not `python -m http.server`: on the maintainer's Windows machine it sends each file in one write, and Chrome's
connection is reset partway through a large one (a wheel, 13 Nov 2026), so Python never loads in the page. This
server is the standard one with two changes, the same as the test servers in tools/test_runner.py: it writes in
64 KB pieces, and it speaks HTTP/1.1 (keep-alive), so a large body is not cut short. It listens on this computer only.
Stop it with Ctrl+C.
"""
import argparse
import functools
import http.server
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHUNK = 65536


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".mjs": "text/javascript", ".wasm": "application/wasm", ".whl": "application/zip"}

    def copyfile(self, source, outputfile):
        shutil.copyfileobj(source, outputfile, CHUNK)
        outputfile.flush()


class Server(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if not isinstance(sys.exc_info()[1], ConnectionError):   # Chrome closing an idle keep-alive connection is normal
            super().handle_error(request, client_address)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8000)
    port = parser.parse_args().port
    server = Server(("127.0.0.1", port), functools.partial(Handler, directory=str(REPO)))
    print(f"Serving {REPO} at http://localhost:{port}/  (demo: http://localhost:{port}/runner/demo.html). Ctrl+C stops it.",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
