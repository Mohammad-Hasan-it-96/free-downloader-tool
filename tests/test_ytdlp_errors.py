"""Tests for turning a yt-dlp failure into something a person can act on.

yt-dlp always exits with code 1, whatever went wrong. "stopped with code 1"
tells the user nothing, so the real reason has to be read out of the output
and, where possible, turned into a next step.
"""

import io

import pytest

from fdl import ytdlp_engine as engine
from fdl.gui import jobs
from fdl.batch import Item
from fdl.config import Config
from fdl.router import KIND_MEDIA

SIGN_IN = (
    "ERROR: [youtube] uuFu1jerbOU: Sign in to confirm you're not a bot. "
    "Use --cookies-from-browser or --cookies for the authentication. See  "
    "https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
)
LOCKED_COOKIES = (
    "ERROR: Could not copy Chrome cookie database. See  "
    "https://github.com/yt-dlp/yt-dlp/issues/7271  for more info"
)


# ---------------------------- finding the error -------------------------- #

@pytest.mark.parametrize("line, expected", [
    ("ERROR: something broke", True),
    ("  ERROR: indented", True),
    ("error: lower case", True),
    ("WARNING: [youtube] retrying", False),
    ("[download]  50.0% of 10MiB", False),
    ("", False),
    (None, False),
])
def test_finding_the_error_line(line, expected):
    assert engine.is_error_line(line) is expected


def test_the_prefix_is_removed():
    assert engine.clean_error("ERROR: it went wrong").startswith("it went")


def test_the_documentation_link_is_cut_off():
    text = engine.clean_error(SIGN_IN)
    assert "https://" not in text
    assert "Sign in to confirm" in text


def test_the_use_cookies_advice_is_cut_off():
    """yt-dlp's own advice is about flags, which our user never types."""
    assert "--cookies-from-browser" not in engine.clean_error(SIGN_IN)


def test_no_dangling_word_is_left_behind():
    """Cutting the link used to leave 'Could not copy ... database. See.'"""
    text = engine.clean_error(LOCKED_COOKIES)
    assert text == "Could not copy Chrome cookie database."


def test_the_sign_in_message_reads_as_a_sentence():
    text = engine.clean_error(SIGN_IN)
    assert text.endswith("not a bot.")


def test_an_empty_line_gives_nothing():
    assert engine.clean_error("") == ""
    assert engine.clean_error("ERROR:") == ""


def test_the_text_ends_in_a_full_stop():
    assert engine.clean_error("ERROR: no").endswith(".")
    assert engine.clean_error("ERROR: no.").endswith(".")
    assert not engine.clean_error("ERROR: no.").endswith("..")


# ------------------------------ giving advice ---------------------------- #

def test_the_sign_in_check_tells_the_user_what_to_do():
    advice = engine.explain(SIGN_IN)
    assert "Settings" in advice
    assert "close that browser" in advice.lower()


def test_a_locked_cookie_file_says_close_the_browser():
    advice = engine.explain(LOCKED_COOKIES)
    assert "close that browser" in advice.lower()


def test_a_site_change_says_update_yt_dlp():
    advice = engine.explain("ERROR: unable to extract player response")
    assert "yt-dlp" in advice
    assert "update" in advice.lower()


def test_a_missing_quality_suggests_best_available():
    advice = engine.explain("ERROR: Requested format is not available")
    assert "Best available" in advice


def test_an_unknown_error_gets_no_made_up_advice():
    assert engine.explain("ERROR: the sky fell on the server") == ""
    assert engine.explain("") == ""


# --------------------- the window shows it, not code 1 ------------------- #

class NowPool:
    def submit(self, function, *args, **kwargs):
        function(*args, **kwargs)

    def shutdown(self, wait=True):
        pass


class FakeToolbox:
    ffmpeg_dir = None
    has_ffmpeg = True

    def env(self):
        return {}


