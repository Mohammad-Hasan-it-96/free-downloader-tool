"""A small log file, so a problem can be looked at after it happened.

The log lives next to the app as `fdl.log`. It is rotated, so it cannot grow
without end. Links are cleaned before they are written, because a link can
carry a token or a password in its query.
"""

import logging
import logging.handlers
import urllib.parse
from pathlib import Path

LOGGER_NAME = "fdl"
MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 2

# Query names that often hold something private.
SECRET_KEYS = {"token", "access_token", "key", "api_key", "apikey", "password",
               "passwd", "pwd", "secret", "sig", "signature", "auth",
               "session", "sessionid", "x-amz-signature", "x-amz-credential"}

_ready = False


def setup(path, enabled=True):
    """Start writing to the log file. Safe to call more than once."""
    global _ready
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    if not enabled:
        logger.addHandler(logging.NullHandler())
        _ready = True
        return logger

    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
            encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    except OSError:
        # A log is a convenience. Never stop the app because of it.
        logger.addHandler(logging.NullHandler())
    _ready = True
    return logger


def get():
    logger = logging.getLogger(LOGGER_NAME)
    if not _ready and not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def redact(url):
    """Hide anything private in a link, so it is safe to write down."""
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "<unreadable link>"

    netloc = parts.netloc
    if "@" in netloc:                      # user:password@host
        netloc = "***@" + netloc.rsplit("@", 1)[1]

    query = parts.query
    if query:
        pairs = urllib.parse.parse_qsl(query, keep_blank_values=True)
        cleaned = [(key, "***" if key.lower() in SECRET_KEYS else value)
                   for key, value in pairs]
        query = urllib.parse.urlencode(cleaned)

    return urllib.parse.urlunsplit(
        (parts.scheme, netloc, parts.path, query, parts.fragment))


def info(message, *args):
    get().info(message, *args)


def warning(message, *args):
    get().warning(message, *args)


def error(message, *args):
    get().error(message, *args)


def tail(path, lines=40):
    """The last lines of the log file, newest last."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-lines:]
