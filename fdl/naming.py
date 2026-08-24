"""Turn a URL or an HTTP header into a safe file name."""

import mimetypes
import re
import unicodedata
import urllib.parse
from pathlib import Path

from .categories import split_extension

FALLBACK_NAME = "download"
MAX_NAME_LENGTH = 150  # characters, extension included

_ILLEGAL = r'<>:"/\\|?*'
_ILLEGAL_RE = re.compile(f"[{re.escape(_ILLEGAL)}]")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

# Names that Windows refuses, even with an extension.
_RESERVED = {"CON", "PRN", "AUX", "NUL"}
_RESERVED |= {f"COM{i}" for i in range(1, 10)}
_RESERVED |= {f"LPT{i}" for i in range(1, 10)}


def sanitize(name, fallback=FALLBACK_NAME):
    """Make a file name that is safe on Windows, macOS, and Linux."""
    if not name:
        return fallback

    name = unicodedata.normalize("NFC", name)
    # A server may send a path. Keep only the last part.
    name = name.replace("\\", "/").split("/")[-1]
    name = _CONTROL_RE.sub("", name)
    name = _ILLEGAL_RE.sub("_", name)
    name = name.strip().strip(".").strip()

    if not name:
        return fallback

    stem, ext = split_extension(name)
    if stem.upper() in _RESERVED:
        stem = f"{stem}_file"

    # Keep the extension when the name is too long.
    if len(stem) + len(ext) > MAX_NAME_LENGTH:
        stem = stem[: max(1, MAX_NAME_LENGTH - len(ext))].rstrip()

    result = f"{stem}{ext}".strip()
    return result or fallback


def filename_from_disposition(header):
    """Read the file name from a Content-Disposition header.

    Supports both `filename="x.zip"` and the UTF-8 form
    `filename*=UTF-8''x%20y.zip`. Returns None when there is none.
    """
    if not header:
        return None

    # The UTF-8 form wins, because it keeps non-English letters.
    star = re.search(r"filename\*\s*=\s*([^;]+)", header, re.IGNORECASE)
    if star:
        value = star.group(1).strip().strip('"')
        parts = value.split("'", 2)
        encoded = parts[2] if len(parts) == 3 else value
        charset = parts[0] or "utf-8" if len(parts) == 3 else "utf-8"
        try:
            return urllib.parse.unquote(encoded, encoding=charset,
                                        errors="replace") or None
        except (LookupError, ValueError):
            return urllib.parse.unquote(encoded) or None

    plain = re.search(r'filename\s*=\s*"([^"]*)"', header, re.IGNORECASE)
    if not plain:
        plain = re.search(r"filename\s*=\s*([^;]+)", header, re.IGNORECASE)
    if plain:
        return plain.group(1).strip().strip('"') or None
    return None


def filename_from_url(url):
    """Read the file name from the path part of a URL. None when unclear."""
    try:
        path = urllib.parse.urlsplit(url).path
    except ValueError:
        return None
    if not path:
        return None
    last = urllib.parse.unquote(path.rstrip("/").split("/")[-1])
    return last or None


def add_extension_if_missing(name, content_type):
    """Add an extension guessed from the MIME type, when the name has none."""
    _, ext = split_extension(name)
    if ext or not content_type:
        return name
    mime = content_type.split(";")[0].strip().lower()
    if not mime or mime == "application/octet-stream":
        return name
    guessed = mimetypes.guess_extension(mime)
    if not guessed or guessed == ".ksh":  # python maps text/plain oddly
        return name
    return name + guessed


def choose_filename(url, content_disposition=None, content_type=None):
    """Pick the best file name we can, in this order:
    Content-Disposition header, then the URL path, then a fallback."""
    candidate = filename_from_disposition(content_disposition)
    if not candidate:
        candidate = filename_from_url(url)

    name = sanitize(candidate or FALLBACK_NAME)
    if name == FALLBACK_NAME or not split_extension(name)[1]:
        name = add_extension_if_missing(name, content_type)
    return sanitize(name)


def unique_path(path):
    """Return a path that does not exist yet, by adding ' (1)', ' (2)', ..."""
    path = Path(path)
    if not path.exists():
        return path
    stem, ext = split_extension(path.name)
    counter = 1
    while True:
        candidate = path.with_name(f"{stem} ({counter}){ext}")
        if not candidate.exists():
            return candidate
        counter += 1
