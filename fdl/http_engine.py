"""Download a direct file link, with resume.

How resume works:
  * The file is written as `name.part`.
  * A small `name.part.meta` file remembers the URL, the size, the server's
    ETag, and **how** the part was written.
  * On the next run we ask the server for the rest with a `Range` header,
    and we send `If-Range`. If the file on the server changed, the server
    sends the whole file again and we start over, so a broken mix of old
    and new bytes can never happen.

There are three ways a part file can be written, and they are not
interchangeable:

  "stream"    one connection, bytes in order. How much is done is simply
              the size of the part file.
  "segments"  several connections at once, bytes out of order. The part
              file is created at full size from the start, so its size
              means nothing. Progress lives in the meta file.
  "aria2"     written by the aria2c program, which keeps its own control
              file. Only aria2c can continue it.

The mode is always read from the meta file before resuming, so a part file
is never continued by the wrong method.
"""

import base64
import http.client
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import segmented
from .limiter import RateLimiter
from .naming import choose_filename, unique_path

CHUNK_SIZE = 64 * 1024
TIMEOUT_SECONDS = 30
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36 FreeDownloaderTool/2.0")

MODE_STREAM = "stream"
MODE_SEGMENTS = "segments"
MODE_ARIA2 = "aria2"

# Errors that are worth retrying, because they are usually temporary.
# http.client.HTTPException covers a connection that dies in the middle of
# a response, which is exactly the case resume exists for.
RETRYABLE = (urllib.error.URLError, socket.timeout, ConnectionError,
             TimeoutError, http.client.HTTPException, OSError)


class DownloadError(Exception):
    """The download cannot go on, and retrying will not help."""


@dataclass
class RemoteInfo:
    url: str                 # the final URL, after redirects
    size: int = None         # None when the server does not say
    resumable: bool = False
    etag: str = None
    last_modified: str = None
    filename: str = "download"
    content_type: str = None


def split_login(url):
    """Take `user:password@` out of a link.

    Returns (clean_url, header_value_or_None). A link written as
    `https://user:pass@host/file.zip` is a normal way to pass a login, but
    the parts must travel in an `Authorization` header, not in the address.
    """
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url, None
    if "@" not in parts.netloc:
        return url, None

    login, _, host = parts.netloc.rpartition("@")
    if not login:
        return url, None

    user, _, password = login.partition(":")
    user = urllib.parse.unquote(user)
    password = urllib.parse.unquote(password)
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode()
    clean = urllib.parse.urlunsplit(
        (parts.scheme, host, parts.path, parts.query, parts.fragment))
    return clean, "Basic " + token


def _request(url, extra_headers=None):
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    url, authorization = split_login(url)
    if authorization:
        headers["Authorization"] = authorization
    if extra_headers:
        headers.update(extra_headers)
    return urllib.request.Request(url, headers=headers)


# urllib sends everything through the system proxy, including addresses on
# this computer. A proxy cannot reach them, so local links must skip it.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"}
_no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_forced_opener = None


def set_opener(opener):
    """Use one opener for every request, or None to go back to the default."""
    global _forced_opener
    _forced_opener = opener


PROXY_SYSTEM = ""        # follow the computer's own proxy settings
PROXY_NONE = "none"      # never use a proxy


def configure_proxy(setting):
    """Apply a proxy setting. Returns a short line describing what was set.

    `""` follows the system settings, `"none"` turns the proxy off, and an
    address such as `http://host:3128` is used for http and https.
    """
    setting = (setting or "").strip()
    if not setting:
        set_opener(None)
        return "the computer's own proxy settings"
    if setting.lower() in (PROXY_NONE, "off", "direct"):
        set_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
        return "no proxy"

    address = setting if "://" in setting else "http://" + setting
    handler = urllib.request.ProxyHandler({"http": address, "https": address})
    set_opener(urllib.request.build_opener(handler))
    return address


def _is_local(host):
    host = (host or "").lower()
    return host in _LOCAL_HOSTS or host.startswith("127.")


