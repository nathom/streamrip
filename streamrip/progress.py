from typing import Callable

from click import style
from rich.progress import Progress

from .console import console

THEMES = {
    "plain": None,
    "dainty": (
        "{desc} |{bar}| "
        + style("{remaining}", fg="magenta")
        + " left at "
        + style("{rate_fmt}{postfix} ", fg="cyan", bold=True)
    ),
}


class ProgressManager:
    def __init__(self):
        self.started = False
        self.progress = Progress(console=console)

    def get_callback(self, total: int, desc: str):
        if not self.started:
            self.progress.start()
            self.started = True

        task = self.progress.add_task(f"[cyan]{desc}", total=total)

        def _callback(x: int):
            self.progress.update(task, advance=x)

        return _callback

    def cleanup(self):
        if self.started:
            self.progress.stop()


# global instance
_p = ProgressManager()


def get_progress_callback(
    enabled: bool, total: int, desc: str
) -> Callable[[int], None]:
    if not enabled:
        return lambda _: None
    return _p.get_callback(total, desc)


def clear_progress():
    _p.cleanup()
