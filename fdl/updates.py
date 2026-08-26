"""Look for a newer version of the tool, once a day, quietly.

Two rules decide everything here:

  * Nothing may ever stop the app or slow the menu down. No internet, a
    proxy in the way, a rate limit, or no release at all: each of those
    simply means "no news".
  * The look happens in a background thread, so the menu appears at once.

This matters most for the single .exe. yt-dlp is built into it and cannot be
updated with pip, so an old .exe slowly stops working on YouTube. A line in
the header is the only warning the user gets.
"""

import json
import re
import threading
import urllib.request
from datetime import date

from . import __version__

OWNER_REPO = "Mohammad-Hasan-it-96/free-downloader-tool"
LATEST_URL = f"https://api.github.com/repos/{OWNER_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{OWNER_REPO}/releases/latest"
TIMEOUT_SECONDS = 5


def parse_version(text):
    """'v2.10.1' -> (2, 10, 1). Text with no numbers gives ()."""
    numbers = [int(n) for n in re.findall(r"\d+", str(text or ""))[:3]]
    if not numbers:
        return ()
    while len(numbers) < 3:
        numbers.append(0)          # '2.1' and '2.1.0' must compare equal
    return tuple(numbers)


def is_newer(found, current=None):
    """True only when we are sure `found` is above `current`."""
    there = parse_version(found)
    here = parse_version(current if current is not None else __version__)
    if not there or not here:
        return False
    return there > here


def due_today(last_checked, today=None):
    """True when the last look did not happen today."""
    today = today or date.today().isoformat()
    return str(last_checked or "") != today


def fetch_latest_tag(open_url=None, timeout=TIMEOUT_SECONDS):
    """The newest tag name on GitHub, or None when we cannot tell."""
    request = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "free-downloader-tool",
    })
    try:
        opener = open_url or urllib.request.urlopen
        with opener(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
        data = json.loads(body)
    except Exception:      # noqa: BLE001 - a failed look is never an error
        return None
    if not isinstance(data, dict):
        return None
    return data.get("tag_name") or None


def check(cfg, open_url=None, today=None):
    """The newer tag name, or ''. Records that we looked, so this is daily."""
    if not cfg.check_updates:
        return ""
    today = today or date.today().isoformat()
    if not due_today(cfg.last_update_check, today):
        return ""

    cfg.last_update_check = today
    cfg.save()                      # write first, so a hang cannot loop daily

    tag = fetch_latest_tag(open_url)
    return tag if tag and is_newer(tag) else ""


class BackgroundCheck:
    """Runs `check` in a thread. Read `.newer` whenever you like."""

    def __init__(self):
        self.newer = ""

    def start(self, cfg, open_url=None):
        if not cfg.check_updates:
            return self
        thread = threading.Thread(target=self._run, args=(cfg, open_url),
                                  daemon=True)
        thread.start()
        return self

    def _run(self, cfg, open_url):
        try:
            self.newer = check(cfg, open_url)
        except Exception:  # noqa: BLE001 - a daemon thread must not shout
            self.newer = ""

    @property
    def message(self):
        """One short line for the header, or '' when there is no news."""
        if not self.newer:
            return ""
        return f"Version {self.newer} is out. Get it at {RELEASES_PAGE}"
