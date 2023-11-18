from dataclasses import dataclass

from .album_metadata import AlbumMetadata
from .track_metadata import TrackMetadata
from .util import typed

NON_STREAMABLE = "_non_streamable"
ORIGINAL_DOWNLOAD = "_original_download"
NOT_RESOLVED = "_not_resolved"


def get_soundcloud_id(resp: dict) -> str:
    item_id = resp["id"]
    if "media" not in resp:
        return f"{item_id}|{NOT_RESOLVED}"

    if not resp["streamable"] or resp["policy"] == "BLOCK":
        return f"{item_id}|{NON_STREAMABLE}"

    if resp["downloadable"] and resp["has_downloads_left"]:
        return f"{item_id}|{ORIGINAL_DOWNLOAD}"

    url = None
    for tc in resp["media"]["transcodings"]:
        fmt = tc["format"]
        if fmt["protocol"] == "hls" and fmt["mime_type"] == "audio/mpeg":
            url = tc["url"]
            break

    assert url is not None
    return f"{item_id}|{url}"


def parse_soundcloud_id(item_id: str) -> tuple[str, str]:
    info = item_id.split("|")
    assert len(info) == 2
    return tuple(info)


@dataclass(slots=True)
class PlaylistMetadata:
    name: str
    tracks: list[TrackMetadata]

    @classmethod
    def from_qobuz(cls, resp: dict):
        name = typed(resp["title"], str)
        tracks = [
            TrackMetadata.from_qobuz(AlbumMetadata.from_qobuz(track["album"]), track)
            for track in resp["tracks"]["items"]
        ]
        return cls(name, tracks)

    @classmethod
    def from_soundcloud(cls, resp: dict):
        """Convert a (modified) soundcloud API response to PlaylistMetadata.

        Args:
            resp (dict): The response, except there should not be any partially resolved items
            in the playlist.

            e.g. If soundcloud only returns the full metadata of 5 of them, the rest of the
            elements in resp['tracks'] should be replaced with their full metadata.

        Returns:
            PlaylistMetadata object.
        """
        name = typed(resp["title"], str)
        tracks = [
            TrackMetadata.from_soundcloud(AlbumMetadata.from_soundcloud(track), track)
            for track in resp["tracks"]
        ]
        return cls(name, tracks)

    def ids(self):
        return [track.info.id for track in self.tracks]

    @classmethod
    def from_resp(cls, resp: dict, source: str):
        if source == "qobuz":
            return cls.from_qobuz(resp)
        elif source == "soundcloud":
            return cls.from_soundcloud(resp)
        else:
            raise NotImplementedError(source)
