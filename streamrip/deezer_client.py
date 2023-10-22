import binascii
import hashlib

import deezer
from Cryptodome.Cipher import AES

from .client import Client
from .config import Config
from .downloadable import DeezerDownloadable
from .exceptions import AuthenticationError, MissingCredentials, NonStreamable


class DeezerClient(Client):
    source = "deezer"
    max_quality = 2

    def __init__(self, config: Config):
        self.global_config = config
        self.client = deezer.Deezer()
        self.logged_in = False
        self.config = config.session.deezer

    async def login(self):
        arl = self.config.arl
        if not arl:
            raise MissingCredentials
        success = self.client.login_via_arl(arl)
        if not success:
            raise AuthenticationError
        self.logged_in = True

    async def get_metadata(self, info: dict, media_type: str) -> dict:
        request_functions = {
            "track": self.client.api.get_track,
            "album": self.client.api.get_album,
            "playlist": self.client.api.get_playlist,
            "artist": self.client.api.get_artist,
        }

        get_item = request_functions[media_type]
        item = get_item(info["id"])
        if media_type in ("album", "playlist"):
            tracks = getattr(self.client.api, f"get_{media_type}_tracks")(
                info["id"], limit=-1
            )
            item["tracks"] = tracks["data"]
            item["track_total"] = len(tracks["data"])
        elif media_type == "artist":
            albums = self.client.api.get_artist_albums(info["id"])
            item["albums"] = albums["data"]

        return item

    async def search(self, query: str, media_type: str, limit: int = 200):
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
        return response

    async def get_downloadable(
        self, info: dict, quality: int = 2
    ) -> DeezerDownloadable:
        item_id = info["id"]
        # TODO: optimize such that all of the ids are requested at once
        dl_info: dict = {"quality": quality, "id": item_id}

        track_info = self.client.gw.get_track(item_id)

        dl_info["fallback_id"] = track_info["FALLBACK"]["SNG_ID"]

        quality_map = [
            (9, "MP3_128"),
            (3, "MP3_320"),
            (1, "FLAC"),
        ]

        # available_formats = [
        #     "AAC_64",
        #     "MP3_64",
        #     "MP3_128",
        #     "MP3_256",
        #     "MP3_320",
        #     "FLAC",
        # ]

        _, format_str = quality_map[quality]

        # dl_info["size_to_quality"] = {
        #     int(track_info.get(f"FILESIZE_{format}")): self._quality_id_from_filetype(
        #         format
        #     )
        #     for format in available_formats
        # }

        token = track_info["TRACK_TOKEN"]
        try:
            url = self.client.get_track_url(token, format_str)
        except deezer.WrongLicense:
            raise NonStreamable(
                "The requested quality is not available with your subscription. "
                "Deezer HiFi is required for quality 2. Otherwise, the maximum "
                "quality allowed is 1."
            )

        if url is None:
            url = self._get_encrypted_file_url(
                item_id, track_info["MD5_ORIGIN"], track_info["MEDIA_VERSION"]
            )

        dl_info["url"] = url
        return DeezerDownloadable(self.session, dl_info)

    def _get_encrypted_file_url(
        self, meta_id: str, track_hash: str, media_version: str
    ):
        format_number = 1

        url_bytes = b"\xa4".join(
            (
                track_hash.encode(),
                str(format_number).encode(),
                str(meta_id).encode(),
                str(media_version).encode(),
            )
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
            AES.new("jo6aey6haid2Teih".encode(), AES.MODE_ECB).encrypt(info_bytes)
        ).decode("utf-8")

        return f"https://e-cdns-proxy-{track_hash[0]}.dzcdn.net/mobile/1/{path}"
