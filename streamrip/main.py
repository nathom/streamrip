import asyncio
import logging

from click import secho

from .client import Client
from .config import Config
from .media import Media, Pending
from .prompter import get_prompter
from .qobuz_client import QobuzClient
from .thread_pool import AsyncThreadPool
from .universal_url import parse_url

logger = logging.getLogger("streamrip")


class Main:
    """Provides all of the functionality called into by the CLI.

    * Logs in to Clients and prompts for credentials
    * Handles output logging
    * Handles downloading Media

    User input (urls) -> Main --> Download files & Output messages to terminal
    """

    def __init__(self, config: Config):
        # Pipeline:
        # input URL -> (URL) -> (Pending) -> (Media) -> (Downloadable) -> downloaded audio file
        self.pending: list[Pending] = []
        self.media: list[Media] = []

        self.config = config
        self.clients: dict[str, Client] = {
            "qobuz": QobuzClient(config),
            # "tidal": TidalClient(config),
            # "deezer": DeezerClient(config),
            # "soundcloud": SoundcloudClient(config),
            # "deezloader": DeezloaderClient(config),
        }

    async def add(self, url: str):
        parsed = parse_url(url)
        if parsed is None:
            secho(f"Unable to parse url {url}", fg="red")
            raise Exception

        client = await self.get_logged_in_client(parsed.source)
        self.pending.append(await parsed.into_pending(client, self.config))

    async def get_logged_in_client(self, source: str):
        client = self.clients[source]
        if not client.logged_in:
            prompter = get_prompter(client, self.config)
            if not prompter.has_creds():
                # Get credentials from user and log into client
                await prompter.prompt_and_login()
                prompter.save()
            else:
                # Log into client using credentials from config
                await client.login()

        assert client.logged_in
        return client

    async def resolve(self):
        logger.info(f"Resolving {len(self.pending)} items")
        assert len(self.pending) != 0
        coros = [p.resolve() for p in self.pending]
        new_media: list[Media] = await asyncio.gather(*coros)
        self.media.extend(new_media)
        self.pending.clear()
        assert len(self.pending) == 0

    async def rip(self):
        c = self.config.session.downloads
        if c.concurrency:
            max_connections = c.max_connections if c.max_connections > 0 else 9999
        else:
            max_connections = 1

        async with AsyncThreadPool(max_connections) as pool:
            await pool.gather([item.rip() for item in self.media])

        for client in self.clients.values():
            await client.session.close()
