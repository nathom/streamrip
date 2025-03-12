"""The clients that interact with the streaming service APIs."""

import contextlib
import logging
from abc import ABC, abstractmethod

import aiohttp
import aiolimiter

from ..utils.ssl_utils import get_aiohttp_connector_kwargs
from .downloadable import Downloadable

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
    async def get_metadata(self, item_id: str, media_type: str):
        """Get metadata for the specified item.
        
        Args:
            item_id: The ID of the item to get metadata for
            media_type: The type of the item (e.g., "track", "album", etc.)
        """
        raise NotImplementedError

    @abstractmethod
    async def search(self, media_type: str, query: str, limit: int = 500) -> list[dict]:
        """Search for items of the specified type.
        
        Args:
            media_type: The type of item to search for
            query: The search query
            limit: Maximum number of results to return
            
        Returns:
            A list of dictionaries containing search results
        """
        raise NotImplementedError

    @abstractmethod
    async def get_downloadable(self, item_id: str, quality: int) -> Downloadable:
        """Get a downloadable object for the specified item.
        
        Args:
            item_id: The ID of the item to download
            quality: The quality level to download
            
        Returns:
            A Downloadable object for the item
        """
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
    async def get_session(
        headers: dict | None = None, verify_ssl: bool = True
    ) -> aiohttp.ClientSession:
        if headers is None:
            headers = {}

        # Get connector kwargs based on SSL verification setting
        connector_kwargs = get_aiohttp_connector_kwargs(verify_ssl=verify_ssl)
        
        # Create a merged dictionary with headers
        all_headers = {"User-Agent": DEFAULT_USER_AGENT}
        all_headers.update(headers)

        # Create the connector with appropriate SSL settings
        if "ssl" in connector_kwargs:
            # When using a custom SSL context
            ssl_context = connector_kwargs["ssl"]
            connector = aiohttp.TCPConnector(ssl=ssl_context)
        else:
            # When using verify_ssl boolean flag
            verify_ssl_flag = bool(connector_kwargs["verify_ssl"])
            connector = aiohttp.TCPConnector(verify_ssl=verify_ssl_flag)
        
        # Create and return the session
        return aiohttp.ClientSession(
            headers=all_headers,
            connector=connector,
        )
