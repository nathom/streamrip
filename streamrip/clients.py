import datetime
import click
import hashlib
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Generator, Sequence, Tuple, Union

import requests
import tidalapi
from dogpile.cache import make_region

from .constants import (
    AGENT,
    CACHE_DIR,
    DEEZER_MAX_Q,
    DEEZER_Q_IDS,
    QOBUZ_FEATURED_KEYS,
    TIDAL_MAX_Q,
    TIDAL_Q_IDS,
)
from .exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    InvalidQuality,
)
from .spoofbuz import Spoofer

os.makedirs(CACHE_DIR, exist_ok=True)
region = make_region().configure(
    "dogpile.cache.dbm",
    arguments={"filename": os.path.join(CACHE_DIR, "clients.db")},
)

logger = logging.getLogger(__name__)

TRACK_CACHE_TIME = datetime.timedelta(weeks=2).total_seconds()
RELEASE_CACHE_TIME = datetime.timedelta(days=1).total_seconds()

# Qobuz
QOBUZ_BASE = "https://www.qobuz.com/api.json/0.2"


# Deezer
DEEZER_BASE = "https://api.deezer.com"
DEEZER_DL = "http://dz.loaderapp.info/deezer"


# ----------- Abstract Classes -----------------


class ClientInterface(ABC):
    """Common API for clients of all platforms.

    This is an Abstract Base Class. It cannot be instantiated;
    it is merely a template.
    """

    @abstractmethod
    def login(self, **kwargs):
        """Authenticate the client.

        :param kwargs:
        """
        pass

    @abstractmethod
    def search(self, query: str, media_type="album"):
        """Search API for query.

        :param query:
        :type query: str
        :param type_:
        """
        pass

    @abstractmethod
    def get(self, item_id, media_type="album"):
        """Get metadata.

        :param meta_id:
        :param type_:
        """
        pass

    @abstractmethod
    def get_file_url(self, track_id, quality=6) -> Union[dict]:
        """Get the direct download url dict for a file.

        :param track_id: id of the track
        """
        pass

    @property
    @abstractmethod
    def source(self):
        pass


# ------------- Clients -----------------


