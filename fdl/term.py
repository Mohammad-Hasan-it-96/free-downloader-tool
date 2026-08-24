"""Small helpers for terminal colours, sizes, and times."""

import os
import sys

_ENABLED = True


def enable_colors():
    """Turn on ANSI colours on Windows terminals. Safe to call many times."""
    global _ENABLED
    if not sys.stdout.isatty():
        _ENABLED = False
        return
    if os.name == "nt":
        os.system("")  # switches the console into ANSI mode


def color(text, code):
    if not _ENABLED:
        return text
    return f"\033[{code}m{text}\033[0m"


def cyan(t):   return color(t, "96")
def green(t):  return color(t, "92")
def yellow(t): return color(t, "93")
def red(t):    return color(t, "91")
def grey(t):   return color(t, "90")
def bold(t):   return color(t, "1")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def human_size(num_bytes):
    """1536 -> '1.5 KB'. Returns '?' when the size is unknown."""
    if num_bytes is None:
        return "?"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def human_time(seconds):
    """90 -> '01:30'. Returns '--:--' when unknown."""
    if seconds is None or seconds < 0 or seconds != seconds:  # NaN check
        return "--:--"
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def ask_yes_no(question, default_no=True):
    suffix = "[y/N]" if default_no else "[Y/n]"
    answer = input(bold(f"{question} {suffix}: ")).strip().lower()
    if not answer:
        return not default_no
    return answer.startswith("y")


def pause():
    input(yellow("\nPress Enter to continue..."))
