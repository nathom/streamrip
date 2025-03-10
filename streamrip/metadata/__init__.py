"""Manages the information that will be embeded in the audio file."""

from . import util
from .album import AlbumInfo, AlbumMetadata
from .artist import ArtistMetadata
from .covers import Covers
from .label import LabelMetadata
from .playlist import PlaylistMetadata
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
from .track import TrackInfo, TrackMetadata

__all__ = [
    "AlbumMetadata",
    "ArtistMetadata",
    "AlbumInfo",
    "TrackInfo",
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
