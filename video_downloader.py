#!/usr/bin/env python3
"""Launcher kept for people who run `python video_downloader.py`.

The real code lives in the `fdl` package next to this file.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fdl.app import run  # noqa: E402  (import must come after the path fix)

if __name__ == "__main__":
    run()
