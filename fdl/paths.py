"""Where the settings, the history, and the log are kept.

This depends on how the tool was started:

  * From the folder you downloaded (double-clicking the .bat file, or
    `python video_downloader.py`), the files sit next to the app. That is
    what people expect from a portable tool, and it keeps working exactly
    as before.
  * After `pip install`, the code lives inside Python's own folders, which
    should never be written to. The files then go to the normal place for
    user settings on each system.

`FDL_HOME` overrides both, which is also how the tests keep to a temporary
folder.
"""

import os
import sys
from pathlib import Path

APP_NAME = "FreeDownloaderTool"
UNIX_NAME = "free-downloader-tool"

PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_DIR.parent

# Files that only exist in a downloaded copy, not in an installed package.
SOURCE_MARKERS = ("pyproject.toml", "video_downloader.py")


def running_from_source():
    return any((SOURCE_ROOT / marker).exists() for marker in SOURCE_MARKERS)


def user_data_dir():
    """The normal place for a program's settings on this system."""
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / UNIX_NAME
    return Path.home() / ".config" / UNIX_NAME


def data_dir():
    """The folder holding config.json, history.json, and fdl.log."""
    override = os.environ.get("FDL_HOME")
    if override:
        return Path(override).expanduser()
    if running_from_source():
        return SOURCE_ROOT
    return user_data_dir()


def config_path():
    return data_dir() / "config.json"


def history_path():
    return data_dir() / "history.json"


def log_path():
    return data_dir() / "fdl.log"
