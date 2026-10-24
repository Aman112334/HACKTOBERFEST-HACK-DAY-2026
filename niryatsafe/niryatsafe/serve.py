"""Zero-dependency server (Python standard library only): same API + the built PWA.
Use it when `pip install` is not possible (venue Wi-Fi, locked laptop).   python -m niryatsafe.serve --port 8000"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .service import DIST, Service

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")


def make_handler(svc: Service, dist: str = DIST):
    class Handler(BaseHTTPRequestHandler):
        server_version = "NiryatSafe"

        def log_message(self, fmt, *args):  # quiet
            pass

        def _json(self, obj, status=200, headers=None):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/api/health":
                return self._json(svc.health())
            if u.path in ("/api/rulebook", "/api/rules-pack"):
                return self._json(svc.rulebook(), headers={"ETag": svc.bundle["meta"]["hash"]})
            if u.path == "/api/signals":
                return self._json(svc.signals())
            rel = u.path.lstrip("/") or "index.html"
            full = os.path.normpath(os.path.join(dist, rel))
            if not full.startswith(os.path.abspath(dist)) or not os.path.isfile(full):
                if os.path.isdir(full) and os.path.isfile(os.path.join(full, "index.html")):
                    full = os.path.join(full, "index.html")
                else:
                    return self._json({"detail": "not found"}, 404)
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or "javascript" in ctype or "json" in ctype else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache" if rel in ("index.html", "sw.js") else "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"detail": "invalid JSON"}, 400)
            if u.path == "/api/evaluate":
                lang = (parse_qs(u.query).get("lang") or [None])[0]
                try:
                    return self._json(svc.evaluate(body, lang))
                except ValueError as exc:
                    return self._json({"detail": str(exc)}, 422)
            if u.path == "/api/parse-lab-table":
                return self._json(svc.parse_lab_table(str(body.get("text", ""))))
            return self._json({"detail": "not found"}, 404)

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(prog="niryatsafe.serve")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(Service()))
    print(f"NiryatSafe on http://{a.host}:{a.port}  (standard-library server; API docs: see README)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
