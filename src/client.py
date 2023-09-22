"""The clients that interact with the streaming service APIs."""

import logging
from abc import ABC, abstractmethod

from .downloadable import Downloadable

logger = logging.getLogger("streamrip")


class Client(ABC):
    source: str
    max_quality: int

    @abstractmethod
    async def login(self):
        raise NotImplemented

    @abstractmethod
    async def get_metadata(self, item_id, media_type):
        raise NotImplemented

    @abstractmethod
    async def search(self, query: str, media_type: str, limit: int = 500):
        raise NotImplemented

    @abstractmethod
    async def get_downloadable(self, item_id: str, quality: int) -> Downloadable:
        raise NotImplemented
