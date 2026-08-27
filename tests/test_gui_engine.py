"""Tests for the pieces the window needs from the engines.

The terminal versions of these functions print and ask questions. A window
cannot answer a question typed into a console nobody can see, so the GUI has
its own quiet versions. These tests keep the two in step.
"""

import io

import pytest

from fdl import app, ytdlp_engine
from fdl.gui import jobs

# `rows` draws widgets, so it needs tkinter present. On Linux that is a
# separate package. Nothing here opens a window, so no screen is needed.
pytest.importorskip("tkinter", reason="tkinter is not installed")
from fdl.gui import rows                                        # noqa: E402


class FakeToolbox:
    ffmpeg_dir = None
    has_ffmpeg = False

    def env(self):
        return {}


# ---------------------------- reading progress --------------------------- #

@pytest.mark.parametrize("line, expected", [
    ("[download]   5.0% of 10.00MiB at 1.00MiB/s ETA 00:09", 5.0),
    ("[download]  75.5% of 10.00MiB", 75.5),
    ("[download] 100% of 10.00MiB", 100.0),
    ("[download] 100.0% of ~ 1.00GiB", 100.0),
])
def test_the_percent_is_read(line, expected):
    assert ytdlp_engine.parse_progress(line) == expected


@pytest.mark.parametrize("line", [
    "[youtube] abc: Downloading webpage",
    "[download] Destination: video.mp4",
    "ERROR: Sign in to confirm you are not a bot",
    "",
    None,
])
def test_other_lines_have_no_percent(line):
    assert ytdlp_engine.parse_progress(line) is None


def test_a_silly_percent_is_pulled_back_into_range():
    assert ytdlp_engine.parse_progress("[download] 999% of x") == 100.0


# ------------------------------ quiet arguments -------------------------- #

def test_the_quiet_builder_never_asks(monkeypatch):
    """A question here would freeze the window with nobody to answer it."""
    monkeypatch.setattr("builtins.input",
                        lambda *_a: pytest.fail("must not ask"))
    args, note = ytdlp_engine.build_args_quiet(
        "https://youtu.be/abc", "C:/dl", "bestvideo+bestaudio/best", None,
        has_ffmpeg=True)
    assert "https://youtu.be/abc" in args
    assert note == ""


def test_mp3_without_ffmpeg_falls_back_and_says_so():
    args, note = ytdlp_engine.build_args_quiet(
        "https://youtu.be/abc", "C:/dl", "AUDIO_MP3", None, has_ffmpeg=False)
    assert "--audio-format" not in args
    assert "bestaudio" in args
    assert "ffmpeg" in note


def test_mp3_with_ffmpeg_makes_mp3():
    args, note = ytdlp_engine.build_args_quiet(
        "https://youtu.be/abc", "C:/dl", "AUDIO_MP3", None, has_ffmpeg=True)
    assert args[args.index("--audio-format") + 1] == "mp3"
    assert note == ""


def test_video_without_ffmpeg_uses_one_file_and_says_so():
    args, note = ytdlp_engine.build_args_quiet(
        "https://youtu.be/abc", "C:/dl", "bestvideo+bestaudio/best", 1080,
        has_ffmpeg=False)
    assert "--merge-output-format" not in args
    assert "quality may be lower" in note.lower()


def test_the_window_needs_one_line_per_progress_step():
    """Without --newline, yt-dlp overwrites one line and we see nothing."""
    args, _note = ytdlp_engine.build_args_quiet(
        "https://youtu.be/abc", "C:/dl", "best", None, has_ffmpeg=True)
    assert "--newline" in args


@pytest.mark.parametrize("whole, expected", [
    (True, "--yes-playlist"),
    (False, "--no-playlist"),
])
def test_the_playlist_tick_box(whole, expected):
    assert ytdlp_engine.playlist_flags(whole) == [expected]


def test_a_playlist_link_is_recognised():
    assert ytdlp_engine.has_playlist("https://youtu.be/a?list=PL1") is True
    assert ytdlp_engine.has_playlist("https://youtu.be/a") is False


# ------------------------------ running yt-dlp --------------------------- #

class FakeProcess:
    def __init__(self, lines, code=0):
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self._code = code
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self):
        return self._code


def test_every_output_line_reaches_the_window():
    process = FakeProcess(["one", "two", "three"])
    seen = []
    code = ytdlp_engine.run_streaming(
        ["-F", "url"], FakeToolbox(), on_line=seen.append,
        popen=lambda *a, **kw: process)
    assert seen == ["one", "two", "three"]
    assert code == 0


def test_the_exit_code_comes_back():
    process = FakeProcess(["x"], code=2)
    assert ytdlp_engine.run_streaming(["url"], FakeToolbox(),
                                      popen=lambda *a, **kw: process) == 2


def test_stopping_kills_yt_dlp():
    import threading
    process = FakeProcess(["a", "b", "c"])
    stop = threading.Event()
    stop.set()
    code = ytdlp_engine.run_streaming(["url"], FakeToolbox(), stop_event=stop,
                                      popen=lambda *a, **kw: process)
    assert process.terminated is True
    assert code == 1


def test_no_black_window_flashes_up():
    """A GUI must not blink a console every time yt-dlp starts."""
    seen = {}

    def popen(command, **kwargs):
        seen.update(kwargs)
        return FakeProcess([])

    ytdlp_engine.run_streaming(["url"], FakeToolbox(), popen=popen)
    assert "creationflags" in seen


# ------------------------------- window or menu -------------------------- #

