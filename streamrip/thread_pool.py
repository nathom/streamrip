import asyncio


class AsyncThreadPool:
    """Allows a maximum of `max_workers` coroutines to be running at once."""

    def __init__(self, max_workers: int):
        self.s = asyncio.Semaphore(max_workers)

    async def gather(self, coros: list):
        async def _wrapper(coro):
            async with self.s:
                await coro

        return await asyncio.gather(*(_wrapper(c) for c in coros))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass
