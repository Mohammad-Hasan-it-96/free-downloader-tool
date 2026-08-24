"""Download one file over several connections at the same time.

The file is split into parts. Each thread downloads its own part and writes
it straight into the right place in the `.part` file, so nothing has to be
joined afterwards.

Because the bytes do NOT arrive in order, the size of the `.part` file says
nothing about how much is really done. The progress of every segment is kept
in the `.part.meta` sidecar instead, so a stopped download can continue.
"""

import concurrent.futures
import threading
import time
import urllib.error

MIN_SIZE_FOR_SPLIT = 2 * 1024 * 1024   # below this, one connection is enough
MIN_SEGMENT_SIZE = 512 * 1024          # do not make tiny segments
META_SAVE_SECONDS = 2.0


class Segment:
    __slots__ = ("index", "start", "end", "done")

    def __init__(self, index, start, end, done=0):
        self.index = index
        self.start = start
        self.end = end          # inclusive
        self.done = done

    @property
    def length(self):
        return self.end - self.start + 1

    @property
    def remaining(self):
        return self.length - self.done

    @property
    def position(self):
        return self.start + self.done

    def as_list(self):
        return [self.start, self.end, self.done]


def wanted_connections(size, connections):
    """How many connections make sense for this size."""
    if connections <= 1 or not size or size < MIN_SIZE_FOR_SPLIT:
        return 1
    return max(1, min(connections, size // MIN_SEGMENT_SIZE))


def should_split(info, connections):
    return bool(info.resumable and info.size
                and wanted_connections(info.size, connections) > 1)


def build_segments(size, count):
    """Cut [0, size) into `count` pieces of nearly equal length."""
    piece = size // count
    segments = []
    start = 0
    for index in range(count):
        end = size - 1 if index == count - 1 else start + piece - 1
        segments.append(Segment(index, start, end))
        start = end + 1
    return segments


def segments_from_meta(meta, size):
    """Rebuild segments saved by an earlier run. None when they do not fit."""
    raw = meta.get("segments")
    if not isinstance(raw, list) or not raw:
        return None

    segments = []
    expected_start = 0
    for index, entry in enumerate(raw):
        if (not isinstance(entry, list) or len(entry) != 3
                or not all(isinstance(v, int) for v in entry)):
            return None
        start, end, done = entry
        if start != expected_start or end < start or done < 0:
            return None
        if done > end - start + 1:
            return None
        segments.append(Segment(index, start, end, done))
        expected_start = end + 1

    if expected_start != size:
        return None
    return segments


def total_done(segments):
    return sum(segment.done for segment in segments)


class SegmentedDownload:
    def __init__(self, url, part_path, info, segments, *, extra_headers=None,
                 retries=5, limiter=None, on_progress=None, on_retry=None,
                 save_meta=None, stop_event=None, urlopen=None):
        self.url = url
        self.part_path = part_path
        self.info = info
        self.segments = segments
        self.extra_headers = dict(extra_headers or {})
        self.retries = retries
        self.limiter = limiter
        self.on_progress = on_progress
        self.on_retry = on_retry
        self.save_meta = save_meta
        self.stop_event = stop_event or threading.Event()
        self.urlopen = urlopen
        self._lock = threading.Lock()
        self._last_saved = time.monotonic()
        self._failure = None

    # ------------------------------------------------------------------ #

    def run(self):
        self._prepare_file()
        self._report()

        workers = len([s for s in self.segments if s.remaining > 0]) or 1
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=workers) as pool:
            futures = [pool.submit(self._run_segment, segment)
                       for segment in self.segments if segment.remaining > 0]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        self._save(force=True)
        if self._failure:
            raise self._failure
        return total_done(self.segments)

    def _prepare_file(self):
        """Make the file its full size, so every thread can write into it."""
        size = self.info.size
        if self.part_path.exists() and self.part_path.stat().st_size == size:
            return
        with open(self.part_path, "r+b" if self.part_path.exists() else "wb") \
                as handle:
            handle.truncate(size)

    # ------------------------------------------------------------------ #

    def _run_segment(self, segment):
        attempt = 0
        while segment.remaining > 0:
            if self.stop_event.is_set():
                return
            try:
                self._fetch_segment(segment)
            except Exception as err:                 # noqa: BLE001
                if self.stop_event.is_set():
                    return
                attempt += 1
                if attempt > self.retries:
                    with self._lock:
                        if self._failure is None:
                            self._failure = err
                        self.stop_event.set()
                    return
                wait = min(30, 2 ** attempt)
                if self.on_retry:
                    self.on_retry(attempt, self.retries, str(err), wait)
                if self.stop_event.wait(wait):
                    return

    def _fetch_segment(self, segment):
        headers = dict(self.extra_headers)
        headers["Range"] = f"bytes={segment.position}-{segment.end}"
        fingerprint = self.info.etag or self.info.last_modified
        if fingerprint:
            headers["If-Range"] = fingerprint

        response = self.urlopen(headers)
        with response:
            status = getattr(response, "status", response.getcode())
            if status != 206:
                # No partial answer means we cannot trust this connection to
                # hold only our slice of the file.
                raise urllib.error.URLError(
                    "the server stopped supporting partial downloads")

            with open(self.part_path, "r+b") as handle:
                handle.seek(segment.position)
                while segment.remaining > 0:
                    if self.stop_event.is_set():
                        return
                    want = min(64 * 1024, segment.remaining)
                    if self.limiter:
                        want = min(want, self.limiter.chunk_size(want))
                        self.limiter.take(want)
                    chunk = response.read(want)
                    if not chunk:
                        break
                    handle.write(chunk)
                    with self._lock:
                        segment.done += len(chunk)
                    self._report()
                    self._save()

        if segment.remaining > 0:
            raise ConnectionError(
                f"the connection closed early, {segment.remaining} bytes short")

    # ------------------------------------------------------------------ #

    def _report(self):
        if self.on_progress:
            self.on_progress(total_done(self.segments), self.info.size)

    def _save(self, force=False):
        if not self.save_meta:
            return
        now = time.monotonic()
        if not force and now - self._last_saved < META_SAVE_SECONDS:
            return
        self._last_saved = now
        self.save_meta([segment.as_list() for segment in self.segments])
