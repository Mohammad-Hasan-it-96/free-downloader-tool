import json
from pathlib import Path

from fdl.config import Config, defaults, migrate


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_missing_file_uses_defaults(tmp_path):
    cfg = Config.load(tmp_path / "nothing.json")
    assert cfg.data == defaults()


def test_broken_json_uses_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    assert Config.load(path).data == defaults()


def test_json_array_uses_defaults(tmp_path):
    path = write(tmp_path / "config.json", [1, 2, 3])
    assert Config.load(path).data == defaults()


def test_wrong_types_are_ignored(tmp_path):
    path = write(tmp_path / "config.json", {
        "version": 2,
        "base_dir": 123,
        "sort_by_type": "yes",
        "cookies_browser": "netscape",
        "retries": "many",
    })
    cfg = Config.load(path)
    assert cfg.base_dir == defaults()["base_dir"]
    assert cfg.sort_by_type is True
    assert cfg.cookies_browser == ""
    assert cfg.retries == defaults()["retries"]


def test_good_values_are_kept(tmp_path):
    path = write(tmp_path / "config.json", {
        "version": 2,
        "base_dir": "  E:/Stuff  ",
        "sort_by_type": False,
        "cookies_browser": "CHROME",
        "retries": 3,
    })
    cfg = Config.load(path)
    assert cfg.base_dir == "E:/Stuff"
    assert cfg.sort_by_type is False
    assert cfg.cookies_browser == "chrome"
    assert cfg.retries == 3


def test_retries_are_clamped(tmp_path):
    path = write(tmp_path / "config.json", {"version": 2, "retries": 999})
    assert Config.load(path).retries == 20


def test_save_and_reload(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config.load(path)
    cfg.base_dir = str(tmp_path / "downloads")
    cfg.sort_by_type = False
    ok, why = cfg.save()
    assert ok, why

    again = Config.load(path)
    assert again.base_dir == str(tmp_path / "downloads")
    assert again.sort_by_type is False


def test_folder_for_uses_subfolders(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "dl")
    assert cfg.folder_for("Videos") == Path(tmp_path / "dl" / "Videos")


def test_folder_for_flat_when_sorting_is_off(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.base_dir = str(tmp_path / "dl")
    cfg.sort_by_type = False
    assert cfg.folder_for("Videos") == Path(tmp_path / "dl")


def test_migration_from_version_1_video_folder():
    upgraded = migrate({"download_dir": r"D:\Videos",
                        "cookies_browser": "edge"})
    # D:\Videos looks like a category folder, so D:\ becomes the base.
    assert upgraded["base_dir"] == "D:\\"
    assert upgraded["cookies_browser"] == "edge"
    assert "D:\\Videos" in upgraded["notice"]


def test_migration_from_version_1_other_folder():
    upgraded = migrate({"download_dir": r"E:\MyStuff"})
    assert upgraded["base_dir"] == r"E:\MyStuff"
    assert upgraded["notice"]


def test_migration_keeps_defaults_when_empty():
    upgraded = migrate({})
    assert upgraded["base_dir"] == defaults()["base_dir"]
    assert upgraded["notice"] == ""


def test_load_migrates_old_file(tmp_path):
    path = write(tmp_path / "config.json",
                 {"download_dir": r"E:\Old", "cookies_browser": "firefox"})
    cfg = Config.load(path)
    assert cfg.data["version"] == 2
    assert cfg.base_dir == r"E:\Old"
    assert cfg.cookies_browser == "firefox"
    assert cfg.take_notice()          # shown once
    assert cfg.take_notice() == ""    # and then cleared
