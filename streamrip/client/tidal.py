import asyncio
import base64
import json
import logging
import re
import time
from json import JSONDecodeError
from xml.etree import ElementTree as ET

import aiohttp

from ..config import Config
from ..exceptions import NonStreamableError
from .client import Client
from .downloadable import TidalDownloadable

logger = logging.getLogger("streamrip")

BASE = "https://api.tidalhifi.com/v1"
AUTH_URL = "https://auth.tidal.com/v1/oauth2"

CLIENT_ID = base64.b64decode("ZlgySnhkbW50WldLMGl4VA==").decode("iso-8859-1")
CLIENT_SECRET = base64.b64decode(
    "MU5tNUFmREFqeHJnSkZKYktOV0xlQXlLR1ZHbUlOdVhQUExIVlhBdnhBZz0=",
).decode("iso-8859-1")
AUTH = aiohttp.BasicAuth(login=CLIENT_ID, password=CLIENT_SECRET)
STREAM_URL_REGEX = re.compile(
    r"#EXT-X-STREAM-INF:BANDWIDTH=\d+,AVERAGE-BANDWIDTH=\d+,CODECS=\"(?!jpeg)[^\"]+\",RESOLUTION=\d+x\d+\n(.+)"
)

QUALITY_MAP = {
    0: "LOW",           # AAC 96kbps
    1: "HIGH",          # AAC 320kbps
    2: "LOSSLESS",      # 16/44.1 FLAC
    3: "HI_RES_LOSSLESS",  # 24-bit FLAC (replaces legacy MQA)
}


