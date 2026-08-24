"""Decide which engine should handle a link.

Two engines can take a link:

  * the file downloader, for a direct link to a file (fast, resumable)
  * yt-dlp, for a page that holds a video or audio

The order of the checks matters:

  1. A link whose path ends in a known file extension is a file, even when
     the site is one that yt-dlp knows. For example
     `archive.org/download/x/tool.zip` is a plain zip, not a video page.
  2. A link to a site yt-dlp has a real extractor for is media.
  3. Anything else is asked. A server that answers with a web page is
     given to yt-dlp; a server that answers with a file is downloaded.
"""

from dataclasses import dataclass

from . import http_engine, ytdlp_engine
from .categories import EXTENSIONS, extension_of
from .http_engine import DownloadError
from .naming import filename_from_url

KIND_FILE = "file"
KIND_MEDIA = "media"

HTML_TYPES = ("text/html", "application/xhtml+xml")

KNOWN_EXTENSIONS = set()
for _exts in EXTENSIONS.values():
    KNOWN_EXTENSIONS |= _exts


@dataclass
class Route:
    kind: str
    info: object = None      # RemoteInfo, when the server was asked
    reason: str = ""         # short text to show the user
    error: str = ""          # why the check failed, if it did

    @property
    def is_media(self):
        return self.kind == KIND_MEDIA

    @property
    def other_kind(self):
        return KIND_FILE if self.kind == KIND_MEDIA else KIND_MEDIA


def looks_like_a_file_name(url):
    """True when the link path ends in an extension we know."""
    name = filename_from_url(url) or ""
    return extension_of(name) in KNOWN_EXTENSIONS


def content_type_of(info):
    return (getattr(info, "content_type", "") or "").split(";")[0].strip().lower()


def decide(url, probe=None):
    """Work out which engine fits this link. Never raises."""
    ask = probe or http_engine.probe

    if looks_like_a_file_name(url):
        reason = "the link ends in a file name"
        try:
            info = ask(url)
        except DownloadError as err:
            return Route(KIND_FILE, None, reason, str(err))
        return Route(KIND_FILE, info, reason)

    if ytdlp_engine.looks_like_media_site(url):
        return Route(KIND_MEDIA, None, "yt-dlp knows this site")

    try:
        info = ask(url)
    except DownloadError as err:
        return Route(KIND_MEDIA, None,
                     "the server did not answer as a file", str(err))

    if content_type_of(info) in HTML_TYPES:
        return Route(KIND_MEDIA, info,
                     "the server sent a web page, so yt-dlp will look inside it")
    return Route(KIND_FILE, info, "the server sent a file, not a page")
