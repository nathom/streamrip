from typing import Optional

from click import style
from tqdm.asyncio import tqdm

from .config import Config

THEMES = {
    "plain": None,
    "dainty": (
        "{desc} |{bar}| "
        + style("{remaining}", fg="magenta")
        + " left at "
        + style("{rate_fmt}{postfix} ", fg="cyan", bold=True)
    ),
}


def get_progress_bar(config: Config, total: int, desc: Optional[str], unit="B"):
    theme = THEMES[config.session.theme.progress_bar]
    return tqdm(
        total=total,
        unit=unit,
        unit_scale=True,
        unit_divisor=1024,
        desc=desc,
        dynamic_ncols=True,
        bar_format=theme,
    )
