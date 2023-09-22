from .client import Client
from .config import Config
from .downloadable import Downloadable


class SoundcloudClient(Client):
    source = "soundcloud"
    logged_in = False

    def __init__(self, config: Config):
        self.config = config.soundcloud

    async def login(self):
        client_id, app_version = self.config.client_id, self.config.app_version
        pass

    async def get_downloadable(self, track: dict, _) -> Downloadable:
        pass

    async def search(
        self, query: str, media_type: str, limit: int = 50, offset: int = 0
    ):
        pass
