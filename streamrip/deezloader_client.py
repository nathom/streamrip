from .client import Client


class DeezloaderClient(Client):
    source = "deezer"
    max_quality = 2

    def __init__(self, config):
        self.session = SRSession()
        self.global_config = config
        self.logged_in = True

    async def search(self, query: str, media_type: str, limit: int = 200):
        pass

    async def login(self):
        pass

    async def get(self, item_id: str, media_type: str):
        pass

    async def get_downloadable(self, item_id: str, quality: int):
        pass
