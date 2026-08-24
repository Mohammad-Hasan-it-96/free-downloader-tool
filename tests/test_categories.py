import pytest

from fdl.categories import category_for, extension_of, split_extension


@pytest.mark.parametrize("name,expected", [
    ("movie.mp4", "Videos"),
    ("clip.MKV", "Videos"),
    ("song.mp3", "Audio"),
    ("track.flac", "Audio"),
    ("setup.exe", "Programs"),
    ("app.apk", "Programs"),
    ("tool.AppImage", "Programs"),
    ("archive.zip", "Archives"),
    ("backup.tar.gz", "Archives"),
    ("disk.iso", "Archives"),
    ("book.pdf", "Documents"),
    ("sheet.xlsx", "Documents"),
    ("photo.jpg", "Images"),
    ("icon.svg", "Images"),
    ("script.py", "Code"),
    ("package.whl", "Code"),
])
def test_known_extensions(name, expected):
    assert category_for(name) == expected


def test_unknown_extension_is_other():
    assert category_for("data.qqq") == "Other"


def test_no_extension_is_other():
    assert category_for("README") == "Other"


def test_mime_type_is_used_only_as_fallback():
    # The extension wins, even when the server says something else.
    assert category_for("song.mp3", "application/octet-stream") == "Audio"
    # With no useful extension, the MIME type decides.
    assert category_for("download", "video/mp4") == "Videos"
    assert category_for("download", "application/pdf") == "Documents"


def test_generic_mime_type_does_not_guess():
    assert category_for("download", "application/octet-stream") == "Other"


def test_split_extension_handles_double():
    assert split_extension("a.tar.gz") == ("a", ".tar.gz")
    assert split_extension("a.zip") == ("a", ".zip")
    assert split_extension("noext") == ("noext", "")
    assert split_extension(".gitignore") == (".gitignore", "")
    assert split_extension("ends.") == ("ends.", "")


def test_extension_of_uses_last_part():
    assert extension_of("a.tar.gz") == "gz"
    assert extension_of("A.ZIP") == "zip"
    assert extension_of("plain") == ""
