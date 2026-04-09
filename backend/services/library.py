"""Library service — fetches and caches streaming library state."""

import logging

from ..models.database import AppDatabase
from .event_bus import EventBus

logger = logging.getLogger("streamrip")


class LibraryService:
    def __init__(self, db: AppDatabase, event_bus: EventBus, clients: dict):
        self.db = db
        self.event_bus = event_bus
        self.clients = clients

    async def get_albums(self, source, page=1, page_size=50, sort_by="added_to_library_at", sort_dir="DESC", status=None, search=None):
        offset = (page - 1) * page_size
        albums = self.db.get_albums(source=source, status=status, search=search, sort_by=sort_by, sort_dir=sort_dir, limit=page_size, offset=offset)
        total = self.db.count_albums(source, status=status, search=search)
        return {"albums": albums, "total": total, "page": page, "page_size": page_size}

    async def get_album_detail(self, album_id):
        album = self.db.get_album(album_id)
        if album is None:
            return None
        tracks = self.db.get_tracks(album_id)

        # If no tracks cached, fetch from API
        if not tracks:
            source = album["source"]
            client = self.clients.get(source)
            if client is not None and hasattr(client, 'catalog'):
                try:
                    tracks = await self._fetch_and_cache_tracks(
                        client, source, album["source_album_id"], album_id
                    )
                except Exception:
                    logger.exception("Failed to fetch tracks for album %s", album_id)

        return {**album, "tracks": tracks}

    async def _fetch_and_cache_tracks(self, client, source, source_album_id, album_id):
        """Fetch track list from API and cache in DB."""
        if source == "qobuz":
            if hasattr(client, 'catalog'):
                return await self._fetch_qobuz_tracks_sdk(client, source_album_id, album_id)
            return await self._fetch_qobuz_tracks(client, source_album_id, album_id)
        elif source == "tidal":
            return await self._fetch_tidal_tracks(client, source_album_id, album_id)
        return []

    async def _fetch_qobuz_tracks_sdk(self, client, source_album_id, album_id):
        """Fetch tracks from Qobuz using SDK client."""
        try:
            album, tracks = await client.catalog.get_album_with_tracks(source_album_id)
        except Exception:
            logger.exception("Failed to fetch Qobuz album %s via SDK", source_album_id)
            return []

        for t in tracks:
            self.db.upsert_track(
                album_id=album_id,
                source_track_id=str(t.id),
                title=t.title,
                artist=t.performer.name,
                track_number=t.track_number,
                disc_number=t.disc_number,
                duration_seconds=t.duration,
                explicit=t.explicit,
                isrc=t.isrc,
            )

        return self.db.get_tracks(album_id)

    async def _fetch_qobuz_tracks(self, client, source_album_id, album_id):
        """Fetch tracks from Qobuz album/get endpoint (streamrip client)."""
        try:
            resp = await client.get_album(source_album_id)
        except Exception:
            logger.exception("Failed to fetch Qobuz album %s", source_album_id)
            return []

        track_items = resp.get("tracks", {}).get("items", [])
        for t in track_items:
            artist = t.get("performer", {})
            artist_name = artist.get("name", "Unknown") if isinstance(artist, dict) else (str(artist) if artist else "Unknown")

            self.db.upsert_track(
                album_id=album_id,
                source_track_id=str(t["id"]),
                title=t.get("title", "Unknown"),
                artist=artist_name,
                track_number=t.get("track_number"),
                disc_number=t.get("media_number", 1),
                duration_seconds=t.get("duration"),
                explicit=t.get("parental_warning", False),
                isrc=t.get("isrc"),
            )

        return self.db.get_tracks(album_id)

    async def _fetch_tidal_tracks(self, client, source_album_id, album_id):
        """Fetch tracks from Tidal using the SDK catalog API."""
        try:
            _, tracks = await client.catalog.get_album_with_tracks(source_album_id)
        except Exception:
            logger.exception("Failed to fetch Tidal album %s via SDK", source_album_id)
            return []

        for t in tracks:
            # Prefer the primary artist's name, fall back to joined artists
            # list for compilations / collaborations.
            artist_name = t.artist.name if t.artist.name else (
                ", ".join(a.name for a in t.artists) if t.artists else "Unknown"
            )
            self.db.upsert_track(
                album_id=album_id,
                source_track_id=str(t.id),
                title=t.title,
                artist=artist_name,
                track_number=t.track_number,
                disc_number=t.volume_number,
                duration_seconds=t.duration,
                explicit=t.explicit,
                isrc=t.isrc,
            )

        return self.db.get_tracks(album_id)

    async def refresh_library(self, source):
        client = self.clients.get(source)
        if client is None:
            raise ValueError(f"No client configured for {source}")

        all_items = await self.fetch_all_favorites(source, client)

        from datetime import datetime
        existing_ids = {a["source_album_id"] for a in self.db.get_albums(source, limit=100000)}
        now = datetime.now().isoformat()
        new_count = 0
        for item in all_items:
            album_resp = self._extract_album_data(source, item)
            if album_resp is None:
                continue
            is_new = album_resp["source_album_id"] not in existing_ids
            if is_new:
                new_count += 1
                album_resp["added_to_library_at"] = now
            self.db.upsert_album(**album_resp)

        await self.event_bus.publish("library_updated", {"source": source, "new_count": new_count, "total": len(all_items)})
        return {"total": len(all_items), "new": new_count}

    async def fetch_all_favorites(self, source: str, client) -> list[dict]:
        """Fetch every favorite album for *source* as a list of raw dicts.

        Normalizes across the Qobuz and Tidal SDK clients so callers
        (refresh_library, sync diff) share one code path. Each returned
        dict is in whatever shape ``_extract_{source}_album`` expects.
        """
        if source == "qobuz":
            return await self._fetch_qobuz_favorites_sdk(client)
        if source == "tidal":
            return await client.favorites.all_albums()
        raise ValueError(f"Unsupported source: {source}")

    async def _fetch_qobuz_favorites_sdk(self, client) -> list[dict]:
        """Fetch all favorite albums using the Qobuz SDK client with pagination."""
        all_items = []
        offset = 0
        while True:
            result = await client.favorites.get_albums(limit=500, offset=offset)
            for album in result.items:
                # Convert SDK Album to dict for _extract_album_data
                all_items.append(self._sdk_album_to_dict(album))
            if offset + result.limit >= result.total:
                break
            offset += result.limit
        return all_items

    def _sdk_album_to_dict_from_raw(self, item: dict) -> dict:
        """Convert a raw dict from SDK PaginatedResult to extract format.

        Search results come as raw dicts (not Album dataclasses).
        """
        artist = item.get("artist", {})
        image = item.get("image", {})
        bit_depth = item.get("maximum_bit_depth", 16)
        sample_rate = item.get("maximum_sampling_rate", 44.1)
        return {
            "id": str(item["id"]),
            "title": item.get("title", "Unknown"),
            "artist": artist if isinstance(artist, dict) else {"name": str(artist)},
            "artists": item.get("artists", []),
            "release_date_original": item.get("release_date_original"),
            "label": item.get("label"),
            "genre": item.get("genre"),
            "tracks_count": item.get("tracks_count"),
            "duration": item.get("duration"),
            "image": image,
            "maximum_bit_depth": bit_depth,
            "maximum_sampling_rate": sample_rate,
        }

    def _sdk_album_to_dict(self, album) -> dict:
        """Convert SDK Album dataclass to a dict matching the extract format."""
        return {
            "id": album.id,
            "title": album.title,
            "artist": {"name": album.artist.name},
            "artists": [{"name": a.name} for a in album.artists],
            "release_date_original": album.release_date_original,
            "label": {"name": album.label.name} if album.label else None,
            "genre": {"name": album.genre.name} if album.genre else None,
            "tracks_count": album.tracks_count,
            "duration": album.duration,
            "image": {
                "large": album.image.large,
                "small": album.image.small,
                "thumbnail": album.image.thumbnail,
            },
            "maximum_bit_depth": album.maximum_bit_depth,
            "maximum_sampling_rate": album.maximum_sampling_rate,
        }

    async def list_playlists(self, source: str, *, limit: int = 500) -> list[dict]:
        """List the current user's playlists from the streaming service.

        Currently only Qobuz is supported (its SDK exposes a full
        ``PlaylistsAPI``).  Tidal's SDK has the ``Playlist`` type but
        no read methods yet — returns an empty list for tidal.
        """
        client = self.clients.get(source)
        if client is None:
            return []
        if source != "qobuz" or not hasattr(client, "playlists"):
            return []

        result = await client.playlists.list(limit=limit)
        playlists = []
        for item in result.items:
            playlists.append({
                "id": item.get("id"),
                "name": item.get("name", "Untitled"),
                "description": item.get("description") or "",
                "tracks_count": item.get("tracks_count", 0),
                "duration": item.get("duration", 0),
                "is_public": item.get("is_public", False),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "owner": (item.get("owner") or {}).get("name", ""),
            })
        return playlists

    async def get_playlist(
        self, source: str, playlist_id: int | str, *, limit: int = 500
    ) -> dict | None:
        """Fetch a single playlist with its tracks."""
        client = self.clients.get(source)
        if client is None or source != "qobuz" or not hasattr(client, "playlists"):
            return None

        playlist = await client.playlists.get(
            playlist_id, extra="tracks", limit=limit
        )
        # Tracks are raw dicts on Playlist.tracks (one per item)
        tracks = []
        for raw in playlist.tracks:
            track_obj = raw.get("track", raw) if isinstance(raw, dict) else raw
            if not isinstance(track_obj, dict):
                continue
            artist = track_obj.get("performer") or track_obj.get("composer") or {}
            album = track_obj.get("album", {})
            tracks.append({
                "id": track_obj.get("id"),
                "title": track_obj.get("title"),
                "artist": (
                    artist.get("name")
                    if isinstance(artist, dict)
                    else str(artist)
                ),
                "duration_seconds": track_obj.get("duration"),
                "album_title": album.get("title") if isinstance(album, dict) else None,
                "album_id": str(album.get("id")) if isinstance(album, dict) and album.get("id") else None,
                "track_number": track_obj.get("track_number"),
            })

        return {
            "id": playlist.id,
            "name": playlist.name,
            "description": playlist.description,
            "tracks_count": playlist.tracks_count,
            "duration": playlist.duration,
            "is_public": playlist.is_public,
            "owner": getattr(playlist.owner, "name", ""),
            "tracks": tracks,
        }

    async def search(self, source, query, *, limit: int = 60, offset: int = 0):
        """Search the streaming service's catalog with pagination.

        Returns a paginated envelope ``{albums, total, limit, offset}``
        matching the shape of ``get_albums``.  ``total`` reflects the
        upstream service's reported total when available so the UI can
        render Load More / page counts.
        """
        empty = {"albums": [], "total": 0, "limit": limit, "offset": offset}
        client = self.clients.get(source)
        if client is None or not hasattr(client, "catalog"):
            return empty

        # Both SDK clients expose a `catalog.search_albums(query, limit, offset)`.
        # Tidal returns dict items in `result.items`; Qobuz returns the raw
        # dict shape under different envelope keys.  Normalize via the
        # per-source extractor below.
        result = await client.catalog.search_albums(query, limit=limit, offset=offset)
        if source == "qobuz":
            raw_items = [self._sdk_album_to_dict_from_raw(item) for item in result.items]
        else:
            raw_items = list(result.items)

        enriched = []
        for album in raw_items:
            parsed = self._extract_album_data(source, album)
            if parsed is None:
                continue
            existing = self.db.get_album_by_source_id(source, parsed["source_album_id"])
            enriched.append({
                **parsed,
                "in_library": existing is not None,
                "download_status": existing["download_status"] if existing else "not_downloaded",
                "id": existing["id"] if existing else 0,
            })

        return {
            "albums": enriched,
            "total": getattr(result, "total", len(enriched)),
            "limit": getattr(result, "limit", limit),
            "offset": getattr(result, "offset", offset),
        }

    def _extract_album_data(self, source, item):
        try:
            if source == "qobuz":
                return self._extract_qobuz_album(item)
            elif source == "tidal":
                return self._extract_tidal_album(item)
            return None
        except Exception:
            logger.exception("Failed to extract album data")
            return None

    def _extract_qobuz_album(self, item):
        album = item.get("album", item) if "album" in item else item
        artist = album.get("artist", {})
        image = album.get("image", {})
        bit_depth = album.get("maximum_bit_depth", 16)
        sample_rate = album.get("maximum_sampling_rate", 44.1)
        quality = f"FLAC {bit_depth}/{sample_rate}kHz" if bit_depth else None
        return {
            "source": "qobuz", "source_album_id": str(album["id"]),
            "title": album.get("title", "Unknown"),
            "artist": artist.get("name", "Unknown") if isinstance(artist, dict) else str(artist),
            "release_date": album.get("release_date_original"),
            "label": album.get("label", {}).get("name") if isinstance(album.get("label"), dict) else None,
            "genre": album.get("genre", {}).get("name") if isinstance(album.get("genre"), dict) else None,
            "track_count": album.get("tracks_count"),
            "duration_seconds": album.get("duration"),
            "cover_url": image.get("large") or image.get("small"),
            "quality": quality,
        }

    def _extract_tidal_album(self, item):
        album = item.get("item", item) if "item" in item else item
        artists = album.get("artists", [])
        artist_name = ", ".join(a["name"] for a in artists) if artists else album.get("artist", {}).get("name", "Unknown")
        cover = album.get("cover", "")
        cover_url = f"https://resources.tidal.com/images/{cover.replace('-', '/')}/640x640.jpg" if cover else None
        return {
            "source": "tidal", "source_album_id": str(album["id"]),
            "title": album.get("title", "Unknown"), "artist": artist_name,
            "release_date": album.get("releaseDate"),
            "track_count": album.get("numberOfTracks"),
            "duration_seconds": album.get("duration"),
            "cover_url": cover_url, "quality": album.get("audioQuality"),
        }
