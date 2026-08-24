# Free Downloader Tool

A download manager for the terminal.

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
  3. Resume unfinished downloads
  4. History
  5. Settings
  6. Tools
  0. Exit
```

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
- **Asks before playlists**, so one link does not pull 200 videos.
- **Works without ffmpeg**, with a lower-quality fallback.

## Where files are saved

The base folder is yours to choose. Inside it:

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

## How to run

On Windows, double-click **`Download Video.bat`**.

Or from a terminal:

```bash
python -m fdl
# or
python video_downloader.py
```

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
`Ctrl+C`, or the connection dies, that part is kept. Use option **3**,
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

## History

Option **4** shows the last 20 downloads: name, time, size, folder, and any
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

Settings live in `config.json`, next to the app. It is created on first run.

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
  "history_limit": 500
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
pip install pytest
python -m pytest
```

The tests start a small web server on your own computer, so no internet is
needed. 152 tests cover file naming, categories, settings, history, the
queue, link routing, the speed limit, multi-connection downloads, and real
resume —
including a server that cuts the connection in the middle, and the check that
a split part file is never continued the wrong way.

## Troubleshooting

| Problem | What to do |
|---|---|
| `ffmpeg : NOT FOUND` in the header | Run `winget install Gyan.FFmpeg`, then restart. |
| "yt-dlp is NOT installed" | Say yes to the install question, or run the command it prints. |
| Download fails on YouTube | Update yt-dlp (Tools), then set a cookies browser (Settings). |
| "Cannot use the folder" | The drive or path does not exist. Change it in Settings. |
| A download keeps stopping | Run it again, or use option 3. It continues from the last byte. |
| Link needs a login (401/403) | The tool cannot download it without your cookies or a token. |

## Roadmap

The plan for the next versions is in **[ROADMAP.md](ROADMAP.md)**: faster
checksum checks, a free space check, clipboard watch, proxy settings, and
packaging.

## Legal note

Download only content that you own, or that its license allows. Respect the
terms of service of each site.

## License

Apache License 2.0. See [LICENSE](LICENSE).
