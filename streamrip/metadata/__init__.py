"""Manages the information that will be embeded in the audio file."""
from . import util
from .album_metadata import AlbumMetadata
from .artist_metadata import ArtistMetadata
from .covers import Covers
from .label_metadata import LabelMetadata
from .playlist_metadata import PlaylistMetadata
from .search_results import (
    AlbumSummary,
    ArtistSummary,
    LabelSummary,
    PlaylistSummary,
    SearchResults,
    Summary,
    TrackSummary,
)
from .tagger import tag_file
from .track_metadata import TrackMetadata

__all__ = [
    "AlbumMetadata",
    "ArtistMetadata",
    "LabelMetadata",
    "TrackMetadata",
    "PlaylistMetadata",
    "Covers",
    "tag_file",
    "util",
    "AlbumSummary",
    "ArtistSummary",
    "LabelSummary",
    "PlaylistSummary",
    "Summary",
    "TrackSummary",
    "SearchResults",
]
