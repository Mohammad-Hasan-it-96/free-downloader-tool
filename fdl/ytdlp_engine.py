"""Download from YouTube and other media sites, using yt-dlp."""

import os
import re
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

# `run()` below starts yt-dlp with `sys.executable -m yt_dlp`. That is right
# for a normal Python run, but inside the single .exe `sys.executable` is the
# .exe itself, and its bootloader ignores `-m`. Without the two helpers here,
# the .exe would simply open a second copy of its own menu, and no video
# would ever download. The launcher checks `wants_passthrough` first.
PASSTHROUGH = ("-m", "yt_dlp")


def wants_passthrough(argv):
    """The yt-dlp arguments inside `argv`, or None for a normal start.

    `argv` is the list after the program name, so
    `["-m", "yt_dlp", "-F", url]` gives back `["-F", url]`.
    """
    if len(argv) >= len(PASSTHROUGH) and tuple(argv[:2]) == PASSTHROUGH:
        return list(argv[2:])
    return None


def _exit_code(code):
    """yt-dlp exits with a number, with None, or with a message to print."""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def run_passthrough(args):
    """Run yt-dlp in this process. Returns the exit code."""
    try:
        from yt_dlp import main as ytdlp_main
    except ImportError:
        print("yt-dlp is missing from this build.", file=sys.stderr)
        return 1
    try:
        ytdlp_main(args)
    except SystemExit as stop:
        return _exit_code(stop.code)
    return 0


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


# ------------------------------ for the GUI ------------------------------ #
#
# The functions above print and ask questions, which only works in a
# terminal. The GUI needs the same decisions with no questions at all, so it
# gets its own small set here. Both go through the same builders, so a change
# to the yt-dlp flags is made in one place.

def playlist_flags(whole_playlist):
    """The playlist flag, decided by a tick box instead of a question."""
    return ["--yes-playlist"] if whole_playlist else ["--no-playlist"]


def has_playlist(url):
    return "list=" in url


def build_args_quiet(url, out_dir, selector, height, has_ffmpeg, extra=()):
    """Like `build_args`, but it never prints and never asks.

    Returns `(args, note)`. `note` is a short line for the GUI to show when
    the result is not what the user picked, or '' when all is well.
    """
    out_template = os.path.join(str(out_dir), "%(title)s [%(id)s].%(ext)s")
    common = ["-o", out_template, "--no-mtime", "--restrict-filenames",
              "--continue", "--progress", "--newline"] + list(extra)

    if selector == "AUDIO_MP3":
        if has_ffmpeg:
            return common + ["-x", "--audio-format", "mp3",
                             "--audio-quality", "0", url], ""
        return (common + ["-f", "bestaudio", url],
                "ffmpeg is missing, so the audio is saved as it comes, "
                "not as MP3.")

    if has_ffmpeg:
        return common + ["-f", selector, "--merge-output-format", "mp4",
                         url], ""

    return (common + ["-f", single_file_selector(height), url],
            "ffmpeg is missing, so the best single file is used. The "
            "quality may be lower.")


PERCENT = re.compile(r"\[download\]\s+(\d{1,3}(?:\.\d+)?)%")

# A playlist prints one of these before each video:
#     [download] Downloading item 3 of 12
# Older versions of yt-dlp said "video" instead of "item". When the output
# goes to a real terminal the numbers carry colour codes, so those are taken
# off first.
ITEM = re.compile(
    r"\[download\]\s+Downloading\s+(?:item|video)\s+(\d+)\s+of\s+(\d+)",
    re.IGNORECASE)
COLOUR_CODES = re.compile(r"\x1b\[[0-9;]*m")

# yt-dlp says why it stopped in its output. The exit code is always 1, so
# "stopped with code 1" tells the user nothing at all. These read the real
# line, and turn the two most common ones into something a person can act on.

def is_error_line(line):
    return (line or "").lstrip().upper().startswith("ERROR:")


