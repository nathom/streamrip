from string import printable

from pathvalidate import sanitize_filename  # type: ignore

ALLOWED_CHARS = set(printable)


def clean_filename(fn: str, restrict: bool = False) -> str:
    path = str(sanitize_filename(fn))
    if restrict:
        path = "".join(c for c in path if c in ALLOWED_CHARS)

    return path
