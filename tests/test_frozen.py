"""Tests for the single .exe build.

Inside PyInstaller's one-file .exe, `sys.executable` is the .exe, not
python.exe. `ytdlp_engine.run()` starts yt-dlp with
`sys.executable -m yt_dlp`, so that command comes back to our own program.
Without the passthrough below, the .exe answers it by opening a second copy
of its menu, and no video ever downloads.
"""

from pathlib import Path

import pytest

from fdl import app, ytdlp_engine
from fdl.config import default_base_dir, defaults


# --------------------------- finding the call --------------------------- #

def test_the_yt_dlp_call_is_recognised():
    assert ytdlp_engine.wants_passthrough(["-m", "yt_dlp"]) == []


def test_the_yt_dlp_arguments_are_kept():
    argv = ["-m", "yt_dlp", "-F", "https://youtu.be/abc"]
    assert ytdlp_engine.wants_passthrough(argv) == ["-F", "https://youtu.be/abc"]


@pytest.mark.parametrize("argv", [
    [],                                  # a normal double-click
    ["-m"],                              # not enough to be the call
    ["-m", "pip", "install", "yt-dlp"],  # a different module
    ["yt_dlp", "-m"],                    # the right words, the wrong order
    ["--help"],
])
def test_a_normal_start_is_left_alone(argv):
    assert ytdlp_engine.wants_passthrough(argv) is None


def test_the_command_that_run_builds_is_the_one_we_catch(monkeypatch):
    """This is the test that ties the two sides together."""
    seen = {}

    class FakeToolbox:
        ffmpeg_dir = None
        def env(self):
            return {}

    def fake_subprocess_run(command, env=None):
        seen["command"] = command

    monkeypatch.setattr(ytdlp_engine.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(ytdlp_engine.sys, "executable", "FreeDownloader.exe")

    ytdlp_engine.run(["-F", "https://youtu.be/abc"], FakeToolbox())

    command = seen["command"]
    assert command[0] == "FreeDownloader.exe"
    # Everything after the program name must be understood as a yt-dlp call.
    assert ytdlp_engine.wants_passthrough(command[1:]) == [
        "-F", "https://youtu.be/abc"]


# ---------------------------- running yt-dlp ---------------------------- #

def test_the_arguments_reach_yt_dlp(monkeypatch):
    seen = {}
    monkeypatch.setitem(
        __import__("sys").modules, "yt_dlp",
        type("Fake", (), {"main": staticmethod(lambda a: seen.update(args=a))}))
    assert ytdlp_engine.run_passthrough(["--version"]) == 0
    assert seen["args"] == ["--version"]


@pytest.mark.parametrize("raised, expected", [
    (SystemExit(0), 0),
    (SystemExit(1), 1),
    (SystemExit(None), 0),
    (SystemExit("ERROR: something broke"), 1),   # yt-dlp can exit with text
])
def test_the_exit_code_is_passed_on(monkeypatch, raised, expected):
    def boom(_args):
        raise raised

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp",
                        type("Fake", (), {"main": staticmethod(boom)}))
    assert ytdlp_engine.run_passthrough([]) == expected


# ------------------------------ the launcher ---------------------------- #

def test_run_hands_the_call_to_yt_dlp(monkeypatch):
    called = {}
    monkeypatch.setattr(app.sys, "argv",
                        ["FreeDownloader.exe", "-m", "yt_dlp", "--version"])
    monkeypatch.setattr(app, "main", lambda: called.setdefault("menu", True))
    def fake_passthrough(args):
        called["args"] = args
        return 7

    monkeypatch.setattr(ytdlp_engine, "run_passthrough", fake_passthrough)

    with pytest.raises(SystemExit) as stop:
        app.run()

    assert stop.value.code == 7
    assert called["args"] == ["--version"]
    assert "menu" not in called      # the menu must never open here


def test_run_still_opens_the_menu_normally(monkeypatch):
    called = {}
    monkeypatch.setattr(app.sys, "argv", ["FreeDownloader.exe"])
    monkeypatch.setattr(app, "main", lambda: called.setdefault("menu", True))
    app.run()
    assert called["menu"] is True


# --------------------------- no pip in the .exe -------------------------- #

def test_a_frozen_build_never_offers_pip(monkeypatch):
    """pip does not exist inside the .exe, so the offer would be a dead end."""
    monkeypatch.setattr(app, "ytdlp_installed", lambda: False)
    monkeypatch.setattr(app, "is_frozen", lambda: True)
    monkeypatch.setattr(app, "clear_screen", lambda: None)
    monkeypatch.setattr(app, "install_ytdlp",
                        lambda: pytest.fail("pip must not be used in the .exe"))
    monkeypatch.setattr(app, "ask_yes_no", lambda *a, **k: True)

    assert app.ensure_ytdlp() is True


def test_a_normal_python_still_offers_pip(monkeypatch):
    called = {}
    monkeypatch.setattr(app, "ytdlp_installed", lambda: bool(called))
    monkeypatch.setattr(app, "is_frozen", lambda: False)
    monkeypatch.setattr(app, "clear_screen", lambda: None)
    monkeypatch.setattr(app, "install_ytdlp",
                        lambda: called.setdefault("pip", True))
    monkeypatch.setattr(app, "ask_yes_no", lambda *a, **k: True)

    assert app.ensure_ytdlp() is True
    assert called["pip"] is True


def test_is_frozen_is_false_under_plain_python():
    assert app.is_frozen() is False


# ------------------------- a folder everyone has ------------------------- #

def test_the_default_folder_is_the_users_own_downloads():
    assert default_base_dir() == str(Path.home() / "Downloads" / "FreeDownloader")


def test_the_default_folder_does_not_depend_on_a_d_drive(monkeypatch):
    """D: can be a DVD drive, a USB stick, or missing on another computer."""
    monkeypatch.setattr(Path, "exists", lambda self: True)
    with_d = default_base_dir()
    monkeypatch.setattr(Path, "exists", lambda self: False)
    without_d = default_base_dir()
    assert with_d == without_d
    assert "D:" not in defaults()["base_dir"]
