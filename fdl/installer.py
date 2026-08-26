"""Install the optional helper programs with winget.

ffmpeg, deno, and aria2c are not needed to start, but without them the tool
quietly does less: lower video quality, no MP3, some YouTube links refused,
and slower single downloads. Asking a normal user to open a terminal and
type three winget commands is where most people give up, so the tool offers
to run them.

winget ships with Windows 10 and 11. On any other system this module says
"not available" and the menu hides the option.
"""

import os
import shutil
import subprocess

# (name we search for, winget id, what it is for)
PACKAGES = [
    ("ffmpeg", "Gyan.FFmpeg", "HD video, and MP3"),
    ("deno", "DenoLand.Deno", "some YouTube links"),
    ("aria2c", "aria2.aria2", "faster single downloads"),
]


def winget_available():
    """True when winget can be used on this computer."""
    return os.name == "nt" and shutil.which("winget") is not None


def build_command(package_id):
    """The winget command. Kept separate so a test can read it."""
    return [
        "winget", "install",
        "--id", package_id,
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]


def missing(toolbox):
    """The packages that are not installed yet, in menu order."""
    found = {
        "ffmpeg": toolbox.ffmpeg_dir,
        "deno": toolbox.deno_dir,
        "aria2c": toolbox.aria2c_dir,
    }
    return [item for item in PACKAGES if not found.get(item[0])]


def install(package_id, runner=None):
    """Run winget. Returns (True, '') or (False, reason)."""
    run = runner or subprocess.run
    try:
        result = run(build_command(package_id))
    except OSError as err:
        return False, str(err)
    if result.returncode != 0:
        return False, f"winget stopped with code {result.returncode}"
    return True, ""
