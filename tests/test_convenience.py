"""Tests for the Phase 6 features: clipboard, proxy, logins, folders, actions."""

import base64
import json
from pathlib import Path

import pytest

from fdl import clipboard, http_engine, postaction
from fdl.config import Config, defaults


# ------------------------------ clipboard ------------------------------- #

@pytest.mark.parametrize("text", [
    "https://example.com/file.zip",
    "http://example.com/",
    "  https://example.com/a b".replace(" b", ""),   # surrounding spaces
])
def test_a_link_is_recognised(text):
    assert clipboard.looks_like_a_link(text) is True


@pytest.mark.parametrize("text", [
    "", "   ", None, "just some words", "ftp://example.com/a.zip",
    "https://example.com/a.zip and more words", "example.com/a.zip",
    "https://",
])
def test_other_text_is_not_a_link(text):
    assert clipboard.looks_like_a_link(text) is False


def test_a_very_long_line_is_refused():
    assert clipboard.looks_like_a_link("https://x.com/" + "a" * 3000) is False


def test_reading_the_clipboard_never_raises():
    result = clipboard.read()
    assert result is None or isinstance(result, str)


# -------------------------- login inside a link ------------------------- #

def test_a_login_in_the_link_becomes_a_header():
    url, header = http_engine.split_login("https://bob:s3cret@x.com/a.zip")
    assert url == "https://x.com/a.zip"
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.split()[1]).decode()
    assert decoded == "bob:s3cret"


def test_the_login_is_taken_out_of_the_address():
    url, _ = http_engine.split_login("https://bob:s3cret@x.com/a.zip?k=1#top")
    assert "bob" not in url and "s3cret" not in url
    assert url == "https://x.com/a.zip?k=1#top"


def test_percent_encoded_logins_are_decoded():
    _, header = http_engine.split_login("https://a%40b.com:p%40ss@x.com/f")
    decoded = base64.b64decode(header.split()[1]).decode()
    assert decoded == "a@b.com:p@ss"


def test_a_normal_link_is_left_alone():
    assert http_engine.split_login("https://x.com/a.zip") == \
        ("https://x.com/a.zip", None)


def test_the_request_carries_the_login_header():
    request = http_engine._request("https://bob:pw@x.com/a.zip")
    assert request.get_header("Authorization")
    assert "bob" not in request.full_url


def test_extra_headers_are_added():
    request = http_engine._request("https://x.com/a.zip",
                                   {"Referer": "https://x.com/"})
    assert request.get_header("Referer") == "https://x.com/"
    assert request.get_header("User-agent")        # still there


# --------------------------------- proxy -------------------------------- #

def test_proxy_blank_follows_the_system():
    message = http_engine.configure_proxy("")
    assert "own proxy" in message
    assert http_engine._forced_opener is None
    http_engine.configure_proxy("")


def test_proxy_none_turns_it_off():
    message = http_engine.configure_proxy("none")
    assert message == "no proxy"
    assert http_engine._forced_opener is not None
    http_engine.configure_proxy("")


def test_proxy_address_is_used():
    assert http_engine.configure_proxy("10.0.0.1:3128") == \
        "http://10.0.0.1:3128"
    assert http_engine.configure_proxy("http://p.local:8080") == \
        "http://p.local:8080"
    http_engine.configure_proxy("")


def test_a_local_address_always_skips_the_proxy():
    """The test server runs on this computer; a proxy cannot reach it."""
    http_engine.configure_proxy("http://10.255.255.1:9")   # unreachable
    try:
        assert http_engine._is_local("127.0.0.1") is True
        assert http_engine._is_local("localhost") is True
        assert http_engine._is_local("example.com") is False
    finally:
        http_engine.configure_proxy("")


# --------------------------- category folders --------------------------- #

def test_a_plain_name_goes_inside_the_base_folder(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "dl")
    assert cfg.folder_for("Videos") == Path(tmp_path / "dl" / "Videos")


def test_a_full_path_is_used_as_written(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "dl")
    other = tmp_path / "other-drive" / "Apps"
    cfg.set_category_folder("Programs", str(other))
    assert cfg.folder_for("Programs") == other
    assert cfg.folder_for("Videos") == Path(tmp_path / "dl" / "Videos")


def test_a_renamed_folder_still_sits_in_the_base(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "dl")
    cfg.set_category_folder("Videos", "Films")
    assert cfg.folder_for("Videos") == Path(tmp_path / "dl" / "Films")


