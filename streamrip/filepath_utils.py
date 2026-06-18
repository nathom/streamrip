from string import printable

from pathvalidate import sanitize_filename, sanitize_filepath  # type: ignore

ALLOWED_CHARS = set(printable)


# TODO: remove this when new pathvalidate release arrives with https://github.com/thombashi/pathvalidate/pull/48
def truncate_str(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= 255:
        return text
    # Cut at 255 bytes and decode back. errors="ignore" silently drops any
    # incomplete multi-byte sequence that straddles the boundary (e.g. a CJK
    # character whose lead byte is at position 254). The result is always
    # valid UTF-8 and ≤ 255 bytes when re-encoded.
    return encoded[:255].decode("utf-8", errors="ignore")


def clean_filename(fn: str, restrict: bool = False) -> str:
    fn = fn.replace("/", "-")
    path = truncate_str(str(sanitize_filename(fn)))
    if restrict:
        path = "".join(c for c in path if c in ALLOWED_CHARS)

    return path


def clean_filepath(fn: str, restrict: bool = False) -> str:
    path = str(sanitize_filepath(fn))
    if restrict:
        path = "".join(c for c in path if c in ALLOWED_CHARS)

    return path
