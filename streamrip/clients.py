import base64
import datetime
import hashlib
import json
import logging
import os
import sys
import time
from abc import ABC, abstractmethod
from pprint import pformat  # , pprint
from typing import Generator, Sequence, Tuple, Union

import click
import requests
from dogpile.cache import make_region
from requests.packages import urllib3

from .constants import (
    AGENT,
    AVAILABLE_QUALITY_IDS,
    CACHE_DIR,
    DEEZER_MAX_Q,
    QOBUZ_FEATURED_KEYS,
    TIDAL_MAX_Q,
)
from .exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    InvalidQuality,
)
from .spoofbuz import Spoofer
from .utils import get_quality

urllib3.disable_warnings()
requests.adapters.DEFAULT_RETRIES = 5

os.makedirs(CACHE_DIR, exist_ok=True)
region = make_region().configure(
    "dogpile.cache.dbm",
    arguments={"filename": os.path.join(CACHE_DIR, "clients.db")},
)

TIDAL_BASE = "https://api.tidalhifi.com/v1"
TIDAL_AUTH_URL = "https://auth.tidal.com/v1/oauth2"
TIDAL_CLIENT_INFO = {
    "id": "aR7gUaTK1ihpXOEP",
    "secret": "eVWBEkuL2FCjxgjOkR3yK0RYZEbcrMXRc2l8fU3ZCdE=",
}

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
    def get_file_url(self, track_id, quality=3) -> Union[dict]:
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
        click.secho(f"Logging into {self.source}", fg="green")
        if self.logged_in:
            logger.debug("Already logged in")
            return

        if (kwargs.get("app_id") or kwargs.get("secrets")) in (None, [], ""):
            click.secho("Fetching tokens, this may take a few seconds.")
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

    def get_file_url(self, item_id, quality=3) -> dict:
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
        self, track_id: Union[str, int], quality: int = 3, sec: str = None
    ) -> dict:
        unix_ts = time.time()

        if int(quality) not in AVAILABLE_QUALITY_IDS:  # Needed?
            raise InvalidQuality(
                f"Invalid quality id {quality}. Choose from {AVAILABLE_QUALITY_IDS}"
            )

        if sec is not None:
            secret = sec
        elif hasattr(self, "sec"):
            secret = self.sec
        else:
            raise InvalidAppSecretError("Cannot find app secret")

        quality = get_quality(quality, self.source)
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
            r = self._api_get_file_url("19512574", sec=secret)
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
        url = f"{DEEZER_DL}/{get_quality(quality, 'deezer')}/{DEEZER_BASE}/track/{meta_id}"
        logger.debug(f"Download url {url}")
        return url


