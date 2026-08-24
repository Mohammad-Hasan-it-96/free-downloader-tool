"""Tests for where the settings, history, and log are kept.

The important rule: after `pip install`, the tool must never write into
Python's own folders.
"""

import importlib
import os
from pathlib import Path

import pytest

from fdl import paths


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    monkeypatch.delenv("FDL_HOME", raising=False)
    yield


def test_fdl_home_wins_over_everything(monkeypatch, tmp_path):
    monkeypatch.setenv("FDL_HOME", str(tmp_path / "somewhere"))
    assert paths.data_dir() == tmp_path / "somewhere"
    assert paths.config_path() == tmp_path / "somewhere" / "config.json"
    assert paths.history_path() == tmp_path / "somewhere" / "history.json"
    assert paths.log_path() == tmp_path / "somewhere" / "fdl.log"


def test_fdl_home_expands_a_home_shortcut(monkeypatch):
    monkeypatch.setenv("FDL_HOME", "~/fdl-data")
    assert paths.data_dir() == Path.home() / "fdl-data"


def test_a_downloaded_copy_keeps_its_files_next_to_the_app(monkeypatch):
    """Double-clicking the .bat must behave exactly as before."""
    monkeypatch.setattr(paths, "running_from_source", lambda: True)
    assert paths.data_dir() == paths.SOURCE_ROOT


def test_an_installed_package_uses_the_user_folder(monkeypatch):
    monkeypatch.setattr(paths, "running_from_source", lambda: False)
    folder = paths.data_dir()
    assert folder != paths.SOURCE_ROOT
    assert folder == paths.user_data_dir()


def test_an_installed_package_never_writes_into_python(monkeypatch):
    """The whole point: site-packages must stay untouched."""
    monkeypatch.setattr(paths, "running_from_source", lambda: False)
    folder = str(paths.data_dir()).lower()
    assert "site-packages" not in folder
    assert "dist-packages" not in folder


def test_this_checkout_counts_as_source():
    """This repository has pyproject.toml, so it is a downloaded copy."""
    assert paths.running_from_source() is True


@pytest.mark.skipif(os.name != "nt", reason="Windows folder rules")
def test_windows_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert paths.user_data_dir() == tmp_path / "Roaming" / paths.APP_NAME


@pytest.mark.skipif(os.name == "nt", reason="Linux and macOS folder rules")
def test_xdg_config_home_is_used(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    if paths.sys.platform == "darwin":
        pytest.skip("macOS uses Application Support")
    assert paths.user_data_dir() == tmp_path / "cfg" / paths.UNIX_NAME


def test_the_app_reads_its_paths_from_this_module():
    app = importlib.import_module("fdl.app")
    assert app.CONFIG_PATH == paths.config_path()
    assert app.HISTORY_PATH == paths.history_path()
    assert app.LOG_PATH == paths.log_path()
