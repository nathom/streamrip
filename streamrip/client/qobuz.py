import asyncio
import base64
import hashlib
import logging
import re
import time
from collections import OrderedDict
from typing import List, Optional

import aiohttp

from ..config import Config
from ..exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    MissingCredentialsError,
    NonStreamableError,
)
from .client import Client
from .downloadable import BasicDownloadable, Downloadable

logger = logging.getLogger("streamrip")

QOBUZ_BASE_URL = "https://www.qobuz.com/api.json/0.2"

class QobuzSpoofer:
    """Spoofs the information required to stream tracks from Qobuz."""

    def __init__(self):
        self.seed_timezone_regex = (
            r'[a-z]\.initialSeed\("(?P<seed>[\w=]+)",window\.ut'
            r"imezone\.(?P<timezone>[a-z]+)\)"
        )
        self.info_extras_regex = (
            r'name:"\w+/(?P<timezone>{timezones})",info:"'
            r'(?P<info>[\w=]+)",extras:"(?P<extras>[\w=]+)"'
        )
        self.app_id_regex = (
            r'production:{api:{appId:"(?P<app_id>\d{9})",appSecret:"(\w{32})'
        )
        self.session = None

    async def get_app_id_and_secrets(self) -> tuple[str, list[str]]:
        """Fetches app_id and secrets from Qobuz web page."""
        assert self.session is not None
        async with self.session.get("https://play.qobuz.com/login") as req:
            login_page = await req.text()

        bundle_url_match = re.search(
            r'<script src="(/resources/\d+\.\d+\.\d+-[a-z]\d{3}/bundle\.js)"></script>',
            login_page,
        )
        assert bundle_url_match is not None
        bundle_url = bundle_url_match.group(1)

        async with self.session.get("https://play.qobuz.com" + bundle_url) as req:
            self.bundle = await req.text()

        match = re.search(self.app_id_regex, self.bundle)
        if match is None:
            raise Exception("Could not find app id.")

        app_id = str(match.group("app_id"))

        # get secrets
        seed_matches = re.finditer(self.seed_timezone_regex, self.bundle)
        secrets = OrderedDict()
        for match in seed_matches:
            seed, timezone = match.group("seed", "timezone")
            secrets[timezone] = [seed]

        keypairs = list(secrets.items())
        secrets.move_to_end(keypairs[1][0], last=False)

        info_extras_regex = self.info_extras_regex.format(
            timezones="|".join(timezone.capitalize() for timezone in secrets),
        )
        info_extras_matches = re.finditer(info_extras_regex, self.bundle)
        for match in info_extras_matches:
            timezone, info, extras = match.group("timezone", "info", "extras")
            secrets[timezone.lower()] += [info, extras]

        for secret_pair in secrets:
            secrets[secret_pair] = base64.standard_b64decode(
                "".join(secrets[secret_pair])[:-44],
            ).decode("utf-8")

        vals: List[str] = list(secrets.values())
        if "" in vals:
            vals.remove("")

        secrets_list = vals

        return app_id, secrets_list

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *_):
        if self.session is not None:
            await self.session.close()
        self.session = None


