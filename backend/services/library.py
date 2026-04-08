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

        # If no tracks cached, fetch from API
        if not tracks:
            source = album["source"]
            client = self.clients.get(source)
            if client and (hasattr(client, 'favorites') or getattr(client, 'logged_in', False)):
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
        """Fetch tracks from Tidal album endpoint."""
        try:
            resp = await client.get_metadata(source_album_id, "album")
        except Exception:
            logger.exception("Failed to fetch Tidal album %s", source_album_id)
            return []

        track_items = resp.get("tracks", resp.get("items", []))
        if isinstance(track_items, dict):
            track_items = track_items.get("items", [])

        for t in track_items:
            artists = t.get("artists", [])
            artist_name = ", ".join(a["name"] for a in artists) if artists else t.get("artist", {}).get("name", "Unknown")

            self.db.upsert_track(
                album_id=album_id,
                source_track_id=str(t["id"]),
                title=t.get("title", "Unknown"),
                artist=artist_name,
                track_number=t.get("trackNumber"),
                disc_number=t.get("volumeNumber", 1),
                duration_seconds=t.get("duration"),
                explicit=t.get("explicit", False),
                isrc=t.get("isrc"),
            )

        return self.db.get_tracks(album_id)

    async def refresh_library(self, source):
        client = self.clients.get(source)
        if client is None:
            raise ValueError(f"No client configured for {source}")

        if source == "qobuz" and hasattr(client, 'favorites'):
            # SDK client
            all_items = await self._fetch_qobuz_favorites_sdk(client)
        else:
            # Streamrip client (Tidal)
            if not client.logged_in:
                raise ValueError(f"Client {source} is not authenticated")
            raw_pages = await client.get_user_favorites("album", limit=None)
            all_items = self._extract_items_from_pages(source, raw_pages)

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

    async def _fetch_qobuz_favorites_sdk(self, client) -> list[dict]:
        """Fetch all favorite albums using the SDK client with pagination."""
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

    def _extract_items_from_pages(self, source: str, pages) -> list:
        """Extract individual album items from paginated API responses.

        Handles two formats:
        - Tidal: flat list of dicts with 'id' keys
        - Qobuz: list of page dicts containing {albums: {items: [...]}}
        """
        if not pages:
            return []

        # Flat list of items (Tidal) — no nested structure
        if isinstance(pages[0], dict) and "id" in pages[0] and "albums" not in pages[0]:
            return pages

        # Paginated response (Qobuz) — extract items from nested containers
        all_items = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            for key in ("albums", "tracks", "artists"):
                container = page.get(key, {})
                if isinstance(container, dict) and "items" in container:
                    all_items.extend(container["items"])
                    break
            else:
                if "id" in page:
                    all_items.append(page)
        return all_items

    async def search(self, source, query, limit=20):
        client = self.clients.get(source)
        if client is None:
            return []

        if source == "qobuz" and hasattr(client, 'catalog'):
            # SDK client
            result = await client.catalog.search_albums(query, limit=limit)
            albums = [self._sdk_album_to_dict_from_raw(item) for item in result.items]
        else:
            # Streamrip client
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
