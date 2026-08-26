# Free Downloader Tool

[![tests](https://github.com/Mohammad-Hasan-it-96/free-downloader-tool/actions/workflows/tests.yml/badge.svg)](https://github.com/Mohammad-Hasan-it-96/free-downloader-tool/actions/workflows/tests.yml)
[![latest release](https://img.shields.io/github/v/release/Mohammad-Hasan-it-96/free-downloader-tool?label=download)](https://github.com/Mohammad-Hasan-it-96/free-downloader-tool/releases/latest)

A download manager for Windows, macOS, and Linux. It has a **window** for
everyday use and a **terminal menu** for everything else.

Paste any link. The tool works out what it is:

1. **Media sites** — YouTube and 1000+ other sites, through
   [yt-dlp](https://github.com/yt-dlp/yt-dlp). You pick the quality.
2. **Direct links** — any `.exe`, `.zip`, `.pdf`, `.iso`, and so on, with
   **automatic resume** if the connection breaks.

Every file is sorted into a folder by its type, so your downloads stay tidy.

```
========================================================
          FREE DOWNLOADER TOOL
========================================================
Base folder  : D:\Downloads
Sort by type : on    At once: 3
ffmpeg       : ready    deno: ready    aria2c: ready
Cookies from : off

  1. Download (paste any link)
  2. Download many links (queue)
  3. Watch the clipboard for links
  4. Resume unfinished downloads
  5. History
  6. Settings
  7. Tools
  0. Exit
```

## The window

Double-click **`Free Downloader.bat`**, or run `fdl-gui`.

```
+----------------------------------------------------------------+
|  Paste a link:                                                 |
|  [                                        ]  [Paste]  [Add]    |
|  Video quality: [ Best available            v ]  [ ] whole     |
|  Saving to: C:\Users\me\Downloads\FreeDownloader   [Change...] |
+----------------------------------------------------------------+
|  python-3.12.0-embed-amd64.zip                    54%   [Stop] |
|  [##############################              ]                |
|  5.7 MB of 10.5 MB   104.3 KB/s                                |
|                                                                |
|  README.rst                                      done   [Open] |
|  [##############################################]              |
|  C:\Users\me\Downloads\FreeDownloader\Documents\README.rst     |
|                                                                |
|  https://example.com/this-one-does-not-exist.zip  failed [Retry]|
|  Attempt 2. The file was not found (404).                      |
+----------------------------------------------------------------+
|  [Settings]  1 done, 1 failed   [Retry failed] [Open folder]    |
+----------------------------------------------------------------+
```

- Paste a link and press **Add**. Several downloads run at once, each with
  its own bar.
- The tool still decides the engine by itself. **Video quality** and **whole
  playlist** are only used when the link turns out to be a video or audio
  page.
- **Stop** keeps the part of the file already downloaded, so it can continue
  later. **Open** shows the finished file in Explorer.
- A row that failed gets a **Retry** button, and **Retry failed** at the
  bottom tries all of them at once. A retry continues from the byte the
  first try reached, so nothing is downloaded twice.
- **Settings** covers the folder, sorting, speed, cookies, and updates.

The window needs no extra install: it uses tkinter, which comes with Python
on Windows and macOS. On Linux install `python3-tk` first. If the window
cannot open, the tool says so and falls back to the text menu.

**Still only in the text menu:** the queue from a `.txt` file, the history
screen, the clipboard watch, checksums, a proxy, extra headers, and a folder
for each type. Use `Free Downloader (terminal).bat` or `fdl` for those.

## Main features

- **Resume that is safe.** A stopped download continues from the exact byte.
  The tool also checks the server's `ETag` first, so if the file changed, it
  starts again instead of making a broken mix of old and new bytes.
- **Retry on network errors.** Each retry waits a little longer, and continues
  from where it stopped.
- **Sorting by file type.** See the table below. You can turn this off.
- **Good file names.** The name comes from the server header first, then from
  the URL. Illegal characters are removed, and an existing file is never
  overwritten by accident.
- **Live progress**: percent, size, speed, and time left.
- **Fast.** A big file is split and downloaded over several connections at
  once. On a real 10.5 MB test this was **2.2x faster** than one connection,
  and the result was byte-for-byte the same. `aria2c` is used instead when it
  is installed.
- **Speed limit**, so a download does not take all your internet.
- **A queue.** Paste many links at once, or point at a `.txt` list. Several
  download at the same time, each with its own progress line.
- **History.** Every download is recorded, and a link you already have is
  marked "skip" instead of downloading twice.
- **One Download option.** Paste any link. The tool picks the right engine,
  says why, and lets you change it. If one engine fails, it offers the other.
- **Checks that protect you**: a checksum check, a free space check, a
  warning for programs on plain `http`, and a clear message when a link
  really needs a login.
- **A log file**, with tokens and passwords removed from links.
- **Clipboard watch.** Copy a link and the tool offers to download it.
- **Proxy, extra headers, and logins** for links that need them.
- **A folder for each type**, even on another drive.
- **Asks before playlists**, so one link does not pull 200 videos.
- **Works without ffmpeg**, with a lower-quality fallback.
- **Tells you when a new version is out**, once a day, in the background.
  This can be turned off.
- **Installs the extra programs for you** with winget, from the Tools menu.

## Where files are saved

The base folder is yours to choose. The first run picks
`Downloads\FreeDownloader` inside your user folder, because every computer has
one. Change it in **Settings → Base folder**. Inside it:

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

The extension decides the folder. The MIME type from the server is used only
when the file has no useful extension.

## Requirements

| Tool | Needed for | Install |
|---|---|---|
| Python 3.9+ | the app itself | [python.org](https://www.python.org/downloads/) |
| yt-dlp | media sites | `pip install -U yt-dlp` |
| ffmpeg | merging HD video + audio, and MP3 | `winget install Gyan.FFmpeg` |
| deno | JavaScript that yt-dlp needs for YouTube | `winget install DenoLand.Deno` |
| aria2c | even faster single downloads (optional) | `winget install aria2.aria2` |

Direct file links need **only Python** — no extra install. If yt-dlp is
missing, the app tells you at startup and offers to install it.

`aria2c` is optional. Without it the built-in multi-connection downloader is
used, which is already much faster than one connection.

You do not have to type those winget commands yourself. **Tools → Install the
extra programs** lists what is missing and installs it for you, one at a time.

## The first run

The first time you start the tool, it asks one question: where should the
files go. It suggests `Downloads\FreeDownloader` inside your own user folder.
Press Enter to keep it, or type another folder.

Everything else already has a sensible default, and all of it can be changed
later in **Settings**.

## How to install

Pick the first line in this table that fits you.

| You have | Do this | Notes |
|---|---|---|
| Python 3.9 or newer | download the `.whl` from [Releases](https://github.com/Mohammad-Hasan-it-96/free-downloader-tool/releases) and `pip install` it | best way, easy to update |
| no Python | download `FreeDownloader.exe` from [Releases](https://github.com/Mohammad-Hasan-it-96/free-downloader-tool/releases) | read the warning below |
| the source folder | double-click **`Free Downloader.bat`** | needs Python on the computer |

Every release also has a `SHA256SUMS.txt`, so you can check that a file is
really the one that was built. On Windows:

```
certutil -hashfile FreeDownloader.exe SHA256
```

### Windows may block the .exe

The `.exe` is not signed with a paid certificate, so Windows does not know it
yet.

| Message | What to do |
|---|---|
| "Windows protected your PC" (SmartScreen) | Click **More info**, then **Run anyway** |
| "An Application Control policy has blocked this file" (Smart App Control) | This cannot be clicked away. Use Python and the `.whl` instead |

Smart App Control is **on by default on many new Windows 11 computers**. It
blocks every unsigned program. This is a limit of the `.exe`, not a bug in the
tool, and the Python way always works.

## How to run

**1. Portable, no install.** Double-click **`Free Downloader.bat`** to get
the window. For the text menu, double-click
**`Free Downloader (terminal).bat`**, or run:

```bash
python -m fdl              # the text menu
python -m fdl --gui        # the window
```

Settings stay next to the app, so the whole folder can be copied to a USB
stick.

**2. Install it with pip.**

```bash
pip install .
fdl
```

This gives you an `fdl` command (the text menu) and an `fdl-gui` command
(the window), both working from any folder. An installed copy
keeps its settings in the normal user folder, never inside Python:

| System | Where the settings go |
|---|---|
| Windows | `%APPDATA%\FreeDownloaderTool` |
| macOS | `~/Library/Application Support/FreeDownloaderTool` |
| Linux | `~/.config/free-downloader-tool` (or `$XDG_CONFIG_HOME`) |

Set `FDL_HOME` to put them anywhere else.

**3. Build the `.exe` yourself.** Releases carry a ready-made one, so this is
only needed if you changed the code.

```bash
pip install ".[build]"
python build_exe.py
```

The result is `dist/FreeDownloader.exe`. Python and yt-dlp are inside it, so
it is about 30 MB. ffmpeg, deno, and aria2c are **not** inside; the app still
finds them if they are installed, and says what to do when they are missing.

The `.exe` starts yt-dlp by running itself again, so video sites work with no
Python on the computer at all.

## Downloading one link

Choose option **1** and paste any link. You do not choose the engine — the
tool works it out and tells you:

```
  This looks like : a direct file link
  Because         : the link ends in a file name

  Press Enter to continue, or type 'o' to use a video / audio page (yt-dlp).
```

Press Enter to accept, or `o` to use the other engine. If the chosen engine
fails, the tool offers the other one before giving up.

**How it decides**, in this order:

1. The link path ends in a known extension (`.zip`, `.exe`, `.mp4`, …) →
   direct file. This wins even on a site yt-dlp knows, so
   `archive.org/download/item/tool.zip` is treated as a zip, not a video page.
2. yt-dlp has a real extractor for the site (YouTube, Vimeo, …) → media page.
3. Otherwise the server is asked. If it answers with a web page, yt-dlp gets
   it. If it answers with a file, the file downloader gets it.

Rule 3 is why a link with no extension is never saved as an HTML error page
by mistake.

Before anything is saved, a direct file shows you what was found:

```
  Name     : python-3.12.0-embed-amd64.zip
  Size     : 10.5 MB
  Type     : Archives
  Save to  : D:\Downloads\Archives
  Resume   : supported
  Speed    : 8 connections at once
```

While a download runs, the file is written as `name.part`. If you press
`Ctrl+C`, or the connection dies, that part is kept. Use option **4**,
**Resume unfinished downloads**, to continue it later.

## Downloading many links at once

Choose option **2**, then paste your links, one per line. An empty line
finishes the list. You can also type the path of a `.txt` file that holds the
links, one per line.

The tool checks every link first and shows a plan before anything is saved:

```
Plan:
  1. python-3.12.0-embed-amd64.zip
      10.5 MB -> D:\Downloads\Archives
  2. README.md
      174.9 KB -> D:\Downloads\Documents
  3. skip  song.mp3
      already downloaded to D:\Downloads\Audio\song.mp3
  4. cannot use  https://example.com/gone.zip
      The file was not found (404).

  Total to download: about 10.7 MB
```

While the queue runs, each file has its own line:

```
 > [1] python-3.12.0-embed-amd64.zip    44.4%  4.7 MB  598.1 KB/s  ETA 00:10
 > [2] README.md                        81.0%  141.7 KB  210.4 KB/s  ETA 00:00
 - [3] song.mp3                         already downloaded
 x [4] gone.zip                         The file was not found (404).
```

One bad link never stops the others. How many run at the same time is a
setting (1 to 8, default 3).

Media links in a queue are handled one after another, because yt-dlp shows
its own progress.

## Speed

A big file is cut into parts, and the parts download at the same time. This
only happens when the server allows it, and only for files above 2 MB.

| Setting | What it does | Default |
|---|---|---|
| Connections per file | How many parts of one file download together (1 to 32). 1 turns splitting off. | 8 |
| Downloads at once | How many files the queue runs together (1 to 8). | 3 |
| Speed limit | Highest total speed, in KB per second. 0 means no limit. | 0 |
| Use aria2c | Use aria2c for single large downloads, when it is installed. | on |

Before a single download starts, the tool tells you what it will do:

```
  Speed    : 8 connections at once
```

A split download is **not** the same as a normal one on disk. The `.part`
file is created at its full size right away, so its size does not tell you
how much is done. The real progress of every part is kept in the
`.part.meta` file next to it.

This matters for resume. The meta file records **how** the part was written:

| Mode | Written by | Continued by |
|---|---|---|
| `stream` | one connection, bytes in order | this tool |
| `segments` | several connections, bytes out of order | this tool |
| `aria2` | the aria2c program | aria2c only |

The tool always reads the mode before it continues a file, so a part is
never continued by the wrong method. If it cannot be continued safely, the
download starts again instead of making a damaged file.

## Watching the clipboard

Choose option **3**. Every time you copy a link, the tool offers it:

```
New link: https://example.com/tool.zip
Download it? [Y/n/q]:
```

Press Enter to download it, `n` to ignore it, or `q` to stop watching.
`Ctrl+C` also stops. Only plain `http` and `https` links are offered, so
copying ordinary text does nothing.

On Windows and macOS this works out of the box. On Linux it needs `xclip`,
`xsel`, or `wl-clipboard`.

## Links that need a login, a header, or a proxy

**A login in the link.** Write it as `https://user:password@host/file.zip`.
The tool takes the login out of the address and sends it in an
`Authorization` header, which is where it belongs. The log never shows it.

**Extra headers.** Some sites only answer when a header is present, most
often `Referer`. **Settings → Extra headers** lets you add, change, and
delete them. They are sent with every direct download.

**Proxy.** **Settings → Proxy** takes three kinds of answer:

| You type | What happens |
|---|---|
| *(blank)* | follow the computer's own proxy settings (the default) |
| `none` | never use a proxy |
| `http://10.0.0.1:3128` | send everything through that proxy |

Addresses on your own computer always skip the proxy, because no proxy can
reach them.

## When a download finishes

**Settings → After a download finishes** can open the folder with the file
selected, make a sound, do both, or do nothing (the default).

## A folder for each type

**Settings → Folder for each type** changes where any one type goes.

- A plain name such as `Films` goes inside the base folder.
- A full path such as `E:/Programs` is used exactly as written, so one type
  can live on a different drive.
- Type `-` to go back to the default.

## Checks that protect you

**Checksum.** Before a download starts you can paste the checksum the site
published. When the file is saved, the tool works out the real value and
compares them:

```
[OK] The sha256 checksum matches. The file is exactly what the site published.
```

If it does not match, the tool says so plainly and offers to delete the file:

```
[WARNING] The sha256 checksum does NOT match.
  expected: fd611b728e7fda802b450bbdbe84ef6e625e2a0b4df4dae2eff07e5442fdcc53
  actual  : 9c121e619bfe02eaba582d7080eea46fd53ec0b50717e6794a948fada4ae8f3c
The file is damaged, or it is not the file the site published.
```

MD5, SHA-1, SHA-256, and SHA-512 are recognised by the length of the value.
Forms like `sha256:abc...`, `SHA-256 = abc...`, and `abc...  program.zip` all
work. **Tools → Check a file against a checksum** does the same for any file
already on your disk.

**Free space.** The tool checks the drive before it starts, and keeps 50 MB
free, so a big download cannot fill the disk completely. The queue checks the
total of all its files at once.

**Programs over plain `http://`.** A `.exe` or `.msi` on a plain `http` link
is not protected on the way, so somebody on the same network could change it.
The tool warns and asks before downloading. The default answer is **No**.

**Login pages.** If you ask for `tool.zip` and the server answers with a web
page, the tool tells you instead of saving that page under the name
`tool.zip`. This usually means the link needs a login, or it has moved.

## The log file

Everything important is written to `fdl.log`, next to the app: downloads that
finished, downloads that failed, retries, checksum results, and warnings.
The file is rotated at 1 MB, so it cannot grow without end.

**Tools → Show the last lines of the log** reads it inside the app.

Links are cleaned before they are written. A token, a key, or a password in a
link becomes `***`, so the log is safe to share when you ask for help.

## History

Option **5** shows the last 20 downloads: name, time, size, folder, and any
error. Links that were downloaded before are skipped automatically, as long
as the file is still on the disk. The history is stored in `history.json`
next to the app, and you can clear it from the same screen.

## Playlists

If the link contains `list=`, the app asks:

```
This link belongs to a playlist.
Download the WHOLE playlist? [y/N]:
```

The default answer is **No**, so you get only the one video.

## If ffmpeg is not installed

The app does not fail. It changes what it does:

- **Normal quality choices** — downloads the best single file that already
  has video and audio. Quality may be lower than the true maximum.
- **MP3** — cannot convert. It offers to save the raw audio instead.
- **Format codes** — a code like `137+140` cannot be merged. Pick one code
  that already has video and audio.

## Fixing YouTube "Sign in to confirm you're not a bot"

1. Open **Settings**, choose **Browser for cookies**, and select the browser
   where you are logged into YouTube.
2. **Fully close that browser.** While it runs, the cookie file is locked.
3. Download again.

Some Chrome and Edge versions encrypt their cookies and still refuse. Then
export a `cookies.txt` file with an extension such as "Get cookies.txt
LOCALLY", and run:

```bash
python -m yt_dlp --cookies cookies.txt -f best <URL>
```

> **Note:** cookies identify your logged-in account to the site. Leave this
> setting off unless you need it.

## Settings

Settings live in `config.json`, created on first run. Two more files sit
beside it: `history.json` and `fdl.log`. Where that folder is depends on how
you run the tool — see **How to run** above.

```json
{
  "version": 2,
  "base_dir": "D:\\Downloads",
  "sort_by_type": true,
  "category_folders": { "Videos": "Videos", "Audio": "Audio" },
  "cookies_browser": "",
  "retries": 5,
  "max_parallel": 3,
  "connections": 8,
  "speed_limit_kb": 0,
  "use_aria2c": true,
  "history_limit": 500,
  "proxy": "",
  "headers": {},
  "after_download": "nothing",
  "check_updates": true
}
```

Bad values are ignored and the defaults are used, so a broken file cannot
crash the app. Settings from version 1 of the tool are upgraded
automatically, and you are told once what changed.

## Project layout

```
fdl/
  app.py            the menu
  router.py         decides which engine a link needs
  safety.py         free space, plain http, and login page checks
  clipboard.py      reads the clipboard on each system
  postaction.py     open the folder, or make a sound
  checksum.py       reads and compares checksums
  log.py            the log file, with links cleaned
  paths.py          where settings, history, and the log are kept
  batch.py          the queue: check links, download many at once
  history.py        the record of what was downloaded
  multiprogress.py  one progress line per download
  config.py         settings: load, check, save, upgrade
  categories.py     extension -> folder
  naming.py         safe file names
  http_engine.py    direct links, resume, retry, choosing the mode
  segmented.py      one file over several connections
  aria2_engine.py   the aria2c program, when it is installed
  limiter.py        the shared speed limit
  ytdlp_engine.py   media sites
  progress.py       the progress line
  tools.py          finds ffmpeg / deno / aria2c
  term.py           colours, sizes, times
tests/              pytest suite
```

## Running the tests

```bash
pip install -e ".[dev]"
python -m pytest
```

The tests start a small web server on your own computer, so no internet is
needed. 247 tests cover file naming, categories, settings, history, the
queue, link routing, safety checks, checksums, the log, the clipboard, the
proxy, logins in links, the speed limit, multi-connection downloads, where settings are stored, and real resume —
including a server that cuts the connection in the middle, and the check that
a split part file is never continued the wrong way.

## Troubleshooting

| Problem | What to do |
|---|---|
| `ffmpeg : NOT FOUND` in the header | Tools -> Install the extra programs. |
| Nothing happens when you double-click the `.bat` | Python is missing. The file now says so and gives the download link. |
| The `.exe` will not start at all | Smart App Control is blocking it. Use Python and the wheel instead. |
| "yt-dlp is NOT installed" | Say yes to the install question, or run the command it prints. |
| Download fails on YouTube | Update yt-dlp (Tools), then set a cookies browser (Settings). |
| "Cannot use the folder" | The drive or path does not exist. Change it in Settings. |
| A download keeps stopping | Run it again, or use option 4. It continues from the last byte. |
| Link needs a login (401/403) | The tool cannot download it without your cookies or a token. |
| "The server sent a web page, not the file" | The link needs a login, or it has moved. Open it in a browser first. |
| "Not enough free space" | Free some space, or change the base folder in Settings. |
| Something went wrong and you want details | Tools -> Show the last lines of the log. |
| The clipboard watch says it cannot read | On Linux, install xclip, xsel, or wl-clipboard. |
| A site refuses the download but works in a browser | Add a `Referer` header in Settings -> Extra headers. |

## Roadmap

Phases 0 to 7 are done. Phase 8 makes the tool easy for other people to
install, and step 1 of it is done. See **[ROADMAP.md](ROADMAP.md)** for what
was built, what is left, and the "maybe later" list: faster torrents through
aria2c, a scheduler, and browser integration.

## Legal note

Download only content that you own, or that its license allows. Respect the
terms of service of each site.

## License

Apache License 2.0. See [LICENSE](LICENSE).