def test_clearing_a_category_folder_restores_the_default(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "dl")
    cfg.set_category_folder("Videos", "Films")
    cfg.set_category_folder("Videos", "")
    assert cfg.folder_for("Videos") == Path(tmp_path / "dl" / "Videos")


def test_an_unknown_category_is_refused(tmp_path):
    cfg = Config(tmp_path / "config.json")
    assert cfg.set_category_folder("Nonsense", "X:/nope") is False


def test_sorting_off_ignores_category_folders(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "dl")
    cfg.sort_by_type = False
    cfg.set_category_folder("Programs", "E:/Apps")
    assert cfg.folder_for("Programs") == Path(tmp_path / "dl")


# ------------------------------- settings ------------------------------- #

def test_new_settings_survive_a_save_and_reload(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config(path)
    cfg.proxy = "http://p:3128"
    cfg.set_header("Referer", "https://x.com/")
    cfg.after_download = postaction.OPEN_FOLDER
    cfg.set_category_folder("Programs", "E:/Apps")
    ok, why = cfg.save()
    assert ok, why

    again = Config.load(path)
    assert again.proxy == "http://p:3128"
    assert again.headers == {"Referer": "https://x.com/"}
    assert again.after_download == postaction.OPEN_FOLDER
    assert again.data["category_folders"]["Programs"] == "E:/Apps"


def test_bad_new_settings_fall_back(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "version": 2,
        "proxy": 1234,
        "headers": "not a dict",
        "after_download": "explode",
    }), encoding="utf-8")

    cfg = Config.load(path)
    assert cfg.proxy == defaults()["proxy"]
    assert cfg.headers == {}
    assert cfg.after_download == "nothing"


def test_headers_with_odd_values_are_cleaned(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "version": 2,
        "headers": {"Good": "yes", "": "no name", "Number": 7,
                    "Nested": {"a": 1}},
    }), encoding="utf-8")

    cfg = Config.load(path)
    assert cfg.headers == {"Good": "yes", "Number": "7"}


def test_removing_a_header(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.set_header("Referer", "https://x.com/")
    assert cfg.remove_header("Referer") is True
    assert cfg.remove_header("Referer") is False
    assert cfg.headers == {}


def test_an_empty_header_name_is_refused(tmp_path):
    cfg = Config(tmp_path / "config.json")
    assert cfg.set_header("   ", "value") is False
    assert cfg.headers == {}


# ---------------------------- after download ---------------------------- #

def test_every_choice_has_a_description():
    for key in (postaction.NOTHING, postaction.OPEN_FOLDER, postaction.BEEP,
                postaction.BOTH):
        assert postaction.CHOICES[key]


def test_nothing_really_does_nothing(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(postaction, "open_folder", lambda p: called.append(p))
    monkeypatch.setattr(postaction, "beep", lambda: called.append("beep"))
    postaction.run(postaction.NOTHING, tmp_path)
    assert called == []


def test_both_opens_and_beeps(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(postaction, "open_folder", lambda p: called.append("open"))
    monkeypatch.setattr(postaction, "beep", lambda: called.append("beep"))
    postaction.run(postaction.BOTH, tmp_path)
    assert called == ["open", "beep"]


def test_an_unknown_action_does_nothing(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(postaction, "open_folder", lambda p: called.append("open"))
    monkeypatch.setattr(postaction, "beep", lambda: called.append("beep"))
    postaction.run("something-else", tmp_path)
    assert called == []


def test_open_folder_never_raises_on_a_missing_path(tmp_path, monkeypatch):
    monkeypatch.setattr(postaction.subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    assert postaction.open_folder(tmp_path / "gone" / "file.zip") is False


def test_an_empty_clipboard_is_not_the_same_as_no_clipboard(monkeypatch):
    """An empty clipboard must not read as 'this computer has no clipboard'."""
    monkeypatch.setattr(clipboard, "_read_windows", lambda: "")
    monkeypatch.setattr(clipboard, "_read_unix", lambda: "")
    monkeypatch.setattr(clipboard, "_read_tkinter", lambda: None)
    assert clipboard.read() == ""
    assert clipboard.available() is True


def test_no_clipboard_at_all_is_reported(monkeypatch):
    monkeypatch.setattr(clipboard, "_read_windows", lambda: None)
    monkeypatch.setattr(clipboard, "_read_unix", lambda: None)
    monkeypatch.setattr(clipboard, "_read_tkinter", lambda: None)
    assert clipboard.read() is None
    assert clipboard.available() is False
