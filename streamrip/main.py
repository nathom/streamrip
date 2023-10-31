import asyncio
import logging

from .client import Client
from .config import Config
from .console import console
from .media import Media, Pending
from .progress import clear_progress
from .prompter import get_prompter
from .qobuz_client import QobuzClient
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
        # input URL -> (URL) -> (Pending) -> (Media) -> (Downloadable)
        # -> downloaded audio file
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
            raise Exception(f"Unable to parse url {url}")

        client = await self.get_logged_in_client(parsed.source)
        self.pending.append(await parsed.into_pending(client, self.config))
        logger.debug("Added url=%s", url)

    async def get_logged_in_client(self, source: str):
        client = self.clients[source]
        if not client.logged_in:
            prompter = get_prompter(client, self.config)
            if not prompter.has_creds():
                # Get credentials from user and log into client
                await prompter.prompt_and_login()
                prompter.save()
            else:
                with console.status(f"[cyan]Logging into {source}", spinner="dots"):
                    # Log into client using credentials from config
                    await client.login()

        assert client.logged_in
        return client

    async def resolve(self):
        with console.status("Resolving URLs...", spinner="dots"):
            coros = [p.resolve() for p in self.pending]
            new_media: list[Media] = await asyncio.gather(*coros)

        self.media.extend(new_media)
        self.pending.clear()

    async def rip(self):
        await asyncio.gather(*[item.rip() for item in self.media])

        for client in self.clients.values():
            await client.session.close()

        clear_progress()
