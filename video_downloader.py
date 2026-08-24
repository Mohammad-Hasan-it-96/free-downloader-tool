#!/usr/bin/env python3
"""
Simple terminal video downloader (powered by yt-dlp).
Downloads from YouTube and 1000+ other sites, lets you pick the
resolution/quality, and saves to a folder you choose (default: D:\\Videos).
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_DOWNLOAD_DIR = r"D:\Videos"
BROWSERS = ["edge", "chrome", "brave", "firefox", "opera", "vivaldi", "chromium"]


# ----------------------------- helpers ------------------------------------ #

def color(text, code):
    return f"\033[{code}m{text}\033[0m"


def cyan(t):   return color(t, "96")
def green(t):  return color(t, "92")
def yellow(t): return color(t, "93")
def red(t):    return color(t, "91")
def bold(t):   return color(t, "1")


def ask_yes_no(question, default_no=True):
    suffix = "[y/N]" if default_no else "[Y/n]"
    answer = input(bold(f"{question} {suffix}: ")).strip().lower()
    if not answer:
        return not default_no
    return answer.startswith("y")


def load_config():
    """Read config.json, ignoring any value that has the wrong shape."""
    cfg = {"download_dir": DEFAULT_DOWNLOAD_DIR, "cookies_browser": ""}
    if not CONFIG_PATH.exists():
        return cfg
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        print(yellow(f"Warning: {CONFIG_PATH.name} is not valid JSON. "
                     "Using default settings."))
        return cfg
    if not isinstance(data, dict):
        return cfg

    folder = data.get("download_dir")
    if isinstance(folder, str) and folder.strip():
        cfg["download_dir"] = folder.strip()

    browser = data.get("cookies_browser")
    if isinstance(browser, str) and browser.strip().lower() in BROWSERS:
        cfg["cookies_browser"] = browser.strip().lower()
    return cfg


def save_config(cfg):
    """Write config.json. Returns True on success."""
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return True
    except OSError as err:
        print(red(f"Could not save settings to {CONFIG_PATH}: {err}"))
        return False


def ytdlp_installed():
    return importlib.util.find_spec("yt_dlp") is not None


def _search(globs, extra_dirs, exe_name):
    exe = shutil.which(exe_name)
    if exe:
        return str(Path(exe).parent)
    candidates = []
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        pkgs = Path(localappdata) / "Microsoft" / "WinGet" / "Packages"
        for g in globs:
            candidates += list(pkgs.glob(g))
    candidates += [Path(d) for d in extra_dirs if d]
    for c in candidates:
        if (c / exe_name).exists():
            return str(c)
    return None


def find_ffmpeg():
    return _search(["Gyan.FFmpeg*/**/bin"],
                   [r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin"],
                   "ffmpeg.exe")


def find_deno():
    home = os.environ.get("USERPROFILE", "")
    extra = [os.path.join(home, ".deno", "bin")] if home else []
    return _search(["DenoLand.Deno*/**"], extra, "deno.exe")


def build_env(deno_dir):
    """Return an environment where deno is on PATH so yt-dlp can find it."""
    env = os.environ.copy()
    if deno_dir:
        env["PATH"] = deno_dir + os.pathsep + env.get("PATH", "")
    return env


def run_ytdlp(args, ffmpeg_dir=None, deno_dir=None, cookies_browser=""):
    """Run yt-dlp as a module so it works even if not on PATH."""
    cmd = [sys.executable, "-m", "yt_dlp"]
    if ffmpeg_dir:
        cmd += ["--ffmpeg-location", ffmpeg_dir]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    cmd += args
    return subprocess.run(cmd, env=build_env(deno_dir))


def clear():
    os.system("cls" if os.name == "nt" else "clear")


# ----------------------------- actions ------------------------------------ #

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


def single_file_selector(height):
    """Format that needs no merging, for when ffmpeg is missing."""
    if height:
        return (f"best[height<={height}][ext=mp4]/"
                f"best[height<={height}]/best")
    return "best[ext=mp4]/best"


def choose_quality():
    print(bold("\nChoose quality:"))
    for key, (label, _, _) in QUALITY_PRESETS.items():
        print(f"  {cyan(key)}. {label}")
    while True:
        pick = input(bold("Enter number [1]: ")).strip() or "1"
        if pick in QUALITY_PRESETS:
            _, selector, height = QUALITY_PRESETS[pick]
            return selector, height
        print(red("Invalid choice, try again."))


def playlist_args(url):
    """Ask first, so a playlist link does not download 200 videos."""
    if "list=" not in url:
        return ["--no-playlist"]
    print(yellow("\nThis link belongs to a playlist."))
    if ask_yes_no("Download the WHOLE playlist?", default_no=True):
        return ["--yes-playlist"]
    return ["--no-playlist"]


def list_formats(url, ctx):
    print(yellow("\nFetching available formats...\n"))
    run_ytdlp(["-F", url], **ctx)


def download(url, cfg, ctx):
    out_dir = cfg["download_dir"]
    try:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
    except OSError as err:
        print(red(f"\nCannot use the save folder: {out_dir}"))
        print(red(f"Reason: {err}"))
        print(yellow("Use menu option 2 to pick a folder that works."))
        return
    out_tmpl = os.path.join(out_dir, "%(title)s [%(id)s].%(ext)s")

    selector, height = choose_quality()
    has_ffmpeg = bool(ctx.get("ffmpeg_dir"))

    common = ["-o", out_tmpl, "--no-mtime", "--restrict-filenames",
              "--progress"] + playlist_args(url)

    if selector == "AUDIO_MP3":
        if has_ffmpeg:
            args = common + ["-x", "--audio-format", "mp3",
                             "--audio-quality", "0", url]
        else:
            print(red("\nffmpeg is NOT installed, so MP3 conversion is "
                      "not possible."))
            print(yellow("Install it with:  winget install Gyan.FFmpeg"))
            if not ask_yes_no("Download the raw audio file instead "
                              "(m4a/webm)?", default_no=False):
                print(red("Aborted."))
                return
            args = common + ["-f", "bestaudio", url]
    elif selector == "MANUAL":
        list_formats(url, ctx)
        if not has_ffmpeg:
            print(red("ffmpeg is NOT installed. Codes like '137+140' "
                      "cannot be merged."))
            print(yellow("Pick one single code that already has "
                         "video + audio."))
        fid = input(bold("\nEnter format code(s) "
                         "(e.g. 137+140): ")).strip()
        if not fid:
            print(red("No format entered, aborting."))
            return
        args = common + ["-f", fid]
        if has_ffmpeg:
            args += ["--merge-output-format", "mp4"]
        args += [url]
    else:
        if has_ffmpeg:
            args = common + ["-f", selector,
                             "--merge-output-format", "mp4", url]
        else:
            print(yellow("\nffmpeg is NOT installed, so video and audio "
                         "cannot be merged."))
            print(yellow("Using the best single file instead. Quality may "
                         "be lower."))
            print(yellow("For full quality:  winget install Gyan.FFmpeg"))
            args = common + ["-f", single_file_selector(height), url]

    print(green(f"\nDownloading to: {out_dir}\n"))
    result = run_ytdlp(args, **ctx)
    if result.returncode == 0:
        print(green("\n[DONE] Saved to " + out_dir))
    else:
        print(red("\n[FAILED] yt-dlp reported an error."))
        if not ctx.get("cookies_browser"):
            print(yellow("If YouTube says 'Sign in to confirm you're not a "
                         "bot', use menu option 3 to enable browser cookies."))


def change_download_dir(cfg):
    print(f"\nCurrent download folder: {cyan(cfg['download_dir'])}")
    new = input(bold("New folder path (blank to keep): ")).strip().strip('"')
    if not new:
        return
    folder = Path(new).expanduser()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        print(red(f"That folder cannot be created: {err}"))
        print(yellow("Nothing was changed. Check the drive letter and "
                     "the spelling."))
        return
    if not os.access(folder, os.W_OK):
        print(red(f"No permission to write in: {folder}"))
        print(yellow("Nothing was changed."))
        return
    cfg["download_dir"] = str(folder)
    if save_config(cfg):
        print(green(f"Saved. Downloads will go to: {folder}"))


def change_cookies(cfg):
    print(bold("\nUse cookies from a browser to bypass YouTube's "
               "'not a bot' check."))
    print("Pick the browser where you are logged into YouTube:")
    print(f"  {cyan('0')}. None (disable)")
    for i, b in enumerate(BROWSERS, 1):
        print(f"  {cyan(str(i))}. {b}")
    pick = input(bold("Select [0]: ")).strip() or "0"
    if pick == "0":
        cfg["cookies_browser"] = ""
    elif pick.isdigit() and 1 <= int(pick) <= len(BROWSERS):
        cfg["cookies_browser"] = BROWSERS[int(pick) - 1]
    else:
        print(red("Invalid choice."))
        return
    if save_config(cfg):
        val = cfg["cookies_browser"] or "None"
        print(green(f"Saved. Cookies source: {val}"))


def install_ytdlp():
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
    importlib.invalidate_caches()


def ensure_ytdlp():
    """Check yt-dlp before the menu, so the error is clear. True = ready."""
    if ytdlp_installed():
        return True
    clear()
    print(red("yt-dlp is NOT installed for this Python:"))
    print(f"  {cyan(sys.executable)}")
    print()
    if ask_yes_no("Install it now with pip?", default_no=False):
        install_ytdlp()
    if ytdlp_installed():
        return True
    print(red("\nyt-dlp is still missing. Run this command yourself:"))
    print(bold(f'  "{sys.executable}" -m pip install -U yt-dlp'))
    input(yellow("\nPress Enter to exit..."))
    return False


# ----------------------------- main menu ---------------------------------- #

def main():
    if os.name == "nt":
        os.system("")  # enable ANSI colors in Windows terminal

    cfg = load_config()
    if not ensure_ytdlp():
        return
    ffmpeg_dir = find_ffmpeg()
    deno_dir = find_deno()

    while True:
        ctx = {"ffmpeg_dir": ffmpeg_dir, "deno_dir": deno_dir,
               "cookies_browser": cfg.get("cookies_browser", "")}
        clear()
        print(bold(cyan("=" * 52)))
        print(bold(cyan("          VIDEO DOWNLOADER  (yt-dlp)")))
        print(bold(cyan("=" * 52)))
        print(f"Save folder  : {green(cfg['download_dir'])}")
        print(f"ffmpeg       : "
              f"{green(ffmpeg_dir) if ffmpeg_dir else red('NOT FOUND')}")
        print(f"deno (JS)    : "
              f"{green('ready') if deno_dir else yellow('not found')}")
        cb = cfg.get("cookies_browser", "")
        print(f"Cookies from : {green(cb) if cb else yellow('off')}")
        print()
        print(f"  {cyan('1')}. Download a video / audio")
        print(f"  {cyan('2')}. Change download folder")
        print(f"  {cyan('3')}. Set browser for cookies (fix 'not a bot')")
        print(f"  {cyan('4')}. Show available formats for a URL")
        print(f"  {cyan('5')}. Update yt-dlp")
        print(f"  {cyan('0')}. Exit")
        choice = input(bold("\nSelect: ")).strip()

        if choice == "1":
            url = input(bold("\nPaste the video URL: ")).strip().strip('"')
            if url:
                download(url, cfg, ctx)
            input(yellow("\nPress Enter to continue..."))
        elif choice == "2":
            change_download_dir(cfg)
            input(yellow("\nPress Enter to continue..."))
        elif choice == "3":
            change_cookies(cfg)
            input(yellow("\nPress Enter to continue..."))
        elif choice == "4":
            url = input(bold("\nPaste the video URL: ")).strip().strip('"')
            if url:
                list_formats(url, ctx)
            input(yellow("\nPress Enter to continue..."))
        elif choice == "5":
            install_ytdlp()
            input(yellow("\nPress Enter to continue..."))
        elif choice == "0":
            print("Bye!")
            break
        else:
            print(red("Invalid choice."))
            input(yellow("Press Enter to continue..."))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
