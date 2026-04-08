"""Typed response models for the Qobuz API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageSet:
    small: str | None = None
    thumbnail: str | None = None
    large: str | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> ImageSet:
        if not d:
            return cls()
        return cls(small=d.get("small"), thumbnail=d.get("thumbnail"), large=d.get("large"))


@dataclass
class ArtistSummary:
    id: int
    name: str

    @classmethod
    def from_dict(cls, d: dict) -> ArtistSummary:
        name = d.get("name", "Unknown")
        # artist/page uses {"name": {"display": "..."}}
        if isinstance(name, dict):
            name = name.get("display", "Unknown")
        return cls(id=d["id"], name=name)


@dataclass
class ArtistRole:
    id: int
    name: str
    roles: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> ArtistRole:
        return cls(id=d["id"], name=d.get("name", "Unknown"), roles=d.get("roles", []))


@dataclass
class Label:
    id: int
    name: str

    @classmethod
    def from_dict(cls, d: dict | None) -> Label | None:
        if not d:
            return None
        return cls(id=d["id"], name=d.get("name", "Unknown"))


@dataclass
class Genre:
    id: int
    name: str
    color: str = ""
    path: list[int] = field(default_factory=list)
    slug: str = ""

    @classmethod
    def from_dict(cls, d: dict | None) -> Genre | None:
        if not d:
            return None
        return cls(
            id=d["id"], name=d.get("name", ""), color=d.get("color", ""),
            path=d.get("path", []), slug=d.get("slug", ""),
        )


@dataclass
class AudioInfo:
    maximum_bit_depth: int = 16
    maximum_channel_count: int = 2
    maximum_sampling_rate: float = 44.1

    @classmethod
    def from_dict(cls, d: dict | None) -> AudioInfo:
        if not d:
            return cls()
        return cls(
            maximum_bit_depth=d.get("maximum_bit_depth", 16),
            maximum_channel_count=d.get("maximum_channel_count", 2),
            maximum_sampling_rate=d.get("maximum_sampling_rate", 44.1),
        )


@dataclass
class Rights:
    streamable: bool = False
    downloadable: bool = False
    hires_streamable: bool = False
    purchasable: bool = False

    @classmethod
    def from_dict(cls, d: dict | None) -> Rights:
        if not d:
            return cls()
        return cls(
            streamable=d.get("streamable", False),
            downloadable=d.get("downloadable", False),
            hires_streamable=d.get("hires_streamable", False),
            purchasable=d.get("purchasable", False),
        )


@dataclass
class AlbumSummary:
    id: str
    title: str
    image: ImageSet = field(default_factory=ImageSet)

    @classmethod
    def from_dict(cls, d: dict) -> AlbumSummary:
        return cls(id=str(d["id"]), title=d.get("title", ""), image=ImageSet.from_dict(d.get("image")))


@dataclass
class UserSummary:
    id: int
    name: str

    @classmethod
    def from_dict(cls, d: dict) -> UserSummary:
        return cls(id=d["id"], name=d.get("name", d.get("display_name", "")))


@dataclass
class Award:
    id: int
    name: str
    awarded_at: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Award:
        return cls(id=d["id"], name=d.get("name", ""), awarded_at=d.get("awarded_at"))


@dataclass
class Album:
    id: str
    title: str
    version: str | None
    artist: ArtistSummary
    artists: list[ArtistRole]
    image: ImageSet
    duration: int
    tracks_count: int
    maximum_bit_depth: int
    maximum_sampling_rate: float
    maximum_channel_count: int
    streamable: bool
    downloadable: bool
    hires: bool
    hires_streamable: bool
    release_date_original: str | None = None
    upc: str | None = None
    label: Label | None = None
    genre: Genre | None = None
    description: str | None = None
    awards: list[Award] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Album:
        return cls(
            id=str(d["id"]),
            title=d.get("title", ""),
            version=d.get("version"),
            artist=ArtistSummary.from_dict(d.get("artist", {"id": 0, "name": "Unknown"})),
            artists=[ArtistRole.from_dict(a) for a in d.get("artists", [])],
            image=ImageSet.from_dict(d.get("image")),
            duration=d.get("duration", 0),
            tracks_count=d.get("tracks_count", 0),
            maximum_bit_depth=d.get("maximum_bit_depth", 16),
            maximum_sampling_rate=d.get("maximum_sampling_rate", 44.1),
            maximum_channel_count=d.get("maximum_channel_count", 2),
            streamable=d.get("streamable", False),
            downloadable=d.get("downloadable", False),
            hires=d.get("hires", False),
            hires_streamable=d.get("hires_streamable", False),
            release_date_original=d.get("release_date_original"),
            upc=d.get("upc"),
            label=Label.from_dict(d.get("label")),
            genre=Genre.from_dict(d.get("genre")),
            description=d.get("description"),
            awards=[Award.from_dict(a) for a in d.get("awards", [])],
        )


@dataclass
class Track:
    id: int
    title: str
    version: str | None
    duration: int
    track_number: int
    disc_number: int
    explicit: bool
    performer: ArtistSummary
    album: AlbumSummary
    audio_info: AudioInfo
    rights: Rights
    isrc: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Track:
        phys = d.get("physical_support", {})
        return cls(
            id=d["id"],
            title=d.get("title", ""),
            version=d.get("version"),
            duration=d.get("duration", 0),
            track_number=phys.get("track_number", d.get("track_number", 0)),
            disc_number=phys.get("media_number", d.get("media_number", 1)),
            explicit=d.get("parental_warning", False),
            performer=ArtistSummary.from_dict(d.get("performer", {"id": 0, "name": "Unknown"})),
            album=AlbumSummary.from_dict(d.get("album", {"id": "", "title": ""})),
            audio_info=AudioInfo.from_dict(d.get("audio_info")),
            rights=Rights.from_dict(d.get("rights")),
            isrc=d.get("isrc"),
        )


@dataclass
class Playlist:
    id: int
    name: str
    description: str
    tracks_count: int
    users_count: int
    duration: int
    is_public: bool
    is_collaborative: bool
    public_at: int | bool
    created_at: int
    updated_at: int
    owner: UserSummary

    @classmethod
    def from_dict(cls, d: dict) -> Playlist:
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            description=d.get("description", ""),
            tracks_count=d.get("tracks_count", 0),
            users_count=d.get("users_count", 0),
            duration=d.get("duration", 0),
            is_public=d.get("is_public", False),
            is_collaborative=d.get("is_collaborative", False),
            public_at=d.get("public_at", False),
            created_at=d.get("created_at", 0),
            updated_at=d.get("updated_at", 0),
            owner=UserSummary.from_dict(d.get("owner", {"id": 0, "name": ""})),
        )


@dataclass
class FavoriteIds:
    albums: list[str] = field(default_factory=list)
    tracks: list[int] = field(default_factory=list)
    artists: list[int] = field(default_factory=list)
    labels: list[int] = field(default_factory=list)
    awards: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> FavoriteIds:
        return cls(
            albums=[str(a) for a in d.get("albums", [])],
            tracks=d.get("tracks", []),
            artists=d.get("artists", []),
            labels=d.get("labels", []),
            awards=d.get("awards", []),
        )


@dataclass
class LastUpdate:
    favorite: int = 0
    favorite_album: int = 0
    favorite_artist: int = 0
    favorite_track: int = 0
    favorite_label: int = 0
    playlist: int = 0
    purchase: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> LastUpdate:
        lu = d.get("last_update", d)
        return cls(
            favorite=lu.get("favorite", 0),
            favorite_album=lu.get("favorite_album", 0),
            favorite_artist=lu.get("favorite_artist", 0),
            favorite_track=lu.get("favorite_track", 0),
            favorite_label=lu.get("favorite_label", 0),
            playlist=lu.get("playlist", 0),
            purchase=lu.get("purchase", 0),
        )


@dataclass
class FileUrl:
    track_id: int
    format_id: int
    mime_type: str
    sampling_rate: int
    bits_depth: int
    duration: float
    url_template: str
    n_segments: int
    key_id: str | None = None
    key: str | None = None
    blob: str | None = None
    restrictions: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> FileUrl:
        return cls(
            track_id=d["track_id"],
            format_id=d["format_id"],
            mime_type=d.get("mime_type", ""),
            sampling_rate=d.get("sampling_rate", 0),
            bits_depth=d.get("bits_depth", 0),
            duration=d.get("duration", 0),
            url_template=d.get("url_template", ""),
            n_segments=d.get("n_segments", 0),
            key_id=d.get("key_id"),
            key=d.get("key"),
            blob=d.get("blob"),
            restrictions=d.get("restrictions", []),
        )


@dataclass
class Session:
    session_id: str
    profile: str
    expires_at: int

    @classmethod
    def from_dict(cls, d: dict) -> Session:
        return cls(session_id=d["session_id"], profile=d.get("profile", ""), expires_at=d.get("expires_at", 0))


@dataclass
class PaginatedResult:
    """Wraps a paginated API response."""
    items: list[dict]
    total: int | None  # None for has_more-style pagination
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def from_dict(cls, d: dict, key: str | None = None) -> PaginatedResult:
        """Parse paginated response.

        Two styles:
        - {key: {items: [...], total, limit, offset}}  (most endpoints)
        - {has_more: bool, items: [...]}                (discovery, releases)
        """
        if key and key in d:
            container = d[key]
            return cls(
                items=container.get("items", []),
                total=container.get("total"),
                limit=container.get("limit", 500),
                offset=container.get("offset", 0),
                has_more=container.get("offset", 0) + container.get("limit", 500) < container.get("total", 0),
            )
        if "items" in d:
            return cls(
                items=d["items"],
                total=None,
                limit=len(d["items"]),
                offset=0,
                has_more=d.get("has_more", False),
            )
        return cls(items=[], total=0, limit=0, offset=0, has_more=False)
