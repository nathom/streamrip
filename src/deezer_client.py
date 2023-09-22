class DeezerClient(Client):
    source = "deezer"
    max_quality = 2

    def __init__(self, config: Config):
        self.client = deezer.Deezer()
        self.logged_in = False
        self.config = config.deezer

    async def login(self):
        arl = self.config.arl
        if not arl:
            raise MissingCredentials
        success = self.client.login_via_arl(arl)
        if not success:
            raise AuthenticationError
        self.logged_in = True

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        pass

    async def search(
        self, query: str, media_type: str, limit: int = 200
    ) -> SearchResult:
        pass

    async def get_downloadable(self, item_id: str, quality: int = 2) -> Downloadable:
        pass
