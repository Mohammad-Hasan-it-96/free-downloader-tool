"""A record of what was downloaded, kept in one JSON file."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


def now_text():
    """The time now, as text, without microseconds."""
    return datetime.now(timezone.utc).astimezone().replace(
        microsecond=0).isoformat()


def short_time(iso_text):
    """'2026-08-24T14:05:00+03:00' -> '2026-08-24 14:05'."""
    if not iso_text:
        return "?"
    try:
        moment = datetime.fromisoformat(iso_text)
    except ValueError:
        return iso_text[:16]
    return moment.strftime("%Y-%m-%d %H:%M")


class History:
    """The newest entry is always first."""

    def __init__(self, path, limit=500):
        self.path = Path(path)
        self.limit = limit
        self.entries = []
        # Downloads run in several threads, and each one records a result.
        self._lock = threading.Lock()

    @classmethod
    def load(cls, path, limit=500):
        history = cls(path, limit)
        try:
            data = json.loads(history.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return history
        if isinstance(data, list):
            history.entries = [e for e in data if isinstance(e, dict)]
        return history

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(
                json.dumps(self.entries[: self.limit], indent=2,
                           ensure_ascii=False),
                encoding="utf-8")
            temp.replace(self.path)
            return True, ""
        except OSError as err:
            return False, str(err)

    # ------------------------------------------------------------------ #

    def add(self, url, status, path=None, size=None, category=None,
            engine="file", error=None):
        with self._lock:
            return self._add(url, status, path, size, category, engine, error)

    def _add(self, url, status, path, size, category, engine, error):
        entry = {
            "url": url,
            "status": status,
            "path": str(path) if path else None,
            "size": size,
            "category": category,
            "engine": engine,
            "error": error,
            "when": now_text(),
        }
        self.entries.insert(0, entry)
        if self.limit:
            del self.entries[self.limit:]
        self.save()
        return entry

    def find_done(self, url):
        """The newest successful entry for this URL, or None."""
        for entry in self.entries:
            if entry.get("url") == url and entry.get("status") == STATUS_DONE:
                return entry
        return None

    def already_have(self, url):
        """True when this URL was downloaded and the file is still there."""
        entry = self.find_done(url)
        if not entry or not entry.get("path"):
            return None
        if Path(entry["path"]).exists():
            return entry
        return None

    def recent(self, count=20):
        return self.entries[:count]

    def clear(self):
        self.entries = []
        return self.save()

    def counts(self):
        result = {STATUS_DONE: 0, STATUS_FAILED: 0, STATUS_SKIPPED: 0}
        for entry in self.entries:
            status = entry.get("status")
            if status in result:
                result[status] += 1
        return result
