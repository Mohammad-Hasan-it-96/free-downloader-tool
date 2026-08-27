"""Tests for the work behind the window.

`fdl.gui.jobs` holds no widgets on purpose, so all of it can be tested with
no screen at all. The pool is replaced by one that runs the work right away,
which makes every test straight-line code instead of a race.
"""

import threading

import pytest

from fdl.gui import jobs
from fdl.batch import Item
from fdl.config import Config
from fdl.http_engine import DownloadError
from fdl.router import KIND_FILE, KIND_MEDIA


class NowPool:
    """A thread pool that is not a pool: it runs the work immediately."""

    def submit(self, function, *args, **kwargs):
        function(*args, **kwargs)

    def shutdown(self, wait=True):
        pass


class FakeToolbox:
    ffmpeg_dir = None
    deno_dir = None
    aria2c_dir = None
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


class FakeInfo:
    def __init__(self, size=1000, content_type="application/zip",
                 filename="thing.zip"):
        self.size = size
        self.content_type = content_type
        self.filename = filename


@pytest.fixture
def setup(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "dl")
    history = FakeHistory()
    manager = jobs.Manager(cfg, FakeToolbox(), history, pool=NowPool())
    return manager, cfg, history


def file_item(tmp_path, **changes):
    item = Item(url="https://example.com/thing.zip", kind=KIND_FILE)
    item.info = FakeInfo()
    item.name = "thing.zip"
    item.category = "Archives"
    item.dest = tmp_path / "dl" / "Archives"
    for key, value in changes.items():
        setattr(item, key, value)
    return item


def give_prepare(monkeypatch, item):
    monkeypatch.setattr(jobs.batch, "prepare",
                        lambda urls, cfg, history=None, **kw: [item])


def events_of(manager):
    seen = []
    while not manager.events.empty():
        seen.append(manager.events.get_nowait())
    return seen


# ------------------------------ a direct file ---------------------------- #

def test_a_file_download_finishes(setup, monkeypatch, tmp_path):
    manager, _cfg, history = setup
    saved = tmp_path / "dl" / "Archives" / "thing.zip"
    give_prepare(monkeypatch, file_item(tmp_path))
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: saved)

    job = manager.add("https://example.com/thing.zip")

    assert job.status == jobs.DONE
    assert job.path == saved
    assert job.percent == 100.0
    assert job.category == "Archives"
    assert history.rows[0][1] == "done"


def test_the_window_is_told_about_every_change(setup, monkeypatch, tmp_path):
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path))
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: tmp_path / "thing.zip")

    job = manager.add("https://example.com/thing.zip")

    assert events_of(manager).count(job.job_id) >= 2


def test_a_download_error_is_shown_not_raised(setup, monkeypatch, tmp_path):
    manager, _cfg, history = setup
    give_prepare(monkeypatch, file_item(tmp_path))

    def boom(*_a, **_kw):
        raise DownloadError("The file was not found (404).")

    monkeypatch.setattr(jobs.http_engine, "download", boom)

    job = manager.add("https://example.com/gone.zip")

    assert job.status == jobs.FAILED
    assert "404" in job.error
    assert history.rows[0][1] == "failed"


def test_a_link_that_cannot_be_checked_fails_early(setup, monkeypatch,
                                                   tmp_path):
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path, status="failed",
                                        error="No such host"))
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: pytest.fail("must not download"))

    job = manager.add("https://nowhere.invalid/x.zip")

    assert job.status == jobs.FAILED
    assert job.error == "No such host"


def test_a_link_already_downloaded_is_skipped(setup, monkeypatch, tmp_path):
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path, status="skipped",
                                        note="already downloaded to D:/x.zip"))
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: pytest.fail("must not download"))

    job = manager.add("https://example.com/thing.zip")

    assert job.status == jobs.SKIPPED
    assert "already downloaded" in job.message


def test_a_login_page_is_refused_before_saving(setup, monkeypatch, tmp_path):
    """Otherwise the window would save an HTML page called thing.zip."""
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path))
    monkeypatch.setattr(jobs.safety, "looks_like_a_login_page",
                        lambda _info: True)
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: pytest.fail("must not download"))

    job = manager.add("https://example.com/thing.zip")

    assert job.status == jobs.FAILED
    assert "web page" in job.error


def test_no_room_on_the_disk_stops_the_download(setup, monkeypatch, tmp_path):
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path))
    monkeypatch.setattr(jobs.safety, "check_space",
                        lambda _dir, _need: (False, "Not enough free space."))
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: pytest.fail("must not download"))

    job = manager.add("https://example.com/thing.zip")

    assert job.status == jobs.FAILED
    assert "free space" in job.error


