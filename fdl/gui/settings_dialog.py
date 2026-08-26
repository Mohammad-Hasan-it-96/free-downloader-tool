"""The Settings window.

It holds the settings a normal user touches. The rarer ones - a proxy, extra
headers, a folder for each type - stay in the terminal menu, where there is
room to explain them.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import BROWSERS
from ..postaction import CHOICES as AFTER_CHOICES

NO_COOKIES = "off"


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, cfg, ensure_folder):
        super().__init__(parent)
        self.cfg = cfg
        self.ensure_folder = ensure_folder
        self.saved = False

        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        frame = ttk.Frame(self, padding=14)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        row = 0

        # ---- where the files go ----
        ttk.Label(frame, text="Save downloads in").grid(
            row=row, column=0, sticky="w", pady=4)
        self.folder = tk.StringVar(value=cfg.base_dir)
        entry = ttk.Entry(frame, textvariable=self.folder, width=44)
        entry.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 4))
        ttk.Button(frame, text="Browse...", command=self._browse).grid(
            row=row, column=2, pady=4)
        row += 1

        self.sort = tk.BooleanVar(value=cfg.sort_by_type)
        ttk.Checkbutton(
            frame, variable=self.sort,
            text="Sort into folders by type (Videos, Audio, Programs, ...)"
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1

        ttk.Separator(frame).grid(row=row, column=0, columnspan=3,
                                  sticky="ew", pady=6)
        row += 1

        # ---- speed ----
        self.parallel = self._number(frame, row, "Downloads at the same time",
                                     cfg.max_parallel, 1, 8)
        row += 1
        self.connections = self._number(frame, row, "Connections per file",
                                        cfg.connections, 1, 32)
        row += 1
        self.speed = self._number(frame, row, "Speed limit, KB/s (0 = none)",
                                  cfg.speed_limit_kb, 0, 1000000)
        row += 1

        self.aria2 = tk.BooleanVar(value=cfg.use_aria2c)
        ttk.Checkbutton(frame, variable=self.aria2,
                        text="Use aria2c when it is installed").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(4, 8))
        row += 1

        ttk.Separator(frame).grid(row=row, column=0, columnspan=3,
                                  sticky="ew", pady=6)
        row += 1

        # ---- the rest ----
        ttk.Label(frame, text="When a download finishes").grid(
            row=row, column=0, sticky="w", pady=4)
        self._after_labels = {text: key for key, text in AFTER_CHOICES.items()}
        self.after = ttk.Combobox(
            frame, state="readonly", values=list(AFTER_CHOICES.values()))
        self.after.set(AFTER_CHOICES[cfg.after_download])
        self.after.grid(row=row, column=1, columnspan=2, sticky="ew",
                        pady=4, padx=(8, 0))
        row += 1

        ttk.Label(frame, text="Take cookies from").grid(
            row=row, column=0, sticky="w", pady=4)
        self.cookies = ttk.Combobox(frame, state="readonly",
                                    values=[NO_COOKIES] + BROWSERS)
        self.cookies.set(cfg.cookies_browser or NO_COOKIES)
        self.cookies.grid(row=row, column=1, columnspan=2, sticky="ew",
                          pady=4, padx=(8, 0))
        row += 1
        ttk.Label(frame, foreground="#777777", font=("Segoe UI", 8),
                  text="Only needed when a site says you must sign in. "
                       "Close that browser first.").grid(
            row=row, column=0, columnspan=3, sticky="w")
        row += 1

        self.updates = tk.BooleanVar(value=cfg.check_updates)
        ttk.Checkbutton(frame, variable=self.updates,
                        text="Tell me when a new version is out").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        row += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="right", padx=(6, 0))
        ttk.Button(buttons, text="Save", command=self._save).pack(side="right")

        self.bind("<Escape>", lambda _e: self.destroy())
        entry.focus_set()

    def _number(self, frame, row, label, value, low, high):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w",
                                          pady=4)
        holder = tk.StringVar(value=str(value))
        ttk.Spinbox(frame, from_=low, to=high, textvariable=holder,
                    width=8).grid(row=row, column=1, sticky="w", pady=4,
                                  padx=(8, 0))
        return holder

    def _browse(self):
        chosen = filedialog.askdirectory(
            parent=self, title="Where should downloads go?",
            initialdir=self.folder.get() or None)
        if chosen:
            # The dialog answers with forward slashes even on Windows.
            self.folder.set(os.path.normpath(chosen))

    def _whole_number(self, holder, name, low, high):
        try:
            value = int(str(holder.get()).strip())
        except ValueError:
            messagebox.showerror("Settings",
                                 f"{name} must be a whole number.",
                                 parent=self)
            return None
        return max(low, min(high, value))

    def _save(self):
        folder = self.folder.get().strip().strip('"')
        if not folder:
            messagebox.showerror("Settings", "Choose a folder for downloads.",
                                 parent=self)
            return
        ok, why = self.ensure_folder(folder)
        if not ok:
            messagebox.showerror("Settings",
                                 f"That folder cannot be used:\n\n{why}",
                                 parent=self)
            return

        parallel = self._whole_number(self.parallel, "Downloads at the same "
                                      "time", 1, 8)
        connections = self._whole_number(self.connections,
                                         "Connections per file", 1, 32)
        speed = self._whole_number(self.speed, "Speed limit", 0, 1000000)
        if None in (parallel, connections, speed):
            return

        cfg = self.cfg
        cfg.base_dir = folder
        cfg.sort_by_type = self.sort.get()
        cfg.max_parallel = parallel
        cfg.connections = connections
        cfg.speed_limit_kb = speed
        cfg.use_aria2c = self.aria2.get()
        cfg.after_download = self._after_labels.get(self.after.get(),
                                                    cfg.after_download)
        chosen = self.cookies.get()
        cfg.cookies_browser = "" if chosen == NO_COOKIES else chosen
        cfg.check_updates = self.updates.get()

        saved, why = cfg.save()
        if not saved:
            messagebox.showerror("Settings",
                                 f"The settings could not be saved:\n\n{why}",
                                 parent=self)
            return
        self.saved = True
        self.destroy()
