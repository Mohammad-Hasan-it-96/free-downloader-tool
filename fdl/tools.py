"""Find helper programs (ffmpeg, deno, aria2c) without asking the user."""

import importlib.util
import os
import shutil
from pathlib import Path

IS_WINDOWS = os.name == "nt"


def _exe(name):
    return f"{name}.exe" if IS_WINDOWS else name


def _search(exe_name, winget_globs=(), extra_dirs=()):
    """Return the folder holding `exe_name`, or None.

    PATH is checked first, then the folders where winget installs things,
    then a few common install folders.
    """
    found = shutil.which(exe_name)
    if found:
        return str(Path(found).parent)

    candidates = []
    if IS_WINDOWS:
        localappdata = os.environ.get("LOCALAPPDATA", "")
        if localappdata:
            packages = Path(localappdata) / "Microsoft" / "WinGet" / "Packages"
            for pattern in winget_globs:
                try:
                    candidates += list(packages.glob(pattern))
                except OSError:
                    pass
    candidates += [Path(d) for d in extra_dirs if d]

    for folder in candidates:
        try:
            if (folder / exe_name).exists():
                return str(folder)
        except OSError:
            continue
    return None


def find_ffmpeg():
    return _search(_exe("ffmpeg"),
                   winget_globs=["Gyan.FFmpeg*/**/bin"],
                   extra_dirs=[r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin",
                               "/usr/local/bin", "/opt/homebrew/bin"])


def find_deno():
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    extra = [os.path.join(home, ".deno", "bin")] if home else []
    return _search(_exe("deno"), winget_globs=["DenoLand.Deno*/**"],
                   extra_dirs=extra)


def find_aria2c():
    """aria2c is optional. It is used later for faster downloads."""
    return _search(_exe("aria2c"), winget_globs=["aria2.aria2*/**"],
                   extra_dirs=["/usr/local/bin", "/opt/homebrew/bin"])


def ytdlp_installed():
    return importlib.util.find_spec("yt_dlp") is not None


class Toolbox:
    """Where the helper programs are. Found once at startup."""

    def __init__(self):
        self.refresh()

    def refresh(self):
        self.ffmpeg_dir = find_ffmpeg()
        self.deno_dir = find_deno()
        self.aria2c_dir = find_aria2c()

    @property
    def has_ffmpeg(self):
        return bool(self.ffmpeg_dir)

    def env(self):
        """An environment where deno is on PATH, so yt-dlp can find it."""
        env = os.environ.copy()
        if self.deno_dir:
            env["PATH"] = self.deno_dir + os.pathsep + env.get("PATH", "")
        return env
