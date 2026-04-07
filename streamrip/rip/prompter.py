import asyncio
import logging
import time
from abc import ABC, abstractmethod

from click import launch
from rich.prompt import Confirm, Prompt

from ..client import Client, DeezerClient, QobuzClient, SoundcloudClient, TidalClient
from ..config import Config
from ..console import console
from ..exceptions import AuthenticationError, MissingCredentialsError

logger = logging.getLogger("streamrip")


class CredentialPrompter(ABC):
    client: Client

    def __init__(self, config: Config, client: Client):
        self.config = config
        self.client = self.type_check_client(client)

    @abstractmethod
    def has_creds(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def prompt_and_login(self):
        """Prompt for credentials in the appropriate way,
        and save them to the configuration.
        """
        raise NotImplementedError

    @abstractmethod
    def save(self):
        """Save current config to file"""
        raise NotImplementedError

    @abstractmethod
    def type_check_client(self, client: Client):
        raise NotImplementedError


class QobuzPrompter(CredentialPrompter):
    client: QobuzClient

    def has_creds(self) -> bool:
        c = self.config.session.qobuz
        if not c.email_or_userid or not c.password_or_token:
            return False
        # Legacy email+md5 credentials no longer work — force re-prompt
        if not c.use_auth_token:
            return False
        return True

    async def prompt_and_login(self):
        if not self.has_creds():
            await self._prompt_creds_and_set_session_config()

        while True:
            try:
                await self.client.login()
                break
            except AuthenticationError:
                console.print(
                    "[yellow]Invalid Qobuz token or user id. "
                    "The token may have expired, please refresh it from your browser.[/yellow]"
                )
                await self._prompt_creds_and_set_session_config()
            except MissingCredentialsError:
                await self._prompt_creds_and_set_session_config()

    async def _prompt_creds_and_set_session_config(self):
        console.print(
            "[cyan]Qobuz now requires token-based login.[/cyan]\n"
            "1) Log in at qobuz.com or play.qobuz.com\n"
            "2) Open browser DevTools -> Network\n"
            "3) Find a request to [bold]www.qobuz.com/api.json[/bold]\n"
            "4) Copy [bold]X-User-Auth-Token[/bold] from the request headers"
        )
        if Confirm.ask("Open Qobuz login page in your browser now?", default=True):
            launch("https://play.qobuz.com/login")

        # Ensure we have an app_id to resolve the user ID
        c = self.config.session.qobuz
        if not c.app_id or not c.secrets:
            console.print("[cyan]Fetching app credentials...[/cyan]")
            c.app_id, c.secrets = await self.client._get_app_id_and_secrets()
            f = self.config.file
            f.qobuz.app_id = c.app_id
            f.qobuz.secrets = c.secrets
            f.set_modified()

        verify_ssl = self.config.session.downloads.verify_ssl

        while True:
            token = Prompt.ask("Enter your Qobuz user_auth_token", password=True)
            console.print("[cyan]Resolving user ID from token...[/cyan]")
            try:
                user_id = await QobuzClient.resolve_user_id(
                    token, str(c.app_id), verify_ssl=verify_ssl
                )
            except AuthenticationError:
                console.print(
                    "[yellow]Token appears invalid or expired. Please try again.[/yellow]"
                )
                continue
            break

        console.print(f"[green]Found user ID: {user_id}[/green]")

        c.use_auth_token = True
        c.email_or_userid = user_id
        c.password_or_token = token
        console.print(
            f"[green]Credentials saved to config file at [bold cyan]{self.config.path}",
        )

    def save(self):
        c = self.config.session.qobuz
        cf = self.config.file.qobuz
        cf.use_auth_token = True
        cf.email_or_userid = c.email_or_userid
        cf.password_or_token = c.password_or_token
        self.config.file.set_modified()

    def type_check_client(self, client) -> QobuzClient:
        assert isinstance(client, QobuzClient)
        return client


class TidalPrompter(CredentialPrompter):
    timeout_s: int = 600  # 5 mins to login
    client: TidalClient

    def has_creds(self) -> bool:
        return len(self.config.session.tidal.access_token) > 0

    async def prompt_and_login(self):
        device_code, uri = await self.client._get_device_code()
        login_link = f"https://{uri}"

        console.print(
            f"Go to [blue underline]{login_link}[/blue underline] to log into Tidal within 5 minutes.",
        )
        launch(login_link)

        start = time.time()
        elapsed = 0.0
        info = {}
        while elapsed < self.timeout_s:
            elapsed = time.time() - start
            status, info = await self.client._get_auth_status(device_code)
            if status == 2:
                # pending
                await asyncio.sleep(4)
                continue
            elif status == 0:
                # successful
                break
            else:
                raise Exception

        c = self.config.session.tidal
        c.user_id = info["user_id"]  # type: ignore
        c.country_code = info["country_code"]  # type: ignore
        c.access_token = info["access_token"]  # type: ignore
        c.refresh_token = info["refresh_token"]  # type: ignore
        c.token_expiry = info["token_expiry"]  # type: ignore

        self.client._update_authorization_from_config()
        self.client.logged_in = True
        self.save()

    def type_check_client(self, client) -> TidalClient:
        assert isinstance(client, TidalClient)
        return client

    def save(self):
        c = self.config.session.tidal
        cf = self.config.file.tidal
        cf.user_id = c.user_id
        cf.country_code = c.country_code
        cf.access_token = c.access_token
        cf.refresh_token = c.refresh_token
        cf.token_expiry = c.token_expiry
        self.config.file.set_modified()


class DeezerPrompter(CredentialPrompter):
    client: DeezerClient

    def has_creds(self):
        c = self.config.session.deezer
        return c.arl != ""

    async def prompt_and_login(self):
        if not self.has_creds():
            self._prompt_creds_and_set_session_config()
        while True:
            try:
                await self.client.login()
                break
            except AuthenticationError:
                console.print("[yellow]Invalid arl, try again.")
                self._prompt_creds_and_set_session_config()
        self.save()

    def _prompt_creds_and_set_session_config(self):
        console.print(
            "If you're not sure how to find the ARL cookie, see the instructions at ",
            "[blue underline]https://github.com/nathom/streamrip/wiki/Finding-your-Deezer-ARL-Cookie",
        )
        c = self.config.session.deezer
        c.arl = Prompt.ask("Enter your [bold]ARL")

    def save(self):
        c = self.config.session.deezer
        cf = self.config.file.deezer
        cf.arl = c.arl
        self.config.file.set_modified()
        console.print(
            f"[green]Credentials saved to config file at [bold cyan]{self.config.path}",
        )

    def type_check_client(self, client) -> DeezerClient:
        assert isinstance(client, DeezerClient)
        return client


class SoundcloudPrompter(CredentialPrompter):
    def has_creds(self) -> bool:
        return True

    async def prompt_and_login(self):
        pass

    def save(self):
        pass

    def type_check_client(self, client) -> SoundcloudClient:
        assert isinstance(client, SoundcloudClient)
        return client


PROMPTERS = {
    "qobuz": QobuzPrompter,
    "deezer": DeezerPrompter,
    "tidal": TidalPrompter,
    "soundcloud": SoundcloudPrompter,
}


def get_prompter(client: Client, config: Config) -> CredentialPrompter:
    """Return an instance of a prompter."""
    p = PROMPTERS[client.source]
    return p(config, client)
