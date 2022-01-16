"""The clients that interact with the service APIs."""

import base64
import binascii
import concurrent.futures
import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, Optional, Sequence, Tuple, Union

import deezer
from click import launch, secho
from Cryptodome.Cipher import AES

from .constants import (
    AGENT,
    AVAILABLE_QUALITY_IDS,
    DEEZER_BASE,
    DEEZER_DL,
    DEEZER_FORMATS,
    QOBUZ_BASE,
    QOBUZ_FEATURED_KEYS,
    SOUNDCLOUD_BASE,
    SOUNDCLOUD_USER_ID,
    TIDAL_AUTH_URL,
    TIDAL_BASE,
    TIDAL_CLIENT_INFO,
    TIDAL_MAX_Q,
)
from .exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    InvalidQuality,
    MissingCredentials,
    NonStreamable,
)
from .spoofbuz import Spoofer
from .utils import gen_threadsafe_session, get_quality, safe_get

logger = logging.getLogger("streamrip")


class Client(ABC):
    """Common API for clients of all platforms.

    This is an Abstract Base Class. It cannot be instantiated;
    it is merely a template.
    """

    source: str
    max_quality: int
    logged_in: bool

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
    def get_file_url(self, track_id, quality=3) -> dict:
        """Get the direct download url dict for a file.

        :param track_id: id of the track
        """
        pass


class QobuzClient(Client):
    """QobuzClient."""

    source = "qobuz"
    max_quality = 4

    # ------- Public Methods -------------
    def __init__(self):
        """Create a QobuzClient object."""
        self.logged_in = False

    def login(self, **kwargs):
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
        # TODO: make this faster
        secho(f"Logging into {self.source}", fg="green")
        email: str = kwargs["email"]
        pwd: str = kwargs["pwd"]
        if not email or not pwd:
            raise MissingCredentials

        if self.logged_in:
            logger.debug("Already logged in")
            return

        if not kwargs.get("app_id") or not kwargs.get("secrets"):
            self._get_app_id_and_secrets()  # can be async
        else:
            self.app_id, self.secrets = (
                str(kwargs["app_id"]),
                kwargs["secrets"],
            )
            self.session = gen_threadsafe_session(
                headers={"User-Agent": AGENT, "X-App-Id": self.app_id}
            )
            self._validate_secrets()

        self._api_login(email, pwd)
        logger.debug("Logged into Qobuz")
        logger.debug("Qobuz client is ready to use")

        self.logged_in = True

    def get_tokens(self) -> Tuple[str, Sequence[str]]:
        """Return app id and secrets.

        These can be saved and reused.

        :rtype: Tuple[str, Sequence[str]]
        """
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

    def get(self, item_id: Union[str, int], media_type: str = "album") -> dict:
        """Get an item from the API.

        :param item_id:
        :type item_id: Union[str, int]
        :param media_type:
        :type media_type: str
        :rtype: dict
        """
        resp = self._api_get(media_type, item_id=item_id)
        logger.debug(resp)
        return resp

    def get_file_url(self, item_id, quality=3) -> dict:
        """Get the downloadble file url for a track.

        :param item_id:
        :param quality:
        :rtype: dict
        """
        return self._api_get_file_url(item_id, quality=quality)

    # ---------- Private Methods ---------------

    def _get_app_id_and_secrets(self):
        if not hasattr(self, "app_id") or not hasattr(self, "secrets"):
            spoofer = Spoofer()
            self.app_id, self.secrets = (
                str(spoofer.get_app_id()),
                spoofer.get_secrets(),
            )

        if not hasattr(self, "sec"):
            if not hasattr(self, "session"):
                self.session = gen_threadsafe_session(
                    headers={"User-Agent": AGENT, "X-App-Id": self.app_id}
                )
            self._validate_secrets()

    def _gen_pages(self, epoint: str, params: dict) -> Generator:
        """When there are multiple pages of results, this yields them.

        :param epoint:
        :type epoint: str
        :param params:
        :type params: dict
        :rtype: dict
        """
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
        """Check if the secrets are usable."""
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(self._test_secret, secret) for secret in self.secrets
            ]

            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result is not None:
                    self.sec = result
                    break

        if not hasattr(self, "sec"):
            raise InvalidAppSecretError(f"Invalid secrets: {self.secrets}")

    def _api_get(self, media_type: str, **kwargs) -> dict:
        """Request metadata from the Qobuz API.

        :param media_type:
        :type media_type: str
        :param kwargs:
        :rtype: dict
        """
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
            "label": "albums",
        }

        if media_type in extras:
            params.update({"extra": extras[media_type]})

        logger.debug("request params: %s", params)

        epoint = f"{media_type}/get"

        response, status_code = self._api_request(epoint, params)
        if status_code != 200:
            raise Exception(f'Error fetching metadata. "{response["message"]}"')

        return response

    def _api_search(self, query: str, media_type: str, limit: int = 500) -> Generator:
        """Send a search request to the API.

        :param query:
        :type query: str
        :param media_type:
        :type media_type: str
        :param limit:
        :type limit: int
        :rtype: Generator
        """
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
        """Log into the api to get the user authentication token.

        :param email:
        :type email: str
        :param pwd:
        :type pwd: str
        """
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
            logger.debug(resp)
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
        """Get the file url given a track id.

        :param track_id:
        :type track_id: Union[str, int]
        :param quality:
        :type quality: int
        :param sec: only used to check whether a specific secret is valid.
        If it is not provided, it is set to `self.sec`.
        :type sec: str
        :rtype: dict
        """
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

        quality = int(get_quality(quality, self.source))  # type: ignore
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
        """Send a request to the API.

        :param epoint:
        :type epoint: str
        :param params:
        :type params: dict
        :rtype: Tuple[dict, int]
        """
        logging.debug(f"Calling API with endpoint {epoint} params {params}")
        r = self.session.get(f"{QOBUZ_BASE}/{epoint}", params=params)
        try:
            logger.debug(r.text)
            return r.json(), r.status_code
        except Exception:
            logger.error("Problem getting JSON. Status code: %s", r.status_code)
            raise

    def _test_secret(self, secret: str) -> Optional[str]:
        """Test the authenticity of a secret.

        :param secret:
        :type secret: str
        :rtype: bool
        """
        try:
            self._api_get_file_url("19512574", sec=secret)
            return secret
        except InvalidAppSecretError as error:
            logger.debug("Test for %s secret didn't work: %s", secret, error)
            return None


