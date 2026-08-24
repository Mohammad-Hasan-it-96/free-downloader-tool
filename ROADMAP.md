# Roadmap — Free Downloader Tool

Goal: grow the tool from a **video downloader** into a **general download
manager** for the terminal.

Three decisions are fixed:

| Decision | Choice |
|---|---|
| Interface | Terminal menu only. Code is split so a GUI can be added later. |
| Engine for direct links | Pure Python (works everywhere), and `aria2c` when it is installed, for speed. |
| Code layout | A Python package of small modules, not one big file. |

Legend: ✅ done · 🔨 in progress · ⬜ planned

---

## Phase 0 — Groundwork

Nothing new for the user, but everything after this depends on it.

- ⬜ Split the single script into a package: `fdl/`
  (`config`, `categories`, `naming`, `tools`, `progress`, engines, `app`).
- ⬜ New settings format (version 2) with a safe upgrade from the old
  `config.json`. Old values are never lost without telling the user.
- ⬜ Remove Windows-only assumptions, so it also runs on Linux and macOS.
- ⬜ Add a `tests/` folder and the first tests.
- ⬜ Keep `Download Video.bat` working during the change.

## Phase 1 — Direct file downloads, resume, and type folders

This is the main request.

- ⬜ **Direct link downloader** in pure Python (`urllib`, no extra install):
  `.exe`, `.zip`, `.pdf`, `.iso`, anything.
- ⬜ **Auto-resume.** The file is written as `name.part`. If the download stops,
  the next run sends an HTTP `Range` header and continues from that byte.
- ⬜ **Safe resume.** A small sidecar file remembers the URL, the size, and the
  server `ETag`. If the file on the server changed, the download restarts
  instead of producing a broken file.
- ⬜ **Retry with backoff.** Network errors retry a few times, each time waiting
  a bit longer, and each retry continues where it stopped.
- ⬜ **Folders by type.** Files are sorted automatically:

  | Folder | Examples |
  |---|---|
  | `Videos` | mp4, mkv, avi, mov, webm |
  | `Audio` | mp3, m4a, flac, wav, opus |
  | `Programs` | exe, msi, apk, deb, dmg, AppImage |
  | `Archives` | zip, rar, 7z, tar.gz, iso |
  | `Documents` | pdf, docx, xlsx, epub, txt |
  | `Images` | jpg, png, gif, webp, svg |
  | `Code` | py, js, json, sql, whl, jar |
  | `Other` | everything else |

  Sorting can be turned off, and every folder name can be changed.
- ⬜ **Good file names.** The name comes from the `Content-Disposition` header
  first, then from the URL. Illegal characters are removed. Windows reserved
  names (`CON`, `NUL`, …) are handled. An existing file is never overwritten by
  accident — the new file becomes `name (1).ext`.
- ⬜ **Live progress**: percent, downloaded / total, speed, and time left.

## Phase 2 — One smart "Download" option

- ⬜ Paste any URL into **one** menu item. The tool decides by itself:
  a media page goes to yt-dlp, a direct file link goes to the file downloader.
- ⬜ If one engine fails, try the other before giving up.
- ⬜ yt-dlp results also land in the right folder (`Videos` or `Audio`).

## Phase 3 — Speed

- ⬜ Use **aria2c** when it is installed (16 connections, built-in resume).
  The tool finds it the same way it finds ffmpeg today.
- ⬜ Without aria2c, use **multi-connection download in Python**: split the file
  into parts, download them at the same time, write into one file.
  Only when the server supports `Range`.
- ⬜ **Speed limit** setting, so a big download does not block your internet.

## Phase 4 — Queue and history

- ⬜ **Queue**: paste many URLs at once, or load a `.txt` list.
- ⬜ Run several downloads at the same time, with a "how many at once" setting.
- ⬜ **History file**: URL, saved path, size, date, and status.
- ⬜ **Resume all unfinished** — one menu item that restarts every broken
  download from the last byte.
- ⬜ **Duplicate check**: warn if this URL, or a file with the same name and
  size, is already downloaded.

## Phase 5 — Trust and safety

- ⬜ **Checksum check** (SHA-256 / MD5) after download, when you paste one.
- ⬜ **Free space check** before starting, so you do not fill the disk.
- ⬜ **Log file** for troubleshooting.
- ⬜ Warn when a program file (`.exe`, `.msi`) comes from a plain `http://`
  link, because it can be changed on the way.
- ⬜ Clear message when a link needs a login, instead of saving the HTML
  error page as if it were the file.

## Phase 6 — Convenience

- ⬜ **Clipboard watch** (optional): when you copy a link, the tool offers to
  download it.
- ⬜ **Custom headers, cookies, basic auth, and proxy** for protected links.
- ⬜ **After download**: open the folder, or play a sound.
- ⬜ Per-category custom folders (for example, send `Programs` to another drive).

## Phase 7 — Packaging and quality

- ⬜ `pyproject.toml` and an `fdl` command, so `pip install .` works.
- ⬜ Full `pytest` suite: naming, categories, config, and resume logic
  (with a small local test server, no internet needed).
- ⬜ GitHub Actions CI: run the tests on every push.
- ⬜ Optional single `.exe` build with PyInstaller, for people without Python.

## Maybe later

These are useful, but they are not needed for a good tool. They go last.

- ⬜ Torrent and magnet links, through aria2c.
- ⬜ Scheduler: start downloads at a chosen time, for example at night.
- ⬜ Browser integration: a "send to downloader" helper.
- ⬜ Mirror support: same file from several servers.

## Not planned

- No GUI for now (the code stays ready for one).
- No account system, no cloud sync.
- No downloading of DRM-protected content.

---

## Order of work

1. Phase 0 + Phase 1 together — the restructure and the main feature.
2. Phase 2 — makes the tool feel like one product.
3. Phase 3 — speed.
4. Phase 4 — queue and history.
5. Phase 5, 6, 7 — polish, safety, and packaging.