# -------------------------------- stopping ------------------------------- #

def test_stopping_marks_the_job_cancelled(setup, monkeypatch, tmp_path):
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path))

    def download(*_a, **kwargs):
        kwargs["on_progress"](10, 1000)      # the window pressed Stop
        pytest.fail("the download should have been stopped")

    monkeypatch.setattr(jobs.http_engine, "download", download)

    job = jobs.Job(job_id=1, url="https://example.com/thing.zip")
    job.stop.set()
    manager.jobs[1] = job
    manager._run(job, "1", False)

    assert job.status == jobs.CANCELLED


def test_a_job_stopped_while_running_ends_as_cancelled(setup, monkeypatch,
                                                       tmp_path):
    manager, _cfg, history = setup
    give_prepare(monkeypatch, file_item(tmp_path))

    def download(*_a, **kwargs):
        job = manager.jobs[1]
        job.stop.set()
        kwargs["on_progress"](10, 1000)      # this must raise
        pytest.fail("on_progress did not stop the download")

    monkeypatch.setattr(jobs.http_engine, "download", download)
    manager._ids = iter([1])

    job = manager.add("https://example.com/thing.zip")

    assert job.status == jobs.CANCELLED
    # A stop is not a failure. Nothing is written down: the part file is kept
    # and Retry carries on from it.
    assert history.rows == []


def test_cancel_before_the_work_starts(setup):
    manager, _cfg, _history = setup
    job = jobs.Job(job_id=7, url="https://example.com/a.zip")
    manager.jobs[7] = job

    manager.cancel(7)

    assert job.stop.is_set()


def test_cancel_does_nothing_to_a_finished_job(setup):
    manager, _cfg, _history = setup
    job = jobs.Job(job_id=7, status=jobs.DONE)
    manager.jobs[7] = job

    manager.cancel(7)

    assert job.stop.is_set() is False


# -------------------------------- retrying ------------------------------- #

def test_a_failed_job_can_be_tried_again(setup, monkeypatch, tmp_path):
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path))
    tries = []

    def download(*_a, **_kw):
        tries.append(1)
        if len(tries) == 1:
            raise DownloadError("The connection was lost.")
        return tmp_path / "thing.zip"

    monkeypatch.setattr(jobs.http_engine, "download", download)

    job = manager.add("https://example.com/thing.zip")
    assert job.status == jobs.FAILED

    manager.retry(job.job_id)

    assert job.status == jobs.DONE
    assert len(tries) == 2


def test_retrying_clears_the_old_error(setup, monkeypatch, tmp_path):
    """A stale red line under a running download would be confusing."""
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path))
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: tmp_path / "thing.zip")

    job = jobs.Job(job_id=1, url="https://example.com/thing.zip",
                   status=jobs.FAILED, error="The file was not found (404).",
                   warnings=["close that browser"], percent=42.0)
    manager.jobs[1] = job

    manager.retry(1)

    assert job.error == ""
    assert job.warnings == []
    assert job.status == jobs.DONE


def test_retrying_counts_the_attempts(setup, monkeypatch, tmp_path):
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path))
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            DownloadError("no")))

    job = manager.add("https://example.com/thing.zip")
    assert job.attempts == 1

    manager.retry(job.job_id)
    manager.retry(job.job_id)

    assert job.attempts == 3


def test_retrying_uses_the_choices_from_the_first_time(setup, monkeypatch):
    """The quality box may have changed since. The row keeps its own."""
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, media_item())
    seen = []

    def stream(args, *_a, **_kw):
        seen.append(list(args))
        return 1

    monkeypatch.setattr(jobs.ytdlp_engine, "run_streaming", stream)

    job = manager.add("https://youtu.be/abc", quality="6",
                      whole_playlist=True)
    manager.retry(job.job_id)

    assert len(seen) == 2
    for args in seen:
        assert "--yes-playlist" in args
    assert job.category == "Audio"          # quality 6 is audio only


def test_a_stopped_job_can_be_tried_again(setup, monkeypatch, tmp_path):
    """The old stop signal must not kill the new attempt at once."""
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path))
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: tmp_path / "thing.zip")

    job = jobs.Job(job_id=1, url="https://example.com/thing.zip",
                   status=jobs.CANCELLED)
    job.stop.set()
    manager.jobs[1] = job

    manager.retry(1)

    assert job.stop.is_set() is False
    assert job.status == jobs.DONE


