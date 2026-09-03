#!/usr/bin/env python3
"""Serve dist/ for local review: python3 tools/serve.py [port]"""
import functools
import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "dist"


class Handler(http.server.SimpleHTTPRequestHandler):
    """Static handler that mirrors how a host resolves clean URLs and 404s."""

    def send_error(self, code, message=None, explain=None):
        if code == 404:
            page = DIST / "404.html"
            if page.exists():
                body = page.read_bytes()
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
                return
        super().send_error(code, message, explain)


def main() -> None:
    if not DIST.exists():
        sys.exit("dist/ not found — run: python3 tools/build.py")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = functools.partial(Handler, directory=str(DIST))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}/"
        print(f"Serving {DIST} at {url}  (Ctrl-C to stop)")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        httpd.serve_forever()


if __name__ == "__main__":
    main()
