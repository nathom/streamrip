import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DownloadStats:
    """Accumulates per-session download metrics.

    Attributes:
        tracks_downloaded: Number of tracks successfully downloaded and tagged.
        tracks_failed: Number of tracks that raised an exception during rip().
        bytes_downloaded: Total on-disk size of successfully downloaded files.
    """

    tracks_downloaded: int = field(default=0)
    tracks_failed: int = field(default=0)
    bytes_downloaded: int = field(default=0)

    def record_success(self, path: str) -> None:
        """Record a successful track download.

        Args:
            path: Absolute path to the final downloaded (and possibly converted) file.
        """
        self.tracks_downloaded += 1
        try:
            self.bytes_downloaded += os.path.getsize(path)
        except OSError:
            pass

    def record_failure(self) -> None:
        """Record a failed track download."""
        self.tracks_failed += 1


class Media(ABC):
    async def rip(self, stats: DownloadStats | None = None) -> None:
        await self.preprocess()
        await self.download(stats)
        await self.postprocess()

    @abstractmethod
    async def preprocess(self):
        """Create directories, download cover art, etc."""
        raise NotImplementedError

    @abstractmethod
    async def download(self, stats: DownloadStats | None = None):
        """Download and tag the actual audio files in the correct directories."""
        raise NotImplementedError

    @abstractmethod
    async def postprocess(self):
        """Update database, run conversion, delete garbage files etc."""
        raise NotImplementedError

    @staticmethod
    def batch(iterable, n=1):
        """Split iterable into consecutive chunks of at most n items."""
        total = len(iterable)
        for ndx in range(0, total, n):
            yield iterable[ndx : min(ndx + n, total)]


class Pending(ABC):
    """A request to download a `Media` whose metadata has not been fetched."""

    @abstractmethod
    async def resolve(self) -> Media | None:
        """Fetch metadata and resolve into a downloadable `Media` object."""
        raise NotImplementedError
