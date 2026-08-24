"""Tests for the direct-link downloader, against a local test server.

No internet is used. The server can support ranges or refuse them, and it
can drop the connection in the middle, so resume is really exercised.
"""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fdl import http_engine
from fdl.http_engine import DownloadError

PAYLOAD = bytes((i * 7 + 11) % 256 for i in range(200_000))
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


class State:
    """Settings the tests change between requests."""

    def __init__(self):
        self.support_ranges = True
        self.etag = '"v1"'
        self.disposition = None
        self.send_length = True
        self.break_after = 0      # 0 = never break
        self.requests = []        # (path, Range header)


STATE = State()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # keep the test output clean

    def do_GET(self):
        STATE.requests.append((self.path, self.headers.get("Range")))

        if self.path == "/missing":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        start, end = 0, len(PAYLOAD) - 1
        status = 200
        range_header = self.headers.get("Range")

        if range_header and STATE.support_ranges:
            if_range = self.headers.get("If-Range")
            if if_range and STATE.etag and if_range != STATE.etag:
                pass  # fingerprint changed: send the whole file again
            else:
                try:
                    raw = range_header.split("=", 1)[1]
                    first, _, last = raw.partition("-")
                    start = int(first)
                    end = int(last) if last else len(PAYLOAD) - 1
                except (IndexError, ValueError):
                    start, end = 0, len(PAYLOAD) - 1
                else:
                    if start >= len(PAYLOAD):
                        self.send_response(416)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    status = 206

        body = PAYLOAD[start:end + 1]
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        if STATE.etag:
            self.send_header("ETag", STATE.etag)
        if STATE.disposition:
            self.send_header("Content-Disposition", STATE.disposition)
        self.send_header("Accept-Ranges",
                         "bytes" if STATE.support_ranges else "none")
        if status == 206:
            self.send_header("Content-Range",
                             f"bytes {start}-{end}/{len(PAYLOAD)}")
        if STATE.send_length:
            self.send_header("Content-Length", str(len(body)))
        else:
            self.send_header("Connection", "close")
        self.end_headers()

        if STATE.break_after and len(body) > STATE.break_after:
            # Send part of the answer, then cut the connection.
            self.wfile.write(body[: STATE.break_after])
            self.wfile.flush()
            self.close_connection = True
            try:
                self.connection.close()
            except OSError:
                pass
            return

        self.wfile.write(body)


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture(autouse=True)
def fresh_state():
    STATE.__init__()
    yield


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------- probe -------------------------------- #

def test_probe_reads_size_and_range_support(server):
    info = http_engine.probe(f"{server}/big.bin")
    assert info.size == len(PAYLOAD)
    assert info.resumable is True
    assert info.etag == '"v1"'
    assert info.filename == "big.bin"


def test_probe_uses_content_disposition(server):
    STATE.disposition = 'attachment; filename="real name.zip"'
    info = http_engine.probe(f"{server}/download.php")
    assert info.filename == "real name.zip"


def test_probe_reports_no_range_support(server):
    STATE.support_ranges = False
    info = http_engine.probe(f"{server}/big.bin")
    assert info.resumable is False


def test_probe_raises_clear_error_on_404(server):
    with pytest.raises(DownloadError) as err:
        http_engine.probe(f"{server}/missing")
    assert "404" in str(err.value)


def test_probe_rejects_non_http_scheme():
    with pytest.raises(DownloadError):
        http_engine.probe("ftp://example.com/file.zip")


# ------------------------------- downloads ------------------------------ #

def test_full_download(server, tmp_path):
    saved = http_engine.download(f"{server}/big.bin", tmp_path)
    assert saved.name == "big.bin"
    assert sha(saved) == PAYLOAD_SHA
    assert not list(tmp_path.glob("*.part"))
    assert not list(tmp_path.glob("*.meta"))


