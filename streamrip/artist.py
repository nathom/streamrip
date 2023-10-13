class Artist(Media):
    name: str
    albums: list[Album]
    config: Config


class PendingArtist(Pending):
    id: str
    client: Client
