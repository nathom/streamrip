from string import Formatter, printable

from pathvalidate import sanitize_filename


def clean_filename(fn: str, restrict=False) -> str:
    path = str(sanitize_filename(fn))
    if restrict:
        allowed_chars = set(printable)
        path = "".join(c for c in path if c in allowed_chars)

    return path


def clean_format(formatter: str, format_info: dict, restrict: bool = False) -> str:
    """Format track or folder names sanitizing every formatter key.

    :param formatter:
    :type formatter: str
    :param kwargs:
    """
    fmt_keys = filter(None, (i[1] for i in Formatter().parse(formatter)))

    clean_dict = {}
    for key in fmt_keys:
        if isinstance(format_info.get(key), (str, float)):
            clean_dict[key] = clean_filename(str(format_info[key]), restrict=restrict)
        elif key == "explicit":
            clean_dict[key] = " (Explicit) " if format_info.get(key, False) else ""
        elif isinstance(format_info.get(key), int):  # track/discnumber
            clean_dict[key] = f"{format_info[key]:02}"
        else:
            clean_dict[key] = "Unknown"

    return formatter.format(**clean_dict)
