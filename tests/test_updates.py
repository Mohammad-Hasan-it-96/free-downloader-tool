"""Tests for the daily "is there a newer version?" check.

The rule this file protects: a failed check is never an error. No internet,
a proxy in the way, a rate limit, or no release at all must all end as
"no news", with the menu opening normally.
"""

import io
import json

import pytest

from fdl import updates
from fdl.config import Config


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def opener_returning(payload):
    def opener(_request, timeout=None):
        return FakeResponse(json.dumps(payload).encode("utf-8"))
    return opener


def opener_raising(error):
    def opener(_request, timeout=None):
        raise error
    return opener


# ----------------------------- reading versions ------------------------- #

@pytest.mark.parametrize("text, expected", [
    ("v2.1.0", (2, 1, 0)),
    ("2.1.0", (2, 1, 0)),
    ("v2.1", (2, 1, 0)),          # padded, so '2.1' equals '2.1.0'
    ("v10.0.2", (10, 0, 2)),
    ("v2.1.0-beta", (2, 1, 0)),
    ("", ()),
    (None, ()),
    ("nightly", ()),
])
def test_parse_version(text, expected):
    assert updates.parse_version(text) == expected


@pytest.mark.parametrize("found, current, expected", [
    ("v2.2.0", "2.1.0", True),
    ("v2.1.1", "2.1.0", True),
    ("v10.0.0", "9.9.9", True),    # numbers, not text order
    ("v2.1.0", "2.1.0", False),
    ("v2.0.0", "2.1.0", False),
    ("v2.1", "2.1.0", False),      # the same version, written shorter
    ("nightly", "2.1.0", False),   # unreadable means no news
    ("v2.2.0", "", False),
])
def test_is_newer(found, current, expected):
    assert updates.is_newer(found, current) is expected


# ------------------------------- once a day ----------------------------- #

def test_due_when_never_checked():
    assert updates.due_today("", today="2026-08-26") is True


def test_due_when_checked_before():
    assert updates.due_today("2026-08-25", today="2026-08-26") is True


def test_not_due_twice_in_one_day():
    assert updates.due_today("2026-08-26", today="2026-08-26") is False


# ------------------------------ asking GitHub --------------------------- #

def test_the_tag_is_read():
    tag = updates.fetch_latest_tag(opener_returning({"tag_name": "v9.9.9"}))
    assert tag == "v9.9.9"


@pytest.mark.parametrize("problem", [
    OSError("no route to host"),
    ValueError("not json"),
    TimeoutError("too slow"),
])
def test_a_broken_answer_is_just_no_news(problem):
    assert updates.fetch_latest_tag(opener_raising(problem)) is None


def test_an_answer_without_a_tag_is_no_news():
    assert updates.fetch_latest_tag(opener_returning({"message": "Not Found"})) is None


def test_a_list_instead_of_an_object_is_no_news():
    assert updates.fetch_latest_tag(opener_returning([1, 2, 3])) is None


# -------------------------------- the check ----------------------------- #

def make_config(tmp_path, **values):
    cfg = Config(tmp_path / "config.json")
    for key, value in values.items():
        setattr(cfg, key, value)
    return cfg


def test_nothing_happens_when_the_setting_is_off(tmp_path):
    cfg = make_config(tmp_path, check_updates=False)
    # The opener would raise if it were used at all.
    assert updates.check(cfg, opener_raising(AssertionError("must not ask"))) == ""
    assert cfg.last_update_check == ""


def test_a_newer_version_is_reported(tmp_path):
    cfg = make_config(tmp_path)
    found = updates.check(cfg, opener_returning({"tag_name": "v99.0.0"}),
                          today="2026-08-26")
    assert found == "v99.0.0"


def test_the_same_version_is_not_reported(tmp_path):
    cfg = make_config(tmp_path)
    tag = "v" + updates.__version__
    assert updates.check(cfg, opener_returning({"tag_name": tag}),
                         today="2026-08-26") == ""


def test_the_day_is_written_down(tmp_path):
    cfg = make_config(tmp_path)
    updates.check(cfg, opener_returning({"tag_name": "v99.0.0"}),
                  today="2026-08-26")
    assert cfg.last_update_check == "2026-08-26"
    assert Config.load(cfg.path).last_update_check == "2026-08-26"


def test_the_second_look_on_the_same_day_does_nothing(tmp_path):
    cfg = make_config(tmp_path)
    updates.check(cfg, opener_returning({"tag_name": "v99.0.0"}),
                  today="2026-08-26")
    again = updates.check(cfg, opener_raising(AssertionError("must not ask")),
                          today="2026-08-26")
    assert again == ""


def test_the_day_is_written_before_the_network_call(tmp_path):
    """A server that hangs must not make us try again every single start."""
    cfg = make_config(tmp_path)
    updates.check(cfg, opener_raising(TimeoutError("hangs")),
                  today="2026-08-26")
    assert cfg.last_update_check == "2026-08-26"


# ---------------------------- the background run ------------------------- #

def test_the_thread_reports_news(tmp_path):
    cfg = make_config(tmp_path)
    check = updates.BackgroundCheck()
    check._run(cfg, opener_returning({"tag_name": "v99.0.0"}))
    assert check.newer == "v99.0.0"
    assert "v99.0.0" in check.message
    assert updates.RELEASES_PAGE in check.message


def test_the_thread_never_raises(tmp_path):
    cfg = make_config(tmp_path)
    check = updates.BackgroundCheck()
    check._run(cfg, opener_raising(RuntimeError("anything at all")))
    assert check.newer == ""
    assert check.message == ""


def test_no_thread_starts_when_the_setting_is_off(tmp_path):
    cfg = make_config(tmp_path, check_updates=False)
    check = updates.BackgroundCheck().start(cfg)
    assert check.newer == ""
    assert check.message == ""


def test_a_fresh_check_says_nothing():
    assert updates.BackgroundCheck().message == ""
