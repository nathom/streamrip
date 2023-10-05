"""The clients that interact with the streaming service APIs."""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Union

import aiohttp
import aiolimiter

from .downloadable import Downloadable

logger = logging.getLogger("streamrip")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0"
)


class Client(ABC):
    source: str
    max_quality: int

    @abstractmethod
    async def login(self):
        raise NotImplemented

    @abstractmethod
    async def get_metadata(self, item: dict[str, Union[str, int, float]], media_type):
        raise NotImplemented

    @abstractmethod
    async def search(self, query: str, media_type: str, limit: int = 500):
        raise NotImplemented

    @abstractmethod
    async def get_downloadable(self, item_id: str, quality: int) -> Downloadable:
        raise NotImplemented

    @staticmethod
    def get_rate_limiter(
        requests_per_min: int,
    ) -> Optional[aiolimiter.AsyncLimiter]:
        return (
            aiolimiter.AsyncLimiter(requests_per_min, 60)
            if requests_per_min > 0
            else None
        )

    @staticmethod
    def get_session(headers: Optional[dict] = None) -> aiohttp.ClientSession:
        if headers is None:
            headers = {}
        return aiohttp.ClientSession(
            headers={"User-Agent": DEFAULT_USER_AGENT}, **headers
        )


class NonStreamable(Exception):
    pass


class MissingCredentials(Exception):
    pass


class AuthenticationError(Exception):
    pass
