"""Tests for resumable downloads in fast_async_download.

These spin up a local HTTP server that interrupts the first response
mid-stream (reproducing the IncompleteRead errors seen on large tracks)
and verify that a subsequent attempt resumes and produces a byte-for-byte
correct file.
"""
import hashlib
import http.server
import os
import threading

import pytest

from streamrip.client.downloadable import fast_async_download


def _payload(n: int) -> bytes:
    return bytes((i * 31 + 7) % 256 for i in range(n))


def _start_server(handler_cls):
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


@pytest.mark.asyncio
async def test_resume_with_range_support(tmp_path):
    """Server drops the connection mid-stream, then honors Range with 206."""
    total = 1_000_000
    payload = _payload(total)
    full_sha = hashlib.sha256(payload).hexdigest()
    request_ranges = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            rng = self.headers.get("Range")
            request_ranges.append(rng)
            if rng is None:
                self.send_response(200)
                self.send_header("Content-Length", str(total))
                self.end_headers()
                self.wfile.write(payload[: total // 2])
                self.wfile.flush()
                self.close_connection = True
                self.connection.close()
            else:
                start = int(rng.replace("bytes=", "").split("-")[0])
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{total-1}/{total}")
                self.send_header("Content-Length", str(total - start))
                self.end_headers()
                self.wfile.write(payload[start:])

    srv, port = _start_server(Handler)
    url = f"http://127.0.0.1:{port}/track.flac"
    path = str(tmp_path / "track.flac")

    last_exc = None
    for _ in range(4):
        try:
            await fast_async_download(path, url, {}, lambda n: None)
            last_exc = None
            break
        except Exception as e:  # noqa: BLE001
            last_exc = e

    srv.shutdown()

    assert last_exc is None
    assert os.path.getsize(path) == total
    with open(path, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == full_sha
    # The retry sent a Range header (resume actually happened).
    assert any(r and r.startswith("bytes=") for r in request_ranges)


@pytest.mark.asyncio
async def test_resume_falls_back_when_range_ignored(tmp_path):
    """If the server ignores Range and replies 200 with the full body,
    the partial file must be overwritten, not appended to."""
    total = 600_000
    payload = _payload(total)
    full_sha = hashlib.sha256(payload).hexdigest()
    calls = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            calls.append(self.headers.get("Range"))
            if len(calls) == 1:
                self.send_response(200)
                self.send_header("Content-Length", str(total))
                self.end_headers()
                self.wfile.write(payload[: total // 2])
                self.wfile.flush()
                self.close_connection = True
                self.connection.close()
            else:
                # Range ignored: send the whole file from the start.
                self.send_response(200)
                self.send_header("Content-Length", str(total))
                self.end_headers()
                self.wfile.write(payload)

    srv, port = _start_server(Handler)
    url = f"http://127.0.0.1:{port}/x.flac"
    path = str(tmp_path / "x.flac")

    for _ in range(4):
        try:
            await fast_async_download(path, url, {}, lambda n: None)
            break
        except Exception:  # noqa: BLE001
            pass

    srv.shutdown()

    # No duplicated bytes despite the partial file already existing.
    assert os.path.getsize(path) == total
    with open(path, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == full_sha
