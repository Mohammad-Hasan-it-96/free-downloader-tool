"""Tests for the screen a brand new user sees.

The first run must end with a saved config.json and a folder that exists.
If it does not, the user meets an error on their very first download.
"""

import pytest

from fdl import app
from fdl.config import Config


@pytest.fixture
def quiet(monkeypatch):
    """Silence the screen, so the tests read the values, not the output."""
    monkeypatch.setattr(app, "clear_screen", lambda: None)
    monkeypatch.setattr(app, "pause", lambda: None)


def answers(monkeypatch, *replies):
    """Feed the given answers to input(), in order."""
    queue = list(replies)
    monkeypatch.setattr("builtins.input", lambda _prompt="": queue.pop(0))
    return queue


def fresh_config(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "Downloads" / "FreeDownloader")
    return cfg


def test_pressing_enter_keeps_the_suggested_folder(quiet, monkeypatch, tmp_path):
    cfg = fresh_config(tmp_path)
    suggested = cfg.base_dir
    answers(monkeypatch, "")

    app.welcome(cfg)

    assert cfg.base_dir == suggested
    assert (tmp_path / "Downloads" / "FreeDownloader").is_dir()


def test_a_typed_folder_is_used(quiet, monkeypatch, tmp_path):
    cfg = fresh_config(tmp_path)
    chosen = tmp_path / "Elsewhere"
    answers(monkeypatch, str(chosen))

    app.welcome(cfg)

    assert cfg.base_dir == str(chosen)
    assert chosen.is_dir()


def test_quotes_around_a_pasted_folder_are_removed(quiet, monkeypatch, tmp_path):
    """Windows Explorer's "Copy as path" wraps the path in quotes."""
    cfg = fresh_config(tmp_path)
    chosen = tmp_path / "Pasted"
    answers(monkeypatch, '"' + str(chosen) + '"')

    app.welcome(cfg)

    assert cfg.base_dir == str(chosen)


def test_the_settings_are_saved(quiet, monkeypatch, tmp_path):
    cfg = fresh_config(tmp_path)
    answers(monkeypatch, "")

    app.welcome(cfg)

    assert cfg.path.exists()
    assert Config.load(cfg.path).base_dir == cfg.base_dir


def test_a_bad_folder_is_asked_again(quiet, monkeypatch, tmp_path):
    """A typing mistake must not end the first run with a broken folder."""
    cfg = fresh_config(tmp_path)
    good = tmp_path / "Good"
    calls = []

    real_ensure = app.ensure_folder

    def fake_ensure(path):
        calls.append(str(path))
        if str(path).endswith("Bad"):
            return False, "no permission to write here"
        return real_ensure(path)

    monkeypatch.setattr(app, "ensure_folder", fake_ensure)
    answers(monkeypatch, str(tmp_path / "Bad"), str(good))

    app.welcome(cfg)

    assert len(calls) == 2
    assert cfg.base_dir == str(good)
    assert good.is_dir()


def test_a_bare_name_becomes_a_folder_in_the_home_folder(quiet, monkeypatch,
                                                         tmp_path):
    """"Movies" typed alone must not depend on where the app was started."""
    from pathlib import Path

    cfg = fresh_config(tmp_path)
    made = []
    monkeypatch.setattr(app, "ensure_folder",
                        lambda p: (made.append(str(p)), (True, ""))[1])
    answers(monkeypatch, "Movies")

    app.welcome(cfg)

    assert cfg.base_dir == str(Path.home() / "Movies")
    assert made == [str(Path.home() / "Movies")]


def test_a_full_path_is_used_as_typed(quiet, monkeypatch, tmp_path):
    cfg = fresh_config(tmp_path)
    chosen = tmp_path / "Full" / "Path"
    answers(monkeypatch, str(chosen))

    app.welcome(cfg)

    assert cfg.base_dir == str(chosen)


def test_it_gives_up_politely_after_three_tries(quiet, monkeypatch, tmp_path):
    """It must never loop for ever, whatever the user types."""
    cfg = fresh_config(tmp_path)
    monkeypatch.setattr(app, "ensure_folder", lambda _p: (False, "nope"))
    answers(monkeypatch, "a", "b", "c")

    app.welcome(cfg)          # must return, not hang

    assert cfg.path.exists()  # the settings are still written


def test_a_first_run_is_a_missing_config_file(tmp_path):
    """This is how main() decides to show the welcome screen."""
    path = tmp_path / "config.json"
    assert path.exists() is False
    Config(path).save()
    assert path.exists() is True
