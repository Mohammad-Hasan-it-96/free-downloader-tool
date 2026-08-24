"""Download many links: check them, then run several at the same time."""

import concurrent.futures
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import http_engine, ytdlp_engine
from .categories import category_for
from .history import STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED
from .http_engine import DownloadError

KIND_FILE = "file"
KIND_MEDIA = "media"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"


@dataclass
class Item:
    url: str
    kind: str = KIND_FILE
    info: object = None
    name: str = ""
    category: str = ""
    dest: Path = None
    status: str = STATUS_PENDING
    path: Path = None
    error: str = ""
    note: str = ""
    resume_from: int = 0

    @property
    def label(self):
        return self.name or self.url

    @property
    def size(self):
        return getattr(self.info, "size", None)


@dataclass
class Summary:
    done: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)

    def add(self, item):
        if item.status == STATUS_DONE:
            self.done.append(item)
        elif item.status == STATUS_SKIPPED:
            self.skipped.append(item)
        else:
            self.failed.append(item)


def read_url_list(path):
    """Read one URL per line from a text file. Blank lines and # are ignored."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    urls = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def classify(url):
    """Decide which engine should handle this URL."""
    if ytdlp_engine.looks_like_media_site(url):
        return KIND_MEDIA
    return KIND_FILE


def dedupe(urls):
    """Keep the order, drop links that appear twice in the same list."""
    seen = set()
    result = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def prepare(urls, cfg, history=None, workers=4, on_checked=None):
    """Ask every server about its file, and mark links we already have.

    Media links are not probed, because yt-dlp decides the name itself.
    """
    items = [Item(url=url, kind=classify(url)) for url in dedupe(urls)]

    to_probe = [item for item in items if item.kind == KIND_FILE]
    if to_probe:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, min(workers, len(to_probe)))) as pool:
            futures = {pool.submit(_prepare_one, item, cfg, history): item
                       for item in to_probe}
            for future in concurrent.futures.as_completed(futures):
                future.result()
                if on_checked:
                    on_checked(futures[future])

    for item in items:
        if item.kind == KIND_MEDIA:
            item.category = "Videos"
            item.dest = cfg.folder_for("Videos")
    return items


def _prepare_one(item, cfg, history):
    try:
        item.info = http_engine.probe(item.url)
    except DownloadError as err:
        item.status = STATUS_FAILED
        item.error = str(err)
        item.name = item.url
        return item

    item.name = item.info.filename
    item.category = category_for(item.info.filename, item.info.content_type)
    item.dest = cfg.folder_for(item.category)

    part = Path(item.dest) / (item.name + ".part")
    if part.exists():
        try:
            item.resume_from = part.stat().st_size
        except OSError:
            item.resume_from = 0

    if history:
        earlier = history.already_have(item.url)
        if earlier:
            item.status = STATUS_SKIPPED
            item.note = f"already downloaded to {earlier['path']}"
    return item


def run_files(items, cfg, progress=None, workers=3, history=None):
    """Download the file items, several at the same time.

    `progress` is a MultiProgress. Its row numbers match `items`.
    """
    summary = Summary()
    targets = [(index, item) for index, item in enumerate(items)
               if item.kind == KIND_FILE and item.status == STATUS_PENDING]

    stop = threading.Event()
    if targets:
        count = max(1, min(workers, len(targets)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(_download_one, index, item, cfg, progress,
                                   history, stop)
                       for index, item in targets]
            try:
                for future in concurrent.futures.as_completed(futures):
                    future.result()
            except KeyboardInterrupt:
                stop.set()
                for future in futures:
                    future.cancel()
                raise

    for item in items:
        if item.kind == KIND_FILE:
            summary.add(item)
    return summary


def _download_one(index, item, cfg, progress, history, stop):
    if stop.is_set():
        item.status = STATUS_SKIPPED
        item.note = "cancelled"
        return item

    item.status = STATUS_RUNNING
    if progress:
        progress.begin(index, item.resume_from)

    def on_progress(done, total):
        if stop.is_set():
            raise KeyboardInterrupt("cancelled by the user")
        if progress:
            progress.update(index, done, total)

    try:
        saved = http_engine.download(
            item.url, item.dest, item.info, name=item.name,
            retries=cfg.retries, on_progress=on_progress)
    except DownloadError as err:
        item.status = STATUS_FAILED
        item.error = str(err)
        if progress:
            progress.finish(index, STATUS_FAILED, _short(str(err)))
    except KeyboardInterrupt:
        item.status = STATUS_FAILED
        item.error = "stopped by the user"
        if progress:
            progress.finish(index, STATUS_FAILED, "stopped")
    else:
        item.status = STATUS_DONE
        item.path = saved
        if progress:
            progress.finish(index, STATUS_DONE)

    if history:
        history.add(item.url, item.status, path=item.path, size=item.size,
                    category=item.category, engine="file",
                    error=item.error or None)
    return item


def _short(text, limit=48):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "~"
