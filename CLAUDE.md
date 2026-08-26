# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"        # install the package plus pytest
python -m pytest               # run all tests (no internet needed)
python -m pytest -q tests/test_http_engine.py            # one file
python -m pytest tests/test_router.py::test_a_zip_wins   # one test
python -m fdl                  # run the app from a checkout
python build_exe.py            # build dist/FreeDownloader.exe (needs pyinstaller)
python build_exe.py clean      # remove build/ and dist/
```

Tests write settings to `FDL_HOME` in CI. Set it locally too if you do not want
the suite to touch `config.json` in the repo:
`FDL_HOME=/tmp/fdl python -m pytest`.

## Making a release

The version lives in **one** place, `fdl/__init__.py`. `pyproject.toml` reads
it from there (`dynamic = ["version"]`), so the two can never disagree.

```bash
# 1. bump __version__ in fdl/__init__.py, commit
git tag v2.1.0 && git push origin v2.1.0
```

The tag runs `.github/workflows/release.yml`: it builds the `.exe` on
`windows-latest`, the wheel and sdist on Ubuntu, writes `SHA256SUMS.txt`, and
publishes a GitHub release. The body comes from `.github/release-notes.md`,
with `__VERSION__` replaced and the checksums appended. Running the workflow
by hand builds the files but publishes nothing — only a `v*` tag does that.

The `.exe` is unsigned. **Smart App Control**, which is on by default on many
new Windows 11 machines, refuses to run it, and that cannot be clicked away.
The wheel is therefore the main way to install, not a fallback. Do not write
docs that treat the `.exe` as the normal route.

## Architecture

The app is a terminal menu (`fdl/app.py`) over **two download engines**. Almost
every design decision follows from keeping those two engines apart.

### The two engines and the router

| Engine | File | Handles |
|---|---|---|
| Direct HTTP | `http_engine.py` (+ `segmented.py`, `aria2_engine.py`) | `.zip`, `.exe`, `.pdf`, any real file |
| yt-dlp | `ytdlp_engine.py` | YouTube and other media pages |

`router.py` picks one, in this fixed order. **Do not reorder these rules** —
each one exists because of a real failure:

1. The URL path ends in a known extension -> direct file. This wins even on a
   site yt-dlp knows, so `archive.org/download/x/tool.zip` is a zip.
2. yt-dlp has a real extractor for the host -> media. `looks_like_media_site()`
   deliberately ignores yt-dlp's generic extractor, which matches everything.
3. Otherwise ask the server. HTML answer -> yt-dlp, anything else -> file.

Rule 3 stops the tool from saving a login page under the name `tool.zip`.

### The part-file mode invariant (most important rule)

A download in progress is `name.part` plus a sidecar `name.part.meta` (JSON).
The meta records **how** the part was written:

| Mode | Writer | Bytes | Can be continued by |
|---|---|---|---|
| `stream` | `_download_stream` | in order, appended | this tool |
| `segments` | `SegmentedDownload` | out of order, file preallocated to full size | this tool |
| `aria2` | `aria2_engine` | aria2c owns it, plus a `.aria2` control file | aria2c only |

Rules that must hold:

- Never use `part.stat().st_size` as progress. In `segments` mode the file is
  full-size from the first second. Use `http_engine.part_progress(part, meta)`.
- Never continue a part in a different mode than the meta says. If it cannot be
  continued safely, delete the part and start again. A wrong continue produces a
  silently damaged file, which is worse than a re-download.
- `meta_matches()` compares the URL, the size, and the `ETag` before resuming.

`_plan()` in `http_engine.py` is where the mode is chosen and where an unusable
part is thrown away. Tests for each trap live in `test_segmented.py` and
`test_aria2.py`.

### Where settings live (`paths.py`)

The same code must behave in two ways:

- **Run from a checkout or the downloaded folder** (a `pyproject.toml` or
  `video_downloader.py` sits next to `fdl/`): `config.json`, `history.json`, and
  `fdl.log` go next to the app, so the folder stays portable.
- **After `pip install`**: they go to `%APPDATA%\FreeDownloaderTool`, or the
  macOS / XDG equivalent. Nothing may ever be written into `site-packages`.

`FDL_HOME` overrides both. `app.py` reads its three paths from this module only.

### Entry points

- `video_downloader.py` — thin launcher using an **absolute** import
  (`from fdl.app import run`). This is the PyInstaller entry point, because
  PyInstaller runs the entry file as a plain script and the relative import in
  `fdl/__main__.py` would fail there. Do not point `build_exe.py` at
  `fdl/__main__.py`.
- `fdl/__main__.py` — for `python -m fdl`.
- `fdl.app:run` — the `fdl` and `free-downloader` console scripts.

### Config (`config.py`)

Version 2, with per-key validation: a bad value is dropped and the default is
used, so a broken `config.json` can never crash the app. Version 1 files are
migrated on load, and `take_notice()` shows the user once what changed.
`folder_for(category)` returns the base folder when sorting is off, a subfolder
for a plain name, and the path as written when it is absolute (so one category
can live on another drive).

### Other modules

`batch.py` is the queue: it probes every link first, builds a plan, then runs
files through a thread pool while media links run one at a time (yt-dlp draws
its own progress). `limiter.py` is one token bucket shared by all threads.
`multiprogress.py` draws one line per download with ANSI cursor moves, and falls
back to plain status lines when stdout is not a terminal. `log.py` redacts
tokens and `user:pass@host` before writing.

## Things that bite

- **Proxy.** `http_engine._urlopen` bypasses the proxy for loopback hosts before
  any configured opener. Without this, a machine with `http_proxy` set fails the
  whole test suite, because the tests talk to `127.0.0.1`.
- **Console text.** The Windows console is not UTF-8 by default. Keep
  user-facing strings to plain ASCII — an em dash or a middle dot prints as `?`.
- **Heredocs.** Writing Python through a bash heredoc in this environment
  mangles backslash escapes (`\\n` becomes a real newline). Use the Write/Edit
  tools for any file containing them, and run `python -c "import fdl.app"`
  after a shell-driven edit.
- **`sys.executable` in the exe.** `ytdlp_engine.run()` starts yt-dlp with
  `[sys.executable, "-m", "yt_dlp"]`. Inside the PyInstaller exe that is the
  exe itself, and its bootloader ignores `-m`, so the call comes back to our
  own program. `app.run()` therefore checks
  `ytdlp_engine.wants_passthrough(sys.argv[1:])` **before** the menu and hands
  those arguments to `run_passthrough()`. If you change the command that
  `run()` builds, change `wants_passthrough()` to match —
  `test_frozen.py::test_the_command_that_run_builds_is_the_one_we_catch` ties
  the two together.
- **No pip in the exe.** Anything that shells out to
  `sys.executable -m pip` only works under a real Python. Guard it with
  `app.is_frozen()`.
- Tests start real `ThreadingHTTPServer` instances that can serve ranges, refuse
  ranges, or cut the connection mid-body. Add new network behaviour there rather
  than mocking urllib.
