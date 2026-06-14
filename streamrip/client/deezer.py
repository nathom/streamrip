import asyncio
import binascii
import hashlib
import logging
import re

import deezer
import requests
from deezer.errors import DataException
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

    def __init__(self, config: Config):
        """
        Initializes the DeezerClient.

        Args:
            config (Config): The configuration object.
        """
        self.global_config = config
        self.client = deezer.Deezer()
        self.logged_in = False
        self.config = config.session.deezer
        self.logged_in_user_id: int | None = None

        # Size the deezer-py requests session pool to match max_connections so
        # urllib3 never needs to discard connections and logs no warnings.
        max_conn = config.session.downloads.max_connections
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=max_conn,
            pool_maxsize=max_conn,
            max_retries=0,
        )
        self.client.session.mount("https://", adapter)
        self.client.session.mount("http://", adapter)

    async def login(self):
        """
        Logs in to Deezer using the ARL (Authentication Request Login) token.

        Raises:
            MissingCredentialsError: If the ARL is missing from the config.
            AuthenticationError: If login fails.
        """
        # Used for track downloads
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
        """
        Fetches metadata for a given item.

        Args:
            item_id (str): The ID of the item.
            media_type (str): The type of media (track, album, playlist, artist).

        Returns:
            dict: The metadata of the item.

        Raises:
            Exception: If the media type is invalid.
        """
        # TODO: open asyncio PR to deezer py and integrate
        if media_type == "track":
            return await self.get_track(item_id)
        elif media_type == "album":
            return await self.get_album(item_id)
        elif media_type == "playlist":
            return await self.get_playlist(item_id)
        elif media_type == "artist":
            return await self.get_artist(item_id)
        else:
            raise Exception(f"Media type {media_type} not available on deezer")

    async def get_track(self, item_id: str) -> dict:
        """
        Fetches metadata for a track.

        Args:
            item_id (str): The track ID.

        Returns:
            dict: The track metadata.

        Raises:
            NonStreamableError: If the track is not streamable.
        """
        try:
            item = await asyncio.to_thread(self.client.api.get_track, item_id)
        except Exception as e:
            raise NonStreamableError(e)

        album_id = item["album"]["id"]
        try:
            # reuse get_album to handle redirects
            album_metadata = await self.get_album(str(album_id))
        except Exception as e:
            logger.error(f"Error fetching album of track {item_id}: {e}")
            return item

        item["album"] = album_metadata

        return item

    async def get_album(self, item_id: str) -> dict:
        """
        Fetches metadata for an album.

        Args:
            item_id (str): The album ID.

        Returns:
            dict: The album metadata.
        """
        try:
            album_metadata, album_tracks = await asyncio.gather(
                asyncio.to_thread(self.client.api.get_album, item_id),
                asyncio.to_thread(self.client.api.get_album_tracks, item_id),
            )
        except DataException:
            new_id = await self._resolve_redirect("album", item_id)
            if new_id:
                return await self.get_album(new_id)
            raise

        album_metadata["tracks"] = album_tracks["data"]
        album_metadata["track_total"] = len(album_tracks["data"])
        return album_metadata

    async def _resolve_redirect(self, media_type: str, item_id: str) -> str | None:
        """
        Resolves potential Deezer redirects to find the actual item ID.
        
        Returns:
            The new ID if a redirect occurred, otherwise None.
        """
        url = f"https://www.deezer.com/{media_type}/{item_id}"

        try:
            # Perform a HEAD request to follow redirects without downloading content
            async with self.session.head(url, allow_redirects=True) as response:
                final_url = str(response.url)
        except Exception as e:
            logger.warning(f"Failed to resolve redirect for {item_id}: {e}")
            return None

        # If the URL hasn't changed, return early
        if final_url == url:
            return None

        # Attempt to extract the new ID from the final URL
        match = re.search(rf"/{media_type}/(\d+)", final_url)

        # If a valid new ID is found and it differs from the original
        if match and (new_id := match.group(1)) != item_id:
            logger.debug(f"Resolved redirect for {media_type} {item_id} -> {new_id}")
            return new_id

        return None

    async def get_playlist(self, item_id: str) -> dict:
        """
        Fetches metadata for a playlist.

        Args:
            item_id (str): The playlist ID, or "favorites:{user_id}" for loved tracks.

        Returns:
            dict: The playlist metadata.
        """
        if item_id.startswith("favorites:"):
            user_id = item_id[len("favorites:"):]
            return await self.get_user_favorites(user_id)

        try:
            pl_metadata, pl_tracks = await asyncio.gather(
                asyncio.to_thread(self.client.gw.get_playlist, item_id),
                asyncio.to_thread(self.client.gw.get_playlist_tracks, item_id),
            )
        except Exception:
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
        """
        Fetches the loved tracks for a Deezer user profile.

        Args:
            user_id (str): The Deezer user ID.

        Returns:
            dict: A playlist-shaped dict with title and tracks list.
        """
        # deezer-py's get_user_tracks() drops the limit arg when routing to
        # get_my_favorite_tracks(), so we detect own profile and call it directly.
        if int(user_id) == self.logged_in_user_id:
            tracks = await asyncio.to_thread(
                self.client.gw.get_my_favorite_tracks, self.max_favorites
            )
        else:
            tracks = await asyncio.to_thread(
                self.client.gw.get_user_tracks, int(user_id), self.max_favorites
            )
        return {
            "title": "Loved Tracks",
            "tracks": tracks,
            "track_total": len(tracks),
        }

    async def get_artist(self, item_id: str) -> dict:
        """
        Fetches metadata for an artist.

        Args:
            item_id (str): The artist ID.

        Returns:
            dict: The artist metadata.
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
        """
        Searches for items on Deezer.

        Args:
            media_type (str): The type of media to search for.
            query (str): The search query.
            limit (int): The maximum number of results to return.

        Returns:
            list[dict]: A list of search results.
        """
        # TODO: use limit parameter
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
        item_id: str,
        quality: int = 2,
        is_retry: bool = False,
    ) -> DeezerDownloadable:
        """
        Prepares a downloadable object for a track.

        Args:
            item_id (str): The track ID.
            quality (int): The desired quality (0, 1, or 2).
            is_retry (bool): whether this is a retry attempt (internal use).

        Returns:
            DeezerDownloadable: The downloadable object.

        Raises:
            NonStreamableError: If the track cannot be streamed.
        """
        if item_id is None:
            raise NonStreamableError(
                "No item id provided. This can happen when searching for fallback songs.",
            )

        # Ensure quality is within bounds [0, 2]
        quality = max(0, min(quality, 2))

        # TODO: optimize such that all of the ids are requested at once
        track_info = self.client.gw.get_track(item_id)
        fallback_id = track_info.get("FALLBACK", {}).get("SNG_ID")

        # Mapping internal quality levels to Deezer API formats
        # We list them in descending order to facilitate the fallback loop
        quality_map = [
            (9, "MP3_128"),  # quality 0
            (3, "MP3_320"),  # quality 1
            (1, "FLAC"),     # quality 2
        ]

        # Pre-calculate file sizes for metadata
        dl_info: dict = {"quality": quality, "id": item_id}
        dl_info["quality_to_size"] = [
            int(track_info.get(f"FILESIZE_{fmt}", 0)) for _, fmt in quality_map
        ]

        token = track_info["TRACK_TOKEN"]
        url = None
        final_quality = quality

        # --- START OF FALLBACK LOOP ---
        # We try from the requested quality down to 0 (MP3_128)
        for q_level in range(quality, -1, -1):
            _, format_str = quality_map[q_level]
            
            try:
                logger.debug(f"Attempting to fetch URL for quality {q_level} ({format_str})")
                url = self.client.get_track_url(token, format_str)
                if url:
                    final_quality = q_level
                    break # Success!
            except deezer.WrongLicense:
                logger.warning(f"Quality {q_level} not available for this account. Trying lower...")
                continue
            except deezer.WrongGeolocation:
                if not is_retry and fallback_id:
                    logger.debug(f"Geoblocked. Trying fallback ID: {fallback_id}")
                    return await self.get_downloadable(fallback_id, quality, is_retry=True)
                raise NonStreamableError("Track geoblocked and no fallback available.")
        # --- END OF FALLBACK LOOP ---

        # If no URL was found through the official API, try the legacy encrypted method
        if url is None:
            logger.debug("Official API failed, trying encrypted file URL.")
            url = self._get_encrypted_file_url(
                item_id,
                track_info["MD5_ORIGIN"],
                track_info["MEDIA_VERSION"],
            )

        if not url:
            raise NonStreamableError(f"Could not retrieve any download URL for track {item_id}")

        dl_info["quality"] = final_quality
        dl_info["url"] = url
        logger.debug("dz track info: %s", track_info)
        return DeezerDownloadable(self.session, dl_info)

    def _get_encrypted_file_url(
        self,
        meta_id: str,
        track_hash: str,
        media_version: str,
    ):
        """
        Generates an encrypted file URL for a track when the standard API fails.

        Args:
            meta_id (str): The metadata ID.
            track_hash (str): The track hash.
            media_version (str): The media version.

        Returns:
            str: The encrypted file URL.
        """
        logger.debug("Unable to fetch URL. Trying encryption method.")
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
