"""The terminal menu that ties everything together."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

from . import http_engine, ytdlp_engine
from .categories import CATEGORY_ORDER, category_for
from .config import BROWSERS, Config
from .http_engine import DownloadError
from .progress import ProgressPrinter
from .term import (ask_yes_no, bold, clear_screen, cyan, enable_colors, green,
                   grey, human_size, pause, red, yellow)
from .tools import Toolbox, ytdlp_installed

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
TITLE = "FREE DOWNLOADER TOOL"


# ----------------------------- setup checks ----------------------------- #

def install_ytdlp():
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
    importlib.invalidate_caches()


def ensure_ytdlp():
    """Check yt-dlp before the menu, so the error is clear. True = ready."""
    if ytdlp_installed():
        return True
    clear_screen()
    print(red("yt-dlp is NOT installed for this Python:"))
    print(f"  {cyan(sys.executable)}")
    print(grey("\nyt-dlp is needed for video sites. Direct file links would "
               "still work without it."))
    print()
    if ask_yes_no("Install it now with pip?", default_no=False):
        install_ytdlp()
    if ytdlp_installed():
        return True
    print(red("\nyt-dlp is still missing. Run this command yourself:"))
    print(bold(f'  "{sys.executable}" -m pip install -U yt-dlp'))
    return ask_yes_no("\nContinue anyway (direct file links only)?",
                      default_no=False)


def ensure_folder(path):
    """Create a folder and check we can write in it. Returns (ok, reason)."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
    except OSError as err:
        return False, str(err)
    if not os.access(path, os.W_OK):
        return False, "no permission to write here"
    return True, ""


# --------------------------- direct file links -------------------------- #

def download_file(cfg, url):
    """Download a direct link, sorted into the folder for its type."""
    print(yellow("\nAsking the server about this file..."))
    try:
        info = http_engine.probe(url)
    except DownloadError as err:
        print(red(f"\n{err}"))
        return

    category = category_for(info.filename, info.content_type)
    dest_dir = cfg.folder_for(category)

    print()
    print(f"  Name     : {bold(info.filename)}")
    print(f"  Size     : {human_size(info.size)}")
    print(f"  Type     : {cyan(category)}")
    print(f"  Save to  : {green(str(dest_dir))}")
    print(f"  Resume   : "
          f"{green('supported') if info.resumable else yellow('not supported')}")

    part_path = dest_dir / (info.filename + ".part")
    if part_path.exists():
        have = part_path.stat().st_size
        print(f"  Found    : {yellow(human_size(have) + ' already downloaded')}")

    if not ask_yes_no("\nStart the download?", default_no=False):
        print(red("Cancelled."))
        return

    _run_file_download(cfg, url, dest_dir, info)


def _run_file_download(cfg, url, dest_dir, info, name=None):
    part_path = Path(dest_dir) / ((name or info.filename) + ".part")
    already = part_path.stat().st_size if part_path.exists() else 0
    bar = ProgressPrinter(total=info.size, already_done=already)

    def on_progress(done, total):
        if total and bar.total != total:
            bar.total = total
        bar.update(done)

    def on_retry(attempt, total_attempts, reason, wait):
        bar.fail(yellow(f"  Connection problem ({reason}). "
                        f"Retry {attempt}/{total_attempts} in {wait}s..."))

    print()
    try:
        saved = http_engine.download(url, dest_dir, info, name=name,
                                     retries=cfg.retries,
                                     on_progress=on_progress,
                                     on_retry=on_retry)
    except DownloadError as err:
        bar.fail(red(f"\n[FAILED] {err}"))
        return None
    except KeyboardInterrupt:
        bar.fail(yellow("\n[PAUSED] Stopped by you. The part that is already "
                        "downloaded was kept."))
        print(yellow("Use 'Resume unfinished downloads' to continue it."))
        return None

    bar.finish()
    print(green(f"[DONE] Saved to {saved}"))
    return saved


