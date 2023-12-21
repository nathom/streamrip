from .client import Client
from .deezer import DeezerClient
from .downloadable import BasicDownloadable, Downloadable
from .qobuz import QobuzClient
from .soundcloud import SoundcloudClient
from .tidal import TidalClient

__all__ = [
    "Client",
    "DeezerClient",
    "TidalClient",
    "QobuzClient",
    "SoundcloudClient",
    "Downloadable",
    "BasicDownloadable",
]
