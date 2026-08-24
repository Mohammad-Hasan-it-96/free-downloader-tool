"""Use the aria2c program for very fast downloads, when it is installed.

aria2c opens many connections at once and handles its own resume. It writes
a control file next to the download (`name.part.aria2`) that holds the
progress of every connection.

We still write our own `name.part.meta` file, with `mode` set to "aria2", so
the rest of the app knows that only aria2c can continue this part file.
"""

import os
import subprocess
from pathlib import Path

from . import http_engine
from .http_engine import MODE_ARIA2, DownloadError
from .naming import unique_path

DEFAULT_CONNECTIONS = 16
MIN_SIZE = 2 * 1024 * 1024      # below this, aria2c brings no real gain


def executable(toolbox):
    """Full path of aria2c, or None when it is not installed."""
    if not toolbox or not getattr(toolbox, "aria2c_dir", None):
        return None
    name = "aria2c.exe" if os.name == "nt" else "aria2c"
    path = Path(toolbox.aria2c_dir) / name
    return str(path) if path.exists() else None


def is_useful_for(info, toolbox, enabled=True):
    """True when aria2c would really help for this file."""
    if not enabled or not executable(toolbox):
        return False
    if not info.resumable or not info.size:
        return False
    return info.size >= MIN_SIZE


def control_file(part_path):
    return Path(part_path).with_name(Path(part_path).name + ".aria2")


def build_command(program, url, dest_dir, part_name, *, connections,
                  speed_limit_kb=0, retries=5, extra_headers=None):
    command = [
        program,
        f"--dir={dest_dir}",
        f"--out={part_name}",
        "--continue=true",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        f"--max-connection-per-server={connections}",
        f"--split={connections}",
        "--min-split-size=1M",
        f"--max-tries={max(1, retries + 1)}",
        "--retry-wait=2",
        "--summary-interval=1",
        "--console-log-level=warn",
        "--show-console-readout=true",
    ]
    if speed_limit_kb and speed_limit_kb > 0:
        command.append(f"--max-overall-download-limit={int(speed_limit_kb)}K")
    for key, value in (extra_headers or {}).items():
        command.append(f"--header={key}: {value}")
    command.append(url)
    return command


def download(url, dest_dir, info, *, toolbox, name=None, connections=None,
             speed_limit_kb=0, retries=5, extra_headers=None):
    """Download with aria2c and return the final path.

    aria2c prints its own progress, so nothing is drawn here.
    """
    program = executable(toolbox)
    if not program:
        raise DownloadError("aria2c is not installed.")

    dest_dir = Path(dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise DownloadError(f"Cannot use the folder {dest_dir}: {err}") from err

    file_name = name or info.filename
    part_path = dest_dir / (file_name + ".part")
    _clean_unusable_part(part_path, url, info)

    http_engine.write_meta(part_path, {
        "url": url, "size": info.size, "etag": info.etag,
        "last_modified": info.last_modified, "mode": MODE_ARIA2,
    })

    command = build_command(
        program, info.url, str(dest_dir), part_path.name,
        connections=connections or DEFAULT_CONNECTIONS,
        speed_limit_kb=speed_limit_kb, retries=retries,
        extra_headers=extra_headers)

    try:
        result = subprocess.run(command)
    except OSError as err:
        raise DownloadError(f"Cannot run aria2c: {err}") from err

    if result.returncode != 0:
        raise DownloadError(
            f"aria2c stopped with code {result.returncode}. The part file "
            "was kept, so you can continue it later.")

    return _finalise(part_path, dest_dir, file_name, info)


def _clean_unusable_part(part_path, url, info):
    """Throw away a part file that aria2c cannot safely continue.

    aria2c writes its pieces out of order. Without its control file, the
    bytes already on disk cannot be trusted, so we start again.
    """
    if not part_path.exists():
        return
    meta = http_engine.read_meta(part_path)
    same_file = http_engine.meta_matches(meta, url, info)
    was_aria2 = (meta or {}).get("mode") == MODE_ARIA2
    if same_file and was_aria2 and control_file(part_path).exists():
        return
    try:
        part_path.unlink()
        control_file(part_path).unlink(missing_ok=True)
    except OSError as err:
        raise DownloadError(f"Cannot replace {part_path}: {err}") from err
    http_engine.clear_meta(part_path)


def _finalise(part_path, dest_dir, file_name, info):
    if not part_path.exists():
        raise DownloadError("aria2c finished but the file is missing.")

    actual = part_path.stat().st_size
    if info.size is not None and actual != info.size:
        raise DownloadError(
            f"The download is incomplete: got {actual} bytes, expected "
            f"{info.size}. The part file was kept.")

    final_path = unique_path(dest_dir / file_name)
    try:
        part_path.replace(final_path)
    except OSError as err:
        raise DownloadError(f"Cannot save {final_path}: {err}") from err
    control_file(part_path).unlink(missing_ok=True)
    http_engine.clear_meta(part_path)
    return final_path