class DeezerClient(Client):
    """DeezerClient."""

    source = "deezer"
    max_quality = 2

    def __init__(self):
        """Create a DeezerClient."""
        self.client = deezer.Deezer()
        # self.session = gen_threadsafe_session()

        # no login required
        self.logged_in = False

    def search(self, query: str, media_type: str = "album", limit: int = 200) -> dict:
        """Search API for query.

        :param query:
        :type query: str
        :param media_type:
        :type media_type: str
        :param limit:
        :type limit: int
        """
        # TODO: use limit parameter
        try:
            if media_type == "featured":
                if query:
                    search_function = getattr(self.client.api, f"get_editorial_{query}")
                else:
                    search_function = self.client.api.get_editorial_releases

            else:
                search_function = getattr(self.client.api, f"search_{media_type}")
        except AttributeError:
            raise Exception

        response = search_function(query, limit=limit)
        return response

    def login(self, **kwargs):
        """Log into Deezer.

        :param kwargs:
        """
        try:
            arl = kwargs["arl"]
        except KeyError:
            raise MissingCredentials

        success = self.client.login_via_arl(arl)
        if not success:
            raise AuthenticationError

        self.logged_in = True

    def get(self, meta_id: Union[str, int], media_type: str = "album"):
        """Get metadata.

        :param meta_id:
        :type meta_id: Union[str, int]
        :param type_:
        :type type_: str
        """
        GET_FUNCTIONS = {
            "track": self.client.api.get_track,
            "album": self.client.api.get_album,
            "playlist": self.client.api.get_playlist,
            "artist": self.client.api.get_artist,
        }

        get_item = GET_FUNCTIONS[media_type]
        item = get_item(meta_id)
        if media_type in ("album", "playlist"):
            tracks = getattr(self.client.api, f"get_{media_type}_tracks")(
                meta_id, limit=-1
            )
            item["tracks"] = tracks["data"]
            item["track_total"] = len(tracks["data"])
        elif media_type == "artist":
            albums = self.client.api.get_artist_albums(meta_id)
            item["albums"] = albums["data"]

        logger.debug(item)
        return item

    def get_file_url(self, meta_id: str, quality: int = 2) -> dict:
        """Get downloadable url for a track.

        :param meta_id: The track ID.
        :type meta_id: Union[str, int]
        :param quality:
        :type quality: int
        """
        # TODO: optimize such that all of the ids are requested at once
        dl_info: Dict[str, Any] = {"quality": quality}

        track_info = self.client.gw.get_track(meta_id)
        logger.debug("Track info: %s", track_info)

        dl_info["fallback_id"] = safe_get(track_info, "FALLBACK", "SNG_ID")

        format_info = get_quality(quality, "deezer")
        assert isinstance(format_info, tuple)  # for typing
        format_no, format_str = format_info

        dl_info["size_to_quality"] = {
            int(track_info.get(f"FILESIZE_{format}")): self._quality_id_from_filetype(
                format
            )
            for format in DEEZER_FORMATS
        }

        token = track_info["TRACK_TOKEN"]
        try:
            url = self.client.get_track_url(token, format_str)
        except deezer.WrongLicense:
            raise NonStreamable(
                "The requested quality is not available with your subscription. "
                "Deezer HiFi is required for quality 2. Otherwise, the maximum "
                "quality allowed is 1."
            )

        if url is None:
            url = self._get_encrypted_file_url(
                meta_id, track_info["MD5_ORIGIN"], track_info["MEDIA_VERSION"]
            )

        dl_info["url"] = url
        logger.debug("dl_info %s", dl_info)
        return dl_info

    def _get_encrypted_file_url(
        self, meta_id: str, track_hash: str, media_version: str
    ):
        format_number = 1

        url_bytes = b"\xa4".join(
            (
                track_hash.encode(),
                str(format_number).encode(),
                str(meta_id).encode(),
                str(media_version).encode(),
            )
        )
        url_hash = hashlib.md5(url_bytes).hexdigest()
        info_bytes = bytearray(url_hash.encode())
        info_bytes.extend(b"\xa4")
        info_bytes.extend(url_bytes)
        info_bytes.extend(b"\xa4")
        # Pad the bytes so that len(info_bytes) % 16 == 0
        padding_len = 16 - (len(info_bytes) % 16)
        info_bytes.extend(b"." * padding_len)

        logger.debug("Info bytes: %s", info_bytes)
        path = self._gen_url_path(info_bytes)
        logger.debug(path)
        return f"https://e-cdns-proxy-{track_hash[0]}.dzcdn.net/mobile/1/{path}"

    def _gen_url_path(self, data):
        return binascii.hexlify(
            AES.new("jo6aey6haid2Teih".encode(), AES.MODE_ECB).encrypt(data)
        ).decode("utf-8")

    @staticmethod
    def _quality_id_from_filetype(filetype: str) -> Optional[int]:
        return {
            "MP3_128": 0,
            "MP3_256": 0,
            "MP3_320": 1,
            "FLAC": 2,
        }.get(filetype)


