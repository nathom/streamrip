import asyncio

loop = asyncio.new_event_loop()


def arun(coro):
    return loop.run_until_complete(coro)


def afor(async_gen):
    async def _afor(async_gen):
        l = []
        async for item in async_gen:
            l.append(item)
        return l

    return arun(_afor(async_gen))
