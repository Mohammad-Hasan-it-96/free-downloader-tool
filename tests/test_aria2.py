"""Tests for the aria2c wrapper.

aria2c itself may not be installed, so the real program is replaced by a
small fake in most tests. What matters here is the command we build and the
rule that an aria2c part file is never continued by the wrong method.
"""

import json
import subprocess
from pathlib import Path

import pytest

from fdl import aria2_engine, http_engine
from fdl.http_engine import MODE_ARIA2, MODE_STREAM, DownloadError, RemoteInfo


class FakeToolbox:
    def __init__(self, folder=None):
        self.aria2c_dir = str(folder) if folder else None


def fake_program(tmp_path):
    """A folder holding a file named like the aria2c program."""
    folder = tmp_path / "bin"
    folder.mkdir()
    for candidate in ("aria2c.exe", "aria2c"):
        (folder / candidate).write_text("fake")
    return folder


def info_for(url="http://x/big.zip", size=50_000_000, resumable=True):
    return RemoteInfo(url=url, size=size, resumable=resumable, etag='"v1"',
                      filename="big.zip")


# ------------------------------ when to use ----------------------------- #

def test_not_used_when_aria2c_is_missing():
    assert aria2_engine.is_useful_for(info_for(), FakeToolbox()) is False


def test_not_used_when_turned_off(tmp_path):
    toolbox = FakeToolbox(fake_program(tmp_path))
    assert aria2_engine.is_useful_for(info_for(), toolbox, enabled=False) \
        is False


def test_not_used_for_small_files(tmp_path):
    toolbox = FakeToolbox(fake_program(tmp_path))
    assert aria2_engine.is_useful_for(info_for(size=100_000), toolbox) is False


def test_not_used_when_the_server_refuses_ranges(tmp_path):
    toolbox = FakeToolbox(fake_program(tmp_path))
    assert aria2_engine.is_useful_for(info_for(resumable=False), toolbox) \
        is False


def test_used_for_a_big_resumable_file(tmp_path):
    toolbox = FakeToolbox(fake_program(tmp_path))
    assert aria2_engine.is_useful_for(info_for(), toolbox) is True


# ------------------------------ the command ----------------------------- #

def test_command_has_the_important_flags():
    command = aria2_engine.build_command(
        "aria2c", "http://x/big.zip", "/downloads", "big.zip.part",
        connections=16, retries=5)

    assert "--dir=/downloads" in command
    assert "--out=big.zip.part" in command
    assert "--continue=true" in command
    assert "--max-connection-per-server=16" in command
    assert "--split=16" in command
    assert "--auto-file-renaming=false" in command
    assert command[-1] == "http://x/big.zip"


def test_command_adds_the_speed_limit():
    command = aria2_engine.build_command(
        "aria2c", "http://x/a.zip", "/d", "a.zip.part", connections=8,
        speed_limit_kb=500)
    assert "--max-overall-download-limit=500K" in command


def test_command_leaves_out_the_limit_when_it_is_zero():
    command = aria2_engine.build_command(
        "aria2c", "http://x/a.zip", "/d", "a.zip.part", connections=8,
        speed_limit_kb=0)
    assert not any(c.startswith("--max-overall-download-limit") for c in command)


def test_command_passes_extra_headers():
    command = aria2_engine.build_command(
        "aria2c", "http://x/a.zip", "/d", "a.zip.part", connections=8,
        extra_headers={"Referer": "http://x/"})
    assert "--header=Referer: http://x/" in command


# --------------------------- part file safety --------------------------- #

def test_a_part_from_another_engine_is_thrown_away(tmp_path, monkeypatch):
    """A stream part cannot be continued by aria2c, and the other way round."""
    dest = tmp_path / "dl"
    dest.mkdir()
    part = dest / "big.zip.part"
    part.write_bytes(b"x" * 1000)
    http_engine.write_meta(part, {
        "url": "http://x/big.zip", "size": 50_000_000, "etag": '"v1"',
        "last_modified": None, "mode": MODE_STREAM,
    })

    aria2_engine._clean_unusable_part(part, "http://x/big.zip", info_for())
    assert not part.exists()
    assert not http_engine.meta_path(part).exists()


def test_an_aria2_part_without_its_control_file_is_thrown_away(tmp_path):
    dest = tmp_path / "dl"
    dest.mkdir()
    part = dest / "big.zip.part"
    part.write_bytes(b"x" * 1000)
    http_engine.write_meta(part, {
        "url": "http://x/big.zip", "size": 50_000_000, "etag": '"v1"',
        "last_modified": None, "mode": MODE_ARIA2,
    })
    # No big.zip.part.aria2 file, so the bytes cannot be trusted.
    aria2_engine._clean_unusable_part(part, "http://x/big.zip", info_for())
    assert not part.exists()


