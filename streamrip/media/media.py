import asyncio
import logging
from abc import ABC, abstractmethod


class Media(ABC):
    async def rip(self):
        await self.preprocess()
        await self.download()
        await self.postprocess()

    @abstractmethod
    async def preprocess(self):
        """Create directories, download cover art, etc."""
        raise NotImplementedError

    @abstractmethod
    async def download(self):
        """Download and tag the actual audio files in the correct directories."""
        raise NotImplementedError

    @abstractmethod
    async def postprocess(self):
        """Update database, run conversion, delete garbage files etc."""
        raise NotImplementedError


class Pending(ABC):
    """A request to download a `Media` whose metadata has not been fetched."""

    @abstractmethod
    async def resolve(self) -> Media | None:
        """Fetch metadata and resolve into a downloadable `Media` object."""
        raise NotImplementedError


def _active_rip_limit(config, total: int) -> int:
    downloads = config.session.downloads
    if not getattr(downloads, "concurrency", False):
        return 1

    max_connections = getattr(downloads, "max_connections", total)
    if isinstance(max_connections, int) and max_connections > 0:
        return max_connections

    return max(total, 1)


async def rip_pending_items_in_order(
    pending_items: list[Pending],
    config,
    logger: logging.Logger,
    error_message: str = "Error downloading track",
):
    active: set[asyncio.Task] = set()
    limit = _active_rip_limit(config, len(pending_items))

    async def _rip(media: Media):
        try:
            await media.rip()
        except Exception as e:
            logger.error("%s: %s", error_message, e)

    async def _wait_for_one():
        nonlocal active
        done, active = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task

    for pending in pending_items:
        try:
            media = await pending.resolve()
        except Exception as e:
            logger.error("%s: %s", error_message, e)
            continue

        if media is None:
            continue

        active.add(asyncio.create_task(_rip(media)))
        await asyncio.sleep(0)

        if len(active) >= limit:
            await _wait_for_one()

    if active:
        await asyncio.gather(*active)
