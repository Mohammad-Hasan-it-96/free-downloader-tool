"""The terminal menu that ties everything together."""

import importlib
import os
import subprocess
import sys
import time
from pathlib import Path

from . import (aria2_engine, batch, checksum, clipboard, http_engine, log,
               paths, postaction, router, safety, ytdlp_engine)
from .batch import KIND_FILE, KIND_MEDIA
from .categories import CATEGORY_ORDER, category_for
from .config import BROWSERS, Config
from .history import (STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED, History,
                      short_time)
from .http_engine import MODE_ARIA2, DownloadError
from .multiprogress import MultiProgress
from .progress import ProgressPrinter
from .term import (ask_yes_no, bold, clear_screen, cyan, enable_colors, green,
                   grey, human_size, pause, red, yellow)
from .segmented import wanted_connections
from .tools import Toolbox, ytdlp_installed

APP_DIR = paths.data_dir()
CONFIG_PATH = paths.config_path()
HISTORY_PATH = paths.history_path()
LOG_PATH = paths.log_path()
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


def _speed_plan(cfg, toolbox, info):
    """A short sentence about how this file will be downloaded."""
    limit = ""
    if cfg.speed_limit_kb:
        limit = f", limited to {cfg.speed_limit_kb} KB/s"
    if aria2_engine.is_useful_for(info, toolbox, cfg.use_aria2c):
        return (f"aria2c, {aria2_engine.DEFAULT_CONNECTIONS} "
                f"connections{limit}")
    if info.size and info.resumable:
        count = wanted_connections(info.size, cfg.connections)
        if count > 1:
            return f"{count} connections at once{limit}"
    return f"1 connection{limit}"


# --------------------------- clipboard watch ---------------------------- #

WATCH_SECONDS = 1.0


def watch_clipboard(cfg, toolbox, history):
    """Offer to download every new link you copy, until you stop."""
    # Read once: it both tests the clipboard and gives us the starting text.
    seen = clipboard.read()
    if seen is None:
        print(red("\nThe clipboard cannot be read on this computer."))
        print(grey("On Linux, install xclip, xsel, or wl-clipboard."))
        return

    print(bold("\nWatching the clipboard."))
    print(grey("Copy a link and it will be offered here. "
               "Press Ctrl+C to stop."))
    log.info("clipboard watch started")

    try:
        while True:
            text = clipboard.read()
            if text != seen:
                seen = text
                if clipboard.looks_like_a_link(text):
                    link = text.strip()
                    print(bold(f"\nNew link: {cyan(link)}"))
                    answer = input(bold("Download it? [Y/n/q]: ")).strip().lower()
                    if answer.startswith("q"):
                        break
                    if not answer or answer.startswith("y"):
                        download_any(cfg, toolbox, history, link)
                        print(bold("\nStill watching. Ctrl+C to stop."))
            time.sleep(WATCH_SECONDS)
    except KeyboardInterrupt:
        pass
    print(yellow("\nStopped watching the clipboard."))
    log.info("clipboard watch stopped")


# ------------------------- one smart download --------------------------- #

KIND_NAMES = {
    router.KIND_MEDIA: "a video / audio page (yt-dlp)",
    router.KIND_FILE: "a direct file link",
}


def download_any(cfg, toolbox, history, url):
    """One option for any link. The tool picks the engine, you can change it."""
    print(yellow("\nChecking the link..."))
    route = router.decide(url)

    print()
    print(f"  This looks like : {cyan(KIND_NAMES[route.kind])}")
    print(f"  Because         : {grey(route.reason)}")
    if route.error:
        print(f"  Note            : {yellow(route.error)}")

    other = KIND_NAMES[route.other_kind]
    print(grey(f"\n  Press Enter to continue, or type 'o' to use {other}."))
    answer = input(bold("  Choice [Enter]: ")).strip().lower()
    kind = route.other_kind if answer == "o" else route.kind
    info = route.info if kind == route.kind else None

    if route.error and kind == route.kind and kind == router.KIND_FILE:
        # The check already failed. Asking the same server again would only
        # print the same error twice.
        print(red(f"\n{route.error}"))
        history.add(url, STATUS_FAILED, error=route.error)
        worked = False
    else:
        worked = _run_kind(cfg, toolbox, history, url, kind, info)
    if worked:
        return

    # The first engine did not manage. The other one may still do it.
    fallback = (router.KIND_FILE if kind == router.KIND_MEDIA
                else router.KIND_MEDIA)
    print()
    if not ask_yes_no(f"That did not work. Try it as {KIND_NAMES[fallback]}?",
                      default_no=False):
        return
    _run_kind(cfg, toolbox, history, url, fallback, None)