def _urlopen(request, timeout):
    if _is_local(urllib.parse.urlsplit(request.full_url).hostname):
        return _no_proxy_opener.open(request, timeout=timeout)
    if _forced_opener is not None:
        return _forced_opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _total_from_content_range(header):
    """'bytes 0-0/12345' -> 12345"""
    if not header or "/" not in header:
        return None
    return _int_or_none(header.rsplit("/", 1)[1].strip())


# --------------------------------- probe -------------------------------- #

def probe(url, extra_headers=None, timeout=TIMEOUT_SECONDS):
    """Ask the server about the file, without downloading it.

    We use a one-byte Range request instead of HEAD, because many servers
    answer HEAD wrongly or block it.
    """
    if not urllib.parse.urlsplit(url).scheme in ("http", "https"):
        raise DownloadError("Only http:// and https:// links are supported "
                            "by the file downloader.")

    headers = dict(extra_headers or {})
    headers["Range"] = "bytes=0-0"

    try:
        response = _urlopen(_request(url, headers), timeout)
    except urllib.error.HTTPError as err:
        if err.code == 416:  # the server dislikes Range; try without it
            return _probe_plain(url, extra_headers, timeout)
        raise DownloadError(_http_message(err)) from err
    except RETRYABLE as err:
        raise DownloadError(f"Cannot reach the server: {err}") from err

    with response:
        headers_in = response.headers
        status = getattr(response, "status", response.getcode())
        if status == 206:
            size = _total_from_content_range(headers_in.get("Content-Range"))
            resumable = True
        else:
            # The server ignored Range and is sending everything. We do not
            # read the body here, we just close the connection.
            size = _int_or_none(headers_in.get("Content-Length"))
            resumable = "bytes" in (headers_in.get("Accept-Ranges") or
                                    "").lower()
        return _build_info(response.geturl(), headers_in, size, resumable)


def _probe_plain(url, extra_headers, timeout):
    try:
        response = _urlopen(_request(url, extra_headers), timeout)
    except urllib.error.HTTPError as err:
        raise DownloadError(_http_message(err)) from err
    except RETRYABLE as err:
        raise DownloadError(f"Cannot reach the server: {err}") from err
    with response:
        headers_in = response.headers
        size = _int_or_none(headers_in.get("Content-Length"))
        resumable = "bytes" in (headers_in.get("Accept-Ranges") or "").lower()
        return _build_info(response.geturl(), headers_in, size, resumable)


def _build_info(final_url, headers_in, size, resumable):
    return RemoteInfo(
        url=final_url,
        size=size,
        resumable=resumable,
        etag=headers_in.get("ETag"),
        last_modified=headers_in.get("Last-Modified"),
        content_type=headers_in.get("Content-Type"),
        filename=choose_filename(final_url,
                                 headers_in.get("Content-Disposition"),
                                 headers_in.get("Content-Type")),
    )


def _http_message(err):
    common = {
        401: "The link needs a login (401).",
        403: "The server refused the download (403).",
        404: "The file was not found (404).",
        429: "Too many requests (429). Wait a while and try again.",
    }
    return common.get(err.code, f"Server error {err.code}: {err.reason}")


# --------------------------- resume bookkeeping ------------------------- #

def meta_path(part_path):
    return Path(part_path).with_name(Path(part_path).name + ".meta")


def _base_meta(url, info, mode):
    return {"url": url, "size": info.size, "etag": info.etag,
            "last_modified": info.last_modified, "mode": mode}


