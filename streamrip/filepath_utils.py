from string import printable

from pathvalidate import sanitize_filename, sanitize_filepath  # type: ignore

import os

ALLOWED_CHARS = set(printable)


def clean_filename(fn: str, restrict: bool = False) -> str:
    if fn:
        parts = os.path.normpath(fn).split(os.path.sep)
        for index, part in enumerate(parts):
            if index < len(parts)-1:
                path = str(sanitize_filepath(part))
            else:
                path = str(sanitize_filename(part))
            if restrict:
                path = "".join(c for c in path if c in ALLOWED_CHARS)
            parts[index] = path
        return os.path.sep.join(parts)
    else:
        return fn

def clean_pathsep(fn: str) -> str:
    if fn:
        return fn.replace("/", "_").replace("\\", "_")
    else:
        return fn

def clean_filepath(fn: str, restrict: bool = False) -> str:
    if fn:
        parts = os.path.normpath(fn).split(os.path.sep)
        for index, part in enumerate(parts):
            path = str(sanitize_filepath(part))
            if restrict:
                path = "".join(c for c in path if c in ALLOWED_CHARS)
            parts[index] = path
        return os.path.sep.join(parts)
    else:
        return fn
