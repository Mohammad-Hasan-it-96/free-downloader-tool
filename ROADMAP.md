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

## Phase 0 — Groundwork ✅

Nothing new for the user, but everything after this depends on it.

- ✅ Split the single script into a package: `fdl/`
  (`config`, `categories`, `naming`, `tools`, `progress`, engines, `app`).
- ✅ New settings format (version 2) with a safe upgrade from the old
  `config.json`. Old values are never lost without telling the user.
- ✅ Remove Windows-only assumptions, so it also runs on Linux and macOS.
- ✅ Add a `tests/` folder and the first tests.
- ✅ Keep `Download Video.bat` working during the change.

## Phase 1 — Direct file downloads, resume, and type folders ✅

This is the main request.

- ✅ **Direct link downloader** in pure Python (`urllib`, no extra install):
  `.exe`, `.zip`, `.pdf`, `.iso`, anything.
- ✅ **Auto-resume.** The file is written as `name.part`. If the download stops,
  the next run sends an HTTP `Range` header and continues from that byte.
- ✅ **Safe resume.** A small sidecar file remembers the URL, the size, and the
  server `ETag`. If the file on the server changed, the download restarts
  instead of producing a broken file.
- ✅ **Retry with backoff.** Network errors retry a few times, each time waiting
  a bit longer, and each retry continues where it stopped.
- ✅ **Folders by type.** Files are sorted automatically:

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
- ✅ **Good file names.** The name comes from the `Content-Disposition` header
  first, then from the URL. Illegal characters are removed. Windows reserved
  names (`CON`, `NUL`, …) are handled. An existing file is never overwritten by
  accident — the new file becomes `name (1).ext`.
- ✅ **Live progress**: percent, downloaded / total, speed, and time left.

## Phase 2 — One smart "Download" option ✅

- ✅ Paste any URL into **one** menu item. The tool decides by itself:
  a media page goes to yt-dlp, a direct file link goes to the file downloader.
  It shows what it decided and why, and you can change it with one key.
- ✅ If one engine fails, it offers the other before giving up.
- ✅ yt-dlp results also land in the right folder (`Videos` or `Audio`).
- ✅ The queue uses the same rules, so it never saves a web page as a file.

## Phase 3 — Speed ✅

- ✅ Use **aria2c** when it is installed (16 connections, built-in resume).
  The tool finds it the same way it finds ffmpeg today. It is used for single
  large downloads, where aria2c can print its own progress.
- ✅ Without aria2c, use **multi-connection download in Python**: split the file
  into parts, download them at the same time, write into one file.
  Only when the server supports `Range`. Used everywhere, including the queue.
  Each part remembers its own progress, so a split download resumes correctly.
- ✅ **Speed limit** setting, so a big download does not block your internet.

## Phase 4 — Queue and history ✅

- ✅ **Queue**: paste many URLs at once, or load a `.txt` list.
- ✅ Run several downloads at the same time, with a "how many at once" setting.
- ✅ **History file**: URL, saved path, size, date, and status.
- ✅ **Resume all unfinished** — one menu item that restarts every broken
  download from the last byte.
- ✅ **Duplicate check**: warn if this URL, or a file with the same name and
  size, is already downloaded.

## Phase 5 — Trust and safety ✅

- ✅ **Checksum check** after download, when you paste one. MD5, SHA-1,
  SHA-256, and SHA-512 are recognised by the length of the value. Any file on
  the disk can also be checked from the Tools menu.
- ✅ **Free space check** before starting, so you do not fill the disk.
- ✅ **Log file** for troubleshooting, with links cleaned of tokens and
  passwords before they are written.
- ✅ Warn when a program file (`.exe`, `.msi`) comes from a plain `http://`
  link, because it can be changed on the way.
- ✅ Clear message when a link needs a login, instead of saving the HTML
  error page as if it were the file.

## Phase 6 — Convenience ✅

- ✅ **Clipboard watch** (optional): when you copy a link, the tool offers to
  download it.
- ✅ **Custom headers, cookies, basic auth, and proxy** for protected links.
  A login written into a link (`https://user:pass@host/file`) is turned into
  an `Authorization` header, so it never travels in the address.
