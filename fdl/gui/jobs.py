"""Downloads running behind the window.

tkinter may only be touched from the thread that built the window. So no
widget is ever passed in here. Each worker thread writes small events into a
queue, and the window empties that queue on a timer.

Nothing in this file imports tkinter, which is also what makes it testable
without a screen.
"""

import concurrent.futures
import itertools
import queue
import threading
import time
from dataclasses import dataclass, field

from .. import batch, http_engine, log, safety, ytdlp_engine
from ..history import STATUS_DONE, STATUS_FAILED
from ..http_engine import DownloadError
from ..router import KIND_MEDIA

CHECKING = "checking"
WAITING = "waiting"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
SKIPPED = "skipped"
CANCELLED = "cancelled"

FINISHED = (DONE, FAILED, SKIPPED, CANCELLED)

# How often a running download may send news to the window. Faster than this
# only makes the window busy; the numbers on screen do not look any better.
UPDATE_SECONDS = 0.15


@dataclass
class Job:
    """One download, as the window sees it."""

    job_id: int = 0
    url: str = ""
    name: str = ""
    category: str = ""
    kind: str = ""
    dest: object = None
    path: object = None
    status: str = CHECKING
    done_bytes: int = 0
    total_bytes: object = None
    percent: float = 0.0
    speed: float = 0.0
    message: str = ""
    error: str = ""
    warnings: list = field(default_factory=list)
    stop: threading.Event = field(default_factory=threading.Event)

    @property
    def label(self):
        return self.name or self.url

    @property
    def is_finished(self):
        return self.status in FINISHED

    @property
    def can_cancel(self):
        return self.status in (CHECKING, WAITING, RUNNING)


