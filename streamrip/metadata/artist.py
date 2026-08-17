from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .search_results import AlbumSummary

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class ArtistMetadata:
    name: str
    ids: list[str]
    # One per id, in the same order. The artist response already carries the
    # full album objects, so describing a discography costs no extra requests
    # -- and AlbumSummary already knows how to read one from any source.
    albums: list[AlbumSummary] = field(default_factory=list)

    def album_ids(self):
        return self.ids

    @classmethod
    def from_resp(cls, resp: dict, source: str) -> ArtistMetadata:
        logger.debug(resp)
        if source == "qobuz":
            items = resp["albums"]["items"]
        elif source in ("tidal", "deezer"):
            items = resp["albums"]
        else:
            raise NotImplementedError

        return cls(
            resp["name"],
            [str(a["id"]) for a in items],
            [AlbumSummary.from_item(a) for a in items],
        )
