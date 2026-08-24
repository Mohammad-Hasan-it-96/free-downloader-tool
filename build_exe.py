#!/usr/bin/env python3
"""Build one .exe file, for people who do not have Python.

Run:
    pip install pyinstaller
    python build_exe.py

The result is `dist/FreeDownloader.exe`. It holds Python and yt-dlp inside,
so it is large (about 30 MB) and it takes a few minutes to build.

ffmpeg, deno, and aria2c are NOT included. The .exe still finds them if they
are installed, and it explains what to do when they are missing.
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "FreeDownloader"


def build():
    if not (HERE / "fdl" / "app.py").exists():
        print("Run this from the folder that holds the 'fdl' folder.")
        return 1

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed. Run:")
        print(f'  "{sys.executable}" -m pip install pyinstaller')
        return 1

    command = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", NAME,
        "--noconfirm",
        "--clean",
        # yt-dlp loads its site handlers by name, so PyInstaller cannot see
        # them by reading the code. This pulls all of them in.
        "--collect-all", "yt_dlp",
        "--distpath", str(HERE / "dist"),
        "--workpath", str(HERE / "build"),
        "--specpath", str(HERE / "build"),
        # Start from the launcher, not from fdl/__main__.py. PyInstaller
        # runs the entry file as a plain script, and __main__.py uses
        # relative imports (`from .app import run`), which only work inside
        # a package. The launcher uses `from fdl.app import run` instead.
        str(HERE / "video_downloader.py"),
    ]

    print("Building. This takes a few minutes...\n")
    result = subprocess.run(command)
    if result.returncode != 0:
        print("\nThe build failed. The lines above say why.")
        return result.returncode

    exe = HERE / "dist" / (NAME + (".exe" if sys.platform == "win32" else ""))
    if not exe.exists():
        print("\nThe build finished but the file is missing.")
        return 1

    size_mb = exe.stat().st_size / 1024 / 1024
    print(f"\nDone: {exe}  ({size_mb:.0f} MB)")
    print("Settings are saved next to your user profile, not next to the .exe.")
    return 0


def clean():
    for folder in ("build", "dist"):
        shutil.rmtree(HERE / folder, ignore_errors=True)
    print("Removed the build and dist folders.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean()
    else:
        sys.exit(build())
