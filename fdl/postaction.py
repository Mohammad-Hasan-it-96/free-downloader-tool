"""What happens after a download finishes: open the folder, or make a sound."""

import os
import subprocess
import sys
from pathlib import Path

NOTHING = "nothing"
OPEN_FOLDER = "open"
BEEP = "beep"
BOTH = "both"

CHOICES = {
    NOTHING: "do nothing",
    OPEN_FOLDER: "open the folder",
    BEEP: "make a sound",
    BOTH: "open the folder and make a sound",
}


def run(action, path):
    """Do what the setting asks. Never raises."""
    if action in (OPEN_FOLDER, BOTH):
        open_folder(path)
    if action in (BEEP, BOTH):
        beep()


def open_folder(path):
    """Open the folder holding `path`, and select the file where possible."""
    target = Path(path)
    folder = target if target.is_dir() else target.parent
    try:
        if os.name == "nt":
            if target.is_file():
                # /select, needs the path as one argument, quotes included.
                subprocess.Popen(["explorer", f"/select,{target}"])
            else:
                os.startfile(folder)       # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R" if target.is_file() else str(folder),
                              str(target) if target.is_file() else str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return True
    except (OSError, AttributeError):
        return False


def beep():
    try:
        if os.name == "nt":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()
        return True
    except Exception:                      # noqa: BLE001
        return False
