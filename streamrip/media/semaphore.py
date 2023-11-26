import asyncio

from ..config import DownloadsConfig

INF = 9999


class UnlimitedSemaphore:
    """Can be swapped out for a real semaphore when no semaphore is needed."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


_unlimited = UnlimitedSemaphore()
_global_semaphore: None | tuple[int, asyncio.Semaphore] = None


def global_download_semaphore(
    c: DownloadsConfig,
) -> UnlimitedSemaphore | asyncio.Semaphore:
    """A global semaphore that limit the number of total tracks being downloaded
    at once.

    If concurrency is disabled in the config, the semaphore is set to 1.
    Otherwise it's set to `max_connections`.
    A negative `max_connections` value means there is no maximum and no semaphore is used.

    Since it is global, only one value of `max_connections` is allowed per session.
    """
    global _unlimited, _global_semaphore

    if c.concurrency:
        max_connections = c.max_connections if c.max_connections > 0 else INF
    else:
        max_connections = 1

    assert max_connections > 0
    if max_connections == INF:
        return _unlimited

    if _global_semaphore is None:
        _global_semaphore = (max_connections, asyncio.Semaphore(max_connections))

    assert (
        max_connections == _global_semaphore[0]
    ), f"Already have other global semaphore {_global_semaphore}"

    return _global_semaphore[1]
