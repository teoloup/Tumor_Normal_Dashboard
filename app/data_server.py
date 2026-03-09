from __future__ import annotations

import argparse
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

CHUNK_SIZE = 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve synced pipeline files locally with byte-range support for IGV.js.")
    parser.add_argument("--root", required=True, help="Root directory to serve.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


class RangeRequestHandler(BaseHTTPRequestHandler):
    server_version = "TumorNormalVariantDataServer/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_common_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        self.end_headers()

    def do_HEAD(self) -> None:
        self.handle_request(send_body=False)

    def do_GET(self) -> None:
        self.handle_request(send_body=True)

    def handle_request(self, send_body: bool) -> None:
        try:
            file_path = self.translate_path(self.path)
        except PermissionError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        file_size = file_path.stat().st_size
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        range_header = self.headers.get("Range")

        start = 0
        end = file_size - 1
        status = HTTPStatus.OK

        if range_header:
            try:
                units, _, range_spec = range_header.partition("=")
                if units.strip() != "bytes":
                    raise ValueError
                start_text, _, end_text = range_spec.partition("-")
                if start_text:
                    start = int(start_text)
                if end_text:
                    end = int(end_text)
                if not end_text:
                    end = file_size - 1
                if start > end or start < 0 or end >= file_size:
                    raise ValueError
                status = HTTPStatus.PARTIAL_CONTENT
            except ValueError:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "Invalid Range header")
                return

        self.send_response(status)
        self.send_common_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        if not send_body:
            return

        with file_path.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = handle.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges")

    def translate_path(self, request_path: str) -> Path:
        parsed = urlparse(request_path)
        relative_path = unquote(parsed.path.lstrip("/"))
        candidate = (self.server.root / relative_path).resolve()
        root = self.server.root.resolve()
        if root == candidate or root in candidate.parents:
            return candidate
        raise PermissionError

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")


class LocalFileServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], root: Path):
        super().__init__(server_address, RangeRequestHandler)
        self.root = root


def main() -> None:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Invalid root directory: {root}")

    os.chdir(root)
    httpd = LocalFileServer((args.host, args.port), root)
    print(f"Serving {root} on http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
