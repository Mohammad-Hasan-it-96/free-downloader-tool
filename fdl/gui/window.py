"""The main window.

Only this thread may touch a widget. Downloads run in `jobs.Manager`, which
puts job numbers into a queue; `_drain()` empties that queue on a timer and
redraws the rows that changed.
"""

import queue
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import console, jobs as job_state
from .rows import RowList
from .settings_dialog import SettingsDialog
from .. import (batch, clipboard, log, paths, postaction, updates,
                ytdlp_engine)
from ..config import Config
from ..history import History
from ..tools import Toolbox, ytdlp_installed

POLL_MS = 120
# How often the clipboard is read while the watch is on. On Windows this
# costs nothing: it is a plain ctypes call, not a new process.
WATCH_MS = 1000
TITLE = "Free Downloader Tool"

QUALITY_ORDER = ["1", "2", "3", "4", "5", "6"]


class MainWindow(tk.Tk):
    def __init__(self, cfg, toolbox, history, ensure_folder,
                 first_run=False):
        super().__init__()
        self.cfg = cfg
        self.toolbox = toolbox
        self.history = history
        self.ensure_folder = ensure_folder
        self.manager = job_state.Manager(cfg, toolbox, history)
        self.update_check = updates.BackgroundCheck().start(cfg)

        self.title(TITLE)
        self.minsize(720, 480)
        self.geometry("820x560")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(POLL_MS, self._drain)
        self.after(WATCH_MS, self._watch_tick)
        self.after(2000, self._show_news)
        if first_run:
            self.after(300, self._first_time)

    # ------------------------------ building ----------------------------- #

    def _build(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        top = ttk.Frame(outer)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text="Paste a link:",
                  font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")

        self.url = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.url, font=("Segoe UI", 10))
        entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        entry.bind("<Return>", lambda _e: self._add())
        entry.focus_set()
        self.entry = entry

        ttk.Button(top, text="Paste", width=8, command=self._paste).grid(
            row=1, column=1, padx=(6, 0), pady=(2, 0))
        ttk.Button(top, text="Add", width=8, command=self._add).grid(
            row=1, column=2, padx=(6, 0), pady=(2, 0))

        options = ttk.Frame(outer)
        options.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        options.columnconfigure(3, weight=1)

        ttk.Label(options, text="Video quality:").grid(row=0, column=0,
                                                       sticky="w")
        self.quality = ttk.Combobox(
            options, state="readonly", width=40,
            values=[ytdlp_engine.QUALITY_PRESETS[key][0]
                    for key in QUALITY_ORDER])
        self.quality.current(0)
        self.quality.grid(row=0, column=1, sticky="w", padx=(6, 12))

        self.whole_playlist = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, variable=self.whole_playlist,
                        text="whole playlist").grid(row=0, column=2,
                                                    sticky="w")
        ttk.Label(options, foreground="#777777", font=("Segoe UI", 8),
                  text="(used only for video and audio pages)").grid(
            row=0, column=3, sticky="w", padx=(10, 0))

        # Off at every start, and never saved. Turning it on means the tool
        # downloads without being asked, so that has to be a fresh decision.
        self.watching = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, variable=self.watching,
                        text="Watch the clipboard",
                        command=self._toggle_watch).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(options, foreground="#777777", font=("Segoe UI", 8),
                  text="(a link you copy is added by itself)").grid(
            row=1, column=2, columnspan=2, sticky="w", padx=(10, 0),
            pady=(4, 0))
        self._clip_seen = ""

        where = ttk.Frame(outer)
        where.grid(row=2, column=0, sticky="ew", pady=(10, 6))
        where.columnconfigure(1, weight=1)
        ttk.Label(where, text="Saving to:").grid(row=0, column=0, sticky="w")
        self.folder_label = ttk.Label(where, text="", foreground="#0a5ea8")
        self.folder_label.grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Button(where, text="Change...", command=self._settings).grid(
            row=0, column=2, padx=(6, 0))

        # Shown only when there is a newer version, so it does not take room
        # from the status line at the bottom.
        self.news = ttk.Label(where, text="", foreground="#8a5a00",
                              font=("Segoe UI", 9))
        self.news.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.news.grid_remove()

        self.list = RowList(outer, self._cancel, self._open_job,
                            self._retry)
        self.list.grid(row=3, column=0, sticky="nsew")

        bottom = ttk.Frame(outer)
        bottom.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        bottom.columnconfigure(1, weight=1)
        ttk.Button(bottom, text="Settings", command=self._settings).grid(
            row=0, column=0)
        self.status = ttk.Label(bottom, text="", foreground="#555555",
                                font=("Segoe UI", 9))
        self.status.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.clear_button = ttk.Button(bottom, text="Clear done",
                                       command=self._clear_done)
        self.clear_button.grid(row=0, column=2, padx=(6, 0))
        self.clear_button.grid_remove()
        self.retry_button = ttk.Button(bottom, text="Retry failed",
                                       command=self._retry_all)
        self.retry_button.grid(row=0, column=3, padx=(6, 6))
        self.retry_button.grid_remove()
        ttk.Button(bottom, text="Open folder",
                   command=self._open_base_folder).grid(row=0, column=4)

        self._refresh_folder()
        self._check_tools()

    # ------------------------------- actions ----------------------------- #

    def _paste(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            self._say("There is no text on the clipboard.")
            return
        links = batch.split_links(text)
        if len(links) > 1:
            # The box is one line, so keep them on one line.
            self.url.set(" ".join(links))
            self._say(f"{len(links)} links pasted. Press Add.")
        else:
            self.url.set(text.strip())
        self.entry.icursor("end")

    def _add(self):
        text = self.url.get().strip()
        links = batch.split_links(text)
        if not links:
            if not text:
                self._say("Paste a link first.")
            else:
                messagebox.showwarning(
                    TITLE, "That does not look like a link.\n\n"
                           "A link starts with http:// or https://",
                    parent=self)
            return

        ok, why = self.ensure_folder(self.cfg.base_dir)
        if not ok:
            messagebox.showerror(
                TITLE, f"The download folder cannot be used:\n\n{why}\n\n"
                       "Change it under Settings.", parent=self)
            return

        quality = self._quality_key()
        whole = self.whole_playlist.get()
        for link in links:
            self.list.show(self.manager.add(link, quality, whole))
        self.url.set("")
        added = "Added." if len(links) == 1 else f"Added {len(links)} links."
        self._say(f"{added} {len(self.manager.active)} running or waiting.")

    def _quality_key(self):
        index = self.quality.current()
        if index < 0 or index >= len(QUALITY_ORDER):
            return "1"
        return QUALITY_ORDER[index]

    def _cancel(self, job_id):
        self.manager.cancel(job_id)

    def _retry(self, job_id):
        job = self.manager.retry(job_id)
        if job is not None:
            self.list.show(job)
            self._say(self.summary())

    def _retry_all(self):
        started = self.manager.retry_all()
        if started:
            self._say(f"Trying {started} again.")

    # --------------------------- the clipboard --------------------------- #

    def _clipboard_text(self):
        """The clipboard text, or None when it cannot be read at all.

        Tk is asked first because it costs nothing while a window is open.
        An empty string is not the same answer as None: the first means the
        clipboard holds no text, the second that there is no clipboard.
        """
        try:
            return self.clipboard_get()
        except tk.TclError:
            return clipboard.read()

    def _toggle_watch(self):
        if not self.watching.get():
            log.info("gui clipboard watch stopped")
            self._say("The clipboard is no longer watched.")
            return

        text = self._clipboard_text()
        if text is None:
            self.watching.set(False)
            messagebox.showwarning(
                TITLE, "The clipboard cannot be read on this computer.\n\n"
                       "On Linux, install xclip, xsel, or wl-clipboard.",
                parent=self)
            return
        # What is already copied is left alone. Turning the watch on must not
        # start a download the user did not ask for.
        self._clip_seen = text
        log.info("gui clipboard watch started")
        self._say("Watching the clipboard. Copy a link and it is added.")

    def _watch_tick(self):
        """Read the clipboard, and add any new link that appears on it."""
        self.after(WATCH_MS, self._watch_tick)
        if not self.watching.get():
            return
        text = self._clipboard_text()
        if text is None:
            return                  # another program has it open just now
        link = clipboard.new_link(
            text, self._clip_seen,
            known=[job.url for job in self.manager.jobs.values()])
        self._clip_seen = text
        if link is None:
            return

        ok, why = self.ensure_folder(self.cfg.base_dir)
        if not ok:
            self.watching.set(False)
            messagebox.showerror(
                TITLE, f"The download folder cannot be used:\n\n{why}\n\n"
                       "Change it under Settings.", parent=self)
            return
        self.list.show(self.manager.add(link, self._quality_key(),
                                        self.whole_playlist.get()))
        self._say(f"Added from the clipboard: {link}")

    def _clear_done(self):
        """Take the finished rows out, so a long list stays readable."""
        for job_id in self.manager.clear_done():
            self.list.remove(job_id)
        self._show_buttons()
        self._say(self.summary())

    def _open_job(self, job):
        target = job.path or job.dest
        if target is None:
            return
        postaction.open_folder(target)

    def _open_base_folder(self):
        ok, why = self.ensure_folder(self.cfg.base_dir)
        if not ok:
            messagebox.showerror(TITLE, f"That folder cannot be used:\n\n{why}",
                                 parent=self)
            return
        postaction.open_folder(self.cfg.base_dir)

    def _settings(self):
        before = self.cfg.max_parallel
        dialog = SettingsDialog(self, self.cfg, self.ensure_folder)
        self.wait_window(dialog)
        if not dialog.saved:
            return
        self._refresh_folder()
        if self.cfg.max_parallel != before:
            self._say("Saved. 'Downloads at the same time' starts working "
                      "when you next open the app.")
        else:
            self._say("Settings saved.")

    # ------------------------------ the timer ---------------------------- #

    def _drain(self):
        """Empty the event queue and redraw only the rows that changed."""
        changed = {}
        try:
            while True:
                job_id = self.manager.events.get_nowait()
                job = self.manager.jobs.get(job_id)
                if job is not None:
                    changed[job_id] = job
        except queue.Empty:
            pass
        for job in changed.values():
            self.list.show(job)
            if job.status == job_state.DONE:
                postaction.run(self.cfg.after_download, job.path)
        if changed:
            self._say(self.summary())
            self._show_buttons()
        self.after(POLL_MS, self._drain)

    def _show_buttons(self):
        """Each button is only there when it has something to do."""
        for button, wanted in ((self.retry_button, self.manager.failed),
                               (self.clear_button, self.manager.cleanable)):
            if wanted:
                button.grid()
            else:
                button.grid_remove()

    def summary(self):
        """One line counting what is happening, for the bottom of the window."""
        counts = {}
        for job in self.manager.jobs.values():
            counts[job.status] = counts.get(job.status, 0) + 1
        parts = []
        running = len(self.manager.active)
        if running:
            parts.append(f"{running} in progress")
        for status, word in ((job_state.DONE, "done"),
                             (job_state.FAILED, "failed"),
                             (job_state.SKIPPED, "skipped"),
                             (job_state.CANCELLED, "cancelled")):
            if counts.get(status):
                parts.append(f"{counts[status]} {word}")
        return ", ".join(parts) if parts else "Ready."

    def _show_news(self):
        message = self.update_check.message
        if message:
            self.news.configure(text=message)
            self.news.grid()
        else:
            self.after(60000, self._show_news)

    # ------------------------------- helpers ----------------------------- #

    def _first_time(self):
        messagebox.showinfo(
            TITLE,
            "Welcome!\n\n"
            "Paste any link and press Add.\n\n"
            "Videos come from YouTube and 1000+ other sites. Any other "
            "file downloads directly, and continues where it stopped if "
            "your connection breaks.\n\n"
            f"Your files will go to:\n{self.cfg.base_dir}\n\n"
            "You can change that under Settings.", parent=self)

    def _say(self, text):
        self.status.configure(text=text)

    def _refresh_folder(self):
        self.folder_label.configure(text=str(self.cfg.base_dir))

    def _check_tools(self):
        if not ytdlp_installed():
            self._say("yt-dlp is missing, so only direct file links will "
                      "work.")
        elif not self.toolbox.has_ffmpeg:
            self._say("ffmpeg is missing. Video quality may be lower, and "
                      "MP3 is not possible.")
        else:
            self._say("Ready.")

    def _on_close(self):
        running = [job for job in self.manager.active
                   if job.status == job_state.RUNNING]
        if running:
            keep = messagebox.askyesno(
                TITLE,
                f"{len(running)} download(s) are still running.\n\n"
                "Close anyway? Unfinished files are kept, and you can "
                "continue them later.", parent=self)
            if not keep:
                return
        self.manager.close()
        self.destroy()


def run(cfg=None, toolbox=None, history=None, ensure_folder=None,
        first_run=False):
    """Open the window. Returns when the user closes it."""
    from ..app import ensure_folder as default_ensure

    cfg = cfg or Config.load(paths.config_path())
    toolbox = toolbox or Toolbox()
    history = history or History.load(paths.history_path(), cfg.history_limit)
    hidden = console.hide()
    try:
        window = MainWindow(cfg, toolbox, history,
                            ensure_folder or default_ensure, first_run)
        window.mainloop()
    except Exception:
        if hidden:
            console.show()
        raise
    return 0


def open_releases_page():
    webbrowser.open(updates.RELEASES_PAGE)
