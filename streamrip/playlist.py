from dataclasses import dataclass

from .media import Media, Pending


@dataclass(slots=True)
class Playlist(Media):
    pass


@dataclass(slots=True)
class PendingPlaylist(Pending):
    pass
