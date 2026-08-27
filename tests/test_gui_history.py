"""What one line of the history window says.

Building a window needs a screen, so only the rule is tested here. That is
where the decisions are, and it is the part that can be wrong.
"""

from pathlib import Path

import pytest

pytest.importorskip("tkinter", reason="no tkinter on this machine")

from fdl.gui.history_dialog import row_values          # noqa: E402
from fdl.history import (STATUS_DONE, STATUS_FAILED,   # noqa: E402
                         STATUS_SKIPPED)


def test_a_finished_download_shows_its_file_and_folder():
    what, name, when, size, where = row_values({
        "status": STATUS_DONE,
        "url": "https://example.com/get?id=9",
        # Built for whichever system runs the test. A Windows path
        # written out in full has no separators on Linux, so .name
        # would give back the whole string.
        "path": str(Path.home() / "Downloads" / "Archives" / "tool.zip"),
        "size": 2048,
        "when": "2026-08-24T14:05:00+03:00",
        "category": "Archives",
    })
    assert what == "done"
    assert name == "tool.zip"        # the file, not the long address
    assert when == "2026-08-24 14:05"
    assert size == "2.0 KB"
    assert where == "Archives"


def test_a_failed_link_falls_back_to_the_address():
    """It never reached a file, so the address is all there is to show."""
    what, name, _when, size, where = row_values({
        "status": STATUS_FAILED,
        "url": "https://example.com/gone.zip",
        "error": "The file was not found (404).",
        "category": "Archives",
    })
    assert what == "failed"
    assert name == "gone.zip"
    assert size == ""                # nothing was ever downloaded
    assert where == "Archives"       # no path, so the category is used


def test_a_skipped_link_is_marked_as_skipped():
    what, *_rest = row_values({"status": STATUS_SKIPPED,
                               "url": "https://example.com/x.zip"})
    assert what == "skipped"


def test_an_entry_with_almost_nothing_in_it_does_not_break():
    """A history file can be old, or hand edited. It must still open."""
    assert row_values({}) == ("", "", "?", "", "")


def test_a_size_of_zero_is_left_blank():
    """'0 B' in the size column tells the reader nothing."""
    _what, _name, _when, size, _where = row_values({
        "status": STATUS_DONE, "url": "https://x/a.txt", "size": 0})
    assert size == ""


def test_an_address_with_no_file_name_shows_the_site():
    """Better than a whole address in a narrow column."""
    _what, name, *_rest = row_values({"status": STATUS_FAILED,
                                      "url": "https://example.com"})
    assert name == "example.com"

