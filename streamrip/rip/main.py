import asyncio
import logging

from .. import db
from ..client import Client, QobuzClient, SoundcloudClient
from ..config import Config
from ..console import console
from ..media import Media, Pending, remove_artwork_tempdirs
from ..progress import clear_progress
from .parse_url import parse_url
from .prompter import get_prompter

logger = logging.getLogger("streamrip")


class Main:
    """Provides all of the functionality called into by the CLI.

    * Logs in to Clients and prompts for credentials
    * Handles output logging
    * Handles downloading Media

    User input (urls) -> Main --> Download files & Output messages to terminal
    """

    def __init__(self, config: Config):
        # Data pipeline:
        # input URL -> (URL) -> (Pending) -> (Media) -> (Downloadable) -> audio file
        self.pending: list[Pending] = []
        self.media: list[Media] = []
        self.config = config
        self.clients: dict[str, Client] = {
            "qobuz": QobuzClient(config),
            # "tidal": TidalClient(config),
            # "deezer": DeezerClient(config),
            "soundcloud": SoundcloudClient(config),
        }

        self.database: db.Database

        c = self.config.session.database
        if c.downloads_enabled:
            downloads_db = db.Downloads(c.downloads_path)
        else:
            downloads_db = db.Dummy()

        if c.failed_downloads_enabled:
            failed_downloads_db = db.Failed(c.failed_downloads_path)
        else:
            failed_downloads_db = db.Dummy()

        self.database = db.Database(downloads_db, failed_downloads_db)

    async def add(self, url: str):
        """Add url as a pending item.

        Do not `asyncio.gather` calls to this! Use `add_all` for concurrency.
        """
        parsed = parse_url(url)
        if parsed is None:
            raise Exception(f"Unable to parse url {url}")

        client = await self.get_logged_in_client(parsed.source)
        self.pending.append(
            await parsed.into_pending(client, self.config, self.database)
        )
        logger.debug("Added url=%s", url)

    async def add_all(self, urls: list[str]):
        parsed = [parse_url(url) for url in urls]
        url_w_client = [
            (p, await self.get_logged_in_client(p.source))
            for p in parsed
            if p is not None
        ]
        pendings = await asyncio.gather(
            *[
                url.into_pending(client, self.config, self.database)
                for url, client in url_w_client
            ]
        )
        self.pending.extend(pendings)

    async def get_logged_in_client(self, source: str):
        """Return a functioning client instance for `source`."""
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
                # await client.login()

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
            if hasattr(client, "session"):
                await client.session.close()

        # close global progress bar manager
        clear_progress()
        # We remove artwork tempdirs here because multiple singles
        # may be able to share downloaded artwork in the same `rip` session
        # We don't know that a cover will not be used again until end of execution
        remove_artwork_tempdirs()
