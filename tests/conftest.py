import http.server
import re
import threading
from pathlib import Path

import pytest


class RangeHandler(http.server.BaseHTTPRequestHandler):
    """Serves files from `root` with single-range support, like the HF CDN."""

    root: Path
    requests: list

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.requests.append((self.path, self.headers.get("Range")))
        file = self.root / self.path.lstrip("/")
        if not file.is_file():
            self.send_error(404)
            return
        data = file.read_bytes()
        rng = self.headers.get("Range")
        if rng:
            start = int(re.match(r"bytes=(\d+)-", rng).group(1))
            if start >= len(data):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.end_headers()
                return
            body = data[start:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            body = data
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def http_root(tmp_path):
    """(base_url, served_dir, request_log) for a local Range-capable server."""
    served = tmp_path / "served"
    served.mkdir()
    handler = type("H", (RangeHandler,), {"root": served, "requests": []})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", served, handler.requests
    server.shutdown()
