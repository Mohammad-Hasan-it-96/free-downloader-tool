# Free Downloader Tool

A simple terminal app that downloads videos and audio, powered by
[yt-dlp](https://github.com/yt-dlp/yt-dlp).

It works with YouTube and 1000+ other sites. You pick the quality, and the file
is saved to any folder you choose (default: `D:\Videos`, so your C: drive stays
free).

```
====================================================
          VIDEO DOWNLOADER  (yt-dlp)
====================================================
Save folder  : D:\Videos
ffmpeg       : C:\...\ffmpeg-9.0-full_build\bin
deno (JS)    : ready
Cookies from : off

  1. Download a video / audio
  2. Change download folder
  3. Set browser for cookies (fix 'not a bot')
  4. Show available formats for a URL
  5. Update yt-dlp
  0. Exit
```

## Features

- Pick the quality: best, 1080p, 720p, 480p, 360p, MP3 audio, or an exact
  format code.
- Asks before downloading a whole playlist, so one link does not pull 200 files.
- Finds `ffmpeg` and `deno` by itself. You do not set any paths.
- Still works without `ffmpeg`, by falling back to the best single file.
- Uses browser cookies to pass YouTube's "not a bot" check.
- Remembers your settings in `config.json`.

## Requirements

| Tool | Needed for | Install |
|---|---|---|
| Python 3.9+ | the app itself | [python.org](https://www.python.org/downloads/) |
| yt-dlp | downloading | `pip install -U yt-dlp` |
| ffmpeg | merging HD video + audio, and MP3 | `winget install Gyan.FFmpeg` |
| deno | JavaScript that yt-dlp needs for YouTube | `winget install DenoLand.Deno` |

Only Python and yt-dlp are required. Without `ffmpeg` the app still runs, but
quality is lower and MP3 conversion is off. Without `deno`, some YouTube
downloads may fail.

If yt-dlp is missing, the app tells you at startup and offers to install it.

## How to run

On Windows, double-click **`Download Video.bat`**.

Or from a terminal:

```bash
python video_downloader.py
```

## Menu options

| Option | What it does |
|---|---|
| 1 | Download a video or audio. Paste the URL, then pick the quality. |
| 2 | Change the download folder. The path is checked before it is saved. |
| 3 | Choose the browser to read cookies from. Fixes the "not a bot" error. |
| 4 | Show every available format for a URL, with its format code. |
| 5 | Update yt-dlp with pip. Do this often — sites change. |
| 0 | Exit. |

## Quality choices

| Choice | Result |
|---|---|
| Best | Highest video + highest audio, merged into MP4. |
| 1080p / 720p / 480p / 360p | Best file at that height or lower. |
| Audio only (MP3) | Extracts audio and converts it to MP3, best quality. |
| Pick a format code | Shows the format list, then you type a code, for example `137+140`. |

## Playlists

If the link contains `list=` (for example
`youtube.com/watch?v=ABC&list=PL123`), the app asks:

```
This link belongs to a playlist.
Download the WHOLE playlist? [y/N]:
```

The default answer is **No**, so you get only the one video. Press `y` if you
really want every video in the playlist.

## If ffmpeg is not installed

The app does not fail. It changes what it does:

- **Normal quality choices** — downloads the best single file that already
  contains video and audio. Quality may be lower than the true maximum.
- **MP3** — cannot convert. It offers to save the raw audio instead (`.m4a` or
  `.webm`).
- **Format codes** — a code like `137+140` cannot be merged. Pick one single
  code that already has video and audio.

## Fixing YouTube "Sign in to confirm you're not a bot"

YouTube sometimes blocks anonymous downloads. Use your browser cookies:

1. In the app, choose menu option **3**, and select the browser where you are
   logged into YouTube (for example `edge` or `chrome`).
2. **Fully close that browser.** While it runs, the cookie file is locked and
   cannot be read.
3. Download again.

Some Chrome and Edge versions encrypt their cookies and still refuse. In that
case, export a `cookies.txt` file with a browser extension such as
"Get cookies.txt LOCALLY", then run:

```bash
python -m yt_dlp --cookies cookies.txt -f best <URL>
```

> **Note:** cookies identify your logged-in account to the site. Leave this
> setting off unless you need it.

## Settings file

Settings are stored next to the script in `config.json`:

```json
{
  "download_dir": "D:\\Videos",
  "cookies_browser": ""
}
```

- `download_dir` — where files are saved. Must be a text path.
- `cookies_browser` — one of `edge`, `chrome`, `brave`, `firefox`, `opera`,
  `vivaldi`, `chromium`, or `""` to turn cookies off.

Bad values are ignored and the defaults are used, so a broken file cannot crash
the app.

## Troubleshooting

| Problem | What to do |
|---|---|
| Header shows `ffmpeg : NOT FOUND` | Run `winget install Gyan.FFmpeg`, then restart the app. |
| "yt-dlp is NOT installed" at startup | Say yes to the install question, or run the command it prints. |
| Download fails on YouTube | Update yt-dlp (option 5) first. Then try cookies (option 3). |
| "Cannot use the save folder" | The drive or path does not exist. Use option 2 to pick another folder. |
| Downloads go to the wrong place | Check the "Save folder" line in the header, and fix it with option 2. |

## Legal note

Download only content that you own, or that its license allows. Respect the
terms of service of each site.

## License

Apache License 2.0. See [LICENSE](LICENSE).
