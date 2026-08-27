A download manager for Windows, macOS, and Linux. Paste any link. Videos come
from YouTube and 1000+ other sites through yt-dlp. Any other file downloads
directly, and continues where it stopped if your connection breaks.

It opens as a **window** when you double-click it, and as a **text menu** when
you start it from a terminal.

## Which file do I need?

**Do you have Python?** That decides it.

| Your answer | Download | Why |
|---|---|---|
| **Yes**, Python 3.9 or newer | the `.whl` file | Works on every computer. Updating is one command. |
| **No** / not sure | `FreeDownloader.exe` | Python and yt-dlp are already inside it. |

**With Python:**

```
pip install free_downloader_tool-__VERSION__-py3-none-any.whl
fdl-gui      the window
fdl          the text menu
```

**Without Python:** download `FreeDownloader.exe` and double-click it. Please
read the next part first.

| File | For |
|---|---|
| `FreeDownloader.exe` | Windows, no Python needed |
| `free_downloader_tool-__VERSION__-py3-none-any.whl` | any system with Python |
| `free_downloader_tool-__VERSION__.tar.gz` | the source |
| `SHA256SUMS.txt` | to check what you downloaded |

## Windows may warn you about the .exe

**This is not a virus warning.** Windows is saying it does not recognise the
publisher. Signing a program costs money every year, and this tool is free, so
it is not signed. The checksums below let you prove the file is the one this
page built.

There are two different messages, and they are not the same.

### 1. "Windows protected your PC"  (SmartScreen)

This is the common one. A blue box appears. You can get past it:

1. Click **More info**.
2. Click **Run anyway**.

That is all. You only do this the first time.

### 2. "An Application Control policy has blocked this file"

This one is **Smart App Control**, and there is no button to get past it. It
refuses every unsigned program, whoever made it.

Most people never see this. It is on by default only on a **clean install of
Windows 11**, not on a computer upgraded from Windows 10.

If you see it, **install with Python instead**:

1. Get Python from [python.org](https://www.python.org/downloads/). During
   setup, tick **Add python.exe to PATH**.
2. Then run the `pip install` command above.

The Python way is not a worse version. It is the same program, and it works on
every computer.

## Check what you downloaded

Open PowerShell in the folder where the file is, and run:

```
certutil -hashfile FreeDownloader.exe SHA256
```

Compare the answer with the list at the bottom of this page. If they match,
the file is exactly the one this release built. If they do not match, delete
it and download it again.

## Optional extra programs

The tool works without these, and tells you when one is missing.

| Program | Needed for | Install |
|---|---|---|
| ffmpeg | HD video, and MP3 | `winget install Gyan.FFmpeg` |
| deno | some YouTube links | `winget install DenoLand.Deno` |
| aria2c | faster single downloads | `winget install aria2.aria2` |

The text menu can install them for you: **Tools**, then **3**. Start it with
`fdl`, or with `Free Downloader (terminal).bat`.

Full instructions are in the
[README](https://github.com/Mohammad-Hasan-it-96/free-downloader-tool#readme).
