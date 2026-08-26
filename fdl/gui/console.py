"""Hide the black console window while the GUI is open.

The app is built with a console on purpose: the terminal menu needs one, and
so does the yt-dlp call the .exe makes to itself. But when someone
double-clicks the icon to get a window, an empty black box behind it looks
broken.

So the console is hidden once the window is up, and shown again if the GUI
falls over, because then the error text is the only help the user has.
"""

import os

SW_HIDE = 0
SW_SHOW = 5

_handle = None


def _console_window():
    """The handle of our own console window, or None."""
    global _handle
    if os.name != "nt":
        return None
    if _handle is None:
        try:
            import ctypes
            _handle = ctypes.windll.kernel32.GetConsoleWindow()
        except Exception:      # noqa: BLE001 - never stop the GUI for this
            _handle = 0
    return _handle or None


def _show(state):
    window = _console_window()
    if not window:
        return False
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(window, state)
        return True
    except Exception:          # noqa: BLE001
        return False


def hide():
    """True when a console was actually hidden."""
    return _show(SW_HIDE)


def show():
    return _show(SW_SHOW)