@pytest.mark.parametrize("status", [jobs.DONE, jobs.SKIPPED, jobs.RUNNING,
                                    jobs.CHECKING])
def test_only_broken_jobs_offer_a_retry(status):
    assert jobs.Job(status=status).can_retry is False


@pytest.mark.parametrize("status", [jobs.FAILED, jobs.CANCELLED])
def test_a_broken_job_offers_a_retry(status):
    assert jobs.Job(status=status).can_retry is True


def test_retrying_something_finished_does_nothing(setup, monkeypatch,
                                                  tmp_path):
    manager, _cfg, _history = setup
    monkeypatch.setattr(jobs.batch, "prepare",
                        lambda *a, **kw: pytest.fail("must not run again"))
    manager.jobs[1] = jobs.Job(job_id=1, status=jobs.DONE)

    assert manager.retry(1) is None


def test_retrying_an_unknown_job_does_nothing(setup):
    manager, _cfg, _history = setup
    assert manager.retry(999) is None


def test_retry_all_takes_only_the_failed_ones(setup, monkeypatch, tmp_path):
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, file_item(tmp_path))
    monkeypatch.setattr(jobs.http_engine, "download",
                        lambda *a, **kw: tmp_path / "thing.zip")

    manager.jobs[1] = jobs.Job(job_id=1, url="https://a/1.zip",
                               status=jobs.FAILED)
    manager.jobs[2] = jobs.Job(job_id=2, url="https://a/2.zip",
                               status=jobs.DONE)
    manager.jobs[3] = jobs.Job(job_id=3, url="https://a/3.zip",
                               status=jobs.CANCELLED)

    assert manager.retry_all() == 2
    assert manager.jobs[1].status == jobs.DONE
    assert manager.jobs[3].status == jobs.DONE


def test_the_failed_list_drives_the_retry_button(setup):
    manager, _cfg, _history = setup
    assert manager.failed == []
    manager.jobs[1] = jobs.Job(job_id=1, status=jobs.FAILED)
    manager.jobs[2] = jobs.Job(job_id=2, status=jobs.DONE)
    assert [job.job_id for job in manager.failed] == [1]


# ------------------------------- a media page ---------------------------- #

def media_item():
    item = Item(url="https://youtu.be/abc", kind=KIND_MEDIA)
    item.info = None
    item.category = "Videos"
    return item


def test_a_video_reports_progress_from_yt_dlp(setup, monkeypatch):
    manager, _cfg, history = setup
    give_prepare(monkeypatch, media_item())
    lines = [
        "[youtube] abc: Downloading webpage",
        "[download] Destination: video.mp4",
        "[download]   5.0% of 10.00MiB at 1.00MiB/s ETA 00:09",
        "[download]  75.5% of 10.00MiB at 1.00MiB/s ETA 00:02",
        "[download] 100% of 10.00MiB",
    ]

    def fake_stream(args, toolbox, cookies, on_line=None, stop_event=None):
        for line in lines:
            on_line(line)
        return 0

    monkeypatch.setattr(jobs.ytdlp_engine, "run_streaming", fake_stream)

    job = manager.add("https://youtu.be/abc", quality="1")

    assert job.status == jobs.DONE
    assert job.percent == 100.0
    assert job.category == "Videos"
    assert history.rows[0][2]["engine"] == "yt-dlp"


def test_a_video_that_fails_explains_the_sign_in_problem(setup, monkeypatch):
    """With no error line to read, the code is all we have, plus a hint."""
    manager, cfg, _history = setup
    cfg.cookies_browser = ""
    give_prepare(monkeypatch, media_item())
    monkeypatch.setattr(jobs.ytdlp_engine, "run_streaming",
                        lambda *a, **kw: 1)

    job = manager.add("https://youtu.be/abc")

    assert job.status == jobs.FAILED
    assert "code 1" in job.error
    assert any("cookies" in note.lower() for note in job.warnings)


def test_the_audio_choice_uses_the_audio_folder(setup, monkeypatch):
    manager, _cfg, _history = setup
    give_prepare(monkeypatch, media_item())
    monkeypatch.setattr(jobs.ytdlp_engine, "run_streaming",
                        lambda *a, **kw: 0)

    job = manager.add("https://youtu.be/abc", quality="6")   # Audio only

    assert job.category == "Audio"


