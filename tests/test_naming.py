from fdl.naming import (choose_filename, filename_from_disposition,
                        filename_from_url, sanitize, unique_path)


def test_sanitize_removes_illegal_characters():
    assert sanitize('a<b>c:d"e|f?g*h.zip') == "a_b_c_d_e_f_g_h.zip"


def test_sanitize_strips_directory_parts():
    assert sanitize("../../etc/passwd") == "passwd"
    assert sanitize(r"C:\Windows\system32\evil.exe") == "evil.exe"


def test_sanitize_handles_windows_reserved_names():
    assert sanitize("CON.txt") == "CON_file.txt"
    assert sanitize("com1.log") == "com1_file.log"


def test_sanitize_falls_back_when_empty():
    assert sanitize("") == "download"
    assert sanitize("...") == "download"


def test_sanitize_keeps_extension_when_name_is_too_long():
    name = sanitize("x" * 500 + ".tar.gz")
    assert name.endswith(".tar.gz")
    assert len(name) <= 150


def test_disposition_plain_quoted():
    header = 'attachment; filename="report final.pdf"'
    assert filename_from_disposition(header) == "report final.pdf"


def test_disposition_utf8_form_wins():
    header = "attachment; filename=\"fallback.bin\"; filename*=UTF-8''caf%C3%A9.pdf"
    assert filename_from_disposition(header) == "café.pdf"


def test_disposition_without_quotes():
    assert filename_from_disposition("attachment; filename=setup.exe") == \
        "setup.exe"


def test_disposition_missing():
    assert filename_from_disposition(None) is None
    assert filename_from_disposition("attachment") is None


def test_filename_from_url_ignores_query():
    assert filename_from_url("https://x.com/a/b/tool.zip?token=9") == "tool.zip"


def test_filename_from_url_decodes_percent():
    assert filename_from_url("https://x.com/my%20file.pdf") == "my file.pdf"


def test_choose_filename_prefers_header():
    name = choose_filename("https://x.com/download.php?id=7",
                           'attachment; filename="real-name.msi"')
    assert name == "real-name.msi"


def test_choose_filename_adds_extension_from_mime():
    name = choose_filename("https://x.com/download", None, "application/pdf")
    assert name.endswith(".pdf")


def test_unique_path_adds_counter(tmp_path):
    first = tmp_path / "a.zip"
    first.write_text("x")
    assert unique_path(first).name == "a (1).zip"

    (tmp_path / "a (1).zip").write_text("x")
    assert unique_path(first).name == "a (2).zip"


def test_unique_path_keeps_double_extension(tmp_path):
    first = tmp_path / "src.tar.gz"
    first.write_text("x")
    assert unique_path(first).name == "src (1).tar.gz"
