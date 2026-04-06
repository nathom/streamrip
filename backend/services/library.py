"""Library service — fetches and caches streaming library state."""

import logging
from typing import Any

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
        return {**album, "tracks": tracks}

    async def refresh_library(self, source):
        client = self.clients.get(source)
        if client is None:
            raise ValueError(f"No client configured for {source}")
        if not client.logged_in:
            raise ValueError(f"Client {source} is not authenticated")

        albums_data = await client.get_user_favorites("album", limit=None)
        new_count = 0
        for item in albums_data:
            album_resp = self._extract_album_data(source, item)
            if album_resp is None:
                continue
            existing = self.db.get_album_by_source_id(source, album_resp["source_album_id"])
            if existing is None:
                new_count += 1
            self.db.upsert_album(**album_resp)

        await self.event_bus.publish("library_updated", {"source": source, "new_count": new_count, "total": len(albums_data)})
        return {"total": len(albums_data), "new": new_count}

    async def search(self, source, query, limit=20):
        client = self.clients.get(source)
        if client is None:
            raise ValueError(f"No client configured for {source}")

        raw_results = await client.search("album", query, limit=limit)
        if not raw_results:
            return []

        albums = []
        for page in raw_results:
            if isinstance(page, dict) and "albums" in page:
                albums.extend(page["albums"].get("items", []))
            elif isinstance(page, dict) and "items" in page:
                albums.extend(page["items"])

        enriched = []
        for album in albums:
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
        return enriched

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
