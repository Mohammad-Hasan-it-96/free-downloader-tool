"""Read the clipboard, so a copied link can be offered for download.

There is no clipboard in the Python standard library, so each system is
handled on its own. Nothing here ever raises: when the clipboard cannot be
read, the answer is simply None.
"""

import os
import subprocess
import urllib.parse

MAX_LENGTH = 2000

# Linux and macOS helpers, tried in this order.
UNIX_COMMANDS = (
    ["wl-paste", "--no-newline"],
    ["xclip", "-selection", "clipboard", "-o"],
    ["xsel", "--clipboard", "--output"],
    ["pbpaste"],
)


def looks_like_a_link(text):
    """True when the text is one plain http(s) link and nothing else."""
    if not text:
        return False
    text = text.strip()
    if len(text) > MAX_LENGTH or len(text.split()) != 1:
        return False
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def new_link(text, seen, known=()):
    """The link worth adding when the clipboard turns from `seen` into `text`.

    None means do nothing: the clipboard did not change, it could not be
    read, it holds something that is not a link, or that link is already in
    the list. Keeping this decision here means it can be tested without a
    window, and both front ends can follow the same rule.
    """
    if text is None or text == seen:
        return None
    link = text.strip()
    if not looks_like_a_link(link):
        return None
    if link in set(known):
        return None
    return link


def read():
    """The clipboard text.

    An empty string means the clipboard works but holds no text. None means
    the clipboard cannot be read at all on this computer. The two are not
    the same, and mixing them up would say "no clipboard" whenever nothing
    happens to be copied.
    """
    if os.name == "nt":
        return _read_windows()
    text = _read_unix()
    if text is not None:
        return text
    return _read_tkinter()


def _read_windows():
    CF_UNICODETEXT = 13
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.restype = wintypes.BOOL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

        if not user32.OpenClipboard(None):
            return None
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""          # the clipboard works, it just has no text
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return ""
            try:
                return ctypes.c_wchar_p(pointer).value or ""
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:                      # noqa: BLE001
        return None


def _read_unix():
    for command in UNIX_COMMANDS:
        try:
            result = subprocess.run(command, capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
    return None


def _read_tkinter():
    """Last try. Works where a desktop and tkinter are both present."""
    try:
        import tkinter
    except ImportError:
        return None
    root = None
    try:
        root = tkinter.Tk()
        root.withdraw()
        return root.clipboard_get()
    except Exception:                      # noqa: BLE001
        return None
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:              # noqa: BLE001
                pass


def available():
    """True when reading the clipboard works on this computer."""
    return read() is not None
