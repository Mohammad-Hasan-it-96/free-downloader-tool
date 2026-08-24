"""Tests for the queue: checking links, then downloading many at once."""

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fdl import batch
from fdl.batch import KIND_FILE, KIND_MEDIA
from fdl.config import Config
from fdl.history import STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED, History

FILES = {
    "/movie.mp4": b"v" * 30_000,
    "/song.mp3": b"a" * 20_000,
    "/setup.exe": b"p" * 40_000,
    "/book.pdf": b"d" * 10_000,
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = FILES.get(self.path)
        if body is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        start, end = 0, len(body) - 1
        status = 200
        header = self.headers.get("Range")
        if header:
            raw = header.split("=", 1)[1]
            first, _, last = raw.partition("-")
            start = int(first)
            end = int(last) if last else len(body) - 1
            status = 206

        piece = body[start:end + 1]
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", f'"{self.path}"')
        if status == 206:
            self.send_header("Content-Range",
                             f"bytes {start}-{end}/{len(body)}")
        self.send_header("Content-Length", str(len(piece)))
        self.end_headers()
        self.wfile.write(piece)


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def cfg(tmp_path):
    config = Config(tmp_path / "config.json")
    config.base_dir = str(tmp_path / "Downloads")
    return config


# ------------------------------ url lists ------------------------------- #

def test_read_url_list_skips_blanks_and_comments(tmp_path):
    listing = tmp_path / "links.txt"
    listing.write_text("http://a/1\n\n# a comment\n  http://a/2  \n",
                       encoding="utf-8")
    assert batch.read_url_list(listing) == ["http://a/1", "http://a/2"]


def test_dedupe_keeps_order():
    assert batch.dedupe(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]


def test_classify_direct_link_is_a_file():
    assert batch.classify("https://example.com/tool.zip") == KIND_FILE


def test_classify_youtube_is_media():
    assert batch.classify("https://www.youtube.com/watch?v=abc") == KIND_MEDIA


# ------------------------------ preparing ------------------------------- #

def test_prepare_finds_names_sizes_and_folders(server, cfg):
    items = batch.prepare([f"{server}/movie.mp4", f"{server}/song.mp3",
                           f"{server}/setup.exe"], cfg)
    by_name = {item.name: item for item in items}

    assert by_name["movie.mp4"].category == "Videos"
    assert by_name["song.mp3"].category == "Audio"
    assert by_name["setup.exe"].category == "Programs"
    assert by_name["movie.mp4"].size == 30_000
    assert by_name["setup.exe"].dest.name == "Programs"


def test_prepare_marks_a_bad_link_without_stopping_the_rest(server, cfg):
    items = batch.prepare([f"{server}/movie.mp4", f"{server}/nope.zip"], cfg)
    statuses = {item.url.rsplit("/", 1)[1]: item.status for item in items}
    assert statuses["nope.zip"] == STATUS_FAILED
    assert statuses["movie.mp4"] == batch.STATUS_PENDING


def test_prepare_skips_links_already_in_history(server, cfg, tmp_path):
    existing = tmp_path / "movie.mp4"
    existing.write_text("already here")
    history = History(tmp_path / "history.json")
    history.add(f"{server}/movie.mp4", STATUS_DONE, path=existing)

    items = batch.prepare([f"{server}/movie.mp4", f"{server}/song.mp3"],
                          cfg, history)
    by_name = {item.name: item for item in items}
    assert by_name["movie.mp4"].status == STATUS_SKIPPED
    assert "already downloaded" in by_name["movie.mp4"].note
    assert by_name["song.mp3"].status == batch.STATUS_PENDING


def test_prepare_reports_a_part_file_to_resume(server, cfg):
    folder = cfg.folder_for("Videos")
    folder.mkdir(parents=True)
    (folder / "movie.mp4.part").write_bytes(b"v" * 5_000)

    items = batch.prepare([f"{server}/movie.mp4"], cfg)
    assert items[0].resume_from == 5_000


def test_prepare_does_not_probe_media_links(cfg):
    items = batch.prepare(["https://www.youtube.com/watch?v=abc"], cfg)
    assert items[0].kind == KIND_MEDIA
    assert items[0].info is None
    assert items[0].dest.name == "Videos"


# ----------------------------- downloading ------------------------------ #

def test_queue_downloads_every_file_into_the_right_folder(server, cfg,
                                                          tmp_path):
    urls = [f"{server}{path}" for path in FILES]
    items = batch.prepare(urls, cfg)
    summary = batch.run_files(items, cfg, workers=3)

    assert len(summary.done) == 4
    assert not summary.failed

    base = tmp_path / "Downloads"
    assert (base / "Videos" / "movie.mp4").read_bytes() == FILES["/movie.mp4"]
    assert (base / "Audio" / "song.mp3").read_bytes() == FILES["/song.mp3"]
    assert (base / "Programs" / "setup.exe").exists()
    assert (base / "Documents" / "book.pdf").exists()
    assert not list(base.rglob("*.part"))


def test_queue_records_everything_in_history(server, cfg, tmp_path):
    history = History(tmp_path / "history.json")
    items = batch.prepare([f"{server}/song.mp3", f"{server}/book.pdf"], cfg,
                          history)
    batch.run_files(items, cfg, workers=2, history=history)

    assert len(history.entries) == 2
    assert all(e["status"] == STATUS_DONE for e in history.entries)
    assert {e["category"] for e in history.entries} == {"Audio", "Documents"}


def test_queue_keeps_going_when_one_link_fails(server, cfg):
    items = batch.prepare([f"{server}/song.mp3", f"{server}/missing.zip",
                           f"{server}/book.pdf"], cfg)
    summary = batch.run_files(items, cfg, workers=3)

    assert len(summary.done) == 2       # the two good links still finished
    assert len(summary.failed) == 1


def test_queue_does_not_download_skipped_items(server, cfg, tmp_path):
    kept = tmp_path / "song.mp3"
    kept.write_text("old copy")
    history = History(tmp_path / "history.json")
    history.add(f"{server}/song.mp3", STATUS_DONE, path=kept)

    items = batch.prepare([f"{server}/song.mp3", f"{server}/book.pdf"], cfg,
                          history)
    summary = batch.run_files(items, cfg, workers=2, history=history)

    assert len(summary.skipped) == 1
    assert len(summary.done) == 1
    assert kept.read_text() == "old copy"          # untouched
    assert not (cfg.folder_for("Audio") / "song.mp3").exists()


def test_queue_resumes_a_part_file(server, cfg):
    folder = cfg.folder_for("Programs")
    folder.mkdir(parents=True)
    part = folder / "setup.exe.part"
    part.write_bytes(FILES["/setup.exe"][:15_000])
    (folder / "setup.exe.part.meta").write_text(
        '{"url": "%s/setup.exe", "size": 40000, "etag": "\\"/setup.exe\\"", '
        '"last_modified": null}' % server, encoding="utf-8")

    items = batch.prepare([f"{server}/setup.exe"], cfg)
    assert items[0].resume_from == 15_000
    batch.run_files(items, cfg, workers=1)

    saved = folder / "setup.exe"
    assert saved.read_bytes() == FILES["/setup.exe"]


def test_progress_rows_follow_the_item_order(server, cfg):
    """Row numbers must match the plan the user saw."""
    class FakeProgress:
        def __init__(self):
            self.events = []

        def begin(self, index, already=0):
            self.events.append(("begin", index))

        def update(self, index, done, total=None):
            pass

        def finish(self, index, status, message=""):
            self.events.append(("finish", index, status))

    items = batch.prepare([f"{server}/song.mp3", f"{server}/book.pdf"], cfg)
    progress = FakeProgress()
    batch.run_files(items, cfg, progress, workers=1)

    finished = [e for e in progress.events if e[0] == "finish"]
    assert sorted(e[1] for e in finished) == [0, 1]
    assert all(e[2] == STATUS_DONE for e in finished)


def test_sha256_of_queue_results_matches(server, cfg, tmp_path):
    urls = [f"{server}{path}" for path in FILES]
    items = batch.prepare(urls, cfg)
    batch.run_files(items, cfg, workers=4)

    for item in items:
        expected = hashlib.sha256(FILES["/" + item.name]).hexdigest()
        actual = hashlib.sha256(item.path.read_bytes()).hexdigest()
        assert actual == expected, item.name
