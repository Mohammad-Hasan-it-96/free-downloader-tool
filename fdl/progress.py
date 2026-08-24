"""A one-line progress display: percent, size, speed, and time left."""

import shutil
import sys
import time

from .term import human_size, human_time


class ProgressPrinter:
    """Prints progress on one line and keeps rewriting it.

    `already_done` is the number of bytes that existed before this run, so a
    resumed download shows the true total percent, but the speed is measured
    only from the bytes of this run.
    """

    MIN_REDRAW_SECONDS = 0.15

    def __init__(self, total=None, already_done=0, stream=None):
        self.total = total
        self.already_done = already_done
        self.done = already_done
        self.stream = stream or sys.stdout
        self.start_time = time.monotonic()
        self._last_draw = 0.0
        self._last_line_length = 0
        self._finished = False

    def update(self, done_bytes):
        self.done = done_bytes
        now = time.monotonic()
        if now - self._last_draw < self.MIN_REDRAW_SECONDS:
            return
        self._last_draw = now
        self._draw()

    def finish(self):
        if self._finished:
            return
        self._finished = True
        self._draw()
        self.stream.write("\n")
        self.stream.flush()

    def fail(self, message):
        """End the line, then show why it stopped."""
        if not self._finished:
            self._finished = True
            self._draw()
            self.stream.write("\n")
        self.stream.write(message + "\n")
        self.stream.flush()

    # ---------------------------------------------------------------- #

    def _speed(self):
        elapsed = time.monotonic() - self.start_time
        moved = self.done - self.already_done
        if elapsed < 0.3 or moved <= 0:
            return None
        return moved / elapsed

    def _eta(self, speed):
        if not speed or not self.total:
            return None
        left = self.total - self.done
        if left <= 0:
            return 0
        return left / speed

    def _draw(self):
        speed = self._speed()
        parts = []

        if self.total:
            percent = min(100.0, self.done * 100.0 / self.total)
            parts.append(f"{percent:5.1f}%")
            parts.append(_bar(percent))
            parts.append(f"{human_size(self.done)} / {human_size(self.total)}")
        else:
            parts.append(human_size(self.done))

        parts.append(f"{human_size(speed)}/s" if speed else "--")
        if self.total:
            parts.append(f"ETA {human_time(self._eta(speed))}")

        line = "  " + "  ".join(parts)
        width = shutil.get_terminal_size((80, 20)).columns
        line = line[: max(10, width - 1)]

        padding = max(0, self._last_line_length - len(line))
        self._last_line_length = len(line)
        self.stream.write("\r" + line + " " * padding)
        self.stream.flush()


def _bar(percent, width=24):
    filled = int(width * percent / 100.0)
    return "[" + "#" * filled + "-" * (width - filled) + "]"
