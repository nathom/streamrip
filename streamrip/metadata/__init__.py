"""Manages the information that will be embeded in the audio file."""
from . import util
from .album_metadata import AlbumMetadata
from .covers import Covers
from .playlist_metadata import PlaylistMetadata
from .track_metadata import TrackMetadata

__all__ = [
    "AlbumMetadata",
    "TrackMetadata",
    "PlaylistMetadata",
    "Covers",
    "util",
]
