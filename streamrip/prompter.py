import hashlib
import time
from abc import ABC, abstractmethod
from getpass import getpass

from click import launch, secho, style

from .client import Client
from .config import Config
from .deezer_client import DeezerClient
from .exceptions import AuthenticationError, MissingCredentials
from .qobuz_client import QobuzClient
from .tidal_client import TidalClient


class CredentialPrompter(ABC):
    client: Client

    def __init__(self, config: Config, client: Client):
        self.config = config
        self.client = self.type_check_client(client)

    @abstractmethod
    def has_creds(self) -> bool:
        raise NotImplemented

    @abstractmethod
    def prompt(self):
        """Prompt for credentials in the appropriate way,
        and save them to the configuration."""
        raise NotImplemented

    @abstractmethod
    def save(self):
        """Save current config to file"""
        raise NotImplemented

    @abstractmethod
    def type_check_client(self, client: Client):
        raise NotImplemented


class QobuzPrompter(CredentialPrompter):
    client: QobuzClient

    def has_creds(self) -> bool:
        c = self.config.session.qobuz
        return c.email_or_userid != "" and c.password_or_token != ""

    async def prompt(self):
        if not self.has_creds():
            self._prompt_creds_and_set_session_config()

        while True:
            try:
                await self.client.login()
                break
            except AuthenticationError:
                secho("Invalid credentials, try again.", fg="yellow")
                self._prompt_creds_and_set_session_config()
            except MissingCredentials:
                self._prompt_creds_and_set_session_config()

    def _prompt_creds_and_set_session_config(self):
        secho("Enter Qobuz email:", fg="green")
        email = input()
        secho(
            "Enter Qobuz password (will not show on screen):",
            fg="green",
        )
        pwd = hashlib.md5(getpass(prompt="").encode("utf-8")).hexdigest()
        secho(
            f'Credentials saved to config file at "{self.config._path}"',
            fg="green",
        )
        c = self.config.session.qobuz
        c.use_auth_token = False
        c.email_or_userid = email
        c.password_or_token = pwd

    def save(self):
        c = self.config.session.qobuz
        cf = self.config.file.qobuz
        cf.use_auth_token = False
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

    async def prompt(self):
        device_code = await self.client._get_device_code()
        login_link = f"https://{device_code}"

        secho(
            f"Go to {login_link} to log into Tidal within 5 minutes.",
            fg="blue",
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
                time.sleep(4)
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

    async def prompt(self):
        if not self.has_creds():
            self._prompt_creds_and_set_session_config()
        while True:
            try:
                await self.client.login()
                break
            except AuthenticationError:
                secho("Invalid arl, try again.", fg="yellow")
                self._prompt_creds_and_set_session_config()
        self.save()

    def _prompt_creds_and_set_session_config(self):
        secho(
            "If you're not sure how to find the ARL cookie, see the instructions at ",
            nl=False,
            dim=True,
        )
        secho(
            "https://github.com/nathom/streamrip/wiki/Finding-your-Deezer-ARL-Cookie",
            underline=True,
            fg="blue",
        )

        c = self.config.session.deezer
        c.arl = input(style("ARL: ", fg="green"))

    def save(self):
        c = self.config.session.deezer
        cf = self.config.file.deezer
        cf.arl = c.arl
        self.config.file.set_modified()
        secho(
            f'Credentials saved to config file at "{self.config._path}"',
            fg="green",
        )

    def type_check_client(self, client) -> DeezerClient:
        assert isinstance(client, DeezerClient)
        return client


PROMPTERS = {
    "qobuz": (QobuzPrompter, QobuzClient),
    "deezer": (DeezerPrompter, QobuzClient),
    "tidal": (TidalPrompter, QobuzClient),
}


def get_prompter(client: Client, config: Config):
    """Return an instance of a prompter."""
    p, c = PROMPTERS[client.source]
    assert isinstance(client, c)
    return p(config, client)
