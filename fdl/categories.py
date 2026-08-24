"""Decide which folder a file belongs to, based on its extension."""

# Extensions that are really two parts, for example "archive.tar.gz".
DOUBLE_EXTENSIONS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst", ".tar.lz")

# Order matters only for the menu. "Other" is always last.
CATEGORY_ORDER = ["Videos", "Audio", "Programs", "Archives",
                  "Documents", "Images", "Code", "Other"]

OTHER = "Other"

EXTENSIONS = {
    "Videos": {
        "mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "m4v", "mpg",
        "mpeg", "3gp", "ts", "m2ts", "vob", "ogv", "divx", "rmvb", "mts",
    },
    "Audio": {
        "mp3", "m4a", "aac", "flac", "wav", "ogg", "opus", "wma", "aiff",
        "alac", "ape", "mid", "midi", "amr", "m4b",
    },
    "Programs": {
        "exe", "msi", "msix", "appx", "bat", "cmd", "deb", "rpm", "dmg",
        "pkg", "apk", "aab", "appimage", "snap", "flatpak", "run", "bin",
    },
    "Archives": {
        "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "zst", "tgz", "tbz2",
        "iso", "cab", "arj", "lzh", "z", "img", "vhd", "vhdx",
    },
    "Documents": {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf",
        "odt", "ods", "odp", "epub", "mobi", "azw3", "djvu", "csv", "tex",
        "md", "pages",
    },
    "Images": {
        "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "tif", "tiff",
        "heic", "heif", "ico", "psd", "ai", "eps", "raw", "cr2", "nef",
        "avif",
    },
    "Code": {
        "py", "js", "ts", "jsx", "tsx", "java", "c", "h", "cpp", "cs", "go",
        "rs", "rb", "php", "swift", "kt", "sh", "ps1", "sql", "json", "xml",
        "yml", "yaml", "toml", "ini", "html", "css", "scss", "whl", "jar",
        "war", "gem", "patch", "diff",
    },
}

# Built once: extension -> category
_BY_EXTENSION = {}
for _category, _exts in EXTENSIONS.items():
    for _ext in _exts:
        _BY_EXTENSION[_ext] = _category

# Used only when the file has no useful extension.
_BY_MIME_PREFIX = {
    "video/": "Videos",
    "audio/": "Audio",
    "image/": "Images",
    "text/": "Documents",
}
_BY_MIME_EXACT = {
    "application/pdf": "Documents",
    "application/epub+zip": "Documents",
    "application/zip": "Archives",
    "application/x-tar": "Archives",
    "application/gzip": "Archives",
    "application/x-7z-compressed": "Archives",
    "application/x-rar-compressed": "Archives",
    "application/vnd.rar": "Archives",
    "application/x-msdownload": "Programs",
    "application/vnd.microsoft.portable-executable": "Programs",
    "application/vnd.android.package-archive": "Programs",
    "application/x-apple-diskimage": "Programs",
    "application/json": "Code",
    "application/javascript": "Code",
}


def split_extension(name):
    """Split a file name into (stem, extension). Keeps '.tar.gz' together.

    The extension includes the leading dot, or is '' when there is none.
    """
    lower = name.lower()
    for double in DOUBLE_EXTENSIONS:
        if lower.endswith(double) and len(name) > len(double):
            return name[:-len(double)], name[-len(double):]
    dot = name.rfind(".")
    if dot <= 0 or dot == len(name) - 1:
        return name, ""
    return name[:dot], name[dot:]


def extension_of(name):
    """Return the extension without dots, lowercase. '' when there is none.

    For 'a.tar.gz' this returns 'gz', because that is what decides the folder.
    """
    _, ext = split_extension(name)
    if not ext:
        return ""
    return ext.lstrip(".").split(".")[-1].lower()


def category_for(name, content_type=None):
    """Return the category name for a file name.

    The extension is checked first. The MIME type from the server is only a
    fallback, because servers often send a wrong or generic type.
    """
    ext = extension_of(name)
    if ext in _BY_EXTENSION:
        return _BY_EXTENSION[ext]

    if content_type:
        mime = content_type.split(";")[0].strip().lower()
        if mime in _BY_MIME_EXACT:
            return _BY_MIME_EXACT[mime]
        for prefix, category in _BY_MIME_PREFIX.items():
            if mime.startswith(prefix):
                return category
    return OTHER
