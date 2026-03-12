import textwrap
from pathlib import Path
from string import printable

from pathvalidate import sanitize_filename, sanitize_filepath

ALLOWED_CHARS = set(printable)


def truncate_str(text: str, max_len: int = 255) -> str:
    return textwrap.shorten(text, width=max_len, placeholder="...")


def clean_filename(fn: str, restrict: bool = False) -> str:
    path = truncate_str(str(sanitize_filename(fn)))
    if restrict:
        path = "".join(c for c in path if c in ALLOWED_CHARS)

    return path


def clean_filepath(fn: str, restrict: bool = False) -> Path:
    path = Path(sanitize_filepath(fn))
    if restrict:
        path = Path("".join(c for c in str(path) if c in ALLOWED_CHARS))

    return path