class QobuzClient(ClientInterface):
    source = "qobuz"

    # ------- Public Methods -------------
    def __init__(self):
        self.logged_in = False

    def login(self, email: str, pwd: str, **kwargs):
        """Authenticate the QobuzClient. Must have a paid membership.

        If `app_id` and `secrets` are not provided, this will run the
        Spoofer script, which retrieves them. This will take some time,
        so it is recommended to cache them somewhere for reuse.

        :param email: email for the qobuz account
        :type email: str
        :param pwd: password for the qobuz account
        :type pwd: str
        :param kwargs: app_id: str, secrets: list, return_secrets: bool
        """
        click.secho(f"Logging into {self.source}", fg='green')
        if self.logged_in:
            logger.debug("Already logged in")
            return

        if (kwargs.get("app_id") or kwargs.get("secrets")) in (None, [], ""):
            logger.info("Fetching tokens from Qobuz")
            spoofer = Spoofer()
            kwargs["app_id"] = spoofer.get_app_id()
            kwargs["secrets"] = spoofer.get_secrets()

        self.app_id = str(kwargs["app_id"])  # Ensure it is a string
        self.secrets = kwargs["secrets"]

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": AGENT,
                "X-App-Id": self.app_id,
            }
        )

        self._api_login(email, pwd)
        logger.debug("Logged into Qobuz")
        self._validate_secrets()
        logger.debug("Qobuz client is ready to use")

        self.logged_in = True

    def get_tokens(self) -> Tuple[str, Sequence[str]]:
        return self.app_id, self.secrets

    def search(
        self, query: str, media_type: str = "album", limit: int = 500
    ) -> Generator:
        """Search the qobuz API.

        If 'featured' is given as media type, this will retrieve results
        from the featured albums in qobuz. The queries available with this type
        are:

            * most-streamed
            * recent-releases
            * best-sellers
            * press-awards
            * ideal-discography
            * editor-picks
            * most-featured
            * qobuzissims
            * new-releases
            * new-releases-full
            * harmonia-mundi
            * universal-classic
            * universal-jazz
            * universal-jeunesse
            * universal-chanson

        :param query:
        :type query: str
        :param media_type:
        :type media_type: str
        :param limit:
        :type limit: int
        :rtype: Generator
        """
        return self._api_search(query, media_type, limit)

    @region.cache_on_arguments(expiration_time=RELEASE_CACHE_TIME)
    def get(self, item_id: Union[str, int], media_type: str = "album") -> dict:
        return self._api_get(media_type, item_id=item_id)

    def get_file_url(self, item_id, quality=6) -> dict:
        return self._api_get_file_url(item_id, quality=quality)

    # ---------- Private Methods ---------------

    # Credit to Sorrow446 for the original methods

    def _gen_pages(self, epoint: str, params: dict) -> dict:
        page, status_code = self._api_request(epoint, params)
        logger.debug("Keys returned from _gen_pages: %s", ", ".join(page.keys()))
        key = epoint.split("/")[0] + "s"
        total = page.get(key, {})
        total = total.get("total") or total.get("items")

        if not total:
            logger.debug("Nothing found from %s epoint", epoint)
            return

        limit = page.get(key, {}).get("limit", 500)
        offset = page.get(key, {}).get("offset", 0)
        params.update({"limit": limit})
        yield page
        while (offset + limit) < total:
            offset += limit
            params.update({"offset": offset})
            page, status_code = self._api_request(epoint, params)
            yield page

    def _validate_secrets(self):
        for secret in self.secrets:
            if self._test_secret(secret):
                self.sec = secret
                logger.debug("Working secret and app_id: %s - %s", secret, self.app_id)
                break
        if not hasattr(self, "sec"):
            raise InvalidAppSecretError(f"Invalid secrets: {self.secrets}")

    def _api_get(self, media_type: str, **kwargs) -> dict:
        item_id = kwargs.get("item_id")

        params = {
            "app_id": self.app_id,
            f"{media_type}_id": item_id,
            "limit": kwargs.get("limit", 500),
            "offset": kwargs.get("offset", 0),
        }
        extras = {
            "artist": "albums",
            "playlist": "tracks",
            "label": "albums",  # not tested
        }

        if media_type in extras:
            params.update({"extra": extras[media_type]})

        epoint = f"{media_type}/get"

        response, status_code = self._api_request(epoint, params)
        return response

    def _api_search(self, query, media_type, limit=500) -> Generator:
        params = {
            "query": query,
            "limit": limit,
        }
        # TODO: move featured, favorites, and playlists into _api_get later
        if media_type == "featured":
            assert query in QOBUZ_FEATURED_KEYS, f'query "{query}" is invalid.'
            params.update({"type": query})
            del params["query"]
            epoint = "album/getFeatured"

        elif query == "user-favorites":
            assert query in ("track", "artist", "album")
            params.update({"type": f"{media_type}s"})
            epoint = "favorite/getUserFavorites"

        elif query == "user-playlists":
            epoint = "playlist/getUserPlaylists"

        else:
            epoint = f"{media_type}/search"

        return self._gen_pages(epoint, params)

    def _api_login(self, email: str, pwd: str):
        # usr_info = self._api_call("user/login", email=email, pwd=pwd)
        params = {
            "email": email,
            "password": pwd,
            "app_id": self.app_id,
        }
        epoint = "user/login"
        resp, status_code = self._api_request(epoint, params)

        if status_code == 401:
            raise AuthenticationError(f"Invalid credentials from params {params}")
        elif status_code == 400:
            raise InvalidAppIdError(f"Invalid app id from params {params}")
        else:
            logger.info("Logged in to Qobuz")

        if not resp["user"]["credential"]["parameters"]:
            raise IneligibleError("Free accounts are not eligible to download tracks.")

        self.uat = resp["user_auth_token"]
        self.session.headers.update({"X-User-Auth-Token": self.uat})
        self.label = resp["user"]["credential"]["parameters"]["short_label"]

    def _api_get_file_url(
        self, track_id: Union[str, int], quality: int = 6, sec: str = None
    ) -> dict:
        unix_ts = time.time()

        if int(quality) not in (5, 6, 7, 27):  # Needed?
            raise InvalidQuality(f"Invalid quality id {quality}. Choose 5, 6, 7 or 27")

        if sec is not None:
            secret = sec
        elif hasattr(self, "sec"):
            secret = self.sec
        else:
            raise InvalidAppSecretError("Cannot find app secret")

        r_sig = f"trackgetFileUrlformat_id{quality}intentstreamtrack_id{track_id}{unix_ts}{secret}"
        logger.debug("Raw request signature: %s", r_sig)
        r_sig_hashed = hashlib.md5(r_sig.encode("utf-8")).hexdigest()
        logger.debug("Hashed request signature: %s", r_sig_hashed)

        params = {
            "request_ts": unix_ts,
            "request_sig": r_sig_hashed,
            "track_id": track_id,
            "format_id": quality,
            "intent": "stream",
        }
        response, status_code = self._api_request("track/getFileUrl", params)
        if status_code == 400:
            raise InvalidAppSecretError("Invalid app secret from params %s" % params)

        return response

    def _api_request(self, epoint: str, params: dict) -> Tuple[dict, int]:
        logging.debug(f"Calling API with endpoint {epoint} params {params}")
        r = self.session.get(f"{QOBUZ_BASE}/{epoint}", params=params)
        try:
            return r.json(), r.status_code
        except Exception:
            logger.error("Problem getting JSON. Status code: %s", r.status_code)
            raise

    def _test_secret(self, secret: str) -> bool:
        try:
            self._api_get_file_url("19512574", sec=secret)
            return True
        except InvalidAppSecretError as error:
            logger.debug("Test for %s secret didn't work: %s", secret, error)
            return False


