"""Checks that run before a download starts, so problems are caught early."""

import shutil
import urllib.parse
from pathlib import Path

from .categories import extension_of
from .term import human_size

# Keep some room free, so the disk never fills completely.
SPACE_MARGIN = 50 * 1024 * 1024      # 50 MB

HTML_TYPES = ("text/html", "application/xhtml+xml")
RISKY_CATEGORIES = ("Programs",)


def free_space(path):
    """Free bytes on the drive that holds `path`. None when it cannot tell.

    The folder may not exist yet, so we walk up to the first parent that does.
    """
    folder = Path(path)
    while True:
        try:
            return shutil.disk_usage(folder).free
        except (OSError, ValueError):
            if folder.parent == folder:
                return None
            folder = folder.parent


def check_space(dest_dir, needed_bytes):
    """Is there room for this download? Returns (ok, message)."""
    if not needed_bytes:
        return True, ""
    free = free_space(dest_dir)
    if free is None:
        return True, ""
    if free >= needed_bytes + SPACE_MARGIN:
        return True, ""
    return False, (f"Not enough free space. The file needs "
                   f"{human_size(needed_bytes)}, but only "
                   f"{human_size(free)} is free on that drive.")


def is_insecure_program(url, category):
    """True for a program downloaded over plain http, which is risky.

    Plain http has no protection, so somebody between you and the server can
    change the file on the way. For a program, that means running their code.
    """
    if category not in RISKY_CATEGORIES:
        return False
    return urllib.parse.urlsplit(url).scheme == "http"


def content_type_of(info):
    return (getattr(info, "content_type", "") or "").split(";")[0].strip().lower()


def looks_like_a_login_page(info):
    """True when we asked for a file and the server sent a web page.

    This usually means the link needs a login, or the file has moved. Saving
    that page would give you an HTML file with the wrong name.
    """
    if content_type_of(info) not in HTML_TYPES:
        return False
    extension = extension_of(getattr(info, "filename", "") or "")
    return extension not in ("html", "htm", "")


def login_page_message(info):
    return (f"The server sent a web page, not the file. The name says "
            f"'{info.filename}', but the answer is a web page. This usually "
            "means the link needs a login, or it has moved.")
