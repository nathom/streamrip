TIDAL_COVER_URL = "https://resources.tidal.com/images/{uuid}/{width}x{height}.jpg"


class Covers:
    COVER_SIZES = ("thumbnail", "small", "large", "original")
    CoverEntry = tuple[str, str | None, str | None]
    _covers: list[CoverEntry]

    def __init__(self):
        # ordered from largest to smallest
        self._covers = [
            ("original", None, None),
            ("large", None, None),
            ("small", None, None),
            ("thumbnail", None, None),
        ]

    def set_cover(self, size: str, url: str | None, path: str | None):
        i = self._indexof(size)
        self._covers[i] = (size, url, path)

    def set_cover_url(self, size: str, url: str):
        self.set_cover(size, url, None)

    @staticmethod
    def _indexof(size: str) -> int:
        if size == "original":
            return 0
        if size == "large":
            return 1
        if size == "small":
            return 2
        if size == "thumbnail":
            return 3
        raise Exception(f"Invalid {size = }")

    def empty(self) -> bool:
        return all(url is None for _, url, _ in self._covers)

    def set_largest_path(self, path: str):
        for size, url, _ in self._covers:
            if url is not None:
                self.set_cover(size, url, path)
                return
        raise Exception(f"No covers found in {self}")

    def set_path(self, size: str, path: str):
        i = self._indexof(size)
        size, url, _ = self._covers[i]
        self._covers[i] = (size, url, path)

    def largest(self) -> CoverEntry:
        for s, u, p in self._covers:
            if u is not None:
                return (s, u, p)

        raise Exception(f"No covers found in {self}")

    @classmethod
    def from_qobuz(cls, resp):
        img = resp["image"]

        c = cls()
        c.set_cover_url("original", "org".join(img["large"].rsplit("600", 1)))
        c.set_cover_url("large", img["large"])
        c.set_cover_url("small", img["small"])
        c.set_cover_url("thumbnail", img["thumbnail"])
        return c

    @classmethod
    def from_deezer(cls, resp):
        c = cls()
        c.set_cover_url("original", resp["cover_xl"])
        c.set_cover_url("large", resp["cover_big"])
        c.set_cover_url("small", resp["cover_medium"])
        c.set_cover_url("thumbnail", resp["cover_small"])
        return c

    @classmethod
    def from_soundcloud(cls, resp):
        c = cls()
        cover_url = (resp["artwork_url"] or resp["user"].get("avatar_url")).replace(
            "large",
            "t500x500",
        )
        c.set_cover_url("large", cover_url)
        return c

    @classmethod
    def from_tidal(cls, resp):
        uuid = resp["cover"]
        if not uuid:
            return None

        c = cls()
        for size_name, dimension in zip(cls.COVER_SIZES, (160, 320, 640, 1280)):
            c.set_cover_url(size_name, cls._get_tidal_cover_url(uuid, dimension))
        return c

    def get_size(self, size: str) -> CoverEntry:
        i = self._indexof(size)
        size, url, path = self._covers[i]
        if url is not None:
            return (size, url, path)
        if i + 1 < len(self._covers):
            for s, u, p in self._covers[i + 1 :]:
                if u is not None:
                    return (s, u, p)
        raise Exception(f"Cover not found for {size = }. Available: {self}")

    @staticmethod
    def _get_tidal_cover_url(uuid, size):
        """Generate a tidal cover url.

        :param uuid: VALID uuid string
        :param size:
        """
        possibles = (80, 160, 320, 640, 1280)
        assert size in possibles, f"size must be in {possibles}"
        return TIDAL_COVER_URL.format(
            uuid=uuid.replace("-", "/"),
            height=size,
            width=size,
        )

    def __repr__(self):
        covers = "\n".join(map(repr, self._covers))
        return f"Covers({covers})"
