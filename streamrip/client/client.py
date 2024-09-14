"""The clients that interact with the streaming service APIs."""

import contextlib
import logging
from abc import ABC, abstractmethod

import aiohttp
import aiolimiter

from .downloadable import Downloadable
from .ripClient import StreamRipClient

logger = logging.getLogger("streamrip")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0"
)


class Client(ABC):
    source: str
    max_quality: int
    session: aiohttp.ClientSession
    logged_in: bool

    @abstractmethod
    async def login(self):
        raise NotImplementedError

    @abstractmethod
    async def get_metadata(self, item: str, media_type):
        raise NotImplementedError

    @abstractmethod
    async def search(self, media_type: str, query: str, limit: int = 500) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def get_downloadable(self, item: str, quality: int) -> Downloadable:
        raise NotImplementedError

    @staticmethod
    def get_rate_limiter(
        requests_per_min: int,
    ) -> aiolimiter.AsyncLimiter | contextlib.nullcontext:
        return (
            aiolimiter.AsyncLimiter(requests_per_min, 60)
            if requests_per_min > 0
            else contextlib.nullcontext()
        )

    @staticmethod
    async def get_session(headers: dict | None = None) -> aiohttp.ClientSession:
        if headers is None:
            headers = {}
        # return aiohttp.ClientSession(
        #    headers={"User-Agent": DEFAULT_USER_AGENT},
        #    **headers,
        # )

        return StreamRipClient(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            **headers,
        )
