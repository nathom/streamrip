import asyncio
import hashlib
import logging
import re
import time
from typing import AsyncGenerator, Optional

from .client import Client
from .config import Config
from .downloadable import BasicDownloadable, Downloadable
from .exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    MissingCredentials,
    NonStreamable,
)
from .qobuz_spoofer import QobuzSpoofer

logger = logging.getLogger("streamrip")

QOBUZ_BASE_URL = "https://www.qobuz.com/api.json/0.2"

QOBUZ_FEATURED_KEYS = {
    "most-streamed",
    "recent-releases",
    "best-sellers",
    "press-awards",
    "ideal-discography",
    "editor-picks",
    "most-featured",
    "qobuzissims",
    "new-releases",
    "new-releases-full",
    "harmonia-mundi",
    "universal-classic",
    "universal-jazz",
    "universal-jeunesse",
    "universal-chanson",
}


class QobuzClient(Client):
    source = "qobuz"
    max_quality = 4

    def __init__(self, config: Config):
        self.logged_in = False
        self.config = config
        self.rate_limiter = self.get_rate_limiter(
            config.session.downloads.requests_per_minute
        )
        self.secret: Optional[str] = None

    async def login(self):
        logger.info("Logging into qobuz")
        self.session = await self.get_session()
        c = self.config.session.qobuz
        if not c.email_or_userid or not c.password_or_token:
            raise MissingCredentials

        assert not self.logged_in, "Already logged in"

        if not c.app_id or not c.secrets:
            logger.info("App id/secrets not found, fetching")
            c.app_id, c.secrets = await self._get_app_id_and_secrets()
            # write to file
            f = self.config.file
            f.qobuz.app_id = c.app_id
            f.qobuz.secrets = c.secrets
            f.set_modified()
        logger.info(f"Found {c.app_id = } {c.secrets = }")

        self.session.headers.update({"X-App-Id": c.app_id})
        self.secret = await self._get_valid_secret(c.secrets)

        if c.use_auth_token:
            params = {
                "user_id": c.email_or_userid,
                "user_auth_token": c.password_or_token,
                "app_id": c.app_id,
            }
        else:
            params = {
                "email": c.email_or_userid,
                "password": c.password_or_token,
                "app_id": c.app_id,
            }

        logger.debug("Request params %s", params)
        status, resp = await self._api_request("user/login", params)
        logger.debug("Login resp: %s", resp)

        if status == 401:
            raise AuthenticationError(f"Invalid credentials from params {params}")
        elif status == 400:
            raise InvalidAppIdError(f"Invalid app id from params {params}")

        logger.info("Logged in to Qobuz")

        if not resp["user"]["credential"]["parameters"]:
            raise IneligibleError("Free accounts are not eligible to download tracks.")

        uat = resp["user_auth_token"]
        self.session.headers.update({"X-User-Auth-Token": uat})
        # label = resp_json["user"]["credential"]["parameters"]["short_label"]

        self.logged_in = True

    async def get_metadata(self, item_id: str, media_type: str):
        c = self.config.session.qobuz
        params = {
            "app_id": c.app_id,
            f"{media_type}_id": item_id,
            # Do these matter?
            "limit": 500,
            "offset": 0,
        }

        extras = {
            "artist": "albums",
            "playlist": "tracks",
            "label": "albums",
        }

        if media_type in extras:
            params.update({"extra": extras[media_type]})

        logger.debug("request params: %s", params)

        epoint = f"{media_type}/get"

        status, resp = await self._api_request(epoint, params)

        if status != 200:
            raise Exception(f'Error fetching metadata. "{resp["message"]}"')

        return resp

    async def search(
        self, query: str, media_type: str, limit: int = 500
    ) -> AsyncGenerator:
        params = {
            "query": query,
            # "limit": limit,
        }
        # TODO: move featured, favorites, and playlists into _api_get later
        if media_type == "featured":
            assert query in QOBUZ_FEATURED_KEYS, f'query "{query}" is invalid.'
            params.update({"type": query})
            del params["query"]
            epoint = "album/getFeatured"

        elif query == "user-favorites":
            assert query in ("track", "artist", "album")
            params.update({"type": f"{media_type}s"})
            epoint = "favorite/getUserFavorites"

        elif query == "user-playlists":
            epoint = "playlist/getUserPlaylists"

        else:
            epoint = f"{media_type}/search"

        async for status, resp in self._paginate(epoint, params, limit=limit):
            assert status == 200
            yield resp

    async def get_downloadable(self, item: dict, quality: int) -> Downloadable:
        assert self.secret is not None and self.logged_in and 1 <= quality <= 4
        item_id = item["id"]
        status, resp_json = await self._request_file_url(item_id, quality, self.secret)
        assert status == 200
        stream_url = resp_json.get("url")

        if stream_url is None:
            restrictions = resp_json["restrictions"]
            if restrictions:
                # Turn CamelCase code into a readable sentence
                words = re.findall(r"([A-Z][a-z]+)", restrictions[0]["code"])
                raise NonStreamable(
                    words[0] + " " + " ".join(map(str.lower, words[1:])) + "."
                )
            raise NonStreamable

        return BasicDownloadable(
            self.session, stream_url, "flac" if quality > 1 else "mp3"
        )

    async def _paginate(
        self, epoint: str, params: dict, limit: Optional[int] = None
    ) -> AsyncGenerator[tuple[int, dict], None]:
        """Paginate search results.

        params:
            limit: If None, all the results are yielded. Otherwise a maximum
            of `limit` results are yielded.

        returns:
            Generator that yields (status code, response) tuples
        """
        params.update({"limit": limit or 500})
        status, page = await self._api_request(epoint, params)
        logger.debug("paginate: initial request made with status %d", status)
        # albums, tracks, etc.
        key = epoint.split("/")[0] + "s"
        items = page.get(key, {})
        total = items.get("total", 0) or items.get("items", 0)
        if limit is not None and limit < total:
            total = limit

        logger.debug("paginate: %d total items requested", total)

        if not total:
            logger.debug("Nothing found from %s epoint", epoint)
            return

        limit = int(page.get(key, {}).get("limit", 500))
        offset = int(page.get(key, {}).get("offset", 0))

        logger.debug("paginate: from response: limit=%d, offset=%d", limit, offset)
        params.update({"limit": limit})
        yield status, page
        while (offset + limit) < total:
            offset += limit
            params.update({"offset": offset})
            yield await self._api_request(epoint, params)

    async def _get_app_id_and_secrets(self) -> tuple[str, list[str]]:
        async with QobuzSpoofer() as spoofer:
            return await spoofer.get_app_id_and_secrets()

    async def _get_valid_secret(self, secrets: list[str]) -> str:
        results = await asyncio.gather(
            *[self._test_secret(secret) for secret in secrets]
        )
        working_secrets = [r for r in results if r is not None]

        if len(working_secrets) == 0:
            raise InvalidAppSecretError(secrets)

        return working_secrets[0]

    async def _test_secret(self, secret: str) -> Optional[str]:
        status, _ = await self._request_file_url("19512574", 4, secret)
        if status == 400:
            return None
        if status == 200:
            return secret
        logger.warning("Got status %d when testing secret", status)
        return None

    async def _request_file_url(
        self, track_id: str, quality: int, secret: str
    ) -> tuple[int, dict]:
        quality = self.get_quality(quality)
        unix_ts = time.time()
        r_sig = f"trackgetFileUrlformat_id{quality}intentstreamtrack_id{track_id}{unix_ts}{secret}"
        logger.debug("Raw request signature: %s", r_sig)
        r_sig_hashed = hashlib.md5(r_sig.encode("utf-8")).hexdigest()
        logger.debug("Hashed request signature: %s", r_sig_hashed)
        params = {
            "request_ts": unix_ts,
            "request_sig": r_sig_hashed,
            "track_id": track_id,
            "format_id": quality,
            "intent": "stream",
        }
        return await self._api_request("track/getFileUrl", params)

    async def _api_request(self, epoint: str, params: dict) -> tuple[int, dict]:
        """Make a request to the API.
        returns: status code, json parsed response
        """
        url = f"{QOBUZ_BASE_URL}/{epoint}"
        logger.debug("api_request: endpoint=%s, params=%s", epoint, params)
        if self.rate_limiter is not None:
            async with self.rate_limiter:
                async with self.session.get(url, params=params) as response:
                    return response.status, await response.json()
        # return await self.session.get(url, params=params)
        async with self.session.get(url, params=params) as response:
            resp_json = await response.json()
            return response.status, resp_json

    @staticmethod
    def get_quality(quality: int):
        quality_map = (5, 6, 7, 27)
        return quality_map[quality - 1]
