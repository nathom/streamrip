from typing import Optional

from click import style
from tqdm import tqdm

THEMES = {
    "plain": None,
    "dainty": (
        "{desc} |{bar}| "
        + style("{remaining}", fg="magenta")
        + " left at "
        + style("{rate_fmt}{postfix} ", fg="cyan", bold=True)
    ),
}


def get_progress_bar(total, theme="dainty", desc: Optional[str] = None, unit="B"):
    theme = THEMES[theme]
    return tqdm(
        total=total,
        unit=unit,
        unit_scale=True,
        unit_divisor=1024,
        desc=desc,
        dynamic_ncols=True,
        bar_format=theme,
    )
