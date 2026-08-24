"""Tests for choosing the right engine for a link."""

import pytest

from fdl import router
from fdl.http_engine import DownloadError, RemoteInfo
from fdl.router import KIND_FILE, KIND_MEDIA


def probe_returning(content_type="application/octet-stream", filename="x.bin",
                    size=1000):
    def fake(url, *args, **kwargs):
        return RemoteInfo(url=url, size=size, resumable=True,
                          filename=filename, content_type=content_type)
    return fake


def probe_failing(message="The file was not found (404)."):
    def fake(url, *args, **kwargs):
        raise DownloadError(message)
    return fake


def never_probe(url, *args, **kwargs):
    raise AssertionError("the server should not have been asked")


# --------------------------- file name first ---------------------------- #

@pytest.mark.parametrize("url", [
    "https://example.com/tool.zip",
    "https://example.com/a/b/setup.exe",
    "https://example.com/book.pdf?token=9",
    "https://example.com/backup.tar.gz",
])
def test_a_known_extension_is_a_file(url):
    route = router.decide(url, probe=probe_returning())
    assert route.kind == KIND_FILE


def test_a_file_extension_wins_over_a_media_site():
    """archive.org has a yt-dlp extractor, but this link is a plain zip."""
    url = "https://archive.org/download/some-item/software.zip"
    route = router.decide(url, probe=probe_returning(filename="software.zip"))
    assert route.kind == KIND_FILE


def test_a_media_file_extension_is_still_a_direct_file():
    """A direct .mp4 is better downloaded as a file: faster and resumable."""
    route = router.decide("https://cdn.example.com/clip.mp4",
                          probe=probe_returning(content_type="video/mp4",
                                                filename="clip.mp4"))
    assert route.kind == KIND_FILE


def test_a_file_link_that_cannot_be_checked_stays_a_file_with_the_error():
    route = router.decide("https://example.com/gone.zip",
                          probe=probe_failing())
    assert route.kind == KIND_FILE
    assert route.info is None
    assert "404" in route.error


# ----------------------------- media sites ------------------------------ #

def test_youtube_is_media_without_asking_the_server():
    route = router.decide("https://www.youtube.com/watch?v=abc",
                          probe=never_probe)
    assert route.kind == KIND_MEDIA
    assert route.info is None
    assert "yt-dlp" in route.reason


def test_a_youtube_short_link_is_media():
    route = router.decide("https://youtu.be/abcdefghijk", probe=never_probe)
    assert route.kind == KIND_MEDIA


# ------------------------- asking the server ---------------------------- #

def test_an_unknown_link_that_serves_a_page_goes_to_ytdlp():
    route = router.decide("https://example.com/watch/12345",
                          probe=probe_returning(content_type="text/html",
                                                filename="12345"))
    assert route.kind == KIND_MEDIA
    assert "web page" in route.reason


def test_an_unknown_link_that_serves_a_file_is_downloaded():
    route = router.decide("https://example.com/get/12345",
                          probe=probe_returning(
                              content_type="application/octet-stream"))
    assert route.kind == KIND_FILE
    assert route.info is not None      # the check is reused, not repeated


def test_html_with_a_charset_is_still_html():
    route = router.decide("https://example.com/page",
                          probe=probe_returning(
                              content_type="text/html; charset=utf-8"))
    assert route.kind == KIND_MEDIA


def test_an_unknown_link_that_cannot_be_checked_goes_to_ytdlp():
    """Some servers block our check but answer yt-dlp fine."""
    route = router.decide("https://example.com/video/1",
                          probe=probe_failing("The server refused (403)."))
    assert route.kind == KIND_MEDIA
    assert "403" in route.error


# ------------------------------- helpers -------------------------------- #

def test_looks_like_a_file_name():
    assert router.looks_like_a_file_name("https://x.com/a.zip") is True
    assert router.looks_like_a_file_name("https://x.com/a.mp4") is True
    assert router.looks_like_a_file_name("https://x.com/watch?v=1") is False
    assert router.looks_like_a_file_name("https://x.com/a.unknownext") is False
    assert router.looks_like_a_file_name("https://x.com/") is False


def test_other_kind_flips():
    assert router.Route(KIND_FILE).other_kind == KIND_MEDIA
    assert router.Route(KIND_MEDIA).other_kind == KIND_FILE


def test_is_media_flag():
    assert router.Route(KIND_MEDIA).is_media is True
    assert router.Route(KIND_FILE).is_media is False


def test_content_type_of_handles_missing_values():
    assert router.content_type_of(None) == ""
    assert router.content_type_of(RemoteInfo(url="x")) == ""
    assert router.content_type_of(
        RemoteInfo(url="x", content_type="TEXT/HTML; charset=x")) == "text/html"
