import asyncio
import binascii
import hashlib
import logging

import deezer
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
        logged_in_user_id: USER_ID of the authenticated account, set during login
        max_favorites: upper bound for favorites pagination

    """

    source = "deezer"
    max_quality = 2
    max_favorites = 10_000

    def __init__(self, config: Config):
        self.global_config = config
        self.client = deezer.Deezer()
        self.logged_in = False
        self.config = config.session.deezer
        self.logged_in_user_id: int | None = None

    async def login(self):
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
        self.logged_in = True
        user_data = await asyncio.to_thread(self.client.gw.get_user_data)
        self.logged_in_user_id = user_data.get("USER", {}).get("USER_ID")

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
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
        try:
            item = await asyncio.to_thread(self.client.api.get_track, item_id)
        except Exception as e:
            raise NonStreamableError(e)

        album_id = item["album"]["id"]
        try:
            album_metadata, album_tracks = await asyncio.gather(
                asyncio.to_thread(self.client.api.get_album, album_id),
                asyncio.to_thread(self.client.api.get_album_tracks, album_id),
            )
        except Exception as e:
            logger.error(f"Error fetching album of track {item_id}: {e}")
            return item

        album_metadata["tracks"] = album_tracks["data"]
        album_metadata["track_total"] = len(album_tracks["data"])
        item["album"] = album_metadata

        return item

    async def get_album(self, item_id: str) -> dict:
        album_metadata, album_tracks = await asyncio.gather(
            asyncio.to_thread(self.client.api.get_album, item_id),
            asyncio.to_thread(self.client.api.get_album_tracks, item_id),
        )
        album_metadata["tracks"] = album_tracks["data"]
        album_metadata["track_total"] = len(album_tracks["data"])
        return album_metadata

    async def get_playlist(self, item_id: str) -> dict:
        if item_id.startswith("favorites:"):
            user_id = item_id.removeprefix("favorites:")
            return await self.get_user_favorites(user_id)
        pl_metadata, pl_tracks = await asyncio.gather(
            asyncio.to_thread(self.client.api.get_playlist, item_id),
            asyncio.to_thread(self.client.api.get_playlist_tracks, item_id),
        )
        pl_metadata["tracks"] = pl_tracks["data"]
        pl_metadata["track_total"] = len(pl_tracks["data"])
        return pl_metadata

    async def get_user_favorites(self, user_id: str) -> dict:
        """Fetch the loved tracks for the authenticated Deezer account.

        ``song.getFavoriteIds`` silently caps responses at roughly 25 entries per
        call regardless of the ``nb`` parameter; the ``start`` parameter must be
        advanced by the actual count returned to paginate through all favorites.

        ``song.getFavoriteIds`` carries no ``user_id`` parameter — it always
        returns the authenticated user's favorites.  Comparing ``user_id`` against
        ``logged_in_user_id`` to detect "other user" is unreliable for family
        accounts: ``change_account()`` shifts ``current_user`` to a child profile
        whose id differs from the main account's USER_ID that authenticated the
        ARL.  The ``user_id`` argument is accepted for URL-routing compatibility
        but is not forwarded to the GW call.

        Args:
            user_id: The Deezer user ID from the profile URL. Accepted for
                routing compatibility; the GW call always uses the authenticated
                account.

        Returns:
            Playlist-shaped dict with "title", "tracks", and "track_total".
        """
        page_size = 100
        all_entries: list[dict] = []
        start = 0
        while len(all_entries) < self.max_favorites:
            response = await asyncio.to_thread(
                self.client.gw.get_user_favorite_ids, limit=page_size, start=start
            )
            entries: list[dict] = response.get("data", [])
            if not entries:
                break
            all_entries.extend(entries)
            start += len(entries)

        return {
            "title": "Loved Tracks",
            "tracks": [{"id": str(entry["SNG_ID"])} for entry in all_entries],
            "track_total": len(all_entries),
        }

    async def get_artist(self, item_id: str) -> dict:
        artist, albums = await asyncio.gather(
            asyncio.to_thread(self.client.api.get_artist, item_id),
            asyncio.to_thread(self.client.api.get_artist_albums, item_id),
        )
        artist["albums"] = albums["data"]
        return artist

    async def search(self, media_type: str, query: str, limit: int = 200) -> list[dict]:
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
        if item_id is None:
            raise NonStreamableError(
                "No item id provided. This can happen when searching for fallback songs.",
            )
        # TODO: optimize such that all of the ids are requested at once
        dl_info: dict = {"quality": quality, "id": item_id}

        track_info = self.client.gw.get_track(item_id)

        fallback_id = track_info.get("FALLBACK", {}).get("SNG_ID")

        quality_map = [
            (9, "MP3_128"),  # quality 0
            (3, "MP3_320"),  # quality 1
            (1, "FLAC"),  # quality 2
        ]
        size_map = [
            int(track_info.get(f"FILESIZE_{format}", 0)) for _, format in quality_map
        ]
        dl_info["quality_to_size"] = size_map
        
        # Check if requested quality is available
        if size_map[quality] == 0:
            if self.config.lower_quality_if_not_available:
                # Fallback to lower quality
                while size_map[quality] == 0 and quality > 0:
                    logger.warning(
                        "The requested quality %s is not available. Falling back to quality %s",
                        quality,
                        quality - 1,
                    )
                    quality -= 1
            else:
                # No fallback - raise error
                raise NonStreamableError(
                    f"The requested quality {quality} is not available and fallback is disabled."
                )
        
        # Update the quality in dl_info to reflect the final quality used
        dl_info["quality"] = quality

        _, format_str = quality_map[quality]

        token = track_info["TRACK_TOKEN"]
        try:
            logger.debug("Fetching deezer url with token %s", token)
            url = self.client.get_track_url(token, format_str)
        except deezer.WrongLicense:
            raise NonStreamableError(
                "The requested quality is not available with your subscription. "
                "Deezer HiFi is required for quality 2. Otherwise, the maximum "
                "quality allowed is 1.",
            )
        except deezer.WrongGeolocation:
            if not is_retry and fallback_id:
                return await self.get_downloadable(fallback_id, quality, is_retry=True)
            raise NonStreamableError(
                "The requested track is not available. This may be due to your country/location.",
            )

        if url is None:
            url = self._get_encrypted_file_url(
                item_id,
                track_info["MD5_ORIGIN"],
                track_info["MEDIA_VERSION"],
            )

        dl_info["url"] = url
        logger.debug("dz track info: %s", track_info)
        return DeezerDownloadable(self.session, dl_info)

    def _get_encrypted_file_url(
        self,
        meta_id: str,
        track_hash: str,
        media_version: str,
    ):
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
