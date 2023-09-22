import asyncio
import hashlib
import logging
import re
import time
from typing import AsyncGenerator, Optional

import aiohttp
from aiolimiter import AsyncLimiter

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

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0"
)
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
        self.session = aiohttp.ClientSession(headers={"User-Agent": DEFAULT_USER_AGENT})
        rate_limit = config.session.downloads.requests_per_minute
        self.rate_limiter = AsyncLimiter(rate_limit, 60) if rate_limit > 0 else None
        self.secret: Optional[str] = None

    async def login(self):
        c = self.config.session.qobuz
        if not c.email_or_userid or not c.password_or_token:
            raise MissingCredentials

        assert not self.logged_in, "Already logged in"

        if not c.app_id or not c.secrets:
            c.app_id, c.secrets = await self._get_app_id_and_secrets()
            # write to file
            self.config.file.qobuz.app_id = c.app_id
            self.config.file.qobuz.secrets = c.secrets
            self.config.file.set_modified()

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

        resp = await self._api_request("user/login", params)

        if resp.status == 401:
            raise AuthenticationError(f"Invalid credentials from params {params}")
        elif resp.status == 400:
            logger.debug(resp)
            raise InvalidAppIdError(f"Invalid app id from params {params}")

        logger.info("Logged in to Qobuz")

        resp_json = await resp.json()

        if not resp_json["user"]["credential"]["parameters"]:
            raise IneligibleError("Free accounts are not eligible to download tracks.")

        uat = resp_json["user_auth_token"]
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

        response = await self._api_request(epoint, params)
        resp_json = await response.json()

        if response.status != 200:
            raise Exception(f'Error fetching metadata. "{resp_json["message"]}"')

        return resp_json

    async def search(
        self, query: str, media_type: str, limit: int = 500
    ) -> AsyncGenerator:
        params = {
            "query": query,
            "limit": limit,
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

        return self._paginate(epoint, params)

    async def get_downloadable(self, item_id: str, quality: int) -> Downloadable:
        assert self.secret is not None and self.logged_in and 1 <= quality <= 4

        resp = await self._request_file_url(item_id, quality, self.secret)
        resp_json = await resp.json()
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

        return BasicDownloadable(stream_url)

    async def _paginate(self, epoint: str, params: dict) -> AsyncGenerator[dict, None]:
        response = await self._api_request(epoint, params)
        page = await response.json()
        logger.debug("Keys returned from _gen_pages: %s", ", ".join(page.keys()))
        key = epoint.split("/")[0] + "s"
        total = page.get(key, {})
        total = total.get("total") or total.get("items")

        if not total:
            logger.debug("Nothing found from %s epoint", epoint)
            return

        limit = page.get(key, {}).get("limit", 500)
        offset = page.get(key, {}).get("offset", 0)
        params.update({"limit": limit})
        yield page
        while (offset + limit) < total:
            offset += limit
            params.update({"offset": offset})
            response = await self._api_request(epoint, params)
            yield await response.json()

    async def _get_app_id_and_secrets(self) -> tuple[str, list[str]]:
        spoofer = QobuzSpoofer()
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
        resp = await self._request_file_url("19512574", 1, secret)
        if resp.status == 400:
            return None
        resp.raise_for_status()
        return secret

    async def _request_file_url(
        self, track_id: str, quality: int, secret: str
    ) -> aiohttp.ClientResponse:
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

    async def _api_request(self, epoint: str, params: dict) -> aiohttp.ClientResponse:
        url = f"{QOBUZ_BASE_URL}/{epoint}"
        if self.rate_limiter is not None:
            async with self.rate_limiter:
                async with self.session.get(url, params=params) as response:
                    return response
        async with self.session.get(url, params=params) as response:
            return response