def test_resume_continues_from_existing_part(server, tmp_path):
    url = f"{server}/big.bin"
    half = len(PAYLOAD) // 2
    part = tmp_path / "big.bin.part"
    part.write_bytes(PAYLOAD[:half])
    (tmp_path / "big.bin.part.meta").write_text(json.dumps({
        "url": url, "size": len(PAYLOAD), "etag": '"v1"',
        "last_modified": None,
    }), encoding="utf-8")

    STATE.requests.clear()
    saved = http_engine.download(url, tmp_path)

    assert sha(saved) == PAYLOAD_SHA
    # The last request must have asked for the rest, not the whole file.
    assert any(r[1] == f"bytes={half}-" for r in STATE.requests)


def test_resume_restarts_when_file_changed_on_server(server, tmp_path):
    url = f"{server}/big.bin"
    part = tmp_path / "big.bin.part"
    part.write_bytes(b"\x00" * 5000)     # bytes from an older version
    (tmp_path / "big.bin.part.meta").write_text(json.dumps({
        "url": url, "size": len(PAYLOAD), "etag": '"OLD"',
        "last_modified": None,
    }), encoding="utf-8")

    saved = http_engine.download(url, tmp_path)
    assert sha(saved) == PAYLOAD_SHA    # no mix of old and new bytes


def test_resume_ignores_part_from_a_different_url(server, tmp_path):
    part = tmp_path / "big.bin.part"
    part.write_bytes(b"\x01" * 1000)
    (tmp_path / "big.bin.part.meta").write_text(json.dumps({
        "url": "http://somewhere.else/big.bin", "size": len(PAYLOAD),
        "etag": '"v1"', "last_modified": None,
    }), encoding="utf-8")

    saved = http_engine.download(f"{server}/big.bin", tmp_path)
    assert sha(saved) == PAYLOAD_SHA


def test_broken_connection_is_retried_and_resumed(server, tmp_path):
    """The server cuts the connection twice. The file must still be perfect."""
    url = f"{server}/big.bin"
    STATE.break_after = 40_000
    calls = {"n": 0}

    def on_retry(attempt, total, reason, wait):
        calls["n"] += 1
        if calls["n"] >= 2:
            STATE.break_after = 0      # the network "recovers"

    saved = http_engine.download(url, tmp_path, retries=5, on_retry=on_retry)

    assert calls["n"] >= 1             # it really did retry
    assert sha(saved) == PAYLOAD_SHA   # and the result is byte-perfect


def test_download_without_range_support(server, tmp_path):
    STATE.support_ranges = False
    saved = http_engine.download(f"{server}/big.bin", tmp_path)
    assert sha(saved) == PAYLOAD_SHA


def test_existing_file_is_not_overwritten(server, tmp_path):
    (tmp_path / "big.bin").write_bytes(b"keep me")
    saved = http_engine.download(f"{server}/big.bin", tmp_path)
    assert saved.name == "big (1).bin"
    assert (tmp_path / "big.bin").read_bytes() == b"keep me"


def test_progress_callback_reports_growth(server, tmp_path):
    seen = []
    http_engine.download(f"{server}/big.bin", tmp_path,
                         on_progress=lambda done, total: seen.append(done))
    assert seen
    assert seen == sorted(seen)
    assert seen[-1] == len(PAYLOAD)


def test_part_file_survives_a_failure(server, tmp_path):
    """When retries run out, the part file stays so we can resume later."""
    STATE.break_after = 30_000
    with pytest.raises(DownloadError):
        http_engine.download(f"{server}/big.bin", tmp_path, retries=0)
    part = tmp_path / "big.bin.part"
    assert part.exists() and part.stat().st_size > 0


def test_unfinished_downloads_lists_part_files(server, tmp_path):
    STATE.break_after = 30_000
    with pytest.raises(DownloadError):
        http_engine.download(f"{server}/big.bin", tmp_path / "Programs",
                             retries=0)

    found = http_engine.unfinished_downloads(tmp_path)
    assert len(found) == 1
    assert found[0]["part"].name == "big.bin.part"
    assert found[0]["url"].endswith("/big.bin")
    assert found[0]["size"] == len(PAYLOAD)
    assert 0 < found[0]["done"] < len(PAYLOAD)
