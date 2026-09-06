import http.client

# Prevent failures on CDNs (like Qobuz/Akamai) that send >100 response headers
http.client._MAXHEADERS = 1000

from . import converter, db, exceptions, media, metadata
from .config import Config

__all__ = ["Config", "converter", "db", "exceptions", "media", "metadata"]
__version__ = "2.2.0"