class TidalClient(ClientInterface):
    source = "tidal"

    def __init__(self):
        self.logged_in = False

        self.device_code = None
        self.user_code = None
        self.verification_url = None
        self.auth_check_timeout = None
        self.auth_check_interval = None
        self.user_id = None
        self.country_code = None
        self.access_token = None
        self.refresh_token = None
        self.expiry = None

    def login(
        self,
        user_id=None,
        country_code=None,
        access_token=None,
        token_expiry=None,
        refresh_token=None,
    ):
        if access_token is not None:
            self.token_expiry = token_expiry
            self.refresh_token = refresh_token

            if self.token_expiry - time.time() < 86400:  # 1 day
                logger.debug("Refreshing access token")
                self._refresh_access_token()
            else:
                logger.debug("Logging in with access token")
                self._login_by_access_token(access_token, user_id)
        else:
            logger.debug("Logging in as a new user")
            self._login_new_user()

        self.logged_in = True
        click.secho("Logged into Tidal", fg="green")

    def get(self, item_id, media_type):
        return self._api_get(item_id, media_type)

    def search(self, query, media_type="album", limit: int = 100):
        params = {
            "query": query,
            "limit": limit,
        }
        return self._api_request(f"search/{media_type}s", params=params)

    def get_file_url(self, track_id, quality: int = 3):
        params = {
            "audioquality": get_quality(min(quality, TIDAL_MAX_Q), self.source),
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        }
        resp = self._api_request(f"tracks/{track_id}/playbackinfopostpaywall", params)
        manifest = json.loads(base64.b64decode(resp["manifest"]).decode("utf-8"))
        logger.debug(f"{pformat(manifest)=}")
        return {
            "url": manifest["urls"][0],
            "enc_key": manifest.get("keyId"),
            "codec": manifest["codecs"],
        }

    def get_tokens(self):
        return {
            k: getattr(self, k)
            for k in (
                "user_id",
                "country_code",
                "access_token",
                "refresh_token",
                "token_expiry",
            )
        }

    def _login_new_user(self, launch=True):
        login_link = f"https://{self._get_device_code()}"

        click.secho(
            f"Go to {login_link} to log into Tidal within 5 minutes.", fg="blue"
        )
        if launch:
            click.launch(login_link)

        start = time.time()
        elapsed = 0
        while elapsed < 600:  # 5 mins to login
            elapsed = time.time() - start
            status = self._check_auth_status()
            if status == 2:
                # pending
                time.sleep(4)
                continue
            elif status == 1:
                # error checking
                raise Exception
            elif status == 0:
                # successful
                break
            else:
                raise Exception

    def _get_device_code(self):
        data = {
            "client_id": TIDAL_CLIENT_INFO["id"],
            "scope": "r_usr+w_usr+w_sub",
        }
        resp = self._api_post(f"{TIDAL_AUTH_URL}/device_authorization", data)

        if "status" in resp and resp["status"] != 200:
            raise Exception(f"Device authorization failed {resp}")

        logger.debug(pformat(resp))
        self.device_code = resp["deviceCode"]
        self.user_code = resp["userCode"]
        self.user_code_expiry = resp["expiresIn"]
        self.auth_interval = resp["interval"]
        return resp["verificationUriComplete"]

    def _check_auth_status(self):
        data = {
            "client_id": TIDAL_CLIENT_INFO["id"],
            "device_code": self.device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "scope": "r_usr+w_usr+w_sub",
        }
        logger.debug(data)
        resp = self._api_post(
            f"{TIDAL_AUTH_URL}/token",
            data,
            (TIDAL_CLIENT_INFO["id"], TIDAL_CLIENT_INFO["secret"]),
        )
        logger.debug(resp)

        if resp.get("status", 200) != 200:
            if resp["status"] == 400 and resp["sub_status"] == 1002:
                return 2
            else:
                return 1

        self.user_id = resp["user"]["userId"]
        self.country_code = resp["user"]["countryCode"]
        self.access_token = resp["access_token"]
        self.refresh_token = resp["refresh_token"]
        self.token_expiry = resp["expires_in"] + time.time()
        return 0

    def _verify_access_token(self, token):
        headers = {
            "authorization": f"Bearer {token}",
        }
        r = requests.get("https://api.tidal.com/v1/sessions", headers=headers).json()
        if r.status != 200:
            raise Exception("Login failed")

        return True

    def _refresh_access_token(self):
        data = {
            "client_id": TIDAL_CLIENT_INFO["id"],
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "r_usr+w_usr+w_sub",
        }
        resp = self._api_post(
            f"{TIDAL_AUTH_URL}/token",
            data,
            (TIDAL_CLIENT_INFO["id"], TIDAL_CLIENT_INFO["secret"]),
        )

        if resp.get("status", 200) != 200:
            raise Exception("Refresh failed")

        self.user_id = resp["user"]["userId"]
        self.country_code = resp["user"]["countryCode"]
        self.access_token = resp["access_token"]
        self.token_expiry = resp["expires_in"] + time.time()

    def _login_by_access_token(self, token, user_id=None):
        headers = {"authorization": f"Bearer {token}"}
        resp = requests.get("https://api.tidal.com/v1/sessions", headers=headers).json()
        if resp.get("status", 200) != 200:
            raise Exception(f"Login failed {resp=}")

        if str(resp.get("userId")) != str(user_id):
            raise Exception(f"User id mismatch {resp['userId']} v {user_id}")

        self.user_id = resp["userId"]
        self.country_code = resp["countryCode"]
        self.access_token = token

    def _api_get(self, item_id: str, media_type: str) -> dict:
        url = f"{media_type}s/{item_id}"
        item = self._api_request(url)
        if media_type in ("playlist", "album"):
            resp = self._api_request(f"{url}/items")
            item["tracks"] = [item["item"] for item in resp["items"]]
        elif media_type == "artist":
            resp = self._api_request(f"{url}/albums")
            item["albums"] = resp["items"]

        return item

    def _api_request(self, path, params=None) -> dict:
        if params is None:
            params = {}

        headers = {"authorization": f"Bearer {self.access_token}"}
        params["countryCode"] = self.country_code
        params["limit"] = 100
        r = requests.get(f"{TIDAL_BASE}/{path}", headers=headers, params=params).json()
        return r

    def _api_post(self, url, data, auth=None):
        r = requests.post(url, data=data, auth=auth, verify=False).json()
        return r