class DeezerClient(ClientInterface):
    source = "deezer"

    def __init__(self):
        self.session = requests.Session()
        self.logged_in = True

    @region.cache_on_arguments(expiration_time=RELEASE_CACHE_TIME)
    def search(self, query: str, media_type: str = "album", limit: int = 200) -> dict:
        """Search API for query.

        :param query:
        :type query: str
        :param media_type:
        :type media_type: str
        :param limit:
        :type limit: int
        """
        # TODO: more robust url sanitize
        query = query.replace(" ", "+")

        if media_type.endswith("s"):
            media_type = media_type[:-1]

        # TODO: use limit parameter
        response = self.session.get(f"{DEEZER_BASE}/search/{media_type}?q={query}")
        response.raise_for_status()

        return response.json()

    def login(self, **kwargs):
        logger.debug("Deezer does not require login call, returning")

    @region.cache_on_arguments(expiration_time=RELEASE_CACHE_TIME)
    def get(self, meta_id: Union[str, int], media_type: str = "album"):
        """Get metadata.

        :param meta_id:
        :type meta_id: Union[str, int]
        :param type_:
        :type type_: str
        """
        url = f"{DEEZER_BASE}/{media_type}/{meta_id}"
        item = self.session.get(url).json()
        if media_type in ("album", "playlist"):
            tracks = self.session.get(f"{url}/tracks").json()
            item["tracks"] = tracks["data"]
            item["track_total"] = len(tracks["data"])
        elif media_type == "artist":
            albums = self.session.get(f"{url}/albums").json()
            item["albums"] = albums["data"]

        return item

    @staticmethod
    def get_file_url(meta_id: Union[str, int], quality: int = 6):
        quality = min(DEEZER_MAX_Q, quality)
        url = f"{DEEZER_DL}/{DEEZER_Q_IDS[quality]}/{DEEZER_BASE}/track/{meta_id}"
        logger.debug(f"Download url {url}")
        return url


class TidalClient(ClientInterface):
    source = "tidal"

    def __init__(self):
        self.logged_in = False

    def login(self, email: str, pwd: str):
        click.secho(f"Logging into {self.source}", fg='green')
        if self.logged_in:
            return

        config = tidalapi.Config()

        self.session = tidalapi.Session(config=config)
        self.session.login(email, pwd)
        logger.info("Logged into Tidal")

        self.logged_in = True

    @region.cache_on_arguments(expiration_time=RELEASE_CACHE_TIME)
    def search(self, query: str, media_type: str = "album", limit: int = 50):
        """
        :param query:
        :type query: str
        :param media_type: artist, album, playlist, or track
        :type media_type: str
        :param limit:
        :type limit: int
        :raises ValueError: if field value is invalid
        """

        return self._search(query, media_type, limit=limit)

    @region.cache_on_arguments(expiration_time=RELEASE_CACHE_TIME)
    def get(self, meta_id: Union[str, int], media_type: str = "album"):
        """Get metadata.

        :param meta_id:
        :type meta_id: Union[str, int]
        :param media_type:
        :type media_type: str
        """
        return self._get(meta_id, media_type)

    def get_file_url(self, meta_id: Union[str, int], quality: int = 6):
        """
        :param meta_id:
        :type meta_id: Union[str, int]
        :param quality:
        :type quality: int
        """
        logger.debug(f"Fetching file url with quality {quality}")
        return self._get_file_url(meta_id, quality=min(TIDAL_MAX_Q, quality))

    def _search(self, query, media_type="album", **kwargs):
        params = {
            "query": query,
            "limit": kwargs.get("limit", 50),
        }
        return self.session.request("GET", f"search/{media_type}s", params).json()

    def _get(self, media_id, media_type="album"):
        if media_type == "album":
            info = self.session.request("GET", f"albums/{media_id}")
            tracklist = self.session.request("GET", f"albums/{media_id}/tracks")
            album = info.json()
            album["tracks"] = tracklist.json()
            return album

        elif media_type == "track":
            return self.session.request("GET", f"tracks/{media_id}").json()
        elif media_type == "playlist":
            return self.session.request("GET", f"playlists/{media_id}/tracks").json()
        elif media_type == "artist":
            return self.session.request("GET", f"artists/{media_id}/albums").json()
        else:
            raise ValueError

    def _get_file_url(self, track_id, quality=6):
        params = {"soundQuality": TIDAL_Q_IDS[quality]}
        resp = self.session.request("GET", f"tracks/{track_id}/streamUrl", params)
        resp.raise_for_status()
        return resp.json()
