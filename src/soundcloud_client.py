import re

from .client import Client, NonStreamable
from .config import Config
from .downloadable import SoundcloudDownloadable

BASE = "https://api-v2.soundcloud.com"
SOUNDCLOUD_USER_ID = "672320-86895-162383-801513"


class SoundcloudClient(Client):
    source = "soundcloud"
    logged_in = False

    def __init__(self, config: Config):
        self.global_config = config
        self.config = config.session.soundcloud
        self.session = self.get_session()
        self.rate_limiter = self.get_rate_limiter(
            config.session.downloads.requests_per_minute
        )

    async def login(self):
        client_id, app_version = self.config.client_id, self.config.app_version
        if not client_id or not app_version or not self._announce():
            client_id, app_version = await self._refresh_tokens()

        # update file and session configs and save to disk
        c = self.global_config.file.soundcloud
        self.config.client_id = c.client_id = client_id
        self.config.client_id = c.app_version = app_version
        self.global_config.file.set_modified()

    async def _announce(self):
        resp = await self._api_request("announcements")
        return resp.status == 200

    async def _refresh_tokens(self) -> tuple[str, str]:
        """Return a valid client_id, app_version pair."""
        STOCK_URL = "https://soundcloud.com/"
        async with self.session.get(STOCK_URL) as resp:
            page_text = await resp.text(encoding="utf-8")

        *_, client_id_url_match = re.finditer(
            r"<script\s+crossorigin\s+src=\"([^\"]+)\"", page_text
        )

        if client_id_url_match is None:
            raise Exception("Could not find client ID in %s" % STOCK_URL)

        client_id_url = client_id_url_match.group(1)

        app_version_match = re.search(
            r'<script>window\.__sc_version="(\d+)"</script>', page_text
        )
        if app_version_match is None:
            raise Exception("Could not find app version in %s" % client_id_url_match)
        app_version = app_version_match.group(1)

        async with self.session.get(client_id_url) as resp:
            page_text2 = await resp.text(encoding="utf-8")

        client_id_match = re.search(r'client_id:\s*"(\w+)"', page_text2)
        assert client_id_match is not None
        client_id = client_id_match.group(1)

        return client_id, app_version

    async def get_downloadable(self, item: dict, _) -> SoundcloudDownloadable:
        if not item["streamable"] or item["policy"] == "BLOCK":
            raise NonStreamable(item)

        if item["downloadable"] and item["has_downloads_left"]:
            resp = await self._api_request(f"tracks/{item['id']}/download")
            resp_json = await resp.json()
            return SoundcloudDownloadable(
                {"url": resp_json["redirectUri"], "type": "original"}
            )

        else:
            url = None
            for tc in item["media"]["transcodings"]:
                fmt = tc["format"]
                if fmt["protocol"] == "hls" and fmt["mime_type"] == "audio/mpeg":
                    url = tc["url"]
                    break

            assert url is not None

            resp = await self._request(url)
            resp_json = await resp.json()
            return SoundcloudDownloadable({"url": resp_json["url"], "type": "mp3"})

    async def search(
        self, query: str, media_type: str, limit: int = 50, offset: int = 0
    ):
        params = {
            "q": query,
            "facet": "genre",
            "user_id": SOUNDCLOUD_USER_ID,
            "limit": limit,
            "offset": offset,
            "linked_partitioning": "1",
        }
        resp = await self._api_request(f"search/{media_type}s", params=params)
        return await resp.json()

    async def _api_request(self, path, params=None, headers=None):
        url = f"{BASE}/{path}"
        return await self._request(url, params=params, headers=headers)

    async def _request(self, url, params=None, headers=None):
        c = self.config
        _params = {
            "client_id": c.client_id,
            "app_version": c.app_version,
            "app_locale": "en",
        }
        if params is not None:
            _params.update(params)

        async with self.session.get(url, params=_params, headers=headers) as resp:
            return resp

    async def _resolve_url(self, url: str) -> dict:
        resp = await self._api_request(f"resolve?url={url}")
        return await resp.json()