class DeezloaderClient(Client):
    """DeezloaderClient."""

    source = "deezer"
    max_quality = 2

    def __init__(self):
        """Create a DeezloaderClient."""
        self.session = gen_threadsafe_session()

        # no login required
        self.logged_in = True

    def search(self, query: str, media_type: str = "album", limit: int = 200) -> dict:
        """Search API for query.

        :param query:
        :type query: str
        :param media_type:
        :type media_type: str
        :param limit:
        :type limit: int
        """
        # TODO: use limit parameter
        response = self.session.get(
            f"{DEEZER_BASE}/search/{media_type}", params={"q": query}
        )
        response.raise_for_status()
        return response.json()

    def login(self, **kwargs):
        """Return None.

        Dummy method.

        :param kwargs:
        """
        logger.debug("Deezer does not require login call, returning")

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
            tracks = self.session.get(f"{url}/tracks", params={"limit": 1000}).json()
            item["tracks"] = tracks["data"]
            item["track_total"] = len(tracks["data"])
        elif media_type == "artist":
            albums = self.session.get(f"{url}/albums").json()
            item["albums"] = albums["data"]

        logger.debug(item)
        return item

    @staticmethod
    def get_file_url(meta_id: Union[str, int], quality: int = 2):
        """Get downloadable url for a track.

        :param meta_id: The track ID.
        :type meta_id: Union[str, int]
        :param quality:
        :type quality: int
        """
        quality = min(DeezloaderClient.max_quality, quality)
        url = f"{DEEZER_DL}/{get_quality(quality, 'deezloader')}/{DEEZER_BASE}/track/{meta_id}"
        logger.debug("Download url %s", url)
        return {"url": url}


