"""Check that a downloaded file is exactly the file the site promised.

A checksum is a long hex number. If one byte of the file changes, the number
changes completely. Sites publish it next to the download link.
"""

import hashlib
import re

# The length of the hex text tells us which method was used.
BY_LENGTH = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}
KNOWN_NAMES = set(BY_LENGTH.values())

CHUNK_SIZE = 1024 * 1024
_HEX = re.compile(r"^[0-9a-f]+$")


class Result:
    def __init__(self, ok, algorithm="", expected="", actual="", error=""):
        self.ok = ok
        self.algorithm = algorithm
        self.expected = expected
        self.actual = actual
        self.error = error

    def __bool__(self):
        return self.ok


def parse(text):
    """Read what the user pasted. Returns (algorithm, value) or None.

    Accepts a plain hex value, and also forms such as
    `sha256:abc...`, `SHA-256 = abc...`, and `abc...  filename.zip`.
    """
    if not text:
        return None
    cleaned = text.strip().replace("–", "-")

    algorithm = ""
    for separator in (":", "=", " "):
        if separator in cleaned:
            head, _, tail = cleaned.partition(separator)
            name = head.strip().lower().replace("-", "").replace("_", "")
            if name in KNOWN_NAMES:
                algorithm = name
                cleaned = tail.strip()
                break

    # Some sites publish "<hash>  <filename>". Keep the first word.
    value = cleaned.split()[0].strip().lower() if cleaned.split() else ""
    if not value or not _HEX.match(value):
        return None

    if not algorithm:
        algorithm = BY_LENGTH.get(len(value), "")
    if not algorithm:
        return None
    if len(value) != len(hashlib.new(algorithm).hexdigest()):
        return None
    return algorithm, value


def compute(path, algorithm, on_progress=None):
    """Read the file and work out its checksum."""
    digest = hashlib.new(algorithm)
    done = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done)
    return digest.hexdigest()


def verify(path, pasted_text, on_progress=None):
    """Compare a file against what the user pasted."""
    parsed = parse(pasted_text)
    if not parsed:
        return Result(False, error="That is not a checksum I understand. "
                                   "It should be a long hex value, for "
                                   "example a 64 character sha256.")
    algorithm, expected = parsed
    try:
        actual = compute(path, algorithm, on_progress)
    except OSError as err:
        return Result(False, algorithm, expected, error=str(err))
    return Result(actual == expected, algorithm, expected, actual)
