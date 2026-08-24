import json
import threading

from fdl.history import (STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED, History,
                         short_time)


def test_missing_file_gives_empty_history(tmp_path):
    history = History.load(tmp_path / "none.json")
    assert history.entries == []


def test_broken_file_gives_empty_history(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{not json", encoding="utf-8")
    assert History.load(path).entries == []


def test_non_list_file_gives_empty_history(tmp_path):
    path = tmp_path / "history.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    assert History.load(path).entries == []


def test_add_and_reload(tmp_path):
    path = tmp_path / "history.json"
    history = History(path)
    history.add("http://x/a.zip", STATUS_DONE, path=tmp_path / "a.zip",
                size=10, category="Archives")

    again = History.load(path)
    assert len(again.entries) == 1
    assert again.entries[0]["url"] == "http://x/a.zip"
    assert again.entries[0]["category"] == "Archives"
    assert again.entries[0]["when"]


def test_newest_entry_is_first(tmp_path):
    history = History(tmp_path / "history.json")
    history.add("http://x/1", STATUS_DONE)
    history.add("http://x/2", STATUS_DONE)
    assert history.entries[0]["url"] == "http://x/2"


def test_limit_drops_old_entries(tmp_path):
    history = History(tmp_path / "history.json", limit=3)
    for index in range(6):
        history.add(f"http://x/{index}", STATUS_DONE)
    assert len(history.entries) == 3
    assert history.entries[0]["url"] == "http://x/5"

    on_disk = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
    assert len(on_disk) == 3


def test_already_have_needs_the_file_to_exist(tmp_path):
    real = tmp_path / "kept.zip"
    real.write_text("data")
    history = History(tmp_path / "history.json")

    history.add("http://x/kept.zip", STATUS_DONE, path=real, size=4)
    assert history.already_have("http://x/kept.zip")

    history.add("http://x/gone.zip", STATUS_DONE, path=tmp_path / "gone.zip")
    assert history.already_have("http://x/gone.zip") is None


def test_already_have_ignores_failed_entries(tmp_path):
    real = tmp_path / "f.zip"
    real.write_text("x")
    history = History(tmp_path / "history.json")
    history.add("http://x/f.zip", STATUS_FAILED, path=real)
    assert history.already_have("http://x/f.zip") is None


def test_counts(tmp_path):
    history = History(tmp_path / "history.json")
    history.add("http://x/1", STATUS_DONE)
    history.add("http://x/2", STATUS_FAILED)
    history.add("http://x/3", STATUS_SKIPPED)
    history.add("http://x/4", STATUS_DONE)
    counts = history.counts()
    assert counts[STATUS_DONE] == 2
    assert counts[STATUS_FAILED] == 1
    assert counts[STATUS_SKIPPED] == 1


def test_clear(tmp_path):
    path = tmp_path / "history.json"
    history = History(path)
    history.add("http://x/1", STATUS_DONE)
    history.clear()
    assert history.entries == []
    assert History.load(path).entries == []


def test_writing_from_many_threads_keeps_every_entry(tmp_path):
    path = tmp_path / "history.json"
    history = History(path, limit=100)

    def worker(index):
        history.add(f"http://x/{index}", STATUS_DONE, size=index)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(history.entries) == 30
    assert len(History.load(path).entries) == 30


def test_short_time_handles_bad_input():
    assert short_time(None) == "?"
    assert short_time("not a time").startswith("not a time"[:10])
    assert short_time("2026-08-24T14:05:00+03:00") == "2026-08-24 14:05"
