"""Show several downloads at once, one line each, updating together."""

import shutil
import sys
import threading
import time

from .term import human_size, human_time

REFRESH_SECONDS = 0.2


class Row:
    def __init__(self, label):
        self.label = label
        self.done = 0
        self.total = None
        self.status = "waiting"   # waiting, running, done, failed, skipped
        self.message = ""
        self.started = None
        self._done_at_start = 0

    def begin(self, already_done=0):
        self.status = "running"
        self.started = time.monotonic()
        self.done = already_done
        self._done_at_start = already_done

    def speed(self):
        if self.status != "running" or self.started is None:
            return None
        elapsed = time.monotonic() - self.started
        moved = self.done - self._done_at_start
        if elapsed < 0.3 or moved <= 0:
            return None
        return moved / elapsed


class MultiProgress:
    """Draws one line per download.

    In a real terminal the lines are rewritten in place. When the output is
    a file or a pipe, only status changes are printed, so logs stay readable.
    """

    def __init__(self, labels, stream=None):
        self.stream = stream or sys.stdout
        self.rows = [Row(label) for label in labels]
        self.lock = threading.Lock()
        self.live = bool(getattr(self.stream, "isatty", lambda: False)())
        self._stop = threading.Event()
        self._thread = None
        self._drawn = 0

    # ---------------------------- updating ---------------------------- #

    def begin(self, index, already_done=0):
        with self.lock:
            self.rows[index].begin(already_done)
        self._announce(index, "started")

    def update(self, index, done, total=None):
        with self.lock:
            row = self.rows[index]
            row.done = done
            if total:
                row.total = total

    def finish(self, index, status, message=""):
        with self.lock:
            row = self.rows[index]
            row.status = status
            row.message = message
        self._announce(index, status)

    def _announce(self, index, what):
        if self.live:
            return
        row = self.rows[index]
        extra = f" - {row.message}" if row.message else ""
        self.stream.write(f"[{index + 1}] {row.label}: {what}{extra}\n")
        self.stream.flush()

    # ---------------------------- drawing ----------------------------- #

    def start(self):
        if not self.live:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self.live:
            self._draw()

    def _loop(self):
        while not self._stop.is_set():
            self._draw()
            self._stop.wait(REFRESH_SECONDS)

    def _draw(self):
        width = shutil.get_terminal_size((80, 20)).columns
        with self.lock:
            lines = [self._line(i, row, width)
                     for i, row in enumerate(self.rows)]

        out = []
        if self._drawn:
            out.append(f"\033[{self._drawn}A")   # cursor up to the first line
        for line in lines:
            out.append("\033[2K" + line + "\n")  # clear the line, then write
        self._drawn = len(lines)
        self.stream.write("".join(out))
        self.stream.flush()

    def _line(self, index, row, width):
        marks = {"waiting": " ", "running": ">", "done": "+",
                 "failed": "x", "skipped": "-"}
        mark = marks.get(row.status, " ")
        label = row.label
        max_label = max(12, min(38, width - 46))
        if len(label) > max_label:
            label = label[: max_label - 1] + "~"

        if row.status == "running":
            if row.total:
                percent = min(100.0, row.done * 100.0 / row.total)
                tail = f"{percent:5.1f}%  {human_size(row.done)}"
                speed = row.speed()
                if speed:
                    tail += f"  {human_size(speed)}/s"
                    left = row.total - row.done
                    tail += f"  ETA {human_time(left / speed)}"
            else:
                tail = human_size(row.done)
        elif row.status == "done":
            tail = f"done  {human_size(row.total or row.done)}"
        elif row.status in ("failed", "skipped"):
            tail = row.message or row.status
        else:
            tail = "waiting"

        line = f" {mark} [{index + 1}] {label:<{max_label}}  {tail}"
        return line[: max(10, width - 1)]
