"""Tests for the winget helper that installs ffmpeg, deno, and aria2c."""

import subprocess

import pytest

from fdl import installer


class FakeToolbox:
    def __init__(self, ffmpeg=None, deno=None, aria2c=None):
        self.ffmpeg_dir = ffmpeg
        self.deno_dir = deno
        self.aria2c_dir = aria2c


def result(code):
    return subprocess.CompletedProcess(args=[], returncode=code)


# ------------------------------ the command ------------------------------ #

def test_the_command_names_the_package():
    command = installer.build_command("Gyan.FFmpeg")
    assert command[:2] == ["winget", "install"]
    assert "Gyan.FFmpeg" in command


def test_the_command_never_stops_to_ask():
    """winget waits for a licence answer unless it is told not to."""
    command = installer.build_command("aria2.aria2")
    assert "--accept-package-agreements" in command
    assert "--accept-source-agreements" in command


def test_the_command_asks_for_an_exact_id():
    """Without --exact, winget can install a different, similar package."""
    assert "--exact" in installer.build_command("DenoLand.Deno")


@pytest.mark.parametrize("name, package", [
    ("ffmpeg", "Gyan.FFmpeg"),
    ("deno", "DenoLand.Deno"),
    ("aria2c", "aria2.aria2"),
])
def test_every_program_has_an_id(name, package):
    ids = {item[0]: item[1] for item in installer.PACKAGES}
    assert ids[name] == package


# ------------------------------ what is missing -------------------------- #

def test_nothing_is_missing_when_all_three_are_found():
    toolbox = FakeToolbox(ffmpeg="/a", deno="/b", aria2c="/c")
    assert installer.missing(toolbox) == []


def test_only_the_missing_ones_are_listed():
    toolbox = FakeToolbox(ffmpeg="/a", deno=None, aria2c=None)
    names = [item[0] for item in installer.missing(toolbox)]
    assert names == ["deno", "aria2c"]


def test_all_three_are_listed_on_a_fresh_computer():
    names = [item[0] for item in installer.missing(FakeToolbox())]
    assert names == ["ffmpeg", "deno", "aria2c"]


# ------------------------------- installing ------------------------------ #

def test_a_good_install_reports_success():
    ok, why = installer.install("Gyan.FFmpeg", runner=lambda cmd: result(0))
    assert ok is True
    assert why == ""


def test_a_failed_install_explains_itself():
    ok, why = installer.install("Gyan.FFmpeg", runner=lambda cmd: result(3))
    assert ok is False
    assert "3" in why


def test_a_missing_winget_does_not_crash():
    def runner(_cmd):
        raise OSError("winget not found")

    ok, why = installer.install("Gyan.FFmpeg", runner=runner)
    assert ok is False
    assert "winget not found" in why


def test_the_runner_gets_the_built_command():
    seen = {}

    def runner(command):
        seen["command"] = command
        return result(0)

    installer.install("DenoLand.Deno", runner=runner)
    assert seen["command"] == installer.build_command("DenoLand.Deno")


# ------------------------------ availability ----------------------------- #

def test_winget_is_never_used_outside_windows(monkeypatch):
    monkeypatch.setattr(installer.os, "name", "posix")
    monkeypatch.setattr(installer.shutil, "which", lambda _name: "/usr/bin/winget")
    assert installer.winget_available() is False


def test_winget_needs_to_be_on_the_path(monkeypatch):
    monkeypatch.setattr(installer.os, "name", "nt")
    monkeypatch.setattr(installer.shutil, "which", lambda _name: None)
    assert installer.winget_available() is False


def test_winget_is_used_when_it_is_there(monkeypatch):
    monkeypatch.setattr(installer.os, "name", "nt")
    monkeypatch.setattr(installer.shutil, "which",
                        lambda _name: r"C:\Windows\winget.exe")
    assert installer.winget_available() is True
