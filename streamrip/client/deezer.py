import asyncio
import binascii
import hashlib
import logging
import re

import deezer
import requests
from deezer.errors import DataException, GWAPIError
from Cryptodome.Cipher import AES

from ..config import Config
from ..exceptions import (
    AuthenticationError,
    MissingCredentialsError,
    NonStreamableError,
)
from .client import Client
from .downloadable import DeezerDownloadable

logger = logging.getLogger("streamrip")
logging.captureWarnings(True)


class DeezerClient(Client):
    """Client to handle deezer API. Does not do rate limiting.

    Attributes:
        global_config: Entire config object
        client: client from deezer py used for API requests
        logged_in: True if logged in
        config: deezer local config
        session: aiohttp.ClientSession, used only for track downloads not API requests

    """

    source = "deezer"
    max_quality = 2
    max_favorites = 10_000

    # quality index → (gw format id, API format string)
    _QUALITY_MAP: list[tuple[int, str]] = [
        (9, "MP3_128"),  # quality 0
        (3, "MP3_320"),  # quality 1
        (1, "FLAC"),     # quality 2
    ]

    def __init__(self, config: Config):
        """Initialize the DeezerClient.

        Args:
            config (Config): The application configuration object.
        """
        self.global_config = config
        self.client = deezer.Deezer()
        self.logged_in = False
        self._login_lock = asyncio.Lock()
        self.config = config.session.deezer
        self.logged_in_user_id: int | None = None
        self._album_cache: dict[str, dict] = {}
        self._gw_track_cache: dict[str, dict] = {}

        # Increase the deezer-py requests session pool well above max_connections.
        # Each concurrent download spawns several API calls (metadata, track token,
        # GW info…) via asyncio.to_thread(), so the actual number of simultaneous
        # requests easily exceeds max_connections. pool_maxsize is just a ceiling —
        # no memory is pre-allocated — so a generous value avoids the urllib3
        # "Connection pool is full" warning without any real cost.
        max_conn = config.session.downloads.max_connections
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=max_conn,
            pool_maxsize=max(max_conn * 4, 32),
            max_retries=0,
        )
        self.client.session.mount("https://", adapter)
        self.client.session.mount("http://", adapter)

    async def login(self):
        """Log in via ARL token. Sets up the aiohttp session used for track downloads.

        Raises:
            MissingCredentialsError: If the ARL is missing from the config.
            AuthenticationError: If login fails.
        """
        # self.session (aiohttp) is used only for track byte-stream downloads;
        # API calls go through self.client.session (requests).
        self.session = await self.get_session(
            verify_ssl=self.global_config.session.downloads.verify_ssl
        )
        arl = self.config.arl
        if not arl:
            raise MissingCredentialsError
        success = self.client.login_via_arl(arl)
        if not success:
            raise AuthenticationError
        self.logged_in_user_id = self.client.gw.get_user_data()["USER"]["USER_ID"]
        self.logged_in = True

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        """Fetch metadata for a given item, dispatching by media type.

        Args:
            item_id (str): The ID of the item to fetch.
            media_type (str): One of "track", "album", "playlist", or "artist".

        Returns:
            dict: The metadata of the requested item.

        Raises:
            Exception: If the media type is not supported.
        """
        # TODO: open asyncio PR to deezer py and integrate
        handlers = {
            "track": self.get_track,
            "album": self.get_album,
            "playlist": self.get_playlist,
            "artist": self.get_artist,
        }
        handler = handlers.get(media_type)
        if handler is None:
            raise Exception(f"Media type {media_type} not available on deezer")
        return await handler(item_id)

    async def get_track(self, item_id: str) -> dict:
        """Fetch metadata for a track, including its full album info.

        Also fetches GW track info concurrently to enrich the REST response with
        SNG_CONTRIBUTORS (composer/author fields absent from the public REST API).

        Args:
            item_id (str): The Deezer track ID.

        Returns:
            dict: The track metadata dict with a nested "album" key containing
                  the album metadata and its track list. May include "composer"
                  and "author" keys when SNG_CONTRIBUTORS data is available.

        Raises:
            NonStreamableError: If the track cannot be fetched from the API.
        """
        try:
            item = await asyncio.to_thread(self.client.api.get_track, item_id)
        except Exception as e:
            raise NonStreamableError(e)

        album_id = item["album"]["id"]
        try:
            # Fetch album and GW track info concurrently.
            # GW track info provides SNG_CONTRIBUTORS (composer/author) which
            # is not available in the public REST API response.
            album_metadata, gw_info = await asyncio.gather(
                self.get_album(str(album_id)),
                asyncio.to_thread(self.client.gw.get_track, item_id),
            )
            self._gw_track_cache[item_id] = gw_info
        except Exception as e:
            logger.error("Error fetching album of track %s: %s", item_id, e)
            return item

        item["album"] = album_metadata

        contributors = gw_info.get("SNG_CONTRIBUTORS", {})
        if "composer" in contributors:
            item["composer"] = contributors["composer"]
        if "author" in contributors:
            item["author"] = contributors["author"]

        gain = gw_info.get("GAIN")
        if gain is not None:
            item["gain"] = gain

        return item

    async def get_album(self, item_id: str) -> dict:
        """Fetch metadata for an album, including its full track list.

        Results are cached in-process: subsequent calls with the same ID return
        immediately without hitting the API.

        Args:
            item_id (str): The Deezer album ID.

        Returns:
            dict: The album metadata dict with "tracks" and "track_total" keys added.

        Raises:
            DataException: If the album is not found and no redirect can be resolved.
        """
        if item_id in self._album_cache:
            logger.info("Deezer album cache hit for album ID: %s", item_id)
            return self._album_cache[item_id]
        try:
            album_metadata, album_tracks = await asyncio.gather(
                asyncio.to_thread(self.client.api.get_album, item_id),
                asyncio.to_thread(self.client.api.get_album_tracks, item_id),
            )
        except DataException:
            new_id = await self._resolve_redirect("album", item_id)
            if new_id:
                metadata = await self.get_album(new_id)
                self._album_cache[item_id] = metadata
                return metadata
            raise

        album_metadata["tracks"] = album_tracks["data"]
        album_metadata["track_total"] = len(album_tracks["data"])
        self._album_cache[item_id] = album_metadata
        return album_metadata

    async def _resolve_redirect(self, media_type: str, item_id: str) -> str | None:
        """Follow HTTP redirects to find the canonical ID for a moved/aliased item.

        Args:
            media_type: "album", "playlist", or "artist".
            item_id: The original Deezer item ID.

        Returns:
            The new ID if a redirect occurred, otherwise None.
        """
        url = f"https://www.deezer.com/{media_type}/{item_id}"

        try:
            async with self.session.head(url, allow_redirects=True) as response:
                final_url = str(response.url)
        except Exception as e:
            logger.warning("Failed to resolve redirect for %s: %s", item_id, e)
            return None

        if final_url == url:
            return None

        match = re.search(rf"/{media_type}/(\d+)", final_url)
        if match and (new_id := match.group(1)) != item_id:
            logger.debug("Resolved redirect for %s %s -> %s", media_type, item_id, new_id)
            return new_id

        return None

    async def get_playlist(self, item_id: str) -> dict:
        """Fetch metadata for a playlist.

        Args:
            item_id (str): The playlist ID, or "favorites:{user_id}" to fetch
                           a user's loved tracks as a playlist.

        Returns:
            dict: A dict with "title", "tracks" (list of {"id": ...} dicts),
                  and "track_total" keys.
        """
        if item_id.startswith("favorites:"):
            user_id = item_id[len("favorites:"):]
            return await self.get_user_favorites(user_id)

        try:
            pl_metadata, pl_tracks = await asyncio.gather(
                asyncio.to_thread(self.client.gw.get_playlist, item_id),
                asyncio.to_thread(self.client.gw.get_playlist_tracks, item_id),
            )
        except GWAPIError:
            new_id = await self._resolve_redirect("playlist", item_id)
            if new_id:
                return await self.get_playlist(new_id)
            raise

        # Normalize GW response to match expected structure
        tracks = pl_tracks if isinstance(pl_tracks, list) else pl_tracks["data"]
        return {
            "title": pl_metadata["DATA"]["TITLE"],
            "tracks": [{"id": t["SNG_ID"]} for t in tracks],
            "track_total": len(tracks),
        }

    async def get_user_favorites(self, user_id: str) -> dict:
        """Fetch the loved tracks for a Deezer user profile.

        Args:
            user_id (str): The Deezer user ID (numeric string).

        Returns:
            dict: A playlist-shaped dict with "title", "tracks", and "track_total".
        """
        # deezer-py silently drops the limit arg in get_user_tracks() when it detects
        # the own profile and re-routes to get_my_favorite_tracks(). Call the latter
        # directly so the limit is always honoured.
        uid = int(user_id)
        if uid == self.logged_in_user_id:
            tracks = await asyncio.to_thread(
                self.client.gw.get_my_favorite_tracks, self.max_favorites
            )
        else:
            tracks = await asyncio.to_thread(
                self.client.gw.get_user_tracks, uid, self.max_favorites
            )
        return {
            "title": "Loved Tracks",
            "tracks": tracks,
            "track_total": len(tracks),
        }

    async def get_artist(self, item_id: str) -> dict:
        """Fetch metadata for an artist, including their album list.

        Args:
            item_id (str): The Deezer artist ID.

        Returns:
            dict: The artist metadata dict with an "albums" key containing
                  the list of album dicts.

        Raises:
            DataException: If the artist is not found and no redirect can be resolved.
        """
        try:
            artist, albums = await asyncio.gather(
                asyncio.to_thread(self.client.api.get_artist, item_id),
                asyncio.to_thread(self.client.api.get_artist_albums, item_id),
            )
        except DataException:
            new_id = await self._resolve_redirect("artist", item_id)
            if new_id:
                return await self.get_artist(new_id)
            raise

        artist["albums"] = albums["data"]
        return artist

    async def search(self, media_type: str, query: str, limit: int = 200) -> list[dict]:
        """Search for items on Deezer.

        Args:
            media_type (str): The type of media to search for (e.g. "track", "album",
                              "artist"). Pass "featured" to fetch editorial content.
            query (str): The search query. When media_type is "featured", this should
                         match an editorial category name (e.g. "releases").
            limit (int): Maximum number of results to return. Defaults to 200.

        Returns:
            list[dict]: A list containing the raw API response dict(s).
        """
        if media_type == "featured":
            try:
                if query:
                    search_function = getattr(self.client.api, f"get_editorial_{query}")
                else:
                    search_function = self.client.api.get_editorial_releases
            except AttributeError:
                raise Exception(f'Invalid editorical selection "{query}"')
        else:
            try:
                search_function = getattr(self.client.api, f"search_{media_type}")
            except AttributeError:
                raise Exception(f"Invalid media type {media_type}")

        response = search_function(query, limit=limit)  # type: ignore
        if response["total"] > 0:
            return [response]
        return []

    async def get_downloadable(
        self,
        item_id: str | None,
        quality: int = 2,
        is_retry: bool = False,
    ) -> DeezerDownloadable:
        """Resolve the download URL for a track and return a DeezerDownloadable.

        Tries qualities from the requested level down to 0 (MP3_128), falling back
        automatically on WrongLicense. If the token API fails entirely, falls back
        to the legacy AES-encrypted CDN URL.

        Args:
            item_id (str | None): The Deezer track ID. None raises NonStreamableError.
            quality (int): Desired quality level (0=MP3_128, 1=MP3_320, 2=FLAC).
                           Clamped to [0, 2].
            is_retry (bool): Internal flag — True when called recursively to try a
                             geoblocking fallback ID.

        Returns:
            DeezerDownloadable: Ready-to-use downloadable object for the track.

        Raises:
            NonStreamableError: If no download URL can be obtained for the track.
        """
        if item_id is None:
            raise NonStreamableError(
                "No item id provided. This can happen when searching for fallback songs.",
            )

        quality = max(0, min(quality, 2))

        # Use GW info cached by get_track (called during metadata resolution) to
        # avoid a redundant API call. Falls back to a live request for tracks
        # downloaded directly by ID without a prior get_track call.
        track_info = self._gw_track_cache.pop(item_id, None)
        if track_info is None:
            try:
                track_info = self.client.gw.get_track(item_id)
            except Exception as e:
                raise NonStreamableError(f"Could not fetch GW track info for {item_id}: {e}")
        fallback_id = track_info.get("FALLBACK", {}).get("SNG_ID")

        dl_info: dict = {
            "quality": quality,
            "id": item_id,
            "quality_to_size": [
                int(track_info.get(f"FILESIZE_{fmt}", 0)) for _, fmt in self._QUALITY_MAP
            ],
        }

        token = track_info.get("TRACK_TOKEN")
        if token is None:
            raise NonStreamableError(f"Deezer track {item_id} has no TRACK_TOKEN (possibly unavailable in your region or account)")
        url = None
        final_quality = quality

        # Try from the requested quality down to 0 (MP3_128), stopping at first success.
        for q_level in range(quality, -1, -1):
            _, format_str = self._QUALITY_MAP[q_level]
            try:
                logger.debug("Attempting quality %d (%s)", q_level, format_str)
                url = self.client.get_track_url(token, format_str)
                if url:
                    final_quality = q_level
                    break
            except deezer.WrongLicense:
                if not self.config.lower_quality_if_not_available:
                    raise NonStreamableError(
                        f"Quality {q_level} is not available with your subscription "
                        "and fallback is disabled."
                    )
                logger.warning("Quality %d not available for this account, trying lower", q_level)
                continue
            except deezer.WrongGeolocation:
                if not is_retry and fallback_id:
                    logger.debug("Geoblocked; retrying with fallback ID %s", fallback_id)
                    return await self.get_downloadable(fallback_id, quality, is_retry=True)
                raise NonStreamableError("Track geoblocked and no fallback available.")

        # Fall back to the legacy AES-encrypted CDN URL when the token API fails.
        if url is None:
            md5 = track_info.get("MD5_ORIGIN")
            media_version = track_info.get("MEDIA_VERSION")
            if not md5 or not media_version:
                raise NonStreamableError(f"Deezer track {item_id}: token API failed and CDN fallback requires MD5_ORIGIN/MEDIA_VERSION which are missing")
            url = self._get_encrypted_file_url(item_id, md5, media_version)

        if not url:
            raise NonStreamableError("Could not retrieve a download URL for track %s" % item_id)

        dl_info["quality"] = final_quality
        dl_info["url"] = url
        logger.debug("dz track info: %s", track_info)
        return DeezerDownloadable(self.session, dl_info)

    def _get_encrypted_file_url(
        self,
        meta_id: str,
        track_hash: str,
        media_version: str,
    ) -> str:
        """Build the legacy AES-ECB CDN URL used when the token API returns nothing.

        Args:
            meta_id (str): The track metadata ID.
            track_hash (str): The MD5 hash of the track origin URL.
            media_version (str): The media version string from the GW track info.

        Returns:
            str: A signed CDN URL pointing to the encrypted audio file.
        """
        logger.debug("Falling back to encrypted file URL for track %s", meta_id)
        format_number = 1

        url_bytes = b"\xa4".join(
            (
                track_hash.encode(),
                str(format_number).encode(),
                str(meta_id).encode(),
                str(media_version).encode(),
            ),
        )
        url_hash = hashlib.md5(url_bytes).hexdigest()
        info_bytes = bytearray(url_hash.encode())
        info_bytes.extend(b"\xa4")
        info_bytes.extend(url_bytes)
        info_bytes.extend(b"\xa4")
        # Pad the bytes so that len(info_bytes) % 16 == 0
        padding_len = 16 - (len(info_bytes) % 16)
        info_bytes.extend(b"." * padding_len)

        path = binascii.hexlify(
            AES.new(b"jo6aey6haid2Teih", AES.MODE_ECB).encrypt(info_bytes),
        ).decode("utf-8")
        url = f"https://e-cdns-proxy-{track_hash[0]}.dzcdn.net/mobile/1/{path}"
        logger.debug("Encrypted file path %s", url)
        return url