def resume_unfinished(cfg):
    """List every unfinished download and offer to continue it."""
    items = http_engine.unfinished_downloads(cfg.base_dir)
    if not items:
        print(green("\nThere are no unfinished downloads."))
        return

    print(bold(f"\nUnfinished downloads ({len(items)}):"))
    for index, item in enumerate(items, 1):
        name = item["part"].name[:-len(".part")]
        done = human_size(item["done"])
        total = human_size(item["size"])
        print(f"  {cyan(str(index))}. {name}")
        print(f"      {grey(done + ' of ' + total)}")

    print(f"  {cyan('a')}. Resume all")
    print(f"  {cyan('0')}. Back")
    pick = input(bold("\nSelect: ")).strip().lower()

    if pick == "0" or not pick:
        return
    if pick == "a":
        chosen = items
    elif pick.isdigit() and 1 <= int(pick) <= len(items):
        chosen = [items[int(pick) - 1]]
    else:
        print(red("Invalid choice."))
        return

    for item in chosen:
        name = item["part"].name[:-len(".part")]
        print(bold(f"\nResuming: {name}"))
        try:
            info = http_engine.probe(item["url"])
        except DownloadError as err:
            print(red(f"  Cannot resume: {err}"))
            continue
        _run_file_download(cfg, item["url"], item["part"].parent, info,
                           name=name)


# ------------------------------ media sites ----------------------------- #

def download_media(cfg, toolbox, url):
    selector, height = ytdlp_engine.choose_quality()
    category = "Audio" if ytdlp_engine.is_audio_choice(selector) else "Videos"
    dest_dir = cfg.folder_for(category)

    ok, reason = ensure_folder(dest_dir)
    if not ok:
        print(red(f"\nCannot use the save folder: {dest_dir}"))
        print(red(f"Reason: {reason}"))
        print(yellow("Change it with the 'Change base folder' option."))
        return

    if selector == "MANUAL":
        ytdlp_engine.list_formats(url, toolbox, cfg.cookies_browser)

    extra = ytdlp_engine.playlist_args(url)
    args = ytdlp_engine.build_args(url, dest_dir, selector, height,
                                   toolbox.has_ffmpeg, extra)
    if args is None:
        return

    print(green(f"\nDownloading to: {dest_dir}\n"))
    result = ytdlp_engine.run(args, toolbox, cfg.cookies_browser)
    if result.returncode == 0:
        print(green(f"\n[DONE] Saved to {dest_dir}"))
    else:
        print(red("\n[FAILED] yt-dlp reported an error."))
        if not cfg.cookies_browser:
            print(yellow("If YouTube says 'Sign in to confirm you're not a "
                         "bot', use the cookies option in the menu."))


# ------------------------------- settings ------------------------------- #

def change_base_dir(cfg):
    print(f"\nCurrent base folder: {cyan(cfg.base_dir)}")
    if cfg.sort_by_type:
        print(grey("Files are sorted into subfolders by type, for example "
                   f"{Path(cfg.base_dir) / 'Videos'}"))
    new = input(bold("New folder path (blank to keep): ")).strip().strip('"')
    if not new:
        return
    folder = Path(new).expanduser()
    ok, reason = ensure_folder(folder)
    if not ok:
        print(red(f"That folder cannot be used: {reason}"))
        print(yellow("Nothing was changed. Check the drive letter and the "
                     "spelling."))
        return
    cfg.base_dir = str(folder)
    saved, why = cfg.save()
    if saved:
        print(green(f"Saved. Downloads will go to: {folder}"))
    else:
        print(red(f"Could not save settings: {why}"))


def toggle_sorting(cfg):
    cfg.sort_by_type = not cfg.sort_by_type
    saved, why = cfg.save()
    if not saved:
        print(red(f"Could not save settings: {why}"))
        return
    if cfg.sort_by_type:
        print(green("\nSorting is ON. Files go into folders by type:"))
        print("  " + grey(", ".join(CATEGORY_ORDER)))
    else:
        print(yellow(f"\nSorting is OFF. Everything goes into {cfg.base_dir}"))


