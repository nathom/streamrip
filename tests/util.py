import asyncio

loop = asyncio.new_event_loop()


def arun(coro):
    return loop.run_until_complete(coro)


def afor(async_gen):
    async def _afor(async_gen):
        items = []
        async for item in async_gen:
            items.append(item)
        return items

    return arun(_afor(async_gen))