def _run_kind(cfg, toolbox, history, url, kind, info):
    if kind == router.KIND_MEDIA:
        return bool(download_media(cfg, toolbox, history, url))
    return bool(download_file(cfg, toolbox, history, url, info=info))


# --------------------------- one direct link ---------------------------- #

def download_file(cfg, toolbox, history, url, info=None, ask_first=True):
    """Download a direct link, sorted into the folder for its type.

    Returns the saved path, or None when it did not work.
    """
    if info is None:
        print(yellow("\nAsking the server about this file..."))
        try:
            info = http_engine.probe(url, cfg.headers)
        except DownloadError as err:
            print(red(f"\n{err}"))
            history.add(url, STATUS_FAILED, error=str(err))
            return None

    category = category_for(info.filename, info.content_type)
    dest_dir = cfg.folder_for(category)

    print()
    print(f"  Name     : {bold(info.filename)}")
    print(f"  Size     : {human_size(info.size)}")
    print(f"  Type     : {cyan(category)}")
    print(f"  Save to  : {green(str(dest_dir))}")
    print(f"  Resume   : "
          f"{green('supported') if info.resumable else yellow('not supported')}")
    print(f"  Speed    : {cyan(_speed_plan(cfg, toolbox, info))}")

    part_path = dest_dir / (info.filename + ".part")
    already = 0
    if part_path.exists():
        meta = http_engine.read_meta(part_path)
        if http_engine.meta_matches(meta, url, info):
            already = http_engine.part_progress(part_path, meta)
            print(f"  Found    : "
                  f"{yellow(human_size(already) + ' already downloaded')}")

    earlier = history.already_have(url)
    if earlier:
        print(yellow(f"  Note     : you downloaded this before, to "
                     f"{earlier['path']}"))

    if not _passes_safety_checks(cfg, url, info, category, dest_dir, already):
        return None

    if ask_first and not ask_yes_no("\nStart the download?", default_no=False):
        print(red("Cancelled."))
        return None

    expected_sum = ask_checksum()
    saved = _run_file_download(cfg, toolbox, history, url, dest_dir, info)
    if saved and expected_sum:
        check_saved_file(saved, expected_sum)
    return saved


def _passes_safety_checks(cfg, url, info, category, dest_dir, already=0):
    """Warn about space, plain http, and login pages. False = stop."""
    needed = (info.size or 0) - already
    enough, message = safety.check_space(dest_dir, needed)
    if not enough:
        print(red(f"\n{message}"))
        log.warning("not enough space for %s", log.redact(url))
        if not ask_yes_no("Try anyway?", default_no=True):
            return False

    if safety.looks_like_a_login_page(info):
        print(yellow(f"\n{safety.login_page_message(info)}"))
        print(yellow("Saving it would give you a web page with the wrong "
                     "name."))
        log.warning("server sent a page, not a file: %s", log.redact(url))
        if not ask_yes_no("Download it anyway?", default_no=True):
            return False

    if safety.is_insecure_program(url, category):
        print(red("\nThis is a program, and the link is plain http, not "
                  "https."))
        print(yellow("Nothing protects the file on the way, so somebody "
                     "between you and the server could change it. Only "
                     "continue if you trust this network and this site."))
        log.warning("program over plain http: %s", log.redact(url))
        if not ask_yes_no("Download it anyway?", default_no=True):
            return False
    return True


def ask_checksum():
    """Ask for a checksum to compare after the download. May be empty."""
    print(grey("\nIf the site published a checksum, paste it to have the "
               "file checked."))
    return input(bold("Checksum (blank to skip): ")).strip()


