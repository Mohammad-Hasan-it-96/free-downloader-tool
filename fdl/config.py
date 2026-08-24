"""Settings: load, check, save, and upgrade from the old format."""

import json
import os
from pathlib import Path

from .categories import CATEGORY_ORDER

CONFIG_VERSION = 2
BROWSERS = ["edge", "chrome", "brave", "firefox", "opera", "vivaldi",
            "chromium"]


def default_base_dir():
    """Prefer D:\\Downloads on Windows, so the C: drive stays free."""
    if os.name == "nt":
        if Path("D:\\").exists():
            return "D:\\Downloads"
        return str(Path.home() / "Downloads" / "FreeDownloader")
    return str(Path.home() / "Downloads")


def defaults():
    return {
        "version": CONFIG_VERSION,
        "base_dir": default_base_dir(),
        "sort_by_type": True,
        "category_folders": {name: name for name in CATEGORY_ORDER},
        "cookies_browser": "",
        "retries": 5,
        "max_parallel": 3,
        "history_limit": 500,
        "notice": "",
    }


class Config:
    """Settings held in one JSON file, next to the package."""

    def __init__(self, path, data=None):
        self.path = Path(path)
        self.data = data if data is not None else defaults()

    # ------------------------------ loading ------------------------------ #

    @classmethod
    def load(cls, path):
        cfg = cls(path)
        raw = cls._read_raw(cfg.path)
        if raw is None:
            return cfg
        if not isinstance(raw, dict):
            return cfg

        if int(raw.get("version", 1) or 1) < CONFIG_VERSION:
            raw = migrate(raw)
        cfg.data = _validated(raw)
        return cfg

    @staticmethod
    def _read_raw(path):
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(self):
        """Write settings. Returns (True, '') or (False, reason)."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False),
                            encoding="utf-8")
            temp.replace(self.path)
            return True, ""
        except OSError as err:
            return False, str(err)

    # ------------------------------ values ------------------------------- #

    @property
    def base_dir(self):
        return self.data["base_dir"]

    @base_dir.setter
    def base_dir(self, value):
        self.data["base_dir"] = str(value)

    @property
    def sort_by_type(self):
        return self.data["sort_by_type"]

    @sort_by_type.setter
    def sort_by_type(self, value):
        self.data["sort_by_type"] = bool(value)

    @property
    def cookies_browser(self):
        return self.data["cookies_browser"]

    @cookies_browser.setter
    def cookies_browser(self, value):
        self.data["cookies_browser"] = value or ""

    @property
    def retries(self):
        return self.data["retries"]

    @property
    def max_parallel(self):
        return self.data["max_parallel"]

    @max_parallel.setter
    def max_parallel(self, value):
        self.data["max_parallel"] = max(1, min(8, int(value)))

    @property
    def history_limit(self):
        return self.data["history_limit"]

    def take_notice(self):
        """Return a one-time message and clear it."""
        message = self.data.get("notice", "")
        if message:
            self.data["notice"] = ""
            self.save()
        return message

    def folder_for(self, category):
        """Full folder path for a category, following the sort setting."""
        base = Path(self.base_dir)
        if not self.sort_by_type:
            return base
        name = self.data["category_folders"].get(category, category)
        return base / name


# ---------------------------------------------------------------------- #

def _validated(raw):
    """Keep only values with the right type. Anything else falls back."""
    result = defaults()

    base = raw.get("base_dir")
    if isinstance(base, str) and base.strip():
        result["base_dir"] = base.strip()

    if isinstance(raw.get("sort_by_type"), bool):
        result["sort_by_type"] = raw["sort_by_type"]

    folders = raw.get("category_folders")
    if isinstance(folders, dict):
        for category in CATEGORY_ORDER:
            value = folders.get(category)
            if isinstance(value, str) and value.strip():
                result["category_folders"][category] = value.strip()

    browser = raw.get("cookies_browser")
    if isinstance(browser, str) and browser.strip().lower() in BROWSERS:
        result["cookies_browser"] = browser.strip().lower()

    retries = raw.get("retries")
    if isinstance(retries, int) and not isinstance(retries, bool):
        result["retries"] = max(0, min(20, retries))

    parallel = raw.get("max_parallel")
    if isinstance(parallel, int) and not isinstance(parallel, bool):
        result["max_parallel"] = max(1, min(8, parallel))

    limit = raw.get("history_limit")
    if isinstance(limit, int) and not isinstance(limit, bool):
        result["history_limit"] = max(0, min(10000, limit))

    notice = raw.get("notice")
    if isinstance(notice, str):
        result["notice"] = notice

    return result


def migrate(raw):
    """Upgrade version 1 settings (the video-only tool) to version 2.

    Version 1 had one folder for everything, usually D:\\Videos. That folder
    now becomes the `Videos` category, and the folder above it becomes the
    base. The user is told once, and can change it in the menu.
    """
    upgraded = defaults()

    old_dir = raw.get("download_dir")
    if isinstance(old_dir, str) and old_dir.strip():
        old_path = Path(old_dir.strip())
        parent = old_path.parent
        looks_like_category = old_path.name.lower() in {
            c.lower() for c in CATEGORY_ORDER}
        if looks_like_category and str(parent) not in ("", "."):
            upgraded["base_dir"] = str(parent)
        else:
            upgraded["base_dir"] = str(old_path)
        upgraded["notice"] = (
            f"Settings upgraded. Your old folder was {old_path}. "
            f"Downloads now go to {upgraded['base_dir']}, "
            "sorted into folders by file type. "
            "Change it any time with the 'Change base folder' option."
        )

    browser = raw.get("cookies_browser")
    if isinstance(browser, str):
        upgraded["cookies_browser"] = browser

    return upgraded