class TidalClient(Client):
    """TidalClient."""

    source = "tidal"
    max_quality = 3

    # ----------- Public Methods --------------

    def __init__(self):
        """Create a TidalClient."""
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

        self.session = gen_threadsafe_session()

    def login(
        self,
        user_id=None,
        country_code=None,
        access_token=None,
        token_expiry=None,
        refresh_token=None,
    ):
        """Login to Tidal using the browser.

        Providing information from previous logins will allow a user
        to stay logged in.

        :param user_id:
        :param country_code:
        :param access_token:
        :param token_expiry:
        :param refresh_token:
        """
        if access_token:
            self.token_expiry = float(token_expiry)
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
        secho("Logged into Tidal", fg="green")

    def get(self, item_id, media_type):
        """Public method that internally calls _api_get.

        :param item_id:
        :param media_type:
        """
        resp = self._api_get(item_id, media_type)
        logger.debug(resp)
        return resp

    def search(self, query: str, media_type: str = "album", limit: int = 100) -> dict:
        """Search for a query.

        :param query:
        :type query: str
        :param media_type: track, album, playlist, or video.
        :type media_type: str
        :param limit: max is 100
        :type limit: int
        :rtype: dict
        """
        params = {
            "query": query,
            "limit": limit,
        }
        return self._api_request(f"search/{media_type}s", params=params)

    def get_file_url(self, track_id, quality: int = 3, video=False):
        """Get the file url for a track or video given an id.

        :param track_id: or video id
        :param quality: 0, 1, 2, or 3. It is irrelevant for videos.
        :type quality: int
        :param video:
        """
        if video:
            return self._get_video_stream_url(track_id)

        params = {
            "audioquality": get_quality(min(quality, TIDAL_MAX_Q), self.source),
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        }
        resp = self._api_request(f"tracks/{track_id}/playbackinfopostpaywall", params)
        try:
            manifest = json.loads(base64.b64decode(resp["manifest"]).decode("utf-8"))
        except KeyError:
            raise Exception(resp["userMessage"])

        logger.debug(manifest)
        return {
            "url": manifest["urls"][0],
            "enc_key": manifest.get("keyId"),
            "codec": manifest["codecs"],
        }

    def get_tokens(self) -> dict:
        """Return tokens to save for later use.

        :rtype: dict
        """
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

    # ------------ Utilities to login -------------

    def _login_new_user(self, launch_url: bool = True):
        """Create app url where the user can log in.

        :param launch: Launch the browser.
        :type launch: bool
        """
        login_link = f"https://{self._get_device_code()}"

        secho(
            f"Go to {login_link} to log into Tidal within 5 minutes.",
            fg="blue",
        )
        if launch_url:
            launch(login_link)

        start = time.time()
        elapsed = 0.0
        while elapsed < 600:  # 5 mins to login
            elapsed = time.time() - start
            status = self._check_auth_status()
            if status == 2:
                # pending
                time.sleep(4)
                continue
            elif status == 0:
                # successful
                break
            else:
                raise Exception

        self._update_authorization()

    def _get_device_code(self):
        """Get the device code that will be used to log in on the browser."""
        data = {
            "client_id": TIDAL_CLIENT_INFO["id"],
            "scope": "r_usr+w_usr+w_sub",
        }
        resp = self._api_post(f"{TIDAL_AUTH_URL}/device_authorization", data)

        if resp.get("status", 200) != 200:
            raise Exception(f"Device authorization failed {resp}")

        self.device_code = resp["deviceCode"]
        self.user_code = resp["userCode"]
        self.user_code_expiry = resp["expiresIn"]
        self.auth_interval = resp["interval"]
        return resp["verificationUriComplete"]

    def _check_auth_status(self):
        """Check if the user has logged in inside the browser."""
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

    def _verify_access_token(self, token: str):
        """Verify that the access token is valid.

        :param token:
        :type token: str
        """
        headers = {
            "authorization": f"Bearer {token}",
        }
        r = self.session.get(
            "https://api.tidal.com/v1/sessions", headers=headers
        ).json()
        if r.status != 200:
            raise Exception("Login failed")

        return True

    def _refresh_access_token(self):
        """Refresh the access token given a refresh token.

        The access token expires in a week, so it must be refreshed.
        Requires a refresh token.
        """
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
        self._update_authorization()

    def _login_by_access_token(self, token, user_id=None):
        """Login using the access token.

        Used after the initial authorization.

        :param token:
        :param user_id: Not necessary.
        """
        headers = {"authorization": f"Bearer {token}"}  # temporary
        resp = self.session.get(
            "https://api.tidal.com/v1/sessions", headers=headers
        ).json()
        if resp.get("status", 200) != 200:
            raise Exception(f"Login failed {resp}")

        if str(resp.get("userId")) != str(user_id):
            raise Exception(f"User id mismatch {resp['userId']} v {user_id}")

        self.user_id = resp["userId"]
        self.country_code = resp["countryCode"]
        self.access_token = token
        self._update_authorization()

    def _update_authorization(self):
        """Update the requests session headers with the auth token."""
        self.session.headers.update(self.authorization)

    @property
    def authorization(self):
        """Get the auth header."""
        return {"authorization": f"Bearer {self.access_token}"}

    # ------------- Fetch data ------------------

    def _api_get(self, item_id: str, media_type: str) -> dict:
        """Send a request to the api for information.

        :param item_id:
        :type item_id: str
        :param media_type: track, album, playlist, or video.
        :type media_type: str
        :rtype: dict
        """
        url = f"{media_type}s/{item_id}"
        item = self._api_request(url)
        if media_type in ("playlist", "album"):

            resp = self._api_request(f"{url}/items")
            if (tracks_left := item["numberOfTracks"]) > 100:
                offset = 0
                while tracks_left > 0:
                    offset += 100
                    tracks_left -= 100
                    resp["items"].extend(
                        self._api_request(f"{url}/items", {"offset": offset})["items"]
                    )

            item["tracks"] = [item["item"] for item in resp["items"]]
        elif media_type == "artist":
            logger.debug("filtering eps")
            album_resp = self._api_request(f"{url}/albums")
            ep_resp = self._api_request(
                f"{url}/albums", params={"filter": "EPSANDSINGLES"}
            )

            item["albums"] = album_resp["items"]
            item["albums"].extend(ep_resp["items"])

        logger.debug(item)
        return item

    def _api_request(self, path: str, params=None) -> dict:
        """Handle Tidal API requests.

        :param path:
        :type path: str
        :param params:
        :rtype: dict
        """
        if params is None:
            params = {}

        params["countryCode"] = self.country_code
        params["limit"] = 100
        r = self.session.get(f"{TIDAL_BASE}/{path}", params=params)
        r.raise_for_status()
        return r.json()

    def _get_video_stream_url(self, video_id: str) -> str:
        """Get the HLS video stream url.

        The stream is downloaded using ffmpeg for now.

        :param video_id:
        :type video_id: str
        :rtype: str
        """
        params = {
            "videoquality": "HIGH",
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        }
        resp = self._api_request(
            f"videos/{video_id}/playbackinfopostpaywall", params=params
        )
        manifest = json.loads(base64.b64decode(resp["manifest"]).decode("utf-8"))
        available_urls = self.session.get(manifest["urls"][0])
        available_urls.encoding = "utf-8"

        STREAM_URL_REGEX = re.compile(
            r"#EXT-X-STREAM-INF:BANDWIDTH=\d+,AVERAGE-BANDWIDTH=\d+,CODECS=\"(?!jpeg)[^\"]+\",RESOLUTION=\d+x\d+\n(.+)"
        )

        # Highest resolution is last
        *_, last_match = STREAM_URL_REGEX.finditer(available_urls.text)

        return last_match.group(1)

    def _api_post(self, url, data, auth=None):
        """Post to the Tidal API.

        :param url:
        :param data:
        :param auth:
        """
        r = self.session.post(url, data=data, auth=auth, verify=False).json()
        return r


