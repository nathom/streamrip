import os
import re
import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass


class Summary(ABC):
    id: str

    @abstractmethod
    def summarize(self) -> str:
        pass

    @abstractmethod
    def preview(self) -> str:
        pass

    @classmethod
    @abstractmethod
    def from_item(cls, item: dict) -> str:
        pass

    @abstractmethod
    def media_type(self) -> str:
        pass

    def __str__(self):
        return self.summarize()


@dataclass(slots=True)
class ArtistSummary(Summary):
    id: str
    name: str
    num_albums: str

    def media_type(self):
        return "artist"

    def summarize(self) -> str:
        return clean(self.name)

    def preview(self) -> str:
        return f"{self.num_albums} Albums\n\nID: {self.id}"

    @classmethod
    def from_item(cls, item: dict):
        id = str(item["id"])
        name = (
            item.get("name")
            or item.get("performer", {}).get("name")
            or item.get("artist")
            or item.get("artist", {}).get("name")
            or (
                item.get("publisher_metadata")
                and item["publisher_metadata"].get("artist")
            )
            or "Unknown"
        )
        num_albums = item.get("albums_count") or "Unknown"
        return cls(id, name, num_albums)


@dataclass(slots=True)
class TrackSummary(Summary):
    id: str
    name: str
    artist: str
    date_released: str | None

    def media_type(self):
        return "track"

    def summarize(self) -> str:
        # This char breaks the menu for some reason
        return f"{clean(self.name)} by {clean(self.artist)}"

    def preview(self) -> str:
        return f"Released on:\n{self.date_released}\n\nID: {self.id}"

    @classmethod
    def from_item(cls, item: dict):
        id = str(item["id"])
        name = item.get("title") or item.get("name") or "Unknown"
        artist = (
            item.get("performer", {}).get("name")
            or item.get("artist")
            or item.get("artist", {}).get("name")
            or (
                item.get("publisher_metadata")
                and item["publisher_metadata"].get("artist")
            )
            or "Unknown"
        )
        if isinstance(artist, dict) and "name" in artist:
            artist = artist["name"]

        date_released = (
            item.get("release_date")
            or item.get("streamStartDate")
            or item.get("album", {}).get("release_date_original")
            or item.get("display_date")
            or item.get("date")
            or item.get("year")
            or "Unknown"
        )
        return cls(id, name.strip(), artist, date_released)  # type: ignore


@dataclass(slots=True)
class AlbumSummary(Summary):
    id: str
    name: str
    artist: str
    num_tracks: str
    date_released: str | None

    def media_type(self):
        return "album"

    def summarize(self) -> str:
        return f"{clean(self.name)} by {clean(self.artist)}"

    def preview(self) -> str:
        return f"Date released:\n{self.date_released}\n\n{self.num_tracks} Tracks\n\nID: {self.id}"

    @classmethod
    def from_item(cls, item: dict):
        id = str(item["id"])
        title = (item.get("title") or "").strip()
        version = (item.get("version") or "").strip()
        name = title + (" (" + version + ")" if version else "")
        artist = (
            item.get("performer", {}).get("name")
            or item.get("artist", {}).get("name")
            or item.get("artist")
            or (
                item.get("publisher_metadata")
                and item["publisher_metadata"].get("artist")
            )
            or "Unknown"
        )
        num_tracks = (
            item.get("tracks_count", 0)
            or item.get("numberOfTracks", 0)
            or len(
                item.get("tracks", []) or item.get("items", []),
            )
        )

        date_released = (
            item.get("release_date_original")
            or item.get("release_date")
            or item.get("releaseDate")
            or item.get("display_date")
            or item.get("date")
            or item.get("year")
            or "Unknown"
        )
        return cls(id, name, artist, str(num_tracks), date_released)


@dataclass(slots=True)
class LabelSummary(Summary):
    id: str
    name: str

    def media_type(self):
        return "label"

    def summarize(self) -> str:
        return str(self)

    def preview(self) -> str:
        return str(self)

    @classmethod
    def from_item(cls, item: dict):
        id = str(item["id"])
        name = item["name"]
        return cls(id, name)


@dataclass(slots=True)
class PlaylistSummary(Summary):
    id: str
    name: str
    creator: str
    num_tracks: int
    description: str

    def summarize(self) -> str:
        name = clean(self.name)
        creator = clean(self.creator)
        return f"{name} by {creator}"

    def preview(self) -> str:
        desc = clean(self.description, trunc=False)
        wrapped = "\n".join(
            textwrap.wrap(desc, os.get_terminal_size().columns - 4 or 70),
        )
        return f"{self.num_tracks} tracks\n\nDescription:\n{wrapped}\n\nID: {self.id}"

    def media_type(self):
        return "playlist"

    @classmethod
    def from_item(cls, item: dict):
        id = item.get("id") or item.get("uuid") or "Unknown"
        name = item.get("name") or item.get("title") or "Unknown"
        creator = (
            (item.get("publisher_metadata") and item["publisher_metadata"]["artist"])
            or item.get("owner", {}).get("name")
            or item.get("user", {}).get("username")
            or item.get("user", {}).get("name")
            or "Unknown"
        )
        num_tracks = (
            item.get("tracks_count")
            or item.get("nb_tracks")
            or item.get("numberOfTracks")
            or len(item.get("tracks", []))
            or -1
        )
        description = item.get("description") or "No description"
        return cls(id, name, creator, num_tracks, description)


@dataclass(slots=True)
class SearchResults:
    results: list[Summary]

    @classmethod
    def from_pages(cls, source: str, media_type: str, pages: list[dict]):
        if media_type == "track":
            summary_type = TrackSummary
        elif media_type == "album":
            summary_type = AlbumSummary
        elif media_type == "label":
            summary_type = LabelSummary
        elif media_type == "artist":
            summary_type = ArtistSummary
        elif media_type == "playlist":
            summary_type = PlaylistSummary
        else:
            raise Exception(f"invalid media type {media_type}")

        results = []
        for page in pages:
            if source == "soundcloud":
                items = page["collection"]
                for item in items:
                    results.append(summary_type.from_item(item))
            elif source == "qobuz":
                key = media_type + "s"
                for item in page[key]["items"]:
                    results.append(summary_type.from_item(item))
            elif source == "deezer":
                for item in page["data"]:
                    results.append(summary_type.from_item(item))
            elif source == "tidal":
                for item in page["items"]:
                    results.append(summary_type.from_item(item))
            else:
                raise NotImplementedError

        return cls(results)

    def summaries(self) -> list[str]:
        return [f"{i+1}. {r.summarize()}" for i, r in enumerate(self.results)]

    def get_choices(self, inds: tuple[int, ...] | int):
        if isinstance(inds, int):
            inds = (inds,)
        return [self.results[i] for i in inds]

    def preview(self, s: str) -> str:
        ind = re.match(r"^\d+", s)
        assert ind is not None
        i = int(ind.group(0))
        return self.results[i - 1].preview()

    def as_list(self, source: str) -> list[dict[str, str]]:
        return [
            {
                "source": source,
                "media_type": i.media_type(),
                "id": i.id,
                "desc": i.summarize(),
            }
            for i in self.results
        ]


def clean(s: str, trunc=True) -> str:
    s = s.replace("|", "").replace("\n", "")
    if trunc:
        max_chars = 50
        return s[:max_chars]
    return s
