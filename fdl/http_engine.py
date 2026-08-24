"""Download a direct file link, with resume.

How resume works:
  * The file is written as `name.part`.
  * A small `name.part.meta` file remembers the URL, the size, and the
    server's ETag.
  * On the next run we ask the server for the rest of the file with a
    `Range` header, and we send `If-Range`. If the file on the server
    changed, the server sends the whole file again and we start over, so a
    broken mix of old and new bytes can never happen.
"""

import http.client
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .naming import choose_filename, unique_path

CHUNK_SIZE = 64 * 1024
TIMEOUT_SECONDS = 30
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36 FreeDownloaderTool/2.0")

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


def _request(url, extra_headers=None):
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if extra_headers:
        headers.update(extra_headers)
    return urllib.request.Request(url, headers=headers)


# urllib sends everything through the system proxy, including addresses on
# this computer. A proxy cannot reach them, so local links must skip it.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"}
_no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_forced_opener = None


def set_opener(opener):
    """Use one opener for every request, or None to go back to the default.

    This is the place where proxy settings will be applied later.
    """
    global _forced_opener
    _forced_opener = opener


def _is_local(host):
    host = (host or "").lower()
    return host in _LOCAL_HOSTS or host.startswith("127.")


def _urlopen(request, timeout):
    if _forced_opener is not None:
        return _forced_opener.open(request, timeout=timeout)
    if _is_local(urllib.parse.urlsplit(request.full_url).hostname):
        return _no_proxy_opener.open(request, timeout=timeout)
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

def _meta_path(part_path):
    return part_path.with_name(part_path.name + ".meta")


def _meta_for(url, info):
    return {"url": url, "size": info.size, "etag": info.etag,
            "last_modified": info.last_modified}


def _read_meta(part_path):
    try:
        data = json.loads(_meta_path(part_path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_meta(part_path, meta):
    try:
        _meta_path(part_path).write_text(json.dumps(meta), encoding="utf-8")
    except OSError:
        pass  # resume is a convenience; never fail the download for this


def _clear_meta(part_path):
    try:
        _meta_path(part_path).unlink()
    except OSError:
        pass


def _resume_point(part_path, url, info):
    """How many bytes we can keep from an earlier run. 0 means start over."""
    if not part_path.exists():
        return 0
    if not info.resumable:
        return 0

    meta = _read_meta(part_path)
    wanted = _meta_for(url, info)
    if not meta or meta.get("url") != wanted["url"]:
        return 0
    # If the server gives us a fingerprint, it must match.
    if wanted["etag"] and meta.get("etag") != wanted["etag"]:
        return 0
    if wanted["size"] is not None and meta.get("size") != wanted["size"]:
        return 0

    have = part_path.stat().st_size
    if info.size is not None and have > info.size:
        return 0  # the part file is longer than the real file: it is broken
    return have


# ------------------------------ downloading ----------------------------- #

def download(url, dest_dir, info=None, *, name=None, extra_headers=None,
             retries=5, on_progress=None, on_retry=None):
    """Download `url` into `dest_dir` and return the final path.

    `on_progress(done_bytes, total_or_None)` is called while data arrives.
    `on_retry(attempt, total_attempts, reason, wait_seconds)` is called
    before each retry.
    """
    info = info or probe(url, extra_headers)
    dest_dir = Path(dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise DownloadError(f"Cannot use the folder {dest_dir}: {err}") from err

    file_name = name or info.filename
    part_path = dest_dir / (file_name + ".part")

    start_at = _resume_point(part_path, url, info)
    if start_at == 0 and part_path.exists():
        try:
            part_path.unlink()
        except OSError as err:
            raise DownloadError(f"Cannot replace {part_path}: {err}") from err
    _write_meta(part_path, _meta_for(url, info))

    # Already complete from an earlier run.
    if info.size is not None and start_at == info.size and start_at > 0:
        return _finalise(part_path, dest_dir, file_name, info)

    attempt = 0
    while True:
        try:
            _fetch(info.url, part_path, start_at, info, extra_headers,
                   on_progress)
            break
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

    return _finalise(part_path, dest_dir, file_name, info)


def _fetch(url, part_path, start_at, info, extra_headers, on_progress):
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
            response = _urlopen(_request(url, headers),
                                TIMEOUT_SECONDS)
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
                chunk = response.read(CHUNK_SIZE)
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
    _clear_meta(part_path)
    return final_path


def unfinished_downloads(base_dir):
    """Find every `.part` file under `base_dir`, newest first."""
    base = Path(base_dir)
    if not base.exists():
        return []
    found = []
    for part in base.rglob("*.part"):
        meta = _read_meta(part)
        if not meta or not meta.get("url"):
            continue
        try:
            have = part.stat().st_size
        except OSError:
            continue
        found.append({"part": part, "url": meta["url"],
                      "size": meta.get("size"), "done": have})
    found.sort(key=lambda item: item["part"].stat().st_mtime, reverse=True)
    return found
