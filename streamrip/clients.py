"""The clients that interact with the streaming service APIs."""

import base64
import binascii
import concurrent.futures
import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, Optional, Sequence, Tuple, Union

import deezer
from click import launch, secho
from Cryptodome.Cipher import AES

from rip.config import Config, QobuzConfig

from .constants import (
    AGENT,
    AVAILABLE_QUALITY_IDS,
    DEEZER_BASE,
    DEEZER_DL,
    DEEZER_FORMATS,
    QOBUZ_BASE,
    QOBUZ_FEATURED_KEYS,
    SOUNDCLOUD_BASE,
    SOUNDCLOUD_USER_ID,
    TIDAL_AUTH_URL,
    TIDAL_BASE,
    TIDAL_CLIENT_INFO,
    TIDAL_MAX_Q,
)
from .exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    InvalidQuality,
    MissingCredentials,
    NonStreamable,
)
from .spoofbuz import Spoofer
from .utils import gen_threadsafe_session, get_quality, safe_get

logger = logging.getLogger("streamrip")


class Downloadable(ABC):
    @abstractmethod
    async def download(self, path: str):
        raise NotImplemented


class BasicDownloadable(Downloadable):
    """Just downloads a URL."""

    def __init__(self, url: str):
        self.url = url

    async def download(self, path: str) -> bool:
        raise NotImplemented


class DeezerDownloadable(Downloadable):
    def __init__(self, resp: dict):
        self.resp = resp

    async def download(self, path: str) -> bool:
        raise NotImplemented


class TidalDownloadable(Downloadable):
    def __init__(self, info: dict):
        self.info = info

    async def download(self, path: str) -> bool:
        raise NotImplemented


class SoundcloudDownloadable(Downloadable):
    def __init__(self, info: dict):
        self.info = info

    async def download(self, path: str) -> bool:
        raise NotImplemented


class SearchResult(ABC):
    pass


class QobuzClient:
    source = "qobuz"
    max_quality = 4

    def __init__(self, config: Config):
        self.logged_in = False
        self.global_config = config
        self.config: QobuzConfig = config.qobuz
        self.session = None

    async def login(self):
        c = self.config
        if not c.email_or_userid or not c.password_or_token:
            raise MissingCredentials

        assert not self.logged_in

        if not c.app_id or not c.secrets:
            c.app_id, c.secrets = await self._fetch_app_id_and_secrets()
            self.global_config.set_modified()

        self.session = SRSession(
            headers={"User-Agent": AGENT, "X-App-Id": c.app_id},
            requests_per_min=self.global_config.downloads.requests_per_minute,
        )
        await self._validate_secrets(c.secrets)
        await self._api_login(c.use_auth_token, c.email_or_userid, c.password_or_token)
        self.logged_in = True

    async def get_metadata(self, item_id: str, media_type: str) -> Metadata:
        pass

    async def search(
        self, query: str, media_type: str, limit: int = 500
    ) -> SearchResult:
        pass

    async def get_downloadable(self, item_id: str, quality: int) -> Downloadable:
        pass

    async def _fetch_app_id_and_secrets(self) -> tuple[str, list[str]]:
        pass


class DeezerClient:
    source = "deezer"
    max_quality = 2

    def __init__(self, config: Config):
        self.client = deezer.Deezer()
        self.logged_in = False
        self.config = config.deezer

    async def login(self):
        arl = self.config.arl
        if not arl:
            raise MissingCredentials
        success = self.client.login_via_arl(arl)
        if not success:
            raise AuthenticationError
        self.logged_in = True

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        pass

    async def search(
        self, query: str, media_type: str, limit: int = 200
    ) -> SearchResult:
        pass

    async def get_downloadable(self, item_id: str, quality: int = 2) -> Downloadable:
        pass


class SoundcloudClient:
    source = "soundcloud"
    logged_in = False

    def __init__(self, config: Config):
        self.config = config.soundcloud

    async def login(self):
        client_id, app_version = self.config.client_id, self.config.app_version
        pass

    async def get_downloadable(self, track: dict, _) -> Downloadable:
        pass

    async def search(
        self, query: str, media_type: str, limit: int = 50, offset: int = 0
    ) -> SearchResult:
        pass


class DeezloaderClient:
    source = "deezer"
    max_quality = 2

    def __init__(self, config):
        self.session = SRSession()
        self.global_config = config
        self.logged_in = True

    async def search(
        self, query: str, media_type: str, limit: int = 200
    ) -> SearchResult:
        pass

    async def login(self):
        raise NotImplemented

    async def get(self, item_id: str, media_type: str):
        pass

    async def get_downloadable(self, item_id: str, quality: int):
        pass
