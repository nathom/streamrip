import asyncio
from typing import Any

import aiohttp
import aiohttp.log


class StreamRipClient(aiohttp.ClientSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_retries = 5
        self.retry_delay = 5

    async def _request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        for attempt in range(self.max_retries):
            try:
                response = await super()._request(method, url, **kwargs)
                if response.status != 429:
                    return response
                else:
                    aiohttp.log.client_logger.warning(
                        f"Rate limited. Retrying in {self.retry_delay} seconds..."
                    )
                    await asyncio.sleep(self.retry_delay)
            except aiohttp.ClientError:
                if attempt == self.max_retries - 1:
                    raise
                aiohttp.log.client_logger.warning(
                    f"Request failed. Retrying in {self.retry_delay} seconds..."
                )
                await asyncio.sleep(self.retry_delay)

        raise aiohttp.ClientError(f"Max retries ({self.max_retries}) exceeded")