def test_an_aria2_part_with_its_control_file_is_kept(tmp_path):
    dest = tmp_path / "dl"
    dest.mkdir()
    part = dest / "big.zip.part"
    part.write_bytes(b"x" * 1000)
    aria2_engine.control_file(part).write_bytes(b"control")
    http_engine.write_meta(part, {
        "url": "http://x/big.zip", "size": 50_000_000, "etag": '"v1"',
        "last_modified": None, "mode": MODE_ARIA2,
    })

    aria2_engine._clean_unusable_part(part, "http://x/big.zip", info_for())
    assert part.exists()
    assert part.stat().st_size == 1000


def test_a_part_for_a_different_file_is_thrown_away(tmp_path):
    dest = tmp_path / "dl"
    dest.mkdir()
    part = dest / "big.zip.part"
    part.write_bytes(b"x" * 1000)
    aria2_engine.control_file(part).write_bytes(b"control")
    http_engine.write_meta(part, {
        "url": "http://x/big.zip", "size": 50_000_000, "etag": '"OLD"',
        "last_modified": None, "mode": MODE_ARIA2,
    })

    aria2_engine._clean_unusable_part(part, "http://x/big.zip", info_for())
    assert not part.exists()


# ------------------------------ the run --------------------------------- #

def test_a_finished_run_renames_the_part_file(tmp_path, monkeypatch):
    dest = tmp_path / "dl"
    program_dir = fake_program(tmp_path)
    toolbox = FakeToolbox(program_dir)
    info = info_for(size=2 * 1024 * 1024)

    def fake_run(command, *args, **kwargs):
        # Pretend aria2c wrote the whole file.
        out = Path([c for c in command if c.startswith("--dir=")][0][6:])
        name = [c for c in command if c.startswith("--out=")][0][6:]
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(b"z" * info.size)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    saved = aria2_engine.download("http://x/big.zip", dest, info,
                                  toolbox=toolbox)

    assert saved.name == "big.zip"
    assert saved.stat().st_size == info.size
    assert not (dest / "big.zip.part").exists()
    assert not http_engine.meta_path(dest / "big.zip.part").exists()


def test_a_short_file_is_reported_and_the_part_is_kept(tmp_path, monkeypatch):
    dest = tmp_path / "dl"
    toolbox = FakeToolbox(fake_program(tmp_path))
    info = info_for(size=2 * 1024 * 1024)

    def fake_run(command, *args, **kwargs):
        out = Path([c for c in command if c.startswith("--dir=")][0][6:])
        name = [c for c in command if c.startswith("--out=")][0][6:]
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(b"z" * 100)      # too short
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(DownloadError) as err:
        aria2_engine.download("http://x/big.zip", dest, info, toolbox=toolbox)

    assert "incomplete" in str(err.value)
    assert (dest / "big.zip.part").exists()


def test_a_failed_run_keeps_the_part_file(tmp_path, monkeypatch):
    dest = tmp_path / "dl"
    toolbox = FakeToolbox(fake_program(tmp_path))
    info = info_for(size=2 * 1024 * 1024)

    def fake_run(command, *args, **kwargs):
        out = Path([c for c in command if c.startswith("--dir=")][0][6:])
        name = [c for c in command if c.startswith("--out=")][0][6:]
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(b"z" * 500)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(DownloadError):
        aria2_engine.download("http://x/big.zip", dest, info, toolbox=toolbox)
    assert (dest / "big.zip.part").exists()


def test_the_meta_file_marks_the_mode_before_running(tmp_path, monkeypatch):
    dest = tmp_path / "dl"
    toolbox = FakeToolbox(fake_program(tmp_path))
    info = info_for(size=2 * 1024 * 1024)
    seen = {}

    def fake_run(command, *args, **kwargs):
        part = dest / "big.zip.part"
        seen["meta"] = json.loads(
            http_engine.meta_path(part).read_text(encoding="utf-8"))
        part.write_bytes(b"z" * info.size)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    aria2_engine.download("http://x/big.zip", dest, info, toolbox=toolbox)

    assert seen["meta"]["mode"] == MODE_ARIA2
    assert seen["meta"]["url"] == "http://x/big.zip"


def test_download_without_aria2c_gives_a_clear_error(tmp_path):
    with pytest.raises(DownloadError) as err:
        aria2_engine.download("http://x/big.zip", tmp_path, info_for(),
                              toolbox=FakeToolbox())
    assert "not installed" in str(err.value)