def test_a_missing_ffmpeg_is_explained_not_hidden(setup, monkeypatch):
    manager, _cfg, _history = setup
    manager.toolbox.has_ffmpeg = False
    give_prepare(monkeypatch, media_item())
    monkeypatch.setattr(jobs.ytdlp_engine, "run_streaming",
                        lambda *a, **kw: 0)

    job = manager.add("https://youtu.be/abc", quality="6")

    assert any("ffmpeg" in note for note in job.warnings)


# ------------------------------ never get stuck -------------------------- #

def test_an_unexpected_crash_still_ends_the_row(setup, monkeypatch):
    manager, _cfg, _history = setup

    def explode(*_a, **_kw):
        raise ZeroDivisionError("something nobody thought of")

    monkeypatch.setattr(jobs.batch, "prepare", explode)

    job = manager.add("https://example.com/thing.zip")

    assert job.status == jobs.FAILED
    assert job.is_finished
    assert "nobody thought of" in job.error


# -------------------------------- the maths ------------------------------ #

def test_percent_and_speed():
    job = jobs.Job()
    clock = iter([0.0, 2.0, 2.0])
    ticker = jobs._Ticker(job, now=lambda: next(clock))
    ticker.update(500, 1000)
    assert job.percent == 50.0
    assert job.speed == 250.0


def test_percent_stays_inside_the_bar():
    job = jobs.Job()
    ticker = jobs._Ticker(job, now=lambda: 0.0)
    ticker.update(2000, 1000)
    assert job.percent == 100.0


def test_an_unknown_size_gives_no_percent():
    job = jobs.Job()
    ticker = jobs._Ticker(job, now=lambda: 0.0)
    ticker.update(500, None)
    assert job.percent == 0.0
    assert job.done_bytes == 500


def test_news_is_not_sent_on_every_single_chunk():
    """A 4 GB file would otherwise send tens of thousands of redraws."""
    job = jobs.Job()
    times = iter([0.0, 0.0, 0.01, 1.0])
    ticker = jobs._Ticker(job, now=lambda: next(times))
    assert ticker.due() is True       # the first one always goes
    assert ticker.due() is False      # 10 ms later: too soon
    assert ticker.due() is True       # a second later: fine


def test_a_job_knows_when_it_can_be_stopped():
    assert jobs.Job(status=jobs.RUNNING).can_cancel is True
    assert jobs.Job(status=jobs.CHECKING).can_cancel is True
    assert jobs.Job(status=jobs.DONE).can_cancel is False
    assert jobs.Job(status=jobs.FAILED).is_finished is True


def test_the_label_falls_back_to_the_link():
    assert jobs.Job(url="https://x/y.zip").label == "https://x/y.zip"
    assert jobs.Job(url="https://x/y.zip", name="y.zip").label == "y.zip"


def test_closing_stops_everything(setup):
    manager, _cfg, _history = setup
    job = jobs.Job(job_id=1, status=jobs.RUNNING,
                   stop=threading.Event())
    manager.jobs[1] = job

    manager.close()

    assert job.stop.is_set()


# ------------------------- clearing the list -------------------------- #

def test_only_rows_with_nothing_left_to_do_can_be_cleared(setup):
    """A failed row keeps its Retry button, so it stays."""
    manager, _cfg, _history = setup
    for job_id, status in ((1, jobs.DONE), (2, jobs.SKIPPED),
                           (3, jobs.FAILED), (4, jobs.CANCELLED),
                           (5, jobs.RUNNING)):
        manager.jobs[job_id] = jobs.Job(job_id=job_id, status=status)

    assert sorted(job.job_id for job in manager.cleanable) == [1, 2]


def test_clearing_takes_the_finished_rows_out(setup):
    manager, _cfg, _history = setup
    manager.jobs[1] = jobs.Job(job_id=1, status=jobs.DONE)
    manager.jobs[2] = jobs.Job(job_id=2, status=jobs.FAILED)
    manager.jobs[3] = jobs.Job(job_id=3, status=jobs.SKIPPED)

    gone = manager.clear_done()

    assert sorted(gone) == [1, 3]
    assert list(manager.jobs) == [2]


def test_clearing_an_empty_list_does_nothing(setup):
    manager, _cfg, _history = setup
    assert manager.clear_done() == []


def test_a_cleared_row_does_not_come_back_in_the_summary(setup):
    """The history keeps it; the list does not have to."""
    manager, _cfg, _history = setup
    manager.jobs[1] = jobs.Job(job_id=1, status=jobs.DONE)
    manager.clear_done()
    assert manager.cleanable == []
    assert manager.failed == []


