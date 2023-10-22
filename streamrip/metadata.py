"""Manages the information that will be embeded in the audio file."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from string import Formatter
from typing import Optional, Type, TypeVar

# from .constants import (
#     ALBUM_KEYS,
#     COPYRIGHT,
#     FLAC_KEY,
#     MP3_KEY,
#     MP4_KEY,
#     PHON_COPYRIGHT,
#     TIDAL_Q_MAP,
#     TRACK_KEYS,
# )

logger = logging.getLogger("streamrip")


def get_album_track_ids(source: str, resp) -> list[str]:
    tracklist = resp["tracks"]
    if source == "qobuz":
        tracklist = tracklist["items"]
    return [track["id"] for track in tracklist]


# (url to cover, downloaded path of cover)
@dataclass(slots=True)
class Covers:
    CoverEntry = tuple[str | None, str | None]
    thumbnail: CoverEntry
    small: CoverEntry
    large: CoverEntry
    original: CoverEntry

    def empty(self) -> bool:
        return all(
            url is None
            for url, _ in (self.original, self.large, self.small, self.thumbnail)
        )

    def largest(self) -> CoverEntry:
        # Return first item with url
        if self.original[0]:
            return self.original

        if self.large[0]:
            return self.large

        if self.small[0]:
            return self.small

        if self.thumbnail[0]:
            return self.thumbnail

        raise Exception("No covers found")

    @classmethod
    def from_qobuz(cls, resp):
        cover_urls = {k: (v, None) for k, v in resp["image"].items()}
        cover_urls["original"] = ("org".join(cover_urls["large"].rsplit("600", 1)), None)  # type: ignore
        return cls(**cover_urls)  # type: ignore

    def get_size(self, size: str) -> CoverEntry:
        """Get the cover size, or the largest cover smaller than `size`.

        Args:
            size (str):

        Returns:
            CoverEntry


        Raises:
            Exception: If a suitable cover doesn't exist

        """
        fallback = False
        if size == "original":
            if self.original[0] is not None:
                return self.original
            else:
                fallback = True

        if fallback or size == "large":
            if self.large[0] is not None:
                return self.large
            else:
                fallback = True

        if fallback or size == "small":
            if self.small[0] is not None:
                return self.small
            else:
                fallback = True

        # At this point, either size == 'thumbnail' or nothing else was found
        if self.thumbnail[0] is None:
            raise Exception(f"No covers found for {size = }. Covers: {self}")

        return self.thumbnail


COPYRIGHT = "\u2117"
PHON_COPYRIGHT = "\u00a9"


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
        title = typed(resp["title"].strip(), str)

        version = resp.get("version")
        work = resp.get("work")
        if version is not None and version not in title:
            title = f"{title} ({version})"
        if work is not None and work not in title:
            title = f"{work}: {title}"

        composer = typed(resp.get("composer", {}).get("name"), str | None)
        tracknumber = typed(resp.get("track_number", 1), int)
        discnumber = typed(resp.get("media_number", 1), int)
        artist = typed(safe_get(resp, "performer", "name"), str)
        track_id = typed(resp["id"], str)

        info = TrackInfo(id=track_id, quality=album.info.quality)
        return cls(
            info=info,
            title=title,
            album=album,
            artist=artist,
            tracknumber=tracknumber,
            discnumber=discnumber,
            composer=composer,
        )

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

    def format_track_path(self, formatter: str) -> str:
        # Available keys: "tracknumber", "artist", "albumartist", "composer", "title",
        # and "albumcomposer"
        info = {
            "title": self.title,
            "tracknumber": self.tracknumber,
            "artist": self.artist,
            "albumartist": self.album.albumartist,
            "albumcomposer": self.album.albumcomposer or "None",
            "composer": self.composer or "None",
        }
        return formatter.format(**info)


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
    covers: Covers

    albumcomposer: Optional[str] = None
    comment: Optional[str] = None
    compilation: Optional[str] = None
    copyright: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    disctotal: Optional[int] = None
    encoder: Optional[str] = None
    grouping: Optional[str] = None
    lyrics: Optional[str] = None
    purchase_date: Optional[str] = None
    tracktotal: Optional[int] = None

    def format_folder_path(self, formatter: str) -> str:
        # Available keys: "albumartist", "title", "year", "bit_depth", "sampling_rate",
        # "id", and "albumcomposer"
        info = {
            "albumartist": self.albumartist,
            "albumcomposer": self.albumcomposer or "None",
            "bit_depth": self.info.bit_depth,
            "id": self.info.id,
            "sampling_rate": self.info.sampling_rate,
            "title": self.album,
            "year": self.year,
        }
        return formatter.format(**info)

    @classmethod
    def from_qobuz(cls, resp) -> AlbumMetadata:
        album = resp.get("title", "Unknown Album")
        tracktotal = resp.get("tracks_count", 1)
        genre = resp.get("genres_list") or resp.get("genre") or []
        genres = list(set(re.findall(r"([^\u2192\/]+)", "/".join(genre))))
        date = resp.get("release_date_original") or resp.get("release_date")
        year = date[:4]

        _copyright = resp.get("copyright")
        _copyright = re.sub(r"(?i)\(P\)", PHON_COPYRIGHT, _copyright)
        _copyright = re.sub(r"(?i)\(C\)", COPYRIGHT, _copyright)

        if artists := resp.get("artists"):
            albumartist = ", ".join(a["name"] for a in artists)
        else:
            albumartist = typed(safe_get(resp, "artist", "name"), str)

        albumcomposer = typed(safe_get(resp, "composer", "name"), str | None)
        _label = resp.get("label")
        if isinstance(_label, dict):
            _label = _label["name"]
        label = typed(_label, str | None)
        description = typed(resp.get("description"), str | None)
        disctotal = typed(
            max(
                track.get("media_number", 1)
                for track in safe_get(resp, "tracks", "items", default=[{}])  # type: ignore
            )
            or 1,
            int,
        )
        explicit = typed(resp.get("parental_warning", False), bool)

        # Non-embedded information
        # version = resp.get("version")
        cover_urls = Covers.from_qobuz(resp)
        streamable = typed(resp.get("streamable", False), bool)
        assert streamable
        bit_depth = typed(resp.get("maximum_bit_depth"), int | None)
        sampling_rate = typed(resp.get("maximum_sampling_rate"), int | None)
        quality = get_quality_id(bit_depth, sampling_rate)
        booklets = resp.get("goodies")
        item_id = resp.get("id")

        if sampling_rate is not None:
            sampling_rate *= 1000

        info = AlbumInfo(
            item_id, quality, label, explicit, sampling_rate, bit_depth, booklets
        )
        return AlbumMetadata(
            info,
            album,
            albumartist,
            year,
            genre=genres,
            covers=cover_urls,
            albumcomposer=albumcomposer,
            comment=None,
            compilation=None,
            copyright=_copyright,
            date=date,
            description=description,
            disctotal=disctotal,
            encoder=None,
            grouping=None,
            lyrics=None,
            purchase_date=None,
            tracktotal=tracktotal,
        )

    @classmethod
    def from_deezer(cls, resp) -> AlbumMetadata:
        raise NotImplementedError

    @classmethod
    def from_soundcloud(cls, resp) -> AlbumMetadata:
        raise NotImplementedError

    @classmethod
    def from_tidal(cls, resp) -> AlbumMetadata:
        raise NotImplementedError

    @classmethod
    def from_resp(cls, resp, source) -> AlbumMetadata:
        if source == "qobuz":
            return cls.from_qobuz(resp)
        if source == "tidal":
            return cls.from_tidal(resp)
        if source == "soundcloud":
            return cls.from_soundcloud(resp)
        if source == "deezer":
            return cls.from_deezer(resp)
        raise Exception("Invalid source")


@dataclass(slots=True)
class AlbumInfo:
    id: str
    quality: int
    label: Optional[str] = None
    explicit: bool = False
    sampling_rate: Optional[int] = None
    bit_depth: Optional[int] = None
    booklets = None
    work: Optional[str] = None


_formatter = Formatter()


def keys_in_format_string(s: str):
    """Returns the items in {} in a format string."""
    return [f[1] for f in _formatter.parse(s) if f[1] is not None]


def safe_get(d: dict, *keys, default=None) -> dict | str | int | list | None:
    """Nested __getitem__ calls with a default value.

    Use to avoid key not found errors.
    """
    _d = d
    for k in keys:
        _d = _d.get(k, {})
    if _d == {}:
        return default
    return _d


T = TypeVar("T")


def typed(thing, expected_type: Type[T]) -> T:
    assert isinstance(thing, expected_type)
    return thing


def get_quality_id(bit_depth: Optional[int], sampling_rate: Optional[int]) -> int:
    """Get the universal quality id from bit depth and sampling rate.

    :param bit_depth:
    :type bit_depth: Optional[int]
    :param sampling_rate: In kHz
    :type sampling_rate: Optional[int]
    """
    # XXX: Should `0` quality be supported?
    if bit_depth is None or sampling_rate is None:  # is lossy
        return 1

    if bit_depth == 16:
        return 2

    if bit_depth == 24:
        if sampling_rate <= 96:
            return 3

        return 4

    raise Exception(f"Invalid {bit_depth = }")