@pytest.mark.parametrize("argv, frozen, expected", [
    ([], False, app.MODE_TERMINAL),          # typed `fdl` in a terminal
    ([], True, app.MODE_GUI),                # double-clicked the .exe
    (["--gui"], False, app.MODE_GUI),
    (["-g"], False, app.MODE_GUI),
    (["--terminal"], True, app.MODE_TERMINAL),
    (["--cli"], True, app.MODE_TERMINAL),
    (["-t"], True, app.MODE_TERMINAL),
    (["--gui", "--terminal"], False, app.MODE_GUI),   # the first flag wins
])
def test_choose_mode(argv, frozen, expected):
    assert app.choose_mode(argv, frozen) == expected


def test_the_yt_dlp_call_is_never_read_as_a_mode_flag():
    """`-m yt_dlp` must reach yt-dlp, and never open a window."""
    argv = ["-m", "yt_dlp", "--newline", "url"]
    assert ytdlp_engine.wants_passthrough(argv) is not None


# --------------------------- what a row says ----------------------------- #

def test_a_running_row_shows_size_and_speed():
    job = jobs.Job(status=jobs.RUNNING, done_bytes=500_000,
                   total_bytes=1_000_000, speed=250_000)
    text = rows.right_text(job)
    assert "488.3 KB" in text
    assert "244.1 KB/s" in text


def test_a_row_with_no_speed_yet_says_starting():
    job = jobs.Job(status=jobs.RUNNING)
    assert rows.right_text(job) == "starting..."


def test_a_failed_row_shows_the_reason():
    job = jobs.Job(status=jobs.FAILED, error="The file was not found (404).")
    assert rows.right_text(job) == "The file was not found (404)."


def test_a_skipped_row_shows_the_note():
    job = jobs.Job(status=jobs.SKIPPED, message="already downloaded to D:/x")
    assert "already downloaded" in rows.right_text(job)


def test_an_unknown_size_shows_what_has_arrived():
    job = jobs.Job(status=jobs.RUNNING, done_bytes=2048, total_bytes=None)
    assert rows.size_text(job) == "2.0 KB"


def test_every_status_has_a_colour_and_a_word():
    for status in (jobs.CHECKING, jobs.WAITING, jobs.RUNNING, jobs.DONE,
                   jobs.FAILED, jobs.SKIPPED, jobs.CANCELLED):
        assert status in rows.COLOURS
        assert status in rows.WORDS


# ---------------------------- playlists --------------------------------- #

ESCAPE = chr(27)          # written this way so no invisible byte lands here


def test_the_playlist_line_gives_the_position():
    assert ytdlp_engine.parse_item(
        "[download] Downloading item 3 of 12") == (3, 12)


def test_the_older_wording_still_works():
    """Older versions of yt-dlp said 'video' instead of 'item'."""
    assert ytdlp_engine.parse_item(
        "[download] Downloading video 1 of 5") == (1, 5)


def test_colour_codes_around_the_numbers_are_ignored():
    """yt-dlp paints the numbers when it thinks it has a terminal."""
    line = (ESCAPE + "[0;36m[download]" + ESCAPE + "[0m Downloading item "
            + ESCAPE + "[38;5;6m7" + ESCAPE + "[0m of "
            + ESCAPE + "[1m40" + ESCAPE + "[0m")
    assert ytdlp_engine.parse_item(line) == (7, 40)


def test_a_progress_line_is_not_a_playlist_line():
    assert ytdlp_engine.parse_item(
        "[download]  75.5% of 10.00MiB at 1.00MiB/s ETA 00:02") is None


def test_text_that_only_looks_like_a_colour_code_is_left_alone():
    """The pattern must want a real escape byte, not any '[12m' in the text."""
    assert ytdlp_engine.parse_item("a fake [12m marker, not a colour") is None


def test_numbers_that_make_no_sense_are_refused():
    assert ytdlp_engine.parse_item("[download] Downloading item 0 of 3") is None
    assert ytdlp_engine.parse_item("[download] Downloading item 5 of 3") is None


def test_one_bar_for_the_whole_playlist():
    """Video 3 of 12, half done, is (2 + 0.5) of 12 of the work."""
    assert jobs.overall_percent(3, 12, 50.0) == pytest.approx(20.833, abs=0.01)
    assert jobs.overall_percent(1, 12, 0.0) == 0.0
    assert jobs.overall_percent(12, 12, 100.0) == 100.0


def test_a_single_video_keeps_its_own_percent():
    """There is no playlist, so there is nothing to divide."""
    assert jobs.overall_percent(0, 0, 42.0) == 42.0
    assert jobs.overall_percent(1, 1, 42.0) == 42.0


def test_the_playlist_bar_never_goes_backwards():
    """Every new video must start at least where the last one finished."""
    end_of_third = jobs.overall_percent(3, 12, 100.0)
    start_of_fourth = jobs.overall_percent(4, 12, 0.0)
    assert start_of_fourth == pytest.approx(end_of_third)


def test_a_running_playlist_row_says_which_video():
    job = jobs.Job(status=jobs.RUNNING, item_index=3, item_total=12)
    assert rows.right_text(job) == "video 3 of 12"


def test_a_single_video_row_does_not_say_video_1_of_1():
    """That would be noise. One video is just one download."""
    job = jobs.Job(status=jobs.RUNNING, item_index=1, item_total=1,
                   message="[download] Destination: clip.mp4")
    assert rows.playlist_text(job) == ""
    assert rows.right_text(job) == "[download] Destination: clip.mp4"
