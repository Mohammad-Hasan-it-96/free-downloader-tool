"""Tests for multi-connection downloads and the speed limit.

The danger with several connections is silent damage: bytes written to the
wrong place, or a part file continued by the wrong method. These tests check
the bytes, not just the size.
"""

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fdl import http_engine, segmented
from fdl.http_engine import (MODE_ARIA2, MODE_SEGMENTS, MODE_STREAM,
                             DownloadError)
from fdl.limiter import RateLimiter

# Every byte is different, so a wrongly placed chunk cannot hide.
PAYLOAD = bytes((i * 31 + i // 251) % 256 for i in range(3_000_000))
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


class State:
    def __init__(self):
        self.support_ranges = True
        self.break_after = 0
        self.etag = '"v1"'
        self.range_requests = []
        self.lock = threading.Lock()


STATE = State()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        header = self.headers.get("Range")
        with STATE.lock:
            STATE.range_requests.append(header)

        start, end = 0, len(PAYLOAD) - 1
        status = 200
        if header and STATE.support_ranges:
            raw = header.split("=", 1)[1]
            first, _, last = raw.partition("-")
            start = int(first)
            end = int(last) if last else len(PAYLOAD) - 1
            if start > end or start >= len(PAYLOAD):
                self.send_response(416)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206

        body = PAYLOAD[start:end + 1]
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("ETag", STATE.etag)
        self.send_header("Accept-Ranges",
                         "bytes" if STATE.support_ranges else "none")
        if status == 206:
            self.send_header("Content-Range",
                             f"bytes {start}-{end}/{len(PAYLOAD)}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        if STATE.break_after and len(body) > STATE.break_after:
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
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture(autouse=True)
def fresh_state():
    STATE.__init__()
    yield


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------ planning -------------------------------- #

def test_small_files_use_one_connection():
    info = http_engine.RemoteInfo(url="x", size=100_000, resumable=True)
    assert segmented.should_split(info, 8) is False


def test_large_files_split():
    info = http_engine.RemoteInfo(url="x", size=50_000_000, resumable=True)
    assert segmented.should_split(info, 8) is True
    assert segmented.wanted_connections(50_000_000, 8) == 8


def test_a_server_without_range_support_never_splits():
    info = http_engine.RemoteInfo(url="x", size=50_000_000, resumable=False)
    assert segmented.should_split(info, 8) is False


def test_unknown_size_never_splits():
    info = http_engine.RemoteInfo(url="x", size=None, resumable=True)
    assert segmented.should_split(info, 8) is False


def test_segments_cover_the_whole_file_exactly():
    parts = segmented.build_segments(1_000_003, 7)
    assert parts[0].start == 0
    assert parts[-1].end == 1_000_002
    for earlier, later in zip(parts, parts[1:]):
        assert later.start == earlier.end + 1
    assert sum(p.length for p in parts) == 1_000_003


# ----------------------------- downloading ------------------------------ #

def test_multi_connection_download_is_byte_perfect(server, tmp_path):
    saved = http_engine.download(f"{server}/big.bin", tmp_path, connections=8)
    assert sha(saved) == PAYLOAD_SHA
    assert saved.stat().st_size == len(PAYLOAD)
    # It really used several ranges, not one plain request.
    ranges = [r for r in STATE.range_requests if r and r != "bytes=0-0"]
    assert len(ranges) >= 4


def test_one_connection_still_works(server, tmp_path):
    saved = http_engine.download(f"{server}/big.bin", tmp_path, connections=1)
    assert sha(saved) == PAYLOAD_SHA


def test_meta_records_the_mode(server, tmp_path):
    info = http_engine.probe(f"{server}/big.bin")
    part = tmp_path / (info.filename + ".part")

    # Start a split download but stop it, so the meta file stays behind.
    STATE.break_after = 1000
    with pytest.raises(DownloadError):
        http_engine.download(f"{server}/big.bin", tmp_path, info,
                             connections=4, retries=0)

    meta = http_engine.read_meta(part)
    assert meta["mode"] == MODE_SEGMENTS
    assert len(meta["segments"]) == 4


def test_resume_of_a_split_download_is_byte_perfect(server, tmp_path):
    """Break every connection, then let it recover and finish."""
    url = f"{server}/big.bin"
    info = http_engine.probe(url)

    STATE.break_after = 60_000
    with pytest.raises(DownloadError):
        http_engine.download(url, tmp_path, info, connections=4, retries=0)

    part = tmp_path / (info.filename + ".part")
    meta = http_engine.read_meta(part)
    done_before = sum(row[2] for row in meta["segments"])
    assert 0 < done_before < len(PAYLOAD)

    STATE.break_after = 0
    saved = http_engine.download(url, tmp_path, info, connections=4)
    assert sha(saved) == PAYLOAD_SHA


def test_progress_is_read_from_the_meta_not_the_file_size(server, tmp_path):
    """A split part file is full size from the start, so size means nothing."""
    url = f"{server}/big.bin"
    info = http_engine.probe(url)
    STATE.break_after = 50_000
    with pytest.raises(DownloadError):
        http_engine.download(url, tmp_path, info, connections=4, retries=0)

    part = tmp_path / (info.filename + ".part")
    assert part.stat().st_size == len(PAYLOAD)          # full size already

    meta = http_engine.read_meta(part)
    real = http_engine.part_progress(part, meta)
    assert real < len(PAYLOAD)                          # but not really done

    listed = http_engine.unfinished_downloads(tmp_path)
    assert listed[0]["done"] == real
    assert listed[0]["mode"] == MODE_SEGMENTS


def test_a_split_part_is_never_continued_as_a_stream(server, tmp_path):
    """The unsafe case: full-size part file, resumed by appending."""
    url = f"{server}/big.bin"
    info = http_engine.probe(url)
    part = tmp_path / (info.filename + ".part")

    # A part file that looks complete by size, but is really empty.
    part.write_bytes(b"\x00" * len(PAYLOAD))
    http_engine.write_meta(part, {
        "url": url, "size": len(PAYLOAD), "etag": info.etag,
        "last_modified": info.last_modified, "mode": MODE_SEGMENTS,
        "segments": [[0, len(PAYLOAD) - 1, 0]],
    })

    saved = http_engine.download(url, tmp_path, info, connections=1)
    assert sha(saved) == PAYLOAD_SHA        # not the zeros


def test_an_aria2_part_is_started_again(server, tmp_path):
    url = f"{server}/big.bin"
    info = http_engine.probe(url)
    part = tmp_path / (info.filename + ".part")
    part.write_bytes(b"\x00" * 5000)
    http_engine.write_meta(part, {
        "url": url, "size": len(PAYLOAD), "etag": info.etag,
        "last_modified": info.last_modified, "mode": MODE_ARIA2,
    })

    saved = http_engine.download(url, tmp_path, info, connections=1)
    assert sha(saved) == PAYLOAD_SHA


def test_a_stream_part_still_resumes_after_the_change(server, tmp_path):
    url = f"{server}/big.bin"
    info = http_engine.probe(url)
    part = tmp_path / (info.filename + ".part")
    part.write_bytes(PAYLOAD[:900_000])
    http_engine.write_meta(part, {
        "url": url, "size": len(PAYLOAD), "etag": info.etag,
        "last_modified": info.last_modified, "mode": MODE_STREAM,
    })

    saved = http_engine.download(url, tmp_path, info, connections=1)
    assert sha(saved) == PAYLOAD_SHA
    assert any(r == "bytes=900000-" for r in STATE.range_requests)


def test_old_meta_without_a_mode_is_treated_as_a_stream(server, tmp_path):
    """Part files made by the previous version must still resume."""
    url = f"{server}/big.bin"
    info = http_engine.probe(url)
    part = tmp_path / (info.filename + ".part")
    part.write_bytes(PAYLOAD[:400_000])
    (tmp_path / (info.filename + ".part.meta")).write_text(json.dumps({
        "url": url, "size": len(PAYLOAD), "etag": info.etag,
        "last_modified": info.last_modified,
    }), encoding="utf-8")

    saved = http_engine.download(url, tmp_path, info, connections=1)
    assert sha(saved) == PAYLOAD_SHA
    assert any(r == "bytes=400000-" for r in STATE.range_requests)


def test_broken_segment_meta_starts_over_safely(server, tmp_path):
    url = f"{server}/big.bin"
    info = http_engine.probe(url)
    part = tmp_path / (info.filename + ".part")
    part.write_bytes(b"\x00" * len(PAYLOAD))
    http_engine.write_meta(part, {
        "url": url, "size": len(PAYLOAD), "etag": info.etag,
        "last_modified": info.last_modified, "mode": MODE_SEGMENTS,
        "segments": [[0, 10, 0], [50, 99, 0]],        # a gap: not trustworthy
    })

    saved = http_engine.download(url, tmp_path, info, connections=4)
    assert sha(saved) == PAYLOAD_SHA


def test_progress_never_goes_backwards(server, tmp_path):
    seen = []
    http_engine.download(f"{server}/big.bin", tmp_path, connections=6,
                         on_progress=lambda done, total: seen.append(done))
    assert seen
    assert seen[-1] == len(PAYLOAD)
    assert all(b >= a for a, b in zip(seen, seen[1:]))


# ------------------------------- limiter -------------------------------- #

def test_limiter_with_no_limit_never_waits():
    limiter = RateLimiter(0)
    assert limiter.unlimited
    started = time.monotonic()
    limiter.take(10_000_000)
    assert time.monotonic() - started < 0.05


def test_limiter_slows_things_down():
    limiter = RateLimiter(100_000)      # 100 KB per second
    limiter.take(limiter.capacity)      # empty the bucket first
    started = time.monotonic()
    for _ in range(5):
        limiter.take(20_000)            # 100 KB in total
    elapsed = time.monotonic() - started
    assert elapsed > 0.5


def test_limiter_keeps_chunks_inside_the_bucket():
    limiter = RateLimiter(50_000)
    assert limiter.chunk_size(64 * 1024) <= limiter.capacity
    assert RateLimiter(0).chunk_size(64 * 1024) == 64 * 1024


def test_speed_limit_applies_to_a_real_download(server, tmp_path):
    started = time.monotonic()
    saved = http_engine.download(f"{server}/big.bin", tmp_path,
                                 connections=4, speed_limit=1_500_000)
    elapsed = time.monotonic() - started
    assert sha(saved) == PAYLOAD_SHA
    # 3 MB at 1.5 MB/s cannot finish in well under a second.
    assert elapsed > 0.9
