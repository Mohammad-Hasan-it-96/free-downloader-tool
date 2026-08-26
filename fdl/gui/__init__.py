"""The window version of the tool.

Importing this package pulls in tkinter, so the terminal menu must never
import it at module level. `available()` says whether a window can be opened
at all: tkinter ships with Python on Windows and macOS, but on Linux it is a
separate package (`python3-tk`), and there may be no screen.
"""


def available():
    """True when a window can be opened on this computer."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return False
    return True


def why_not():
    """A plain sentence explaining why the window cannot open."""
    return ("tkinter is not installed for this Python, so the window cannot "
            "open. On Debian or Ubuntu install it with: "
            "sudo apt install python3-tk")


def run(**kwargs):
    """Open the window. Returns when the user closes it."""
    from .window import run as open_window
    return open_window(**kwargs)