def check_saved_file(path, pasted_text):
    """Work out the checksum of the saved file and compare it."""
    print(yellow(f"\nChecking the file ({human_size(path.stat().st_size)})..."))
    result = checksum.verify(path, pasted_text)

    if result.error:
        print(red(f"Could not check it: {result.error}"))
        return False
    if result.ok:
        print(green(f"[OK] The {result.algorithm} checksum matches. "
                    "The file is exactly what the site published."))
        log.info("checksum ok (%s) for %s", result.algorithm, path.name)
        return True

    print(red(f"[WARNING] The {result.algorithm} checksum does NOT match."))
    print(f"  expected: {grey(result.expected)}")
    print(f"  actual  : {red(result.actual)}")
    print(yellow("The file is damaged, or it is not the file the site "
                 "published. Do not run or open it."))
    log.error("checksum MISMATCH (%s) for %s", result.algorithm, path.name)
    if ask_yes_no("Delete this file?", default_no=False):
        try:
            path.unlink()
            print(green("Deleted."))
        except OSError as err:
            print(red(f"Could not delete it: {err}"))
    return False


def _run_file_download(cfg, toolbox, history, url, dest_dir, info,
                       name=None, force_python=False):
    file_name = name or info.filename
    part_path = Path(dest_dir) / (file_name + ".part")
    already = part_path.stat().st_size if part_path.exists() else 0
    bar = ProgressPrinter(total=info.size, already_done=already)

    def on_progress(done, total):
        if total and bar.total != total:
            bar.total = total
        bar.update(done)

    def on_retry(attempt, total_attempts, reason, wait):
        log.warning("retry %s/%s for %s (%s)", attempt, total_attempts,
                    log.redact(url), reason)
        bar.fail(yellow(f"  Connection problem ({reason}). "
                        f"Retry {attempt}/{total_attempts} in {wait}s..."))

    category = category_for(file_name, info.content_type)
    use_aria2 = (not force_python
                 and aria2_engine.is_useful_for(info, toolbox, cfg.use_aria2c))
    print()
    try:
        if use_aria2:
            print(grey("Using aria2c for a faster download."))
            print()
            saved = aria2_engine.download(
                url, dest_dir, info, toolbox=toolbox, name=name,
                connections=aria2_engine.DEFAULT_CONNECTIONS,
                speed_limit_kb=cfg.speed_limit_kb, retries=cfg.retries,
                extra_headers=cfg.headers)
        else:
            saved = http_engine.download(url, dest_dir, info, name=name,
                                         extra_headers=cfg.headers,
                                         retries=cfg.retries,
                                         connections=cfg.connections,
                                         speed_limit=cfg.speed_limit_bytes,
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

    if not use_aria2:
        bar.finish()
    print(green(f"[DONE] Saved to {saved}"))
    log.info("done: %s -> %s", log.redact(url), saved)
    history.add(url, STATUS_DONE, path=saved, size=info.size,
                category=category)
    postaction.run(cfg.after_download, saved)
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
        for note in item.warnings:
            print(f"      {yellow('warning: ' + note)}")
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

    enough, message = batch.check_space_for(items, cfg)
    if not enough:
        print(red(f"\n{message}"))
        log.warning("not enough space for the queue")
        if not ask_yes_no("Try anyway?", default_no=True):
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

def resume_unfinished(cfg, toolbox, history):
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
    """Download with yt-dlp. Returns True when it worked."""
    if not ytdlp_installed():
        print(red("\nyt-dlp is not installed, so media pages cannot be "
                  "downloaded."))
        print(yellow("Install it from the Tools menu."))
        return False

    selector, height = ytdlp_engine.choose_quality()
    category = "Audio" if ytdlp_engine.is_audio_choice(selector) else "Videos"
    dest_dir = cfg.folder_for(category)

    ok, reason = ensure_folder(dest_dir)
    if not ok:
        print(red(f"\nCannot use the save folder: {dest_dir}"))
        print(red(f"Reason: {reason}"))
        print(yellow("Change it in Settings."))
        return False

    if selector == "MANUAL":
        ytdlp_engine.list_formats(url, toolbox, cfg.cookies_browser)

    extra = ytdlp_engine.playlist_args(url)
    args = ytdlp_engine.build_args(url, dest_dir, selector, height,
                                   toolbox.has_ffmpeg, extra)
    if args is None:
        return False

    print(green(f"\nDownloading to: {dest_dir}\n"))
    result = ytdlp_engine.run(args, toolbox, cfg.cookies_browser)
    if result.returncode == 0:
        print(green(f"\n[DONE] Saved to {dest_dir}"))
        history.add(url, STATUS_DONE, path=dest_dir, category=category,
                    engine="yt-dlp")
        return True

    print(red("\n[FAILED] yt-dlp reported an error."))
    history.add(url, STATUS_FAILED, category=category, engine="yt-dlp",
                error=f"yt-dlp exit code {result.returncode}")
    if not cfg.cookies_browser:
        print(yellow("If YouTube says 'Sign in to confirm you're not a "
                     "bot', set a cookies browser in Settings."))
    return False


# ------------------------------- history -------------------------------- #

def show_history(history):
    entries = history.recent(20)
    if not entries:
        print(yellow("\nThe history is empty."))
        return

    counts = history.counts()
    print(bold(f"\nLast {len(entries)} of {len(history.entries)} entries"))
    print(grey(f"done {counts[STATUS_DONE]}  |  "
               f"failed {counts[STATUS_FAILED]}  |  "
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
        print(f"      {grey('  |  '.join(details))}")
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


def change_connections(cfg):
    print()
    print(f"Connections per file: {cyan(str(cfg.connections))}")
    print(grey("A big file is split into parts that download at the same "
               "time. More is often faster, but some servers refuse. "
               "1 turns splitting off. 1 to 32."))
    value = input(bold("New number (blank to keep): ")).strip()
    if not value:
        return
    if not value.isdigit() or not 1 <= int(value) <= 32:
        print(red("Please type a number from 1 to 32."))
        return
    cfg.connections = int(value)
    _save(cfg, f"Saved. Files will use up to {cfg.connections} connections.")


def change_speed_limit(cfg):
    current = (f"{cfg.speed_limit_kb} KB/s" if cfg.speed_limit_kb
               else "no limit")
    print()
    print(f"Speed limit: {cyan(current)}")
    print(grey("Keeps downloads from using all your internet. "
               "Type 0 for no limit. The number is in KB per second, "
               "for example 500."))
    value = input(bold("New limit in KB/s (blank to keep): ")).strip()
    if not value:
        return
    if not value.isdigit():
        print(red("Please type a whole number, or 0 for no limit."))
        return
    cfg.speed_limit_kb = int(value)
    if cfg.speed_limit_kb:
        _save(cfg, f"Saved. Downloads are limited to "
                   f"{cfg.speed_limit_kb} KB/s.")
    else:
        _save(cfg, "Saved. There is no speed limit.")


def toggle_aria2c(cfg, toolbox):
    cfg.use_aria2c = not cfg.use_aria2c
    if cfg.use_aria2c and not aria2_engine.executable(toolbox):
        _save(cfg, "aria2c will be used when it is installed. It is not "
                   "installed now, so the built-in downloader is used. "
                   "Install it with:  winget install aria2.aria2")
        return
    if cfg.use_aria2c:
        _save(cfg, "aria2c is ON for single large downloads.")
    else:
        _save(cfg, "aria2c is OFF. The built-in downloader is always used.")


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


def change_proxy(cfg):
    current = cfg.proxy or "the computer's own settings"
    print()
    print(f"Proxy: {cyan(current)}")
    print(grey("Leave blank to follow the computer's own proxy settings.\n"
               "Type 'none' to never use a proxy.\n"
               "Or type an address, for example  http://10.0.0.1:3128"))
    value = input(bold("Proxy ('-' to clear, blank to keep): ")).strip()
    if not value:
        return
    cfg.proxy = "" if value == "-" else value
    applied = http_engine.configure_proxy(cfg.proxy)
    _save(cfg, f"Saved. Downloads will use: {applied}")
    log.info("proxy changed to %s", applied)


def edit_headers(cfg):
    """Add or remove headers that are sent with every direct download."""
    while True:
        print()
        headers = cfg.headers
        if headers:
            print(bold("Extra headers sent with every direct download:"))
            for index, (name, value) in enumerate(sorted(headers.items()), 1):
                shown = value if len(value) <= 50 else value[:47] + "..."
                print(f"  {cyan(str(index))}. {name}: {grey(shown)}")
        else:
            print(yellow("There are no extra headers."))
            print(grey("A header can unlock a link that needs one, for "
                       "example  Referer: https://the-site.com/"))

        print(f"\n  {cyan('a')}. Add or change one")
        print(f"  {cyan('d')}. Delete one")
        print(f"  {cyan('0')}. Back")
        choice = input(bold("\nSelect: ")).strip().lower()

        if choice == "a":
            name = input(bold("Header name (e.g. Referer): ")).strip()
            if not name:
                print(red("No name given."))
                continue
            value = input(bold(f"Value for {name}: ")).strip()
            cfg.set_header(name, value)
            _save(cfg, f"Saved. {name} will be sent with every download.")
        elif choice == "d":
            if not headers:
                continue
            pick = input(bold("Number to delete: ")).strip()
            names = sorted(headers)
            if pick.isdigit() and 1 <= int(pick) <= len(names):
                gone = names[int(pick) - 1]
                cfg.remove_header(gone)
                _save(cfg, f"Removed {gone}.")
            else:
                print(red("Invalid choice."))
        elif choice == "0" or not choice:
            return
        else:
            print(red("Invalid choice."))


def edit_category_folders(cfg):
    """Send one type of file to a folder of its own, even on another drive."""
    while True:
        print()
        print(bold("Folder for each type:"))
        for index, category in enumerate(CATEGORY_ORDER, 1):
            value = cfg.data["category_folders"].get(category, category)
            full = cfg.folder_for(category)
            mark = green("full path") if Path(value).is_absolute() else ""
            print(f"  {cyan(str(index))}. {category:<10} {grey(str(full))} "
                  f"{mark}")
        print(f"\n  {cyan('0')}. Back")
        pick = input(bold("\nNumber to change: ")).strip()

        if pick == "0" or not pick:
            return
        if not pick.isdigit() or not 1 <= int(pick) <= len(CATEGORY_ORDER):
            print(red("Invalid choice."))
            continue

        category = CATEGORY_ORDER[int(pick) - 1]
        print(grey(f"\nA plain name such as '{category}' goes inside the base "
                   "folder.\nA full path such as 'E:/Programs' is used "
                   "exactly as written.\nType '-' to go back to the default."))
        value = input(bold(f"Folder for {category}: ")).strip().strip('"')
        if not value:
            continue
        cfg.set_category_folder(category, "" if value == "-" else value)
        _save(cfg, f"{category} now goes to {cfg.folder_for(category)}")


def change_after_download(cfg):
    print()
    print(f"After a download finishes: {cyan(postaction.CHOICES[cfg.after_download])}")
    keys = list(postaction.CHOICES)
    for index, key in enumerate(keys, 1):
        print(f"  {cyan(str(index))}. {postaction.CHOICES[key]}")
    pick = input(bold("Select (blank to keep): ")).strip()
    if not pick:
        return
    if not pick.isdigit() or not 1 <= int(pick) <= len(keys):
        print(red("Invalid choice."))
        return
    cfg.after_download = keys[int(pick) - 1]
    _save(cfg, f"Saved. After a download it will "
               f"{postaction.CHOICES[cfg.after_download]}.")


def _save(cfg, message):
    saved, why = cfg.save()
    if saved:
        print(green(f"\n{message}"))
    else:
        print(red(f"Could not save settings: {why}"))


SETTINGS_MENU = [
    ("1", "Base folder"),
    ("2", "Sorting by file type (on / off)"),
    ("3", "Folder for each type"),
    ("4", "Downloads at the same time (the queue)"),
    ("5", "Connections per file (speed)"),
    ("6", "Speed limit"),
    ("7", "Use aria2c when installed (on / off)"),
    ("8", "Browser for cookies"),
    ("9", "Proxy"),
    ("10", "Extra headers"),
    ("11", "After a download finishes"),
    ("0", "Back"),
]


def settings_screen(cfg, toolbox):
    while True:
        clear_screen()
        print(bold(cyan("SETTINGS")))
        print()
        print(f"  Base folder            : {green(cfg.base_dir)}")
        print(f"  Sort by type           : "
              f"{green('on') if cfg.sort_by_type else yellow('off')}")
        print(f"  Downloads at once      : {cyan(str(cfg.max_parallel))}")
        print(f"  Connections per file   : {cyan(str(cfg.connections))}")
        limit = (f"{cfg.speed_limit_kb} KB/s" if cfg.speed_limit_kb
                 else "no limit")
        print(f"  Speed limit            : {cyan(limit)}")
        aria2 = "off"
        if cfg.use_aria2c:
            aria2 = ("on" if aria2_engine.executable(toolbox)
                     else "on (not installed)")
        print(f"  Use aria2c             : {cyan(aria2)}")
        print(f"  Retries per download   : {cyan(str(cfg.retries))}")
        print(f"  Cookies from           : "
              f"{green(cfg.cookies_browser) if cfg.cookies_browser else yellow('off')}")
        print(f"  Proxy                  : "
              f"{cyan(cfg.proxy) if cfg.proxy else grey('system settings')}")
        header_count = len(cfg.headers)
        print(f"  Extra headers          : "
              f"{cyan(str(header_count)) if header_count else grey('none')}")
        print(f"  After a download       : "
              f"{cyan(postaction.CHOICES[cfg.after_download])}")
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
            edit_category_folders(cfg)
        elif choice == "4":
            change_parallel(cfg)
            pause()
        elif choice == "5":
            change_connections(cfg)
            pause()
        elif choice == "6":
            change_speed_limit(cfg)
            pause()
        elif choice == "7":
            toggle_aria2c(cfg, toolbox)
            pause()
        elif choice == "8":
            change_cookies(cfg)
            pause()
        elif choice == "9":
            change_proxy(cfg)
            pause()
        elif choice == "10":
            edit_headers(cfg)
        elif choice == "11":
            change_after_download(cfg)
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
    ("4", "Check a file against a checksum"),
    ("5", "Show the last lines of the log"),
    ("0", "Back"),
]


def check_a_file():
    """Compare any file on the disk against a checksum you paste."""
    raw = input(bold("\nPath of the file: ")).strip().strip('"')
    if not raw:
        return
    path = Path(raw).expanduser()
    if not path.is_file():
        print(red(f"There is no file at {path}"))
        return
    pasted = input(bold("Checksum: ")).strip()
    if not pasted:
        print(red("No checksum given."))
        return
    check_saved_file(path, pasted)


def show_log():
    lines = log.tail(LOG_PATH, 30)
    if not lines:
        print(yellow(f"\nThe log is empty, or it cannot be read."))
        print(grey(f"It would be at: {LOG_PATH}"))
        return
    print(bold(f"\nLast {len(lines)} lines of {LOG_PATH}\n"))
    for line in lines:
        colour = grey
        if " ERROR " in line:
            colour = red
        elif " WARNING " in line:
            colour = yellow
        print("  " + colour(line))


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
        elif choice == "4":
            check_a_file()
            pause()
        elif choice == "5":
            show_log()
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
    speed = (f"    Limit: {cyan(str(cfg.speed_limit_kb) + ' KB/s')}"
             if cfg.speed_limit_kb else "")
    print(f"Cookies from : {green(cookies) if cookies else yellow('off')}"
          f"{speed}")
    print()


MENU = [
    ("1", "Download (paste any link)"),
    ("2", "Download many links (queue)"),
    ("3", "Watch the clipboard for links"),
    ("4", "Resume unfinished downloads"),
    ("5", "History"),
    ("6", "Settings"),
    ("7", "Tools"),
    ("0", "Exit"),
]


def main():
    enable_colors()
    cfg = Config.load(CONFIG_PATH)
    log.setup(LOG_PATH)
    log.info("app started, base folder %s", cfg.base_dir)
    log.info("proxy: %s", http_engine.configure_proxy(cfg.proxy))
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
                download_any(cfg, toolbox, history, url)
            pause()
        elif choice == "2":
            download_queue(cfg, toolbox, history)
            pause()
        elif choice == "3":
            watch_clipboard(cfg, toolbox, history)
            pause()
        elif choice == "4":
            resume_unfinished(cfg, toolbox, history)
            pause()
        elif choice == "5":
            show_history(history)
            pause()
        elif choice == "6":
            settings_screen(cfg, toolbox)
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