def test_a_stopped_media_download_is_not_recorded(setup, monkeypatch):
    """The same rule for a video page as for a file."""
    manager, _cfg, history = setup
    give_prepare(monkeypatch, media_item())

    def streaming(*_a, **kwargs):
        manager.jobs[1].stop.set()
        return 1

    monkeypatch.setattr(jobs.ytdlp_engine, "run_streaming", streaming)
    manager._ids = iter([1])

    job = manager.add("https://youtube.com/watch?v=abc")

    assert job.status == jobs.CANCELLED
    assert history.rows == []


# --------------------- how many run at the same time -------------------- #

def in_a_thread(work):
    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    return worker


def test_the_gate_lets_only_so_many_in_at_once():
    gate = jobs._Gate(2)
    with gate:
        assert gate.crowded() is False       # room for one more
        with gate:
            assert gate.crowded() is True    # both slots taken
    assert gate.crowded() is False           # both given back


def test_raising_the_number_frees_a_waiting_download():
    """The whole point: the change works without closing the window."""
    gate = jobs._Gate(1)
    started = threading.Event()
    with gate:
        worker = in_a_thread(lambda: [gate.__enter__(), started.set(),
                                      gate.__exit__()])
        assert started.wait(0.3) is False     # held back by the limit of 1
        gate.set_limit(2)
        assert started.wait(2) is True        # let in at once
    worker.join(timeout=2)


def test_lowering_the_number_does_not_stop_what_is_running():
    """Cutting a download in half would lose the part already fetched."""
    gate = jobs._Gate(3)
    with gate:
        with gate:
            gate.set_limit(1)
            # Both keep their slot. The new number applies to the next one.
            assert gate.crowded() is True


def test_closing_lets_a_waiting_download_go():
    """Otherwise its thread would keep the program alive after the window."""
    gate = jobs._Gate(1)
    passed = threading.Event()
    with gate:
        worker = in_a_thread(lambda: [gate.__enter__(), passed.set(),
                                      gate.__exit__()])
        assert passed.wait(0.3) is False
        gate.open_wide()
        assert passed.wait(2) is True
    worker.join(timeout=2)


def test_the_manager_starts_with_the_number_from_the_settings(setup):
    manager, cfg, _history = setup
    assert manager.parallel == cfg.max_parallel


def test_the_manager_changes_the_number_without_a_restart(setup):
    manager, _cfg, _history = setup
    manager.set_parallel(6)
    assert manager.parallel == 6


def test_the_number_is_never_zero(setup):
    """Zero would mean nothing ever downloads again."""
    manager, _cfg, _history = setup
    manager.set_parallel(0)
    assert manager.parallel == 1


def test_a_link_that_fails_the_check_still_reaches_the_history(setup,
                                                               monkeypatch):
    """It never reaches the downloader, so nothing else would write it down.

    Without this, a 404 shows as failed in the list and then leaves no trace
    at all in the history window.
    """
    manager, _cfg, history = setup
    broken = Item(url="https://example.com/gone.zip", kind=KIND_FILE)
    broken.status = jobs.batch.STATUS_FAILED
    broken.error = "The file was not found (404)."
    give_prepare(monkeypatch, broken)
    manager._ids = iter([1])

    job = manager.add("https://example.com/gone.zip")

    assert job.status == jobs.FAILED
    assert len(history.rows) == 1
    assert history.rows[0][1] == "failed"


def test_a_link_stopped_by_a_safety_check_is_recorded(setup, monkeypatch,
                                                      tmp_path):
    """A login page instead of the file. The user should find out why later."""
    manager, _cfg, history = setup
    give_prepare(monkeypatch, file_item(tmp_path))
    monkeypatch.setattr(jobs.safety, "looks_like_a_login_page",
                        lambda _info: True)
    manager._ids = iter([1])

    job = manager.add("https://example.com/thing.zip")

    assert job.status == jobs.FAILED
    assert len(history.rows) == 1


def test_a_link_already_downloaded_is_not_written_down_twice(setup,
                                                            monkeypatch,
                                                            tmp_path):
    """It is skipped because it is already there. Saying so again is noise."""
    manager, _cfg, history = setup
    known = file_item(tmp_path)
    known.status = jobs.batch.STATUS_SKIPPED
    known.note = "already downloaded"
    give_prepare(monkeypatch, known)
    manager._ids = iter([1])

    job = manager.add("https://example.com/thing.zip")

    assert job.status == jobs.SKIPPED
    assert history.rows == []
