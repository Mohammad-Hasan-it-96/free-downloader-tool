"""One line in the download list, and the scrolling box that holds them."""

import tkinter as tk
from tkinter import ttk

from . import jobs as job_state
from ..term import human_size

COLOURS = {
    job_state.CHECKING: "#555555",
    job_state.WAITING: "#555555",
    job_state.RUNNING: "#0a5ea8",
    job_state.DONE: "#1b7a34",
    job_state.FAILED: "#b3261e",
    job_state.SKIPPED: "#7a6a00",
    job_state.CANCELLED: "#7a6a00",
}

WORDS = {
    job_state.CHECKING: "checking",
    job_state.WAITING: "waiting",
    job_state.RUNNING: "",
    job_state.DONE: "done",
    job_state.FAILED: "failed",
    job_state.SKIPPED: "skipped",
    job_state.CANCELLED: "cancelled",
}


def speed_text(bytes_per_second):
    if not bytes_per_second or bytes_per_second < 1:
        return ""
    return human_size(bytes_per_second) + "/s"


def size_text(job):
    if not job.total_bytes:
        return human_size(job.done_bytes) if job.done_bytes else ""
    return f"{human_size(job.done_bytes)} of {human_size(job.total_bytes)}"


def right_text(job):
    """The line under the name: what is happening, in plain words."""
    if job.status == job_state.RUNNING:
        parts = [p for p in (size_text(job), speed_text(job.speed)) if p]
        return "   ".join(parts) or "starting..."
    if job.status == job_state.DONE:
        return job.message or "done"
    if job.status in (job_state.FAILED, job_state.SKIPPED,
                      job_state.CANCELLED):
        return job.error or job.message or WORDS[job.status]
    return job.message or WORDS.get(job.status, "")


class Row(ttk.Frame):
    """One download. Built once, then only its text and bar change."""

    def __init__(self, parent, job, on_cancel, on_open, on_retry):
        super().__init__(parent, padding=(8, 6))
        self.job = job
        self._on_cancel = on_cancel
        self._on_open = on_open
        self._on_retry = on_retry
        self.columnconfigure(0, weight=1)

        self.title = ttk.Label(self, text=job.label, anchor="w",
                               font=("Segoe UI", 10, "bold"))
        self.title.grid(row=0, column=0, sticky="ew")

        self.state_label = ttk.Label(self, text="", anchor="e",
                                     font=("Segoe UI", 9))
        self.state_label.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.button = ttk.Button(self, text="Stop", width=7,
                                 command=lambda: on_cancel(job.job_id))
        self.button.grid(row=0, column=2, rowspan=2, padx=(8, 0))

        self.bar = ttk.Progressbar(self, maximum=100, length=100)
        self.bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        self.detail = ttk.Label(self, text="", anchor="w", justify="left",
                                font=("Segoe UI", 8), foreground="#555555")
        self.detail.grid(row=2, column=0, columnspan=3, sticky="ew",
                         pady=(2, 0))
        # An error from yt-dlp can be a long sentence. Without this it is cut
        # off at the edge of the window, which is where the answer usually is.
        self.bind("<Configure>", self._fit_text)
        self.refresh()

    def _fit_text(self, event):
        self.detail.configure(wraplength=max(200, event.width - 24))

    def refresh(self):
        job = self.job
        self.title.configure(text=job.label)

        word = WORDS.get(job.status, "")
        percent = f"{job.percent:.0f}%" if job.status == job_state.RUNNING else ""
        self.state_label.configure(
            text=(percent or word), foreground=COLOURS.get(job.status, "#333"))

        if job.status == job_state.RUNNING and not job.total_bytes and not job.percent:
            self.bar.configure(mode="indeterminate")
        else:
            self.bar.configure(mode="determinate", value=job.percent)

        note = right_text(job)
        if job.attempts > 1:
            note = f"Attempt {job.attempts}. " + note
        if job.warnings:
            note = (note + "\n" if note else "") + "\n".join(job.warnings)
        self.detail.configure(
            text=note,
            foreground="#b3261e" if job.status == job_state.FAILED
            else "#555555")

        if job.status == job_state.DONE and job.path is not None:
            self.button.configure(text="Open", state="normal",
                                  command=lambda: self._on_open(self.job))
        elif job.can_retry:
            self.button.configure(
                text="Retry", state="normal",
                command=lambda: self._on_retry(self.job.job_id))
        elif job.is_finished:
            self.button.configure(text="Stop", state="disabled")
        else:
            self.button.configure(
                text="Stop", state="normal",
                command=lambda: self._on_cancel(self.job.job_id))


class RowList(ttk.Frame):
    """A scrolling box of Rows, oldest first."""

    def __init__(self, parent, on_cancel, on_open, on_retry):
        super().__init__(parent)
        self._on_cancel = on_cancel
        self._on_open = on_open
        self._on_retry = on_retry
        self.rows = {}

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical",
                                  command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner,
                                                 anchor="nw")

        self.inner.bind("<Configure>", self._resize_inner)
        self.canvas.bind("<Configure>", self._resize_canvas)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        # A Canvas has no wheel of its own, and the wheel event goes to the
        # small label under the pointer, not to us. So listen everywhere and
        # keep only what happened inside this box.
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.bind_all("<Button-4>", self._wheel, add="+")
        self.bind_all("<Button-5>", self._wheel, add="+")

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.empty = ttk.Label(
            self.inner, foreground="#777777", padding=(10, 24),
            text="Nothing here yet.\nPaste a link above and press Add.")
        self.empty.pack(anchor="w")

    def _resize_inner(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_canvas(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _scroll_to_end(self):
        self._resize_inner()
        self.canvas.yview_moveto(1.0)

    def _wheel(self, event):
        """Scroll the list, but only when the pointer is over it."""
        if not str(event.widget).startswith(str(self.canvas)):
            return
        if event.num == 4:
            steps = -1
        elif event.num == 5:
            steps = 1
        elif abs(event.delta) >= 120:      # Windows counts in 120s
            steps = int(-event.delta / 120)
        else:                              # macOS counts in ones
            steps = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(steps, "units")

    def show(self, job):
        """Add the row if it is new, then update it."""
        if self.empty is not None:
            self.empty.destroy()
            self.empty = None
        row = self.rows.get(job.job_id)
        if row is None:
            row = Row(self.inner, job, self._on_cancel, self._on_open,
                      self._on_retry)
            row.pack(fill="x", expand=True)
            ttk.Separator(self.inner, orient="horizontal").pack(fill="x")
            self.rows[job.job_id] = row
            # Show what was just added, instead of leaving it below the edge.
            # after_idle, because the new row has no size until Tk lays it out
            # and the scroll region is still the old one.
            self.canvas.after_idle(self._scroll_to_end)
        else:
            row.refresh()
        self._resize_inner()
