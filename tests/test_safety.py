"""Tests for the checks that run before and after a download."""

import hashlib

import pytest

from fdl import checksum, log, safety
from fdl.http_engine import RemoteInfo


def info_for(filename="tool.zip", content_type="application/octet-stream",
             size=1000):
    return RemoteInfo(url="http://x/" + filename, size=size, resumable=True,
                      filename=filename, content_type=content_type)


# ------------------------------ free space ------------------------------ #

def test_free_space_of_a_real_folder(tmp_path):
    assert safety.free_space(tmp_path) > 0


def test_free_space_walks_up_to_a_folder_that_exists(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "not-made-yet"
    assert safety.free_space(deep) > 0


def test_space_check_passes_for_a_small_file(tmp_path):
    ok, message = safety.check_space(tmp_path, 1000)
    assert ok and message == ""


def test_space_check_fails_for_an_impossible_size(tmp_path):
    ok, message = safety.check_space(tmp_path, 10 ** 18)
    assert not ok
    assert "Not enough free space" in message


def test_space_check_is_skipped_when_the_size_is_unknown(tmp_path):
    ok, _ = safety.check_space(tmp_path, None)
    assert ok


def test_space_check_keeps_a_margin(tmp_path, monkeypatch):
    """Filling the disk to the last byte must not be allowed."""
    monkeypatch.setattr(safety, "free_space", lambda path: 100 * 1024 * 1024)
    ok, _ = safety.check_space(tmp_path, 99 * 1024 * 1024)
    assert not ok                       # only 1 MB would be left
    ok, _ = safety.check_space(tmp_path, 10 * 1024 * 1024)
    assert ok


# --------------------------- insecure programs -------------------------- #

def test_a_program_over_plain_http_is_flagged():
    assert safety.is_insecure_program("http://x.com/setup.exe",
                                      "Programs") is True


def test_a_program_over_https_is_fine():
    assert safety.is_insecure_program("https://x.com/setup.exe",
                                      "Programs") is False


def test_other_types_over_http_are_not_flagged():
    assert safety.is_insecure_program("http://x.com/a.pdf",
                                      "Documents") is False


# ---------------------------- login pages ------------------------------- #

def test_a_zip_that_answers_with_html_is_flagged():
    assert safety.looks_like_a_login_page(
        info_for("tool.zip", "text/html")) is True


def test_a_real_html_file_is_not_flagged():
    assert safety.looks_like_a_login_page(
        info_for("page.html", "text/html")) is False


def test_a_normal_file_is_not_flagged():
    assert safety.looks_like_a_login_page(info_for()) is False


def test_html_with_a_charset_still_counts():
    assert safety.looks_like_a_login_page(
        info_for("tool.zip", "text/html; charset=utf-8")) is True


def test_the_message_names_the_file():
    message = safety.login_page_message(info_for("tool.zip", "text/html"))
    assert "tool.zip" in message
    assert "login" in message


# ------------------------------ checksums ------------------------------- #

@pytest.mark.parametrize("text,algorithm", [
    ("d41d8cd98f00b204e9800998ecf8427e", "md5"),
    ("da39a3ee5e6b4b0d3255bfef95601890afd80709", "sha1"),
    ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
     "sha256"),
])
def test_plain_hex_is_recognised_by_its_length(text, algorithm):
    assert checksum.parse(text) == (algorithm, text)


def test_a_prefixed_checksum_is_read():
    value = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert checksum.parse(f"sha256:{value}") == ("sha256", value)
    assert checksum.parse(f"SHA-256 = {value}") == ("sha256", value)


def test_a_checksum_followed_by_a_file_name_is_read():
    value = "d41d8cd98f00b204e9800998ecf8427e"
    assert checksum.parse(f"{value}  program.zip") == ("md5", value)


def test_upper_case_is_accepted():
    value = "D41D8CD98F00B204E9800998ECF8427E"
    assert checksum.parse(value) == ("md5", value.lower())


@pytest.mark.parametrize("text", [
    "", "   ", "not a checksum", "abcd", "zzzz8cd98f00b204e9800998ecf8427e",
    "sha256:abcd",
])
def test_rubbish_is_refused(text):
    assert checksum.parse(text) is None


def test_compute_matches_hashlib(tmp_path):
    path = tmp_path / "a.bin"
    payload = b"hello world" * 1000
    path.write_bytes(payload)
    assert checksum.compute(path, "sha256") == \
        hashlib.sha256(payload).hexdigest()


def test_verify_says_ok_for_a_matching_file(tmp_path):
    path = tmp_path / "a.bin"
    path.write_bytes(b"data")
    expected = hashlib.sha256(b"data").hexdigest()

    result = checksum.verify(path, expected)
    assert result.ok
    assert bool(result) is True
    assert result.algorithm == "sha256"


def test_verify_catches_a_changed_file(tmp_path):
    path = tmp_path / "a.bin"
    path.write_bytes(b"data")
    wrong = hashlib.sha256(b"other data").hexdigest()

    result = checksum.verify(path, wrong)
    assert not result.ok
    assert result.expected == wrong
    assert result.actual == hashlib.sha256(b"data").hexdigest()


def test_verify_explains_an_unreadable_checksum(tmp_path):
    path = tmp_path / "a.bin"
    path.write_bytes(b"data")
    result = checksum.verify(path, "hello")
    assert not result.ok
    assert "not a checksum" in result.error


def test_verify_reports_a_missing_file(tmp_path):
    result = checksum.verify(tmp_path / "gone.bin",
                             hashlib.md5(b"x").hexdigest())
    assert not result.ok
    assert result.error


def test_compute_reports_progress(tmp_path):
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * (3 * checksum.CHUNK_SIZE))
    seen = []
    checksum.compute(path, "sha256", on_progress=seen.append)
    assert seen and seen[-1] == 3 * checksum.CHUNK_SIZE


# -------------------------------- the log ------------------------------- #

def test_log_writes_lines(tmp_path):
    path = tmp_path / "fdl.log"
    log.setup(path)
    log.info("a test line")
    log.warning("something odd")
    text = path.read_text(encoding="utf-8")
    assert "a test line" in text
    assert "something odd" in text
    assert "WARNING" in text


def test_log_never_stops_the_app_when_it_cannot_be_written(tmp_path):
    blocked = tmp_path / "a-file"
    blocked.write_text("not a folder")
    log.setup(blocked / "inside" / "fdl.log")   # impossible path
    log.info("this must not raise")


def test_redact_hides_a_token():
    url = "https://x.com/file.zip?token=abc123&name=ok"
    cleaned = log.redact(url)
    assert "abc123" not in cleaned
    assert "name=ok" in cleaned


def test_redact_hides_a_password_in_the_host():
    cleaned = log.redact("https://user:secret@x.com/a.zip")
    assert "secret" not in cleaned
    assert "x.com/a.zip" in cleaned


def test_redact_leaves_a_normal_link_alone():
    url = "https://x.com/a/b/file.zip"
    assert log.redact(url) == url


def test_redact_handles_empty_input():
    assert log.redact("") == ""
    assert log.redact(None) == ""


def test_tail_returns_the_last_lines(tmp_path):
    path = tmp_path / "fdl.log"
    path.write_text("\n".join(f"line {i}" for i in range(100)),
                    encoding="utf-8")
    lines = log.tail(path, 5)
    assert len(lines) == 5
    assert lines[-1] == "line 99"


def test_tail_of_a_missing_file_is_empty(tmp_path):
    assert log.tail(tmp_path / "nothing.log") == []
