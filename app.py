"""SignalLens web server.

The first vertical slice intentionally uses only the Python standard library so
the dashboard can be run and tested without global installs or API keys.
"""

from __future__ import annotations

import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from signal_lens.engine import run_research
from signal_lens.resolver import resolve_company, supported_companies


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
MAX_BODY_BYTES = 64 * 1024


class SignalLensHandler(BaseHTTPRequestHandler):
    server_version = "SignalLens/0.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Keep demo output focused on startup and errors.
        return

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, object] | None:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json({"error": "Invalid content length"}, HTTPStatus.BAD_REQUEST)
            return None
        if length < 0 or length > MAX_BODY_BYTES:
            self._send_json({"error": "Request body is too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": "Request body must be valid JSON"}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self._send_json({"error": "Request body must be an object"}, HTTPStatus.BAD_REQUEST)
            return None
        return payload

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file(STATIC_DIR / "index.html")
            return
        if parsed.path == "/api/health":
            self._send_json({"status": "ok", "mode": os.getenv("SIGNAL_LENS_MODE", "offline")})
            return
        if parsed.path == "/api/companies":
            self._send_json({"companies": supported_companies()})
            return
        if parsed.path.startswith("/static/"):
            requested = (STATIC_DIR / parsed.path.removeprefix("/static/")).resolve()
            if STATIC_DIR.resolve() not in requested.parents:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_file(requested)
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        payload = self._read_json()
        if payload is None:
            return
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            self._send_json({"error": "Enter a company name or NSE symbol."}, HTTPStatus.BAD_REQUEST)
            return

        if self.path == "/api/resolve":
            identity = resolve_company(query)
            if identity is None:
                self._send_json(
                    {"error": "We could not resolve that company in the Track A universe."},
                    HTTPStatus.NOT_FOUND,
                )
                return
            self._send_json({"company": identity.__dict__})
            return

        if self.path == "/api/research":
            mode = payload.get("mode", "offline")
            if mode not in {"offline", "live"}:
                mode = "offline"
            try:
                report = run_research(query, str(mode))
            except ValueError as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"run_id": report.run_id, "status": "complete", "report": report.to_dict()})
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def start_server() -> None:
    host = os.getenv("SIGNAL_LENS_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("SIGNAL_LENS_PORT", "8000"))
    except ValueError:
        port = 8000
    server = ThreadingHTTPServer((host, port), SignalLensHandler)
    print(f"SignalLens running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSignalLens stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    start_server()