class TidalClient(Client):
    """TidalClient."""

    source = "tidal"
    max_quality = 3

    def __init__(self, config: Config):
        self.logged_in = False
        self._login_lock = asyncio.Lock()
        self.global_config = config
        self.config = config.session.tidal
        self.rate_limiter = self.get_rate_limiter(
            config.session.downloads.requests_per_minute,
        )

    async def login(self):
        self.session = await self.get_session(
            verify_ssl=self.global_config.session.downloads.verify_ssl
        )
        c = self.config
        if not c.access_token:
            raise Exception("Access token not found in config.")

        self.token_expiry = float(c.token_expiry)
        self.refresh_token = c.refresh_token

        if self.token_expiry - time.time() < 86400:  # 1 day
            await self._refresh_access_token()
        else:
            await self._login_by_access_token(c.access_token, c.user_id)

        self.logged_in = True

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        """Send a request to the api for information.

        :param item_id:
        :type item_id: str
        :param media_type: track, album, playlist, or video.
        :type media_type: str
        :rtype: dict
        """
        assert media_type in (
            "track",
            "album",
            "playlist",
            "video",
            "artist",
        ), media_type

        url = f"{media_type}s/{item_id}"
        item = await self._api_request(url)
        if media_type in ("playlist", "album"):
            # TODO: move into new method and make concurrent
            resp = await self._api_request(f"{url}/items")
            tracks_left = item["numberOfTracks"]
            if tracks_left > 100:
                offset = 0
                while tracks_left > 0:
                    offset += 100
                    tracks_left -= 100
                    items_resp = await self._api_request(
                        f"{url}/items", {"offset": offset}
                    )
                    resp["items"].extend(items_resp["items"])

            item["tracks"] = [item["item"] for item in resp["items"]]
        elif media_type == "artist":
            logger.debug("filtering eps")
            album_resp, ep_resp = await asyncio.gather(
                self._api_request(f"{url}/albums"),
                self._api_request(f"{url}/albums", params={"filter": "EPSANDSINGLES"}),
            )

            item["albums"] = album_resp["items"]
            item["albums"].extend(ep_resp["items"])
        elif media_type == "track":
            try:
                resp = await self._api_request(
                    f"tracks/{item_id!s}/lyrics", base="https://listen.tidal.com/v1"
                )

                # Use unsynced lyrics for MP3, synced for others (FLAC, OPUS, etc)
                if (
                    self.global_config.session.conversion.enabled
                    and self.global_config.session.conversion.codec.upper() == "MP3"
                ):
                    item["lyrics"] = resp.get("lyrics") or ""
                else:
                    item["lyrics"] = resp.get("subtitles") or resp.get("lyrics") or ""
            except TypeError as e:
                logger.warning(f"Failed to get lyrics for {item_id}: {e}")

        logger.debug(item)
        return item

    async def search(self, media_type: str, query: str, limit: int = 100) -> list[dict]:
        """Search for a query.

        :param query:
        :type query: str
        :param media_type: track, album, playlist, or video.
        :type media_type: str
        :param limit: max is 100
        :type limit: int
        :rtype: dict
        """
        params = {
            "query": query,
            "limit": limit,
        }
        assert media_type in ("album", "track", "playlist", "video", "artist")
        resp = await self._api_request(f"search/{media_type}s", params=params)
        if len(resp["items"]) > 1:
            return [resp]
        return []

    async def get_downloadable(self, track_id: str, quality: int):
        """Resolve the download URL for a Tidal track.

        Handles both the legacy BTS JSON manifest (application/vnd.tidal.bts)
        and the newer MPEG-DASH manifest (application/dash+xml) introduced when
        Tidal dropped MQA in favour of HI_RES_LOSSLESS.

        Args:
            track_id (str): The Tidal track ID.
            quality (int): Quality level (0=LOW, 1=HIGH, 2=LOSSLESS, 3=HI_RES_LOSSLESS).

        Returns:
            TidalDownloadable: Ready-to-use downloadable object.

        Raises:
            NonStreamableError: If the track cannot be streamed at any quality.
            Exception: If manifest data is missing or malformed.
        """
        params = {
            "audioquality": QUALITY_MAP[quality],
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        }
        resp = await self._api_request(
            f"tracks/{track_id}/playbackinfopostpaywall", params
        )
        logger.debug(resp)

        try:
            manifest_b64 = resp["manifest"]
        except KeyError:
            raise Exception(resp.get("userMessage", "Missing manifest in Tidal response"))

        manifest_mime = resp.get("manifestMimeType", "application/vnd.tidal.bts")

        if manifest_mime == "application/dash+xml":
            manifest = self._parse_dash_manifest(manifest_b64)
        else:
            try:
                manifest = json.loads(base64.b64decode(manifest_b64).decode("utf-8"))
            except JSONDecodeError:
                if quality <= 0:
                    raise NonStreamableError(
                        f"Tidal track {track_id} is not streamable at any quality."
                    )
                logger.warning(
                    f"Failed to decode BTS manifest for {track_id}. Retrying with lower quality."
                )
                return await self.get_downloadable(track_id, quality - 1)

        logger.debug(manifest)
        return TidalDownloadable(
            self.session,
            url=manifest["urls"][0],
            codec=manifest["codecs"],
            encryption_key=None,  # MQA encryption abandoned by Tidal
            restrictions=manifest.get("restrictions"),
        )

    def _parse_dash_manifest(self, manifest_b64: str) -> dict:
        """Parse a base64-encoded MPEG-DASH XML manifest into BTS-compatible format.

        Tidal switched from proprietary BTS JSON manifests to MPEG-DASH for
        HI_RES_LOSSLESS streams when they dropped MQA. This method extracts
        the segment URL list from the DASH SegmentTimeline so the rest of the
        download pipeline can treat it like any other multi-URL stream.

        Args:
            manifest_b64 (str): Base64-encoded DASH XML string from the API response.

        Returns:
            dict: A manifest-shaped dict with "urls" (list of segment URLs),
                  "codecs", and "encryptionType" keys.

        Raises:
            Exception: If the XML is malformed or required elements are missing.
        """
        try:
            manifest_xml = base64.b64decode(manifest_b64).decode("utf-8")
            root = ET.fromstring(manifest_xml)
        except ET.ParseError as e:
            raise Exception(f"Failed to parse DASH XML manifest: {e}")

        ns = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}

        representation = root.find(".//mpd:Representation", ns)
        if representation is None:
            raise Exception("No Representation found in DASH manifest")

        codecs = representation.get("codecs", "flac")

        segment_template = representation.find(".//mpd:SegmentTemplate", ns)
        if segment_template is None:
            raise Exception("No SegmentTemplate found in DASH manifest")

        media_template = segment_template.get("media")
        if media_template is None:
            raise Exception("No 'media' attribute in SegmentTemplate of DASH manifest")
        start_number = int(segment_template.get("startNumber", "0"))

        timeline = segment_template.find("mpd:SegmentTimeline", ns)
        if timeline is None:
            raise Exception("No SegmentTimeline found in DASH manifest")

        segment_urls = []
        segment_number = start_number
        for seg in timeline.findall("mpd:S", ns):
            repeat = int(seg.get("r", "0"))
            # r=0 → 1 segment, r=N → N+1 segments, r=-1 → handled as 1
            count = max(repeat + 1, 1)
            for _ in range(count):
                segment_urls.append(media_template.replace("$Number$", str(segment_number)))
                segment_number += 1

        return {
            "urls": segment_urls,
            "codecs": codecs,
            "encryptionType": "NONE",
            "mimeType": f"audio/{codecs}",
        }

    async def get_video_file_url(self, video_id: str) -> str:
        """Get the HLS video stream url.

        The stream is downloaded using ffmpeg for now.

        :param video_id:
        :type video_id: str
        :rtype: str
        """
        params = {
            "videoquality": "HIGH",
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        }
        resp = await self._api_request(
            f"videos/{video_id}/playbackinfopostpaywall", params=params
        )
        manifest = json.loads(base64.b64decode(resp["manifest"]).decode("utf-8"))
        async with self.session.get(manifest["urls"][0]) as resp:
            available_urls = await resp.json()
        available_urls.encoding = "utf-8"

        # Highest resolution is last
        *_, last_match = STREAM_URL_REGEX.finditer(available_urls.text)

        return last_match.group(1)

    # ---------- Login Utilities ---------------

    async def _login_by_access_token(self, token: str, user_id: str):
        """Login using the access token.

        Used after the initial authorization.

        :param token: access token
        :param user_id: To verify that the user is correct
        """
        headers = {"authorization": f"Bearer {token}"}  # temporary
        async with self.session.get(
            "https://api.tidal.com/v1/sessions",
            headers=headers,
        ) as _resp:
            resp = await _resp.json()

        if resp.get("status", 200) != 200:
            raise Exception(f"Login failed {resp}")

        if str(resp.get("userId")) != str(user_id):
            raise Exception(f"User id mismatch {resp['userId']} v {user_id}")

        c = self.config
        c.user_id = resp["userId"]
        c.country_code = resp["countryCode"]
        c.access_token = token
        self._update_authorization_from_config()

    async def _get_login_link(self) -> str:
        data = {
            "client_id": CLIENT_ID,
            "scope": "r_usr+w_usr+w_sub",
        }
        resp = await self._api_post(f"{AUTH_URL}/device_authorization", data)

        if resp.get("status", 200) != 200:
            raise Exception(f"Device authorization failed {resp}")

        device_code = resp["deviceCode"]
        return f"https://{device_code}"

    def _update_authorization_from_config(self):
        self.session.headers.update(
            {"authorization": f"Bearer {self.config.access_token}"},
        )

    async def _get_auth_status(self, device_code) -> tuple[int, dict[str, int | str]]:
        """Check if the user has logged in inside the browser.

        returns (status, authentication info)
        """
        data = {
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "scope": "r_usr+w_usr+w_sub",
        }
        logger.debug("Checking with %s", data)
        resp = await self._api_post(f"{AUTH_URL}/token", data, AUTH)

        if "status" in resp and resp["status"] != 200:
            if resp["status"] == 400 and resp["sub_status"] == 1002:
                return 2, {}
            else:
                return 1, {}

        ret = {}
        ret["user_id"] = resp["user"]["userId"]
        ret["country_code"] = resp["user"]["countryCode"]
        ret["access_token"] = resp["access_token"]
        ret["refresh_token"] = resp["refresh_token"]
        ret["token_expiry"] = resp["expires_in"] + time.time()
        return 0, ret

    async def _refresh_access_token(self):
        """Refresh the access token given a refresh token.

        The access token expires in a week, so it must be refreshed.
        Requires a refresh token.
        """
        data = {
            "client_id": CLIENT_ID,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "r_usr+w_usr+w_sub",
        }
        resp = await self._api_post(f"{AUTH_URL}/token", data, AUTH)

        if resp.get("status", 200) != 200:
            raise Exception("Refresh failed")

        c = self.config
        c.access_token = resp["access_token"]
        c.token_expiry = resp["expires_in"] + time.time()
        self._update_authorization_from_config()

    async def _get_device_code(self) -> tuple[str, str]:
        """Get the device code that will be used to log in on the browser."""
        if not hasattr(self, "session"):
            self.session = await self.get_session()

        data = {
            "client_id": CLIENT_ID,
            "scope": "r_usr+w_usr+w_sub",
        }
        resp = await self._api_post(f"{AUTH_URL}/device_authorization", data)

        if resp.get("status", 200) != 200:
            raise Exception(f"Device authorization failed {resp}")

        return resp["deviceCode"], resp["verificationUriComplete"]

    # ---------- API Request Utilities ---------------

    async def _api_post(self, url, data, auth: aiohttp.BasicAuth | None = None) -> dict:
        """Post to the Tidal API. Status not checked!

        :param url:
        :param data:
        :param auth:
        """
        async with self.rate_limiter:
            async with self.session.post(url, data=data, auth=auth) as resp:
                return await resp.json()

    async def _api_request(self, path: str, params=None, base: str = BASE) -> dict:
        """Handle Tidal API requests.

        :param path:
        :type path: str
        :param params:
        :rtype: dict
        """
        if params is None:
            params = {}

        params["countryCode"] = self.config.country_code
        params["limit"] = 100

        async with self.rate_limiter:
            async with self.session.get(f"{base}/{path}", params=params) as resp:
                if resp.status == 404:
                    logger.warning("TIDAL: track not found", resp)
                    raise NonStreamableError("TIDAL: Track not found")
                resp.raise_for_status()
                return await resp.json()
