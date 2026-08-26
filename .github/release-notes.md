A download manager for the terminal. Paste any link: it downloads videos from
media sites through yt-dlp, and any other file directly, with resume.

## Which file do I need?

**If you have Python** (any version from 3.9), this is the best way. It always
works, and updating is one command.

```
pip install free_downloader_tool-__VERSION__-py3-none-any.whl
fdl
```

**If you do not have Python**, download `FreeDownloader.exe`. Python and
yt-dlp are inside it. Please read the warning below first.

| File | For |
|---|---|
| `FreeDownloader.exe` | Windows, no Python needed |
| `free_downloader_tool-__VERSION__-py3-none-any.whl` | any system with Python |
| `free_downloader_tool-__VERSION__.tar.gz` | the source |
| `SHA256SUMS.txt` | to check what you downloaded |

## Windows may block the .exe

The `.exe` is not signed with a paid certificate, so Windows does not know it
yet. You may see one of these:

**"Windows protected your PC"** (SmartScreen). Click **More info**, then
**Run anyway**.

**"An Application Control policy has blocked this file"**
(Smart App Control). This one cannot be clicked away. Smart App Control is on
by default on many new Windows 11 computers, and it refuses every unsigned
program. If you see this, use the Python way above instead.

## Check what you downloaded

Open PowerShell in the folder where the file is, and run:

```
certutil -hashfile FreeDownloader.exe SHA256
```

Compare the answer with the list at the bottom of this page. If they match,
the file is exactly the one this release built. If they do not match, delete
it.

## Optional extra programs

The tool works without these, and tells you when one is missing.

| Program | Needed for | Install |
|---|---|---|
| ffmpeg | HD video, and MP3 | `winget install Gyan.FFmpeg` |
| deno | some YouTube links | `winget install DenoLand.Deno` |
| aria2c | faster single downloads | `winget install aria2.aria2` |

Full instructions are in the [README](https://github.com/Mohammad-Hasan-it-96/free-downloader-tool#readme).
