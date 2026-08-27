"""The history window, and the log window behind it.

The terminal menu has both. Without them here, someone who never opens a
terminal has no way to see what they downloaded last week, and no way to find
out why something went wrong.

`row_values` holds the whole decision about what a line says, so it can be
tested without a screen.
"""

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .. import log, paths, postaction
from ..history import STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED, short_time
from ..term import human_size

TITLE = "History"
# The newest few hundred. Older ones stay in the file; nobody scrolls further
# than this, and a very long list makes the window slow to open.
SHOWN = 200
LOG_LINES = 300

WORDS = {STATUS_DONE: "done", STATUS_FAILED: "failed",
         STATUS_SKIPPED: "skipped"}
COLOURS = {STATUS_DONE: "#1b7a34", STATUS_FAILED: "#b3261e",
           STATUS_SKIPPED: "#7a6a00"}

COLUMNS = (
    # name,    heading,   width, side
    ("what",   "",          72, "w"),
    ("name",   "Name",     320, "w"),
    ("when",   "When",     130, "w"),
    ("size",   "Size",      90, "e"),
    ("where",  "Folder",   150, "w"),
)


def row_values(entry):
    """The five cells shown for one history entry.

    A skipped or failed link has no path, so the address is used instead.
    """
    target = entry.get("path") or entry.get("url") or ""
    folder = ""
    if entry.get("path"):
        folder = Path(str(entry["path"])).parent.name
    status = entry.get("status") or ""
    return (WORDS.get(status, status),
            Path(str(target)).name or str(target),
            short_time(entry.get("when")),
            human_size(entry["size"]) if entry.get("size") else "",
            folder or entry.get("category") or "")


class HistoryDialog(tk.Toplevel):
    """What was downloaded, newest first."""

    def __init__(self, parent, history):
        super().__init__(parent)
        self.history = history
        self.title(TITLE)
        self.minsize(700, 380)
        self.geometry("880x470")
        self.transient(parent)

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        self.heading = ttk.Label(frame, font=("Segoe UI", 9),
                                 foreground="#555555")
        self.heading.grid(row=0, column=0, columnspan=2, sticky="w",
                          pady=(0, 6))

        self.tree = ttk.Treeview(frame, show="headings", selectmode="browse",
                                 columns=[name for name, *_ in COLUMNS])
        for name, heading, width, side in COLUMNS:
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=width, anchor=side,
                             stretch=(name == "name"))
        for status, colour in COLOURS.items():
            self.tree.tag_configure(status, foreground=colour)

        bar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        bar.grid(row=1, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._chosen)
        self.tree.bind("<Double-1>", lambda _e: self._open())

        # The reason a download failed can be a long sentence, so it gets its
        # own line under the table instead of a column that cuts it off.
        self.note = ttk.Label(frame, font=("Segoe UI", 8),
                              foreground="#b3261e", wraplength=820)
        self.note.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        buttons.columnconfigure(0, weight=1)
        self.open_button = ttk.Button(buttons, text="Open folder",
                                      command=self._open, state="disabled")
        self.open_button.grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Show the log", command=self._show_log).grid(
            row=0, column=1, padx=(6, 0))
        self.clear_button = ttk.Button(buttons, text="Clear history",
                                       command=self._clear)
        self.clear_button.grid(row=0, column=2, padx=(6, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).grid(
            row=0, column=3, padx=(6, 0))

        self.bind("<Escape>", lambda _e: self.destroy())
        self._fill()

    # ------------------------------ filling ------------------------------ #

    def _fill(self):
        self.tree.delete(*self.tree.get_children())
        self.entries = self.history.recent(SHOWN)
        total = len(self.history.entries)
        counts = self.history.counts()

        if not self.entries:
            self.heading.configure(text="Nothing has been downloaded yet.")
            self.clear_button.configure(state="disabled")
            return

        self.clear_button.configure(state="normal")
        self.heading.configure(
            text=f"Showing {len(self.entries)} of {total}       "
                 f"done {counts[STATUS_DONE]}       "
                 f"failed {counts[STATUS_FAILED]}       "
                 f"skipped {counts[STATUS_SKIPPED]}")
        for index, entry in enumerate(self.entries):
            self.tree.insert("", "end", iid=str(index),
                             tags=(entry.get("status") or "",),
                             values=row_values(entry))

    # ------------------------------ actions ------------------------------ #

    def _selected(self):
        chosen = self.tree.selection()
        if not chosen:
            return None
        index = int(chosen[0])
        if index >= len(self.entries):
            return None
        return self.entries[index]

    def _chosen(self, _event=None):
        entry = self._selected() or {}
        self.note.configure(text=entry.get("error") or "")
        has_file = bool(entry.get("path"))
        self.open_button.configure(state="normal" if has_file else "disabled")

    def _open(self):
        entry = self._selected()
        if not entry or not entry.get("path"):
            return
        if not postaction.open_folder(entry["path"]):
            messagebox.showinfo(
                TITLE, "That folder could not be opened.", parent=self)

    def _clear(self):
        if not self.history.entries:
            return
        gone = len(self.history.entries)
        if not messagebox.askyesno(
                TITLE,
                f"Delete all {gone} entries?\n\n"
                "The files you downloaded are not touched. Only this list "
                "goes.", parent=self):
            return
        self.history.clear()
        self._fill()
        self._chosen()

    def _show_log(self):
        LogDialog(self)


class LogDialog(tk.Toplevel):
    """The end of the log file, for when something went wrong."""

    def __init__(self, parent):
        super().__init__(parent)
        self.path = paths.log_path()
        self.title("Log")
        self.minsize(700, 340)
        self.geometry("900x480")
        self.transient(parent)

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(frame, text=str(self.path), font=("Segoe UI", 8),
                  foreground="#555555").grid(row=0, column=0, columnspan=2,
                                             sticky="w", pady=(0, 6))

        text = tk.Text(frame, wrap="none", font=("Consolas", 9),
                       borderwidth=1, relief="solid", height=10)
        down = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        across = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=down.set, xscrollcommand=across.set)
        text.grid(row=1, column=0, sticky="nsew")
        down.grid(row=1, column=1, sticky="ns")
        across.grid(row=2, column=0, sticky="ew")

        text.tag_configure("error", foreground="#b3261e")
        text.tag_configure("warning", foreground="#8a5a00")

        lines = log.tail(self.path, LOG_LINES)
        if lines:
            for line in lines:
                text.insert("end", line + "\n", self._kind(line))
            text.see("end")          # the newest lines are the useful ones
        else:
            text.insert("end", "The log is empty, or it cannot be read.")
        # Read only, but the text can still be selected and copied.
        text.configure(state="disabled")
        self.text = text

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Show the file", command=self._reveal).pack(
            side="right", padx=(6, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(
            side="right")
        self.bind("<Escape>", lambda _e: self.destroy())

    @staticmethod
    def _kind(line):
        if " ERROR " in line:
            return "error"
        if " WARNING " in line:
            return "warning"
        return ""

    def _reveal(self):
        if self.path.exists():
            postaction.open_folder(self.path)
            return
        messagebox.showinfo(
            "Log", f"There is no log file yet.\n\nIt would be at:\n"
                   f"{self.path}", parent=self)