class Manager:
    """Runs downloads in a thread pool and reports back through a queue.

    The window calls `add()` and then reads `events` on a timer. It never
    waits for anything here.
    """

    def __init__(self, cfg, toolbox, history, pool=None):
        self.cfg = cfg
        self.toolbox = toolbox
        self.history = history
        self.events = queue.Queue()
        self.jobs = {}
        self._ids = itertools.count(1)
        self._pool = pool or concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, cfg.max_parallel),
            thread_name_prefix="fdl-gui")

    # ------------------------------ adding ------------------------------ #

    def add(self, url, quality="1", whole_playlist=False):
        """Start one link. Returns the Job at once, before anything runs."""
        job = Job(job_id=next(self._ids), url=url.strip())
        self.jobs[job.job_id] = job
        self._announce(job)
        self._pool.submit(self._guarded, job, quality, whole_playlist)
        return job

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if job and job.can_cancel:
            job.stop.set()
            job.message = "stopping..."
            self._announce(job)

    def close(self):
        for job in self.jobs.values():
            job.stop.set()
        self._pool.shutdown(wait=False)

    @property
    def active(self):
        return [job for job in self.jobs.values() if not job.is_finished]

    # ----------------------------- the work ----------------------------- #

    def _announce(self, job):
        self.events.put(job.job_id)

    def _finish(self, job, status, error="", message=""):
        job.status = status
        job.error = error
        job.message = message or job.message
        if status != RUNNING:
            job.speed = 0.0
        self._announce(job)

    def _guarded(self, job, quality, whole_playlist):
        """A worker must never die quietly: the row would freeze for ever."""
        try:
            self._run(job, quality, whole_playlist)
        except Exception as err:      # noqa: BLE001
            log.error("gui job failed: %s", err)
            self._finish(job, FAILED, str(err))

    def _run(self, job, quality, whole_playlist):
        if job.stop.is_set():
            self._finish(job, CANCELLED, message="cancelled")
            return

        job.message = "checking the link..."
        self._announce(job)

        item = batch.prepare([job.url], self.cfg, self.history)[0]
        job.kind = item.kind
        job.name = item.name or job.url
        job.category = item.category
        job.dest = item.dest
        job.warnings = list(item.warnings or [])

        if item.status == batch.STATUS_SKIPPED:
            self._finish(job, SKIPPED, message=item.note)
            return
        if item.status == batch.STATUS_FAILED:
            self._finish(job, FAILED, item.error)
            return

        blocked = self._safety_problem(item)
        if blocked:
            self._finish(job, FAILED, blocked)
            return

        job.status = RUNNING
        job.message = ""
        job.total_bytes = item.size
        job.done_bytes = item.resume_from
        self._announce(job)

        if item.kind == KIND_MEDIA:
            self._run_media(job, quality, whole_playlist)
        else:
            self._run_file(job, item)

    def _safety_problem(self, item):
        """The checks that must never be silently skipped in a window."""
        if item.info is None:        # a media page: yt-dlp does its own checks
            return ""
        if safety.looks_like_a_login_page(item.info):
            return ("The server sent a web page, not the file. The link "
                    "probably needs a login, or it has moved.")
        needed = getattr(item.info, "size", None) or 0
        ok, reason = safety.check_space(item.dest, max(0, needed - item.resume_from))
        if not ok:
            return reason
        return ""

    # -------------------------- a direct file --------------------------- #

    def _run_file(self, job, item):
        clock = _Ticker(job)

        def on_progress(done, total):
            if job.stop.is_set():
                raise KeyboardInterrupt("cancelled")
            clock.update(done, total)
            if clock.due():
                self._announce(job)

        try:
            saved = http_engine.download(
                job.url, item.dest, item.info, name=item.name,
                extra_headers=self.cfg.headers,
                retries=self.cfg.retries, connections=self.cfg.connections,
                speed_limit=self.cfg.speed_limit_bytes,
                on_progress=on_progress, stop_event=job.stop)
        except KeyboardInterrupt:
            self._record(job, FAILED, "stopped by the user")
            self._finish(job, CANCELLED, message="cancelled")
            return
        except DownloadError as err:
            self._record(job, FAILED, str(err))
            self._finish(job, FAILED, str(err))
            return

        job.path = saved
        job.percent = 100.0
        job.done_bytes = job.total_bytes or job.done_bytes
        self._record(job, DONE)
        self._finish(job, DONE, message=str(saved))

    # ---------------------------- a media page --------------------------- #

    def _run_media(self, job, quality, whole_playlist):
        selector, height = ytdlp_engine.QUALITY_PRESETS.get(
            quality, ytdlp_engine.QUALITY_PRESETS["1"])[1:]
        job.category = ("Audio" if ytdlp_engine.is_audio_choice(selector)
                        else "Videos")
        job.dest = self.cfg.folder_for(job.category)
        job.total_bytes = None

        extra = ytdlp_engine.playlist_flags(whole_playlist)
        args, note = ytdlp_engine.build_args_quiet(
            job.url, job.dest, selector, height, self.toolbox.has_ffmpeg,
            extra)
        if note:
            job.warnings.append(note)
        self._announce(job)

        last = [0.0]
        errors = []

        def on_line(line):
            percent = ytdlp_engine.parse_progress(line)
            if percent is not None:
                job.percent = percent
            elif ytdlp_engine.is_error_line(line):
                # The exit code is always 1, so this line is the only place
                # that ever says what really went wrong.
                errors.append(ytdlp_engine.clean_error(line))
                log.error("yt-dlp: %s", errors[-1])
            elif line.strip():
                job.message = line.strip()[:90]
            now = time.monotonic()
            if now - last[0] >= UPDATE_SECONDS:
                last[0] = now
                self._announce(job)

        code = ytdlp_engine.run_streaming(
            args, self.toolbox, self.cfg.cookies_browser,
            on_line=on_line, stop_event=job.stop)

        if job.stop.is_set():
            self._record(job, FAILED, "stopped by the user")
            self._finish(job, CANCELLED, message="cancelled")
            return
        if code == 0:
            job.path = job.dest
            job.percent = 100.0
            self._record(job, DONE)
            self._finish(job, DONE, message=str(job.dest))
            return

        reason = errors[-1] if errors else f"yt-dlp stopped with code {code}."
        advice = ytdlp_engine.explain(" ".join(errors))
        if advice:
            job.warnings.append(advice)
        elif not errors and not self.cfg.cookies_browser:
            job.warnings.append(
                "If the site asks you to sign in, choose a browser for "
                "cookies in Settings.")
        self._record(job, FAILED, reason)
        self._finish(job, FAILED, reason)

    # ------------------------------ history ------------------------------ #

    def _record(self, job, status, error=""):
        engine = "yt-dlp" if job.kind == KIND_MEDIA else "file"
        if status == DONE:
            log.info("gui done: %s -> %s", log.redact(job.url), job.path)
        else:
            log.error("gui failed: %s (%s)", log.redact(job.url), error)
        if not self.history:
            return
        self.history.add(
            job.url, STATUS_DONE if status == DONE else STATUS_FAILED,
            path=job.path, size=job.total_bytes, category=job.category,
            engine=engine, error=error or None)


class _Ticker:
    """Turns raw byte counts into a percent and a speed, without flooding."""

    def __init__(self, job, now=None):
        self.job = job
        clock = now or time.monotonic
        self._clock = clock
        self._started = clock()
        self._start_bytes = job.done_bytes
        # Set back one step, so the very first update reaches the window at
        # once instead of waiting.
        self._last_sent = self._started - UPDATE_SECONDS

    def update(self, done, total):
        self.job.done_bytes = done
        if total:
            self.job.total_bytes = total
            self.job.percent = max(0.0, min(100.0, done * 100.0 / total))
        seconds = self._clock() - self._started
        if seconds > 0:
            self.job.speed = (done - self._start_bytes) / seconds

    def due(self):
        now = self._clock()
        if now - self._last_sent < UPDATE_SECONDS:
            return False
        self._last_sent = now
        return True