class FakeHistory:
    def __init__(self):
        self.rows = []

    def add(self, url, status, **kwargs):
        self.rows.append((url, status, kwargs))

    def already_have(self, _url):
        return None


@pytest.fixture
def manager(tmp_path, monkeypatch):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "dl")
    cfg.cookies_browser = "chrome"
    item = Item(url="https://youtu.be/abc", kind=KIND_MEDIA)
    item.category = "Videos"
    monkeypatch.setattr(jobs.batch, "prepare",
                        lambda urls, c, h=None, **kw: [item])
    return jobs.Manager(cfg, FakeToolbox(), FakeHistory(), pool=NowPool())


def stream_lines(monkeypatch, lines, code=1):
    def fake(args, toolbox, cookies, on_line=None, stop_event=None):
        for line in lines:
            on_line(line)
        return code

    monkeypatch.setattr(jobs.ytdlp_engine, "run_streaming", fake)


def test_the_window_shows_the_real_reason(manager, monkeypatch):
    """The bug this fixes: the row only said 'yt-dlp stopped with code 1'."""
    stream_lines(monkeypatch, ["[youtube] abc: Downloading webpage", SIGN_IN])

    job = manager.add("https://youtu.be/abc")

    assert job.status == jobs.FAILED
    assert "Sign in to confirm" in job.error
    assert "code 1" not in job.error


def test_the_window_also_shows_what_to_do(manager, monkeypatch):
    stream_lines(monkeypatch, [SIGN_IN])

    job = manager.add("https://youtu.be/abc")

    assert any("Settings" in note for note in job.warnings)


def test_a_locked_cookie_file_is_explained(manager, monkeypatch):
    stream_lines(monkeypatch, [LOCKED_COOKIES])

    job = manager.add("https://youtu.be/abc")

    assert "cookie database" in job.error.lower()
    assert any("close that browser" in note.lower() for note in job.warnings)


def test_the_last_error_wins(manager, monkeypatch):
    """yt-dlp often prints a retry error first and the real one last."""
    stream_lines(monkeypatch, ["ERROR: first try failed", SIGN_IN])

    job = manager.add("https://youtu.be/abc")

    assert "Sign in to confirm" in job.error


def test_a_warning_line_is_not_treated_as_the_error(manager, monkeypatch):
    stream_lines(monkeypatch, ["WARNING: [youtube] Retrying (1/3)...",
                               "ERROR: the real problem"])

    job = manager.add("https://youtu.be/abc")

    assert "real problem" in job.error
    assert "Retrying" not in job.error


def test_no_error_line_falls_back_to_the_code(manager, monkeypatch):
    stream_lines(monkeypatch, ["[youtube] abc: Downloading webpage"], code=2)

    job = manager.add("https://youtu.be/abc")

    assert "code 2" in job.error


def test_the_cookie_hint_only_appears_when_cookies_are_off(manager,
                                                           monkeypatch):
    manager.cfg.cookies_browser = ""
    stream_lines(monkeypatch, [], code=1)

    job = manager.add("https://youtu.be/abc")

    assert any("cookies" in note.lower() for note in job.warnings)


class FakeProcess:
    def __init__(self, lines, code=1):
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self._code = code

    def terminate(self):
        pass

    def wait(self):
        return self._code


def test_yt_dlp_output_is_read_as_utf8():
    """yt-dlp writes UTF-8. This machine's code page is not UTF-8.

    Without saying which encoding to use, a curly quote in a message comes
    back broken, and on some systems the read raises instead.
    """
    seen = {}

    def popen(_command, **kwargs):
        seen.update(kwargs)
        return FakeProcess([u"ERROR: Sign in to confirm you’re not a bot"])

    lines = []
    code = engine.run_streaming(["url"], FakeToolbox(), on_line=lines.append,
                                popen=popen)

    assert seen.get("encoding") == "utf-8"
    assert seen.get("errors") == "replace"
    assert u"’" in lines[0]
    assert code == 1