class QobuzClient(Client):
    source = "qobuz"
    max_quality = 4

    def __init__(self, config: Config):
        """Initialize QobuzClient with config, rate limiter, and secret placeholder."""
        self.logged_in = False
        self.config = config
        self.rate_limiter = self.get_rate_limiter(
            config.session.downloads.requests_per_minute,
        )
        self.secret: Optional[str] = None

    async def login(self):
        """Logs into Qobuz using provided credentials in config."""
        self.session = await self.get_session()
        c = self.config.session.qobuz
        if not c.email_or_userid or not c.password_or_token:
            raise MissingCredentialsError

        assert not self.logged_in, "Already logged in"

        if not c.app_id or not c.secrets:
            logger.info("App id/secrets not found, fetching")
            c.app_id, c.secrets = await self._get_app_id_and_secrets()
            # Save app_id and secrets in the config file
            f = self.config.file
            f.qobuz.app_id = c.app_id
            f.qobuz.secrets = c.secrets
            f.set_modified()

        # Update session headers with app ID
        self.session.headers.update({"X-App-Id": str(c.app_id)})

        # Prepare login parameters based on whether an auth token is used
        if c.use_auth_token:
            params = {
                "user_id": c.email_or_userid,
                "user_auth_token": c.password_or_token,
                "app_id": str(c.app_id),
            }
        else:
            params = {
                "email": c.email_or_userid,
                "password": c.password_or_token,
                "app_id": str(c.app_id),
            }

        status, resp = await self._api_request("user/login", params)

        # Handle potential login errors
        if status == 401:
            raise AuthenticationError(f"Invalid credentials from params {params}")
        elif status == 400:
            raise InvalidAppIdError(f"Invalid app id from params {params}")

        # Check if account type is eligible for downloads
        if not resp["user"]["credential"]["parameters"]:
            raise IneligibleError("Free accounts are not eligible to download tracks.")

        # Save user auth token for authenticated requests
        uat = resp["user_auth_token"]
        self.session.headers.update({"X-User-Auth-Token": uat})

        # Retrieve and set a valid secret
        self.secret = await self._get_valid_secret(c.secrets)
        self.logged_in = True

    async def get_downloadable(self, item: str, quality: int) -> Downloadable:
        """Gets downloadable track URL and quality information."""
        assert self.secret is not None and self.logged_in and 1 <= quality <= 4
        status, resp_json = await self._request_file_url(item, quality, self.secret)
        assert status == 200
        stream_url = resp_json.get("url")

        if stream_url is None:
            restrictions = resp_json["restrictions"]
            if restrictions:
                # Generate error message from restriction codes
                words = re.findall(r"([A-Z][a-z]+)", restrictions[0]["code"])
                raise NonStreamableError(
                    words[0] + " " + " ".join(map(str.lower, words[1:])) + ".",
                )
            raise NonStreamableError

        # BasicDownloadable çağrısında source parametresini kaldırdık
        return BasicDownloadable(self.session, stream_url, "flac" if quality > 1 else "mp3")

    async def get_metadata(self, item: str, media_type: str):
        """Fetches metadata for a specific media item."""
        c = self.config.session.qobuz
        params = {
            "app_id": str(c.app_id),
            f"{media_type}_id": item,
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
        epoint = f"{media_type}/get"
        status, resp = await self._api_request(epoint, params)

        if status != 200:
            raise NonStreamableError(
                f'Error fetching metadata. Message: "{resp["message"]}"',
            )
        return resp

    async def search(self, media_type: str, query: str, limit: int = 500) -> list[dict]:
        """Searches Qobuz for items of the specified media type."""
        if media_type not in ("artist", "album", "track", "playlist"):
            raise Exception(f"{media_type} not available for search on qobuz")

        params = {
            "query": query,
        }
        epoint = f"{media_type}/search"
        return await self._paginate(epoint, params, limit=limit)

    async def _paginate(
        self,
        epoint: str,
        params: dict,
        limit: int = 500,
    ) -> list[dict]:
        """Paginates search results to handle API limits on item count."""
        params.update({"limit": limit})
        status, page = await self._api_request(epoint, params)
        assert status == 200, status
        key = epoint.split("/")[0] + "s"
        items = page.get(key, {})
        total = items.get("total", 0)
        if limit is not None and limit < total:
            total = limit

        limit = int(page.get(key, {}).get("limit", 500))
        offset = int(page.get(key, {}).get("offset", 0))

        pages = [page]
        requests = []
        while (offset + limit) < total:
            offset += limit
            params.update({"offset": offset})
            requests.append(self._api_request(epoint, params.copy()))

        for status, resp in await asyncio.gather(*requests):
            assert status == 200
            pages.append(resp)

        return pages

    async def _get_app_id_and_secrets(self) -> tuple[str, list[str]]:
        """Fetches app_id and secrets using QobuzSpoofer."""
        async with QobuzSpoofer() as spoofer:
            return await spoofer.get_app_id_and_secrets()

    async def _get_valid_secret(self, secrets: list[str]) -> str:
        """Retrieves a working secret by testing each available secret."""
        results = await asyncio.gather(
            *[self._test_secret(secret) for secret in secrets],
        )
        working_secrets = [r for r in results if r is not None]

        if len(working_secrets) == 0:
            raise InvalidAppSecretError(secrets)

        return working_secrets[0]

    async def _test_secret(self, secret: str) -> Optional[str]:
        """Tests if a provided secret is valid for accessing Qobuz API."""
        status, _ = await self._request_file_url("19512574", 4, secret)
        if status == 400:
            return None
        if status == 200:
            return secret
        logger.warning("Got status %d when testing secret", status)
        return None

    async def _request_file_url(
        self,
        track_id: str,
        quality: int,
        secret: str,
    ) -> tuple[int, dict]:
        """Requests file URL from Qobuz API based on track ID and quality."""
        quality = self.get_quality(quality)
        unix_ts = time.time()
        r_sig = f"trackgetFileUrlformat_id{quality}intentstreamtrack_id{track_id}{unix_ts}{secret}"
        r_sig_hashed = hashlib.md5(r_sig.encode("utf-8")).hexdigest()
        params = {
            "request_ts": unix_ts,
            "request_sig": r_sig_hashed,
            "track_id": track_id,
            "format_id": quality,
            "intent": "stream",
        }
        return await self._api_request("track/getFileUrl", params)

    async def _api_request(self, epoint: str, params: dict) -> tuple[int, dict]:
        """Makes an authenticated request to the Qobuz API and returns status and JSON response."""
        url = f"{QOBUZ_BASE_URL}/{epoint}"
        async with self.rate_limiter:
            async with self.session.get(url, params=params) as response:
                return response.status, await response.json()

    @staticmethod
    def get_quality(quality: int):
        """Maps quality to appropriate format ID for Qobuz API requests."""
        quality_map = (5, 6, 7, 27)
        return quality_map[quality - 1]