# Words yt-dlp leaves dangling once its links are cut off, as in
# "... cookie database. See" or "... for the authentication. Use".
DANGLING = {"see", "use", "and", "or", "for", "more", "info", "at", "from"}


def clean_error(line):
    """The error text, without the prefix, yt-dlp's own flags, and the links.

    The advice yt-dlp prints is about command line flags, which the person
    looking at a window never types. Ours replaces it, so it goes.
    """
    text = " ".join((line or "").split())
    if text.upper().startswith("ERROR:"):
        text = text[6:].strip()

    # These come before the link cut. Cutting the link first would leave a
    # bare "See" behind with nothing after it to match.
    for tail in ("Use --cookies", "See ", "https://", "http://"):
        spot = text.find(tail)
        if spot > 20:
            text = text[:spot].strip()

    words = text.rstrip(".,: ").split()
    while words and words[-1].strip(".,:").lower() in DANGLING:
        words.pop()
    text = " ".join(words).rstrip(".,: ")
    return text + "." if text else ""


HINTS = (
    (("sign in to confirm", "not a bot", "confirm your age",
      "login required", "private video"),
     "YouTube wants proof that you are a person. In Settings, choose the "
     "browser where you are signed in to YouTube. Then close that browser "
     "completely and try again."),
    (("could not copy", "cookie database", "database is locked",
      "permission denied while opening cookies"),
     "The browser is holding its cookie file. Close that browser completely, "
     "check the system tray for it, and try again."),
    (("unable to extract", "player response", "please report this issue"),
     "This site changed. Update yt-dlp: Tools -> Update yt-dlp in the text "
     "menu, or `pip install -U yt-dlp`."),
    (("requested format is not available",),
     "That quality is not offered for this video. Try 'Best available'."),
    (("ffmpeg", "postprocessing"),
     "This needs ffmpeg. Install it from Tools -> Install the extra "
     "programs."),
)


def explain(error_text):
    """One plain sentence of advice for a yt-dlp error, or ''."""
    lowered = (error_text or "").lower()
    for needles, advice in HINTS:
        if any(needle in lowered for needle in needles):
            return advice
    return ""


def parse_progress(line):
    """The percent in a yt-dlp progress line, or None for any other line."""
    match = PERCENT.search(line or "")
    if not match:
        return None
    return max(0.0, min(100.0, float(match.group(1))))


def parse_item(line):
    """'[download] Downloading item 3 of 12' -> (3, 12), else None."""
    found = ITEM.search(COLOUR_CODES.sub("", line or ""))
    if not found:
        return None
    index, total = int(found.group(1)), int(found.group(2))
    if total < 1 or not 1 <= index <= total:
        return None
    return index, total


def _no_console_flag():
    """Stop a black window flashing up when the GUI starts yt-dlp."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def run_streaming(args, toolbox, cookies_browser="", on_line=None,
                  stop_event=None, popen=None):
    """Run yt-dlp and pass every output line to `on_line`.

    Returns the exit code. `stop_event` cancels the download.
    """
    command = [sys.executable, "-m", "yt_dlp"]
    if toolbox.ffmpeg_dir:
        command += ["--ffmpeg-location", toolbox.ffmpeg_dir]
    if cookies_browser:
        command += ["--cookies-from-browser", cookies_browser]
    command += args

    start = popen or subprocess.Popen
    # yt-dlp writes UTF-8. Without saying so, Python uses the computer's own
    # code page, and any message with a curly quote in it comes out broken.
    process = start(command, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, bufsize=1,
                    encoding="utf-8", errors="replace",
                    env=toolbox.env(), creationflags=_no_console_flag())
    try:
        for line in process.stdout:
            if on_line:
                on_line(line.rstrip())
            if stop_event is not None and stop_event.is_set():
                process.terminate()
                return 1
    finally:
        process.stdout.close()
    return process.wait()


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
