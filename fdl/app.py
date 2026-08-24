"""The terminal menu that ties everything together."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

from . import batch, http_engine, ytdlp_engine
from .batch import KIND_FILE, KIND_MEDIA
from .categories import CATEGORY_ORDER, category_for
from .config import BROWSERS, Config
from .history import (STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED, History,
                      short_time)
from .http_engine import DownloadError
from .multiprogress import MultiProgress
from .progress import ProgressPrinter
from .term import (ask_yes_no, bold, clear_screen, cyan, enable_colors, green,
                   grey, human_size, pause, red, yellow)
from .tools import Toolbox, ytdlp_installed

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
HISTORY_PATH = APP_DIR / "history.json"
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


def ask_url(prompt="\nPaste the URL: "):
    return input(bold(prompt)).strip().strip('"')


# --------------------------- one direct link ---------------------------- #

def download_file(cfg, history, url):
    """Download a direct link, sorted into the folder for its type."""
    print(yellow("\nAsking the server about this file..."))
    try:
        info = http_engine.probe(url)
    except DownloadError as err:
        print(red(f"\n{err}"))
        history.add(url, STATUS_FAILED, error=str(err))
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

    earlier = history.already_have(url)
    if earlier:
        print(yellow(f"  Note     : you downloaded this before, to "
                     f"{earlier['path']}"))

    if not ask_yes_no("\nStart the download?", default_no=False):
        print(red("Cancelled."))
        return

    _run_file_download(cfg, history, url, dest_dir, info)


def _run_file_download(cfg, history, url, dest_dir, info, name=None):
    file_name = name or info.filename
    part_path = Path(dest_dir) / (file_name + ".part")
    already = part_path.stat().st_size if part_path.exists() else 0
    bar = ProgressPrinter(total=info.size, already_done=already)

    def on_progress(done, total):
        if total and bar.total != total:
            bar.total = total
        bar.update(done)

    def on_retry(attempt, total_attempts, reason, wait):
        bar.fail(yellow(f"  Connection problem ({reason}). "
                        f"Retry {attempt}/{total_attempts} in {wait}s..."))

    category = category_for(file_name, info.content_type)
    print()
    try:
        saved = http_engine.download(url, dest_dir, info, name=name,
                                     retries=cfg.retries,
                                     on_progress=on_progress,
                                     on_retry=on_retry)
    except DownloadError as err:
        bar.fail(red(f"\n[FAILED] {err}"))
        history.add(url, STATUS_FAILED, category=category, error=str(err))
        return None
    except KeyboardInterrupt:
        bar.fail(yellow("\n[PAUSED] Stopped by you. The part that is already "
                        "downloaded was kept."))
        print(yellow("Use 'Resume unfinished downloads' to continue it."))
        return None

    bar.finish()
    print(green(f"[DONE] Saved to {saved}"))
    history.add(url, STATUS_DONE, path=saved, size=info.size,
                category=category)
    return saved


# ------------------------------ the queue ------------------------------- #

def collect_urls():
    """Read links from the user: pasted lines, or a path to a text file."""
    print(bold("\nPaste links, one per line."))
    print(grey("Or type the path of a .txt file that holds the links."))
    print(grey("Finish with an empty line."))
    lines = []
    while True:
        try:
            line = input("  ").strip().strip('"')
        except EOFError:
            break
        if not line:
            break
        lines.append(line)

    urls = []
    for line in lines:
        if line.lower().endswith(".txt") and Path(line).exists():
            try:
                found = batch.read_url_list(line)
            except OSError as err:
                print(red(f"Cannot read {line}: {err}"))
                continue
            print(green(f"Read {len(found)} links from {line}"))
            urls += found
        else:
            urls.append(line)
    return urls


def show_plan(items):
    """Print what will happen, before anything is downloaded."""
    print(bold("\nPlan:"))
    total_size = 0
    for index, item in enumerate(items, 1):
        if item.status == STATUS_FAILED:
            print(f"  {index}. {red('cannot use')}  {item.url}")
            print(f"      {grey(item.error)}")
            continue
        if item.status == STATUS_SKIPPED:
            print(f"  {index}. {yellow('skip')}  {item.name}")
            print(f"      {grey(item.note)}")
            continue
        if item.kind == KIND_MEDIA:
            print(f"  {index}. {cyan('media site')}  {item.url}")
            continue

        if item.size:
            total_size += item.size
        resume = ""
        if item.resume_from:
            resume = yellow(f"  (resume from {human_size(item.resume_from)})")
        print(f"  {index}. {item.name}{resume}")
        print(f"      {grey(f'{human_size(item.size)} -> {item.dest}')}")
    if total_size:
        print(bold(f"\n  Total to download: about {human_size(total_size)}"))


def download_queue(cfg, toolbox, history):
    urls = collect_urls()
    if not urls:
        print(yellow("No links given."))
        return

    print(yellow(f"\nChecking {len(urls)} link(s)..."))
    items = batch.prepare(urls, cfg, history, workers=cfg.max_parallel)
    show_plan(items)

    # Links that failed the check never reach the downloader, so record
    # them here instead.
    for item in items:
        if item.status == STATUS_FAILED:
            history.add(item.url, STATUS_FAILED, error=item.error)

    ready = [i for i in items
             if i.status == batch.STATUS_PENDING and i.kind == KIND_FILE]
    media = [i for i in items
             if i.status == batch.STATUS_PENDING and i.kind == KIND_MEDIA]
    if not ready and not media:
        print(yellow("\nThere is nothing to download."))
        return

    print(grey(f"\n{len(ready)} file(s) will download "
               f"{cfg.max_parallel} at a time."))
    if media:
        print(grey(f"{len(media)} media link(s) will run one after another."))
    if not ask_yes_no("\nStart?", default_no=False):
        print(red("Cancelled."))
        return

    if ready:
        print()
        progress = MultiProgress([item.label for item in items])
        progress.start()
        for index, item in enumerate(items):
            if item.status == STATUS_SKIPPED:
                progress.finish(index, STATUS_SKIPPED, item.note)
            elif item.status == STATUS_FAILED:
                progress.finish(index, STATUS_FAILED, item.error)
        try:
            batch.run_files(items, cfg, progress, cfg.max_parallel, history)
        except KeyboardInterrupt:
            print(yellow("\nStopping... finished parts were kept."))
        finally:
            progress.stop()

    for item in media:
        print(bold(f"\n--- {item.url}"))
        download_media(cfg, toolbox, history, item.url)

    _print_queue_summary(items)


def _print_queue_summary(items):
    done = [i for i in items if i.status == STATUS_DONE]
    failed = [i for i in items if i.status == STATUS_FAILED]
    skipped = [i for i in items if i.status == STATUS_SKIPPED]

    print(bold("\nResult:"))
    print(f"  {green('done')}    : {len(done)}")
    print(f"  {yellow('skipped')} : {len(skipped)}")
    print(f"  {red('failed')}  : {len(failed)}")
    for item in failed:
        print(f"    {red('x')} {item.label}")
        print(f"      {grey(item.error or 'unknown error')}")
    if failed:
        print(grey("\nFailed downloads keep their part file. Use "
                   "'Resume unfinished downloads' to try again."))


# ------------------------- unfinished downloads ------------------------- #

def resume_unfinished(cfg, history):
    items = http_engine.unfinished_downloads(cfg.base_dir)
    if not items:
        print(green("\nThere are no unfinished downloads."))
        return

    print(bold(f"\nUnfinished downloads ({len(items)}):"))
    for index, item in enumerate(items, 1):
        name = item["part"].name[: -len(".part")]
        print(f"  {cyan(str(index))}. {name}")
        print(f"      {grey(human_size(item['done']) + ' of ' + human_size(item['size']))}")

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
        name = item["part"].name[: -len(".part")]
        print(bold(f"\nResuming: {name}"))
        try:
            info = http_engine.probe(item["url"])
        except DownloadError as err:
            print(red(f"  Cannot resume: {err}"))
            continue
        _run_file_download(cfg, history, item["url"], item["part"].parent,
                           info, name=name)


# ------------------------------ media sites ----------------------------- #

def download_media(cfg, toolbox, history, url):
    selector, height = ytdlp_engine.choose_quality()
    category = "Audio" if ytdlp_engine.is_audio_choice(selector) else "Videos"
    dest_dir = cfg.folder_for(category)

    ok, reason = ensure_folder(dest_dir)
    if not ok:
        print(red(f"\nCannot use the save folder: {dest_dir}"))
        print(red(f"Reason: {reason}"))
        print(yellow("Change it in Settings."))
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
        history.add(url, STATUS_DONE, path=dest_dir, category=category,
                    engine="yt-dlp")
    else:
        print(red("\n[FAILED] yt-dlp reported an error."))
        history.add(url, STATUS_FAILED, category=category, engine="yt-dlp",
                    error=f"yt-dlp exit code {result.returncode}")
        if not cfg.cookies_browser:
            print(yellow("If YouTube says 'Sign in to confirm you're not a "
                         "bot', set a cookies browser in Settings."))


# ------------------------------- history -------------------------------- #

def show_history(history):
    entries = history.recent(20)
    if not entries:
        print(yellow("\nThe history is empty."))
        return

    counts = history.counts()
    print(bold(f"\nLast {len(entries)} of {len(history.entries)} entries"))
    print(grey(f"done {counts[STATUS_DONE]}  ·  "
               f"failed {counts[STATUS_FAILED]}  ·  "
               f"skipped {counts[STATUS_SKIPPED]}"))
    print()

    marks = {STATUS_DONE: green("+"), STATUS_FAILED: red("x"),
             STATUS_SKIPPED: yellow("-")}
    for entry in entries:
        mark = marks.get(entry.get("status"), " ")
        name = entry.get("path") or entry.get("url")
        print(f"  {mark} {Path(str(name)).name}")
        details = [short_time(entry.get("when"))]
        if entry.get("size"):
            details.append(human_size(entry["size"]))
        if entry.get("category"):
            details.append(entry["category"])
        print(f"      {grey('  ·  '.join(details))}")
        if entry.get("error"):
            print(f"      {red(entry['error'])}")

    print(f"\n  {cyan('c')}. Clear the history")
    print(f"  {cyan('0')}. Back")
    if input(bold("\nSelect: ")).strip().lower() == "c":
        if ask_yes_no("Delete all history entries?", default_no=True):
            history.clear()
            print(green("History cleared."))


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
    _save(cfg, f"Saved. Downloads will go to: {folder}")


def toggle_sorting(cfg):
    cfg.sort_by_type = not cfg.sort_by_type
    if cfg.sort_by_type:
        message = ("Sorting is ON. Files go into folders by type:\n  "
                   + ", ".join(CATEGORY_ORDER))
    else:
        message = f"Sorting is OFF. Everything goes into {cfg.base_dir}"
    _save(cfg, message)


def change_parallel(cfg):
    print(f"\nDownloads at the same time: {cyan(str(cfg.max_parallel))}")
    print(grey("This is used by the queue. A higher number is not always "
               "faster, and can slow down your internet. 1 to 8."))
    value = input(bold("New number (blank to keep): ")).strip()
    if not value:
        return
    if not value.isdigit() or not 1 <= int(value) <= 8:
        print(red("Please type a number from 1 to 8."))
        return
    cfg.max_parallel = int(value)
    _save(cfg, f"Saved. The queue will run {cfg.max_parallel} at a time.")


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
    _save(cfg, f"Saved. Cookies source: {cfg.cookies_browser or 'None'}")


def _save(cfg, message):
    saved, why = cfg.save()
    if saved:
        print(green(f"\n{message}"))
    else:
        print(red(f"Could not save settings: {why}"))


SETTINGS_MENU = [
    ("1", "Base folder"),
    ("2", "Sorting by file type (on / off)"),
    ("3", "Downloads at the same time"),
    ("4", "Browser for cookies"),
    ("0", "Back"),
]


def settings_screen(cfg):
    while True:
        clear_screen()
        print(bold(cyan("SETTINGS")))
        print()
        print(f"  Base folder            : {green(cfg.base_dir)}")
        print(f"  Sort by type           : "
              f"{green('on') if cfg.sort_by_type else yellow('off')}")
        print(f"  Downloads at once      : {cyan(str(cfg.max_parallel))}")
        print(f"  Retries per download   : {cyan(str(cfg.retries))}")
        print(f"  Cookies from           : "
              f"{green(cfg.cookies_browser) if cfg.cookies_browser else yellow('off')}")
        print()
        for key, label in SETTINGS_MENU:
            print(f"  {cyan(key)}. {label}")
        choice = input(bold("\nSelect: ")).strip()

        if choice == "1":
            change_base_dir(cfg)
            pause()
        elif choice == "2":
            toggle_sorting(cfg)
            pause()
        elif choice == "3":
            change_parallel(cfg)
            pause()
        elif choice == "4":
            change_cookies(cfg)
            pause()
        elif choice == "0":
            return
        else:
            print(red("Invalid choice."))
            pause()


# -------------------------------- tools --------------------------------- #

TOOLS_MENU = [
    ("1", "Show available formats for a URL"),
    ("2", "Update yt-dlp"),
    ("3", "Look for ffmpeg / deno / aria2c again"),
    ("0", "Back"),
]


def tools_screen(cfg, toolbox):
    while True:
        clear_screen()
        print(bold(cyan("TOOLS")))
        print()
        for key, label in TOOLS_MENU:
            print(f"  {cyan(key)}. {label}")
        choice = input(bold("\nSelect: ")).strip()

        if choice == "1":
            url = ask_url()
            if url:
                ytdlp_engine.list_formats(url, toolbox, cfg.cookies_browser)
            pause()
        elif choice == "2":
            install_ytdlp()
            pause()
        elif choice == "3":
            toolbox.refresh()
            print(green("\nSearched again."))
            pause()
        elif choice == "0":
            return
        else:
            print(red("Invalid choice."))
            pause()


# -------------------------------- screen -------------------------------- #

def draw_header(cfg, toolbox):
    line = "=" * 56
    print(bold(cyan(line)))
    print(bold(cyan(f"          {TITLE}")))
    print(bold(cyan(line)))
    print(f"Base folder  : {green(cfg.base_dir)}")
    sorting = green("on") if cfg.sort_by_type else yellow("off")
    print(f"Sort by type : {sorting}    "
          f"At once: {cyan(str(cfg.max_parallel))}")
    print(f"ffmpeg       : "
          f"{green('ready') if toolbox.ffmpeg_dir else red('NOT FOUND')}"
          f"    deno: "
          f"{green('ready') if toolbox.deno_dir else yellow('not found')}"
          f"    aria2c: "
          f"{green('ready') if toolbox.aria2c_dir else grey('none')}")
    cookies = cfg.cookies_browser
    print(f"Cookies from : {green(cookies) if cookies else yellow('off')}")
    print()


MENU = [
    ("1", "Download from a site (video / audio)"),
    ("2", "Download a direct link"),
    ("3", "Download many links (queue)"),
    ("4", "Resume unfinished downloads"),
    ("5", "History"),
    ("6", "Settings"),
    ("7", "Tools"),
    ("0", "Exit"),
]


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
    history = History.load(HISTORY_PATH, cfg.history_limit)

    while True:
        clear_screen()
        draw_header(cfg, toolbox)
        for key, label in MENU:
            print(f"  {cyan(key)}. {label}")
        choice = input(bold("\nSelect: ")).strip()

        if choice == "1":
            url = ask_url()
            if url:
                download_media(cfg, toolbox, history, url)
            pause()
        elif choice == "2":
            url = ask_url()
            if url:
                download_file(cfg, history, url)
            pause()
        elif choice == "3":
            download_queue(cfg, toolbox, history)
            pause()
        elif choice == "4":
            resume_unfinished(cfg, history)
            pause()
        elif choice == "5":
            show_history(history)
            pause()
        elif choice == "6":
            settings_screen(cfg)
        elif choice == "7":
            tools_screen(cfg, toolbox)
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
