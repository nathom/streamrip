"""Manages the information that will be embeded in the audio file."""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from string import Formatter
from typing import Generator, Hashable, Iterable, Optional, Type, Union

from .constants import (
    ALBUM_KEYS,
    COPYRIGHT,
    FLAC_KEY,
    MP3_KEY,
    MP4_KEY,
    PHON_COPYRIGHT,
    TIDAL_Q_MAP,
    TRACK_KEYS,
)
from .exceptions import InvalidContainerError, InvalidSourceError
from .utils import get_cover_urls, get_quality_id

logger = logging.getLogger("streamrip")


def get_album_track_ids(source: str, resp) -> list[str]:
    tracklist = resp["tracks"]
    if source == "qobuz":
        tracklist = tracklist["items"]
    return [track["id"] for track in tracklist]


@dataclass(slots=True)
class CoverUrls:
    thumbnail: Optional[str]
    small: Optional[str]
    large: Optional[str]
    original: Optional[str]

    def largest(self) -> Optional[str]:
        # Return first non-None item
        return self.original or self.large or self.small or self.thumbnail


@dataclass(slots=True)
class TrackMetadata:
    info: TrackInfo

    title: str
    album: AlbumMetadata
    artist: str
    tracknumber: int
    discnumber: int
    composer: Optional[str]

    @classmethod
    def from_qobuz(cls, album: AlbumMetadata, resp) -> TrackMetadata:
        raise NotImplemented

    @classmethod
    def from_deezer(cls, album: AlbumMetadata, resp) -> TrackMetadata:
        raise NotImplemented

    @classmethod
    def from_soundcloud(cls, album: AlbumMetadata, resp) -> TrackMetadata:
        raise NotImplemented

    @classmethod
    def from_tidal(cls, album: AlbumMetadata, resp) -> TrackMetadata:
        raise NotImplemented

    @classmethod
    def from_resp(cls, album: AlbumMetadata, source, resp) -> TrackMetadata:
        if source == "qobuz":
            return cls.from_qobuz(album, resp)
        if source == "tidal":
            return cls.from_tidal(album, resp)
        if source == "soundcloud":
            return cls.from_soundcloud(album, resp)
        if source == "deezer":
            return cls.from_deezer(album, resp)
        raise Exception

    def format_track_path(self, formatter: str):
        pass


@dataclass(slots=True)
class TrackInfo:
    id: str
    quality: int

    bit_depth: Optional[int] = None
    booklets = None
    explicit: bool = False
    sampling_rate: Optional[int] = None
    work: Optional[str] = None


@dataclass(slots=True)
class AlbumMetadata:
    info: AlbumInfo

    album: str
    albumartist: str
    year: str
    genre: list[str]
    covers: CoverUrls

    albumcomposer: Optional[str] = None
    comment: Optional[str] = None
    compilation: Optional[str] = None
    copyright: Optional[str] = None
    cover: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    disctotal: Optional[int] = None
    encoder: Optional[str] = None
    grouping: Optional[str] = None
    lyrics: Optional[str] = None
    purchase_date: Optional[str] = None
    tracktotal: Optional[int] = None

    @classmethod
    def from_qobuz(cls, resp) -> AlbumMetadata:
        album = resp.get("title", "Unknown Album")
        tracktotal = resp.get("tracks_count", 1)
        genre = resp.get("genres_list") or resp.get("genre") or []
        genres = list(set(re.findall(r"([^\u2192\/]+)", "/".join(genre))))
        date = resp.get("release_date_original") or resp.get("release_date")
        year = date[:4]
        copyright = resp.get("copyright")

        if artists := resp.get("artists"):
            albumartist = ", ".join(a["name"] for a in artists)
        else:
            albumartist = safe_get(resp, "artist", "name")

        albumcomposer = safe_get(resp, "composer", "name")
        label = resp.get("label")
        description = resp.get("description")
        disctotal = (
            max(
                track.get("media_number", 1)
                for track in safe_get(resp, "tracks", "items", default=[{}])
            )
            or 1
        )
        explicit = resp.get("parental_warning", False)

        if isinstance(label, dict):
            label = self.label.get("name")

        # Non-embedded information
        version = resp.get("version")
        cover_urls = CoverUrls.from_qobuz(resp)
        streamable = resp.get("streamable", False)
        bit_depth = resp.get("maximum_bit_depth")
        sampling_rate = resp.get("maximum_sampling_rate")
        quality = get_quality_id(self.bit_depth, self.sampling_rate)
        booklets = resp.get("goodies")
        item_id = resp.get("id")

        if sampling_rate is not None:
            sampling_rate *= 1000

        info = AlbumInfo(item_id, quality, explicit, sampling_rate, bit_depth, booklets)
        return AlbumMetadata(
            album,
            albumartist,
            year,
            genre=genres,
            covers=cover_urls,
            albumcomposer,
            comment,
            compilation,
            copyright(),
            cover,
            date,
            description,
            disctotal,
            encoder,
            grouping,
            lyrics,
            purchase_date,
            tracktotal,
        )

    @classmethod
    def from_deezer(cls, resp) -> AlbumMetadata:
        raise NotImplemented

    @classmethod
    def from_soundcloud(cls, resp) -> AlbumMetadata:
        raise NotImplemented

    @classmethod
    def from_tidal(cls, resp) -> AlbumMetadata:
        raise NotImplemented

    @classmethod
    def from_resp(cls, source, resp) -> AlbumMetadata:
        if source == "qobuz":
            return cls.from_qobuz(resp)
        if source == "tidal":
            return cls.from_tidal(resp)
        if source == "soundcloud":
            return cls.from_soundcloud(resp)
        if source == "deezer":
            return cls.from_deezer(resp)
        raise Exception


@dataclass(slots=True)
class AlbumInfo:
    id: str
    quality: int
    explicit: bool = False
    sampling_rate: Optional[int] = None
    bit_depth: Optional[int] = None
    booklets = None
    work: Optional[str] = None


_formatter = Formatter()


def keys_in_format_string(s: str):
    """Returns the items in {} in a format string."""
    return [f[1] for f in _formatter.parse(s) if f[1] is not None]


def safe_get(d: dict, *keys, default=None):
    """Nested __getitem__ calls with a default value.

    Use to avoid key not found errors.
    """
    _d = d
    for k in keys:
        _d = _d.get(k, {})
    if _d == {}:
        return default
    return _d