def read_meta(part_path):
    try:
        data = json.loads(meta_path(part_path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_meta(part_path, meta):
    try:
        meta_path(part_path).write_text(json.dumps(meta), encoding="utf-8")
    except OSError:
        pass  # resume is a convenience; never fail the download for this


def clear_meta(part_path):
    try:
        meta_path(part_path).unlink()
    except OSError:
        pass


def meta_matches(meta, url, info):
    """True when a saved meta file describes the same download."""
    if not meta or meta.get("url") != url:
        return False
    if info.etag and meta.get("etag") != info.etag:
        return False
    if info.size is not None and meta.get("size") != info.size:
        return False
    return True


def part_progress(part_path, meta):
    """How many bytes of this part file are really downloaded."""
    mode = (meta or {}).get("mode", MODE_STREAM)
    if mode == MODE_SEGMENTS:
        raw = (meta or {}).get("segments") or []
        try:
            return sum(entry[2] for entry in raw)
        except (IndexError, TypeError):
            return 0
    try:
        return Path(part_path).stat().st_size
    except OSError:
        return 0


# ------------------------------ downloading ----------------------------- #

def download(url, dest_dir, info=None, *, name=None, extra_headers=None,
             retries=5, connections=1, speed_limit=0, on_progress=None,
             on_retry=None, stop_event=None):
    """Download `url` into `dest_dir` and return the final path.

    `connections` above 1 splits the file and downloads the parts at the
    same time, but only when the server supports it.
    `speed_limit` is in bytes per second; 0 means no limit.
    `on_progress(done_bytes, total_or_None)` is called while data arrives.
    `on_retry(attempt, total_attempts, reason, wait_seconds)` runs before a
    retry.

    A part file left by aria2c cannot be continued here, so it is started
    again from zero.
    """
    info = info or probe(url, extra_headers)
    dest_dir = Path(dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise DownloadError(f"Cannot use the folder {dest_dir}: {err}") from err

    file_name = name or info.filename
    part_path = dest_dir / (file_name + ".part")
    limiter = RateLimiter(speed_limit)

    mode, segments = _plan(part_path, url, info, connections)

    if mode == MODE_SEGMENTS:
        _download_segments(url, part_path, info, segments, extra_headers,
                           retries, limiter, on_progress, on_retry,
                           stop_event)
    else:
        _download_stream(url, part_path, info, extra_headers, retries,
                         limiter, on_progress, on_retry)

    return _finalise(part_path, dest_dir, file_name, info)


def _plan(part_path, url, info, connections):
    """Decide how to download, and keep any part file we can still use."""
    existing = read_meta(part_path) if part_path.exists() else None
    usable = existing if meta_matches(existing, url, info) else None

    if usable:
        mode = usable.get("mode", MODE_STREAM)
        if mode == MODE_SEGMENTS:
            segments = segmented.segments_from_meta(usable, info.size)
            if segments:
                return MODE_SEGMENTS, segments
        elif mode == MODE_STREAM:
            return MODE_STREAM, None
        # aria2, or a meta file we cannot trust: fall through and restart.

    _remove_part(part_path)

    if segmented.should_split(info, connections):
        count = segmented.wanted_connections(info.size, connections)
        segments = segmented.build_segments(info.size, count)
        write_meta(part_path, {**_base_meta(url, info, MODE_SEGMENTS),
                               "segments": [s.as_list() for s in segments]})
        return MODE_SEGMENTS, segments

    write_meta(part_path, _base_meta(url, info, MODE_STREAM))
    return MODE_STREAM, None


def _remove_part(part_path):
    if part_path.exists():
        try:
            part_path.unlink()
        except OSError as err:
            raise DownloadError(f"Cannot replace {part_path}: {err}") from err
    clear_meta(part_path)


def _download_segments(url, part_path, info, segments, extra_headers, retries,
                       limiter, on_progress, on_retry, stop_event):
    base = _base_meta(url, info, MODE_SEGMENTS)

    def save(rows):
        write_meta(part_path, {**base, "segments": rows})

    def open_range(headers):
        return _urlopen(_request(info.url, headers), TIMEOUT_SECONDS)

    job = segmented.SegmentedDownload(
        url, part_path, info, segments, extra_headers=extra_headers,
        retries=retries, limiter=limiter, on_progress=on_progress,
        on_retry=on_retry, save_meta=save, stop_event=stop_event,
        urlopen=open_range)

    try:
        job.run()
    except urllib.error.HTTPError as err:
        raise DownloadError(_http_message(err)) from err
    except RETRYABLE as err:
        raise DownloadError(f"Gave up after {retries} retries: {err}") from err


def _download_stream(url, part_path, info, extra_headers, retries, limiter,
                     on_progress, on_retry):
    start_at = part_path.stat().st_size if part_path.exists() else 0
    if info.size is not None and start_at > info.size:
        _remove_part(part_path)
        write_meta(part_path, _base_meta(url, info, MODE_STREAM))
        start_at = 0
    if info.size is not None and start_at == info.size and start_at > 0:
        return

    attempt = 0
    while True:
        try:
            _fetch(info.url, part_path, start_at, info, extra_headers,
                   limiter, on_progress)
            return
        except DownloadError:
            raise
        except RETRYABLE as err:
            attempt += 1
            if attempt > retries:
                raise DownloadError(
                    f"Gave up after {retries} retries: {err}") from err
            wait = min(30, 2 ** attempt)
            if on_retry:
                on_retry(attempt, retries, str(err), wait)
            time.sleep(wait)
            start_at = part_path.stat().st_size if part_path.exists() else 0
            if not info.resumable:
                start_at = 0


def _fetch(url, part_path, start_at, info, extra_headers, limiter,
           on_progress):
    """One attempt. Raises a retryable error, or returns when finished."""
    headers = dict(extra_headers or {})
    if start_at > 0:
        headers["Range"] = f"bytes={start_at}-"
        fingerprint = info.etag or info.last_modified
        if fingerprint:
            headers["If-Range"] = fingerprint

    try:
        response = _urlopen(_request(url, headers), TIMEOUT_SECONDS)
    except urllib.error.HTTPError as err:
        if err.code in (416, 412) and start_at > 0:
            # Our part file no longer matches. Start again from zero.
            start_at = 0
            headers.pop("Range", None)
            headers.pop("If-Range", None)
            response = _urlopen(_request(url, headers), TIMEOUT_SECONDS)
        elif 500 <= err.code < 600:
            raise ConnectionError(_http_message(err)) from err
        else:
            raise DownloadError(_http_message(err)) from err

    with response:
        status = getattr(response, "status", response.getcode())
        if start_at > 0 and status != 206:
            # The server ignored our Range and is sending the whole file.
            start_at = 0
        mode = "ab" if start_at > 0 else "wb"

        total = info.size
        if total is None:
            length = _int_or_none(response.headers.get("Content-Length"))
            if length is not None:
                total = length + start_at

        done = start_at
        with open(part_path, mode) as out:
            while True:
                want = CHUNK_SIZE
                if limiter and not limiter.unlimited:
                    want = limiter.chunk_size(want)
                    limiter.take(want)
                chunk = response.read(want)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if on_progress:
                    on_progress(done, total)

        # A dropped connection can end the loop quietly, with no error and a
        # short file. Treat that as a network problem, so it is retried and
        # continues from the bytes we already have.
        if total is not None and done < total:
            raise ConnectionError(
                f"the connection closed early at {done} of {total} bytes")


def _finalise(part_path, dest_dir, file_name, info):
    """Check the size, then rename `.part` to the real name."""
    actual = part_path.stat().st_size
    if info.size is not None and actual != info.size:
        raise DownloadError(
            f"The download is incomplete: got {actual} bytes, "
            f"expected {info.size}. The .part file was kept, so running the "
            "download again will continue from there.")

    final_path = unique_path(dest_dir / file_name)
    try:
        part_path.replace(final_path)
    except OSError as err:
        raise DownloadError(f"Cannot save {final_path}: {err}") from err
    clear_meta(part_path)
    return final_path


def unfinished_downloads(base_dir):
    """Find every `.part` file under `base_dir`, newest first."""
    base = Path(base_dir)
    if not base.exists():
        return []
    found = []
    for part in base.rglob("*.part"):
        meta = read_meta(part)
        if not meta or not meta.get("url"):
            continue
        try:
            part.stat()
        except OSError:
            continue
        found.append({"part": part, "url": meta["url"],
                      "size": meta.get("size"),
                      "mode": meta.get("mode", MODE_STREAM),
                      "done": part_progress(part, meta)})
    found.sort(key=lambda item: item["part"].stat().st_mtime, reverse=True)
    return found
