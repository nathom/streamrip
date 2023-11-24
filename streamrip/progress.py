from dataclasses import dataclass
from typing import Callable

from rich.console import Group
from rich.live import Live
from rich.progress import Progress
from rich.rule import Rule
from rich.text import Text

from .console import console


class ProgressManager:
    def __init__(self):
        self.started = False
        self.progress = Progress(console=console)
        self.prefix = Text.assemble(("Downloading ", "bold cyan"), overflow="ellipsis")
        self.live = Live(Group(self.prefix, self.progress), refresh_per_second=10)
        self.task_titles = []

    def get_callback(self, total: int, desc: str):
        if not self.started:
            self.live.start()
            self.started = True

        task = self.progress.add_task(f"[cyan]{desc}", total=total)

        def _callback_update(x: int):
            self.progress.update(task, advance=x)
            self.live.update(Group(self.get_title_text(), self.progress))

        def _callback_done():
            self.progress.update(task, visible=False)

        return Handle(_callback_update, _callback_done)

    def cleanup(self):
        if self.started:
            self.live.stop()

    def add_title(self, title: str):
        self.task_titles.append(title.strip())

    def remove_title(self, title: str):
        self.task_titles.remove(title.strip())

    def get_title_text(self) -> Rule:
        titles = ", ".join(self.task_titles[:3])
        if len(self.task_titles) > 3:
            titles += "..."
        t = self.prefix + Text(titles)
        return Rule(t)


@dataclass(slots=True)
class Handle:
    update: Callable[[int], None]
    done: Callable[[], None]

    def __enter__(self):
        return self.update

    def __exit__(self, *_):
        self.done()


# global instance
_p = ProgressManager()


def get_progress_callback(enabled: bool, total: int, desc: str) -> Handle:
    global _p
    if not enabled:
        return Handle(lambda _: None, lambda: None)
    return _p.get_callback(total, desc)


def add_title(title: str):
    global _p
    _p.add_title(title)


def remove_title(title: str):
    global _p
    _p.remove_title(title)


def clear_progress():
    global _p
    _p.cleanup()