class SoundCloudClient(Client):
    """SoundCloudClient."""

    source = "soundcloud"
    max_quality = 0
    logged_in = False

    client_id: str = ""
    app_version: str = ""

    def __init__(self):
        """Create a SoundCloudClient."""
        self.session = gen_threadsafe_session(
            headers={
                "User-Agent": AGENT,
            }
        )

    def login(self, **kwargs):
        self.client_id = kwargs.get("client_id")
        self.app_version = kwargs.get("app_version")
        logger.debug("client_id: %s, app_version: %s", self.client_id, self.app_version)

        # if (not self.client_id) or (not self.app_version) or (not self._announce()):
        if not (self.client_id and self.app_version and self._announce()):
            logger.debug(
                "Refreshing client_id=%s and app_version=%s",
                self.client_id,
                self.app_version,
            )
            self._refresh_tokens()

        self.logged_in = True

    def _announce(self):
        return self._get("announcements").status_code == 200

    def _refresh_tokens(self):
        STOCK_URL = "https://soundcloud.com/"

        resp = self.session.get(STOCK_URL)
        resp.encoding = "utf-8"

        *_, client_id_url_match = re.finditer(
            r"<script\s+crossorigin\s+src=\"([^\"]+)\"", resp.text
        )
        client_id_url = client_id_url_match.group(1)

        self.app_version = re.search(
            r'<script>window\.__sc_version="(\d+)"</script>', resp.text
        ).group(1)

        resp2 = self.session.get(client_id_url)
        self.client_id = re.search(r'client_id:\s*"(\w+)"', resp2.text).group(1)

    def resolve_url(self, url: str) -> dict:
        resp = self._get(f"resolve?url={url}").json()
        from pprint import pformat

        logger.debug(pformat(resp))
        return resp

    def get_tokens(self):
        return self.client_id, self.app_version

    def get(self, id, media_type="track"):
        """Get metadata for a media type given a soundcloud url.

        :param id:
        :param media_type:
        """
        assert media_type in {
            "track",
            "playlist",
        }, f"{media_type} not supported"

        resp = self._get(f"{media_type}s/{id}")
        resp.raise_for_status()
        resp = resp.json()

        logger.debug(resp)
        return resp

    def get_file_url(self, track, quality):
        """Get the streamable file url from soundcloud.

        It will most likely be an hls stream, which will have to be manually
        parsed, or downloaded with ffmpeg.

        :param track:
        :type track: dict
        :param quality:
        :rtype: dict
        """
        # TODO: find better solution for typing
        assert isinstance(track, dict)

        if not track["streamable"] or track["policy"] == "BLOCK":
            raise Exception

        if track["downloadable"] and track["has_downloads_left"]:
            r = self._get(f"tracks/{track['id']}/download").json()
            return {"url": r["redirectUri"], "type": "original"}

        else:
            url = None
            for tc in track["media"]["transcodings"]:
                fmt = tc["format"]
                if fmt["protocol"] == "hls" and fmt["mime_type"] == "audio/mpeg":
                    url = tc["url"]
                    break

            assert url is not None

            resp = self._get(url, no_base=True).json()
            return {"url": resp["url"], "type": "mp3"}

    def search(self, query: str, media_type="album", limit=50, offset=50):
        """Search for a query.

        :param query:
        :type query: str
        :param media_type: Can be album, though it will return a playlist
        response.
        """
        params = {
            "q": query,
            "facet": "genre",
            "user_id": SOUNDCLOUD_USER_ID,
            "limit": limit,
            "offset": offset,
            "linked_partitioning": "1",
        }
        result = self._get(f"search/{media_type}s", params=params)

        # The response
        return result.json()

    def _get(
        self,
        path,
        params=None,
        no_base=False,
        skip_decode=False,
        headers=None,
    ):
        """Send a request to the SoundCloud API.

        :param path:
        :param params:
        :param no_base: Do not append `path` parameter to the SoundCloud API
        base.
        :param resp_obj: Return the object returned by `requests.get` instead
        of the json response dict.
        """
        param_arg = params
        params = {
            "client_id": self.client_id,
            "app_version": self.app_version,
            "app_locale": "en",
        }
        if param_arg is not None:
            params.update(param_arg)

        if no_base:
            url = path
        else:
            url = f"{SOUNDCLOUD_BASE}/{path}"

        logger.debug("Fetching url %s with params %s", url, params)
        return self.session.get(url, params=params, headers=headers)