def change_cookies(cfg):
    print(bold("\nUse cookies from a browser to bypass YouTube's "
               "'not a bot' check."))
    print(grey("Cookies identify your logged-in account to the site. "
               "Leave this off unless you need it."))
    print("Pick the browser where you are logged into YouTube:")
    print(f"  {cyan('0')}. None (disable)")
    for index, browser in enumerate(BROWSERS, 1):
        print(f"  {cyan(str(index))}. {browser}")
    pick = input(bold("Select [0]: ")).strip() or "0"

    if pick == "0":
        cfg.cookies_browser = ""
    elif pick.isdigit() and 1 <= int(pick) <= len(BROWSERS):
        cfg.cookies_browser = BROWSERS[int(pick) - 1]
    else:
        print(red("Invalid choice."))
        return
    saved, why = cfg.save()
    if saved:
        print(green(f"Saved. Cookies source: {cfg.cookies_browser or 'None'}"))
    else:
        print(red(f"Could not save settings: {why}"))


# -------------------------------- screen -------------------------------- #

def draw_header(cfg, toolbox):
    line = "=" * 56
    print(bold(cyan(line)))
    print(bold(cyan(f"          {TITLE}")))
    print(bold(cyan(line)))
    print(f"Base folder  : {green(cfg.base_dir)}")
    sorting = green("on") if cfg.sort_by_type else yellow("off")
    print(f"Sort by type : {sorting}")
    print(f"ffmpeg       : "
          f"{green('ready') if toolbox.ffmpeg_dir else red('NOT FOUND')}")
    print(f"deno (JS)    : "
          f"{green('ready') if toolbox.deno_dir else yellow('not found')}")
    print(f"aria2c       : "
          f"{green('ready') if toolbox.aria2c_dir else grey('not installed')}")
    cookies = cfg.cookies_browser
    print(f"Cookies from : {green(cookies) if cookies else yellow('off')}")
    print()


MENU = [
    ("1", "Download video / audio from a site (yt-dlp)"),
    ("2", "Download a file from a direct link"),
    ("3", "Resume unfinished downloads"),
    ("4", "Change base folder"),
    ("5", "Turn sorting by file type on / off"),
    ("6", "Set browser for cookies (fix 'not a bot')"),
    ("7", "Show available formats for a URL"),
    ("8", "Update yt-dlp"),
    ("0", "Exit"),
]


def ask_url(prompt="\nPaste the URL: "):
    return input(bold(prompt)).strip().strip('"')


def main():
    enable_colors()
    cfg = Config.load(CONFIG_PATH)
    if not ensure_ytdlp():
        return

    notice = cfg.take_notice()
    if notice:
        clear_screen()
        print(yellow(bold("\nNote about your settings\n")))
        print(notice)
        pause()

    toolbox = Toolbox()

    while True:
        clear_screen()
        draw_header(cfg, toolbox)
        for key, label in MENU:
            print(f"  {cyan(key)}. {label}")
        choice = input(bold("\nSelect: ")).strip()

        if choice == "1":
            url = ask_url()
            if url:
                download_media(cfg, toolbox, url)
            pause()
        elif choice == "2":
            url = ask_url()
            if url:
                download_file(cfg, url)
            pause()
        elif choice == "3":
            resume_unfinished(cfg)
            pause()
        elif choice == "4":
            change_base_dir(cfg)
            pause()
        elif choice == "5":
            toggle_sorting(cfg)
            pause()
        elif choice == "6":
            change_cookies(cfg)
            pause()
        elif choice == "7":
            url = ask_url()
            if url:
                ytdlp_engine.list_formats(url, toolbox, cfg.cookies_browser)
            pause()
        elif choice == "8":
            install_ytdlp()
            toolbox.refresh()
            pause()
        elif choice == "0":
            print("Bye!")
            break
        else:
            print(red("Invalid choice."))
            pause()


def run():
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
