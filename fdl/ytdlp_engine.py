"""Download from YouTube and other media sites, using yt-dlp."""

import os
import subprocess
import sys

from .term import bold, green, red, yellow, ask_yes_no

# key: (label, format selector, max height used by the no-ffmpeg fallback)
QUALITY_PRESETS = {
    "1": ("Best available (auto-merge video+audio)",
          "bestvideo+bestaudio/best", None),
    "2": ("1080p", "bestvideo[height<=1080]+bestaudio/best[height<=1080]", 1080),
    "3": ("720p",  "bestvideo[height<=720]+bestaudio/best[height<=720]", 720),
    "4": ("480p",  "bestvideo[height<=480]+bestaudio/best[height<=480]", 480),
    "5": ("360p",  "bestvideo[height<=360]+bestaudio/best[height<=360]", 360),
    "6": ("Audio only (MP3)", "AUDIO_MP3", None),
    "7": ("Let me pick from the exact list of formats", "MANUAL", None),
}

AUDIO_CHOICES = {"AUDIO_MP3"}


def single_file_selector(height):
    """A format that needs no merging, for when ffmpeg is missing."""
    if height:
        return f"best[height<={height}][ext=mp4]/best[height<={height}]/best"
    return "best[ext=mp4]/best"


def run(args, toolbox, cookies_browser=""):
    """Run yt-dlp as a module, so it works even when not on PATH."""
    command = [sys.executable, "-m", "yt_dlp"]
    if toolbox.ffmpeg_dir:
        command += ["--ffmpeg-location", toolbox.ffmpeg_dir]
    if cookies_browser:
        command += ["--cookies-from-browser", cookies_browser]
    command += args
    return subprocess.run(command, env=toolbox.env())


def list_formats(url, toolbox, cookies_browser=""):
    print(yellow("\nFetching available formats...\n"))
    return run(["-F", url], toolbox, cookies_browser)


def choose_quality():
    print(bold("\nChoose quality:"))
    for key, (label, _, _) in QUALITY_PRESETS.items():
        print(f"  {key}. {label}")
    while True:
        pick = input(bold("Enter number [1]: ")).strip() or "1"
        if pick in QUALITY_PRESETS:
            _, selector, height = QUALITY_PRESETS[pick]
            return selector, height
        print(red("Invalid choice, try again."))


def playlist_args(url):
    """Ask first, so one link does not pull a whole playlist by mistake."""
    if "list=" not in url:
        return ["--no-playlist"]
    print(yellow("\nThis link belongs to a playlist."))
    if ask_yes_no("Download the WHOLE playlist?", default_no=True):
        return ["--yes-playlist"]
    return ["--no-playlist"]


def is_audio_choice(selector):
    return selector in AUDIO_CHOICES


def build_args(url, out_dir, selector, height, has_ffmpeg, extra=()):
    """Build the yt-dlp command line. Returns None when the user cancels."""
    out_template = os.path.join(str(out_dir), "%(title)s [%(id)s].%(ext)s")
    common = ["-o", out_template, "--no-mtime", "--restrict-filenames",
              "--continue", "--progress"] + list(extra)

    if selector == "AUDIO_MP3":
        if has_ffmpeg:
            return common + ["-x", "--audio-format", "mp3",
                             "--audio-quality", "0", url]
        print(red("\nffmpeg is NOT installed, so MP3 conversion is not "
                  "possible."))
        print(yellow("Install it with:  winget install Gyan.FFmpeg"))
        if not ask_yes_no("Download the raw audio file instead (m4a/webm)?",
                          default_no=False):
            return None
        return common + ["-f", "bestaudio", url]

    if selector == "MANUAL":
        code = input(bold("\nEnter format code(s) (e.g. 137+140): ")).strip()
        if not code:
            print(red("No format entered, aborting."))
            return None
        args = common + ["-f", code]
        if has_ffmpeg:
            args += ["--merge-output-format", "mp4"]
        return args + [url]

    if has_ffmpeg:
        return common + ["-f", selector, "--merge-output-format", "mp4", url]

    print(yellow("\nffmpeg is NOT installed, so video and audio cannot be "
                 "merged."))
    print(yellow("Using the best single file instead. Quality may be lower."))
    print(yellow("For full quality:  winget install Gyan.FFmpeg"))
    return common + ["-f", single_file_selector(height), url]


def looks_like_media_site(url):
    """True when yt-dlp has a real extractor for this URL.

    yt-dlp always matches its 'generic' extractor as a last resort, so a
    generic match means 'this is probably a plain file link'.
    """
    try:
        from yt_dlp.extractor import gen_extractor_classes
    except ImportError:
        return False
    try:
        for extractor in gen_extractor_classes():
            name = extractor.IE_NAME
            if name.lower() == "generic":
                continue
            if extractor.suitable(url):
                return True
    except Exception:
        return False
    return False