- ✅ **After download**: open the folder, or play a sound.
- ✅ Per-category custom folders. A plain name goes inside the base folder;
  a full path such as `E:/Programs` is used exactly as written.

## Phase 7 — Packaging and quality ✅

- ✅ `pyproject.toml` and an `fdl` command, so `pip install .` works. An
  installed copy keeps its settings in the user folder, never inside Python.
- ✅ Full `pytest` suite: 247 tests, with a small local test server, so no
  internet is needed.
- ✅ GitHub Actions CI: the tests run on Windows and Linux, on Python 3.9,
  3.11, and 3.13, and the package is built and checked.
- ✅ Optional single `.exe` build with PyInstaller, for people without Python.

## Phase 8 — ready for other people

Everything above assumes the person already has Python, and a `D:` drive.
This phase is about someone else's computer.

**Step 1 — make the .exe correct** ✅

- ✅ **The .exe can download videos.** `ytdlp_engine.run()` starts yt-dlp with
  `sys.executable -m yt_dlp`. Inside the .exe, `sys.executable` is the .exe
  itself and `-m` is ignored, so that call used to open a second copy of the
  menu. Every video download in the .exe silently failed this way. The
  launcher now catches the call and hands it to yt-dlp.
- ✅ **No pip offer inside the .exe.** There is no pip in a frozen build, so
  the old "Install it now with pip?" question was a dead end.
- ✅ **A default folder that exists everywhere.** The old default was
  `D:\Downloads`. On another computer `D:` can be a DVD drive, a USB stick, or
  missing. The default is now `Downloads\FreeDownloader` in the user's own
  folder. A folder already saved in `config.json` is not changed.

**Step 2 — make it reachable** ✅

- ✅ A release workflow. Pushing a `v*` tag builds the `.exe` on
  `windows-latest`, the wheel and the source archive on Ubuntu, and publishes
  them as a GitHub release. Before this, `dist/` was ignored by git, so nobody
  could get the tool at all.
- ✅ `SHA256SUMS.txt` in every release, with instructions to check it.
- ✅ One place for the version number: `fdl/__init__.py`. `pyproject.toml`
  reads it from there, so a release cannot ship two different numbers.

**What we learned: the `.exe` is not the main way to install.**

Windows on this machine refused to run a freshly built `.exe`:

```
An Application Control policy has blocked this file
```

That is **Smart App Control**. It is on by default on many new Windows 11
computers, it blocks every unsigned program, and the user cannot click through
it. SmartScreen can be clicked through; Smart App Control cannot.

| Way to install | Works with Smart App Control on? |
|---|---|
| unsigned `.exe` | no |
| signed `.exe` (needs a paid certificate) | yes |
| wheel, through `pip` | yes |

So the wheel is the main way, and the `.exe` is for people with no Python.
The README and the release notes now say this plainly. A signing certificate
is the only thing that would change it, and it costs money every year.

- ⬜ Publish the wheel to PyPI, so `pip install free-downloader-tool` works
  without downloading a file first. This needs a PyPI account and a token.

**Step 3 — make it friendly** ⬜

- ⬜ The `.bat` file should try `py -3`, then `python`, and print the
  python.org link when neither works. On a clean Windows 11, `python` opens
  the Microsoft Store instead.
- ⬜ A Tools option that installs ffmpeg, deno, and aria2c with `winget`.
- ⬜ A short first-run screen: choose a folder, then start.
- ⬜ A daily update check against the GitHub releases API.

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

1. ✅ Phase 0 + Phase 1 — the restructure and the main feature.
2. ✅ Phase 4 — queue and history.
3. ✅ Phase 3 — speed.
4. ✅ Phase 2 — one smart "Download" option.
5. ✅ Phase 5 — trust and safety.
6. ✅ Phase 6 — convenience.
7. ✅ Phase 7 — packaging and quality.

8. 🔄 Phase 8 — ready for other people. Steps 1 and 2 are done. Step 3 is
   still open.

Phases 0 to 7 are done. Phase 8 is what turns this from "my tool" into a tool
anyone can download.
