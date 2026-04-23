import asyncio
import binascii
import hashlib
import logging

import deezer
from deezer.errors import PermissionException
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

    def __init__(self, config: Config):
        self.global_config = config
        self.client = deezer.Deezer()
        self.logged_in = False
        self.config = config.session.deezer

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
        try:
            # Try public API first
            pl_metadata, pl_tracks = await asyncio.gather(
                asyncio.to_thread(self.client.api.get_playlist, item_id),
                asyncio.to_thread(self.client.api.get_playlist_tracks, item_id),
            )
            pl_metadata["tracks"] = pl_tracks["data"]
            pl_metadata["track_total"] = len(pl_tracks["data"])
            return pl_metadata
        except PermissionException as e:
            # Public API failed - likely a private/user playlist
            # Try GW (gateway) API which works with private playlists when using ARL
            logger.debug(f"Public API failed for playlist {item_id}, trying GW API: {e}")

            try:
                # GW API works with ARL for private playlists
                logger.info(f"Attempting to fetch private playlist {item_id} using GW API with ARL authentication")

                # Verify client is logged in
                if not self.logged_in:
                    raise ValueError("Client not logged in - GW API requires authentication")

                # Fetch both playlist metadata and ALL tracks via GW API
                # Note: get_playlist_page() only returns first 10 tracks (paginated)
                # So we use get_playlist_tracks() to get ALL tracks
                def get_gw_playlist_data():
                    try:
                        # Get metadata (contains playlist info but only first page of tracks)
                        metadata = self.client.gw.get_playlist_page(item_id)
                        # Get ALL tracks (returns complete list, not paginated)
                        all_tracks = self.client.gw.get_playlist_tracks(item_id)

                        logger.debug(f"GW API metadata: {len(metadata.get('SONGS', {}).get('data', []))} tracks (page)")
                        logger.debug(f"GW API all tracks: {len(all_tracks)} tracks (complete)")

                        # Replace paginated tracks with complete track list
                        if 'SONGS' in metadata and isinstance(metadata['SONGS'], dict):
                            metadata['SONGS']['data'] = all_tracks

                        return metadata
                    except Exception as inner_e:
                        logger.error(f"GW API call failed inside thread: {type(inner_e).__name__}: {inner_e}")
                        raise

                gw_response = await asyncio.to_thread(get_gw_playlist_data)

                logger.debug(f"GW API response type: {type(gw_response)}, keys: {list(gw_response.keys()) if isinstance(gw_response, dict) else 'N/A'}")

                if not isinstance(gw_response, dict):
                    raise ValueError(f"Unexpected GW API response type: {type(gw_response)}, value: {gw_response}")

                # Convert GW format to regular API format
                logger.info(f"Successfully fetched private playlist {item_id} via GW API with {len(gw_response.get('SONGS', {}).get('data', []))} tracks, converting to standard format")
                return self._convert_gw_playlist_to_api_format(gw_response)

            except Exception as gw_error:
                # Both APIs failed - provide helpful error message
                logger.error(
                    f"Failed to access playlist {item_id}. "
                    f"This appears to be a private playlist. "
                    f"Public API error: {e}"
                )
                logger.error(
                    f"GW API also failed: {type(gw_error).__name__}: {gw_error}",
                    exc_info=True  # Show full traceback
                )
                logger.error(
                    f"Possible causes:\n"
                    f"  1. Your ARL token may be invalid or expired\n"
                    f"  2. The playlist owner has restricted sharing\n"
                    f"  3. The playlist doesn't exist or was deleted\n\n"
                    f"Workaround: Make the playlist public temporarily in Deezer, "
                    f"download it, then make it private again."
                )
                raise NonStreamableError(
                    f"Cannot access private playlist {item_id}. "
                    f"Verify your ARL token is valid, or make the playlist public temporarily."
                )

    def _convert_gw_playlist_to_api_format(self, gw_response: dict) -> dict:
        """Convert GW API playlist format to regular API format.

        GW API uses uppercase keys (DATA, SONGS) while regular API uses lowercase (data, tracks).
        This method transforms the response to match the expected format.
        """
        logger.debug(f"Converting GW playlist, top-level keys: {list(gw_response.keys())}")

        data = gw_response.get("DATA", {})
        logger.debug(f"DATA type: {type(data)}, is dict: {isinstance(data, dict)}")

        songs_container = gw_response.get("SONGS", {})
        logger.debug(f"SONGS type: {type(songs_container)}, value: {songs_container if not isinstance(songs_container, dict) else 'dict'}")

        # Handle different SONGS formats
        if isinstance(songs_container, list):
            songs = songs_container
        elif isinstance(songs_container, dict):
            songs = songs_container.get("data", [])
        else:
            logger.warning(f"Unexpected SONGS format: {type(songs_container)}, using empty list")
            songs = []

        # Get creator info - CURATOR is dict for public playlists, bool for private
        curator = gw_response.get("CURATOR")
        if isinstance(curator, dict):
            creator_id = curator.get("USER_ID")
            creator_name = curator.get("USER_NAME")
        else:
            # Private playlist - use PARENT_USER info from DATA
            creator_id = data.get("PARENT_USER_ID")
            creator_name = data.get("PARENT_USERNAME")

        # Transform to regular API format
        playlist = {
            "id": data.get("PLAYLIST_ID"),
            "title": data.get("TITLE"),
            "description": data.get("DESCRIPTION"),
            "duration": data.get("DURATION"),
            "public": data.get("STATUS") == 1,  # 1 = public, 0 = private
            "nb_tracks": data.get("NB_SONG", len(songs)),
            "track_total": len(songs),
            "picture": data.get("PLAYLIST_PICTURE"),
            "picture_small": f"https://e-cdns-images.dzcdn.net/images/cover/{data.get('PLAYLIST_PICTURE')}/250x250-000000-80-0-0.jpg" if data.get("PLAYLIST_PICTURE") else None,
            "picture_medium": f"https://e-cdns-images.dzcdn.net/images/cover/{data.get('PLAYLIST_PICTURE')}/500x500-000000-80-0-0.jpg" if data.get("PLAYLIST_PICTURE") else None,
            "picture_big": f"https://e-cdns-images.dzcdn.net/images/cover/{data.get('PLAYLIST_PICTURE')}/1000x1000-000000-80-0-0.jpg" if data.get("PLAYLIST_PICTURE") else None,
            "picture_xl": f"https://e-cdns-images.dzcdn.net/images/cover/{data.get('PLAYLIST_PICTURE')}/1400x1400-000000-80-0-0.jpg" if data.get("PLAYLIST_PICTURE") else None,
            "checksum": data.get("CHECKSUM"),
            "creator": {
                "id": creator_id,
                "name": creator_name,
            },
            "tracks": [
                {
                    "id": track.get("SNG_ID"),
                    "title": track.get("SNG_TITLE"),
                    "duration": track.get("DURATION"),
                    "artist": {
                        "id": track.get("ART_ID"),
                        "name": track.get("ART_NAME"),
                    },
                    "album": {
                        "id": track.get("ALB_ID"),
                        "title": track.get("ALB_TITLE"),
                    },
                }
                for track in songs
            ],
        }

        logger.debug(f"Converted GW playlist to API format: {playlist['title']} ({len(playlist['tracks'])} tracks)")
        return playlist

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
