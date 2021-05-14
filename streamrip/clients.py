"""The clients that interact with the service APIs."""

import base64
import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Generator, Sequence, Tuple, Union

import click

from .constants import (
    AGENT,
    AVAILABLE_QUALITY_IDS,
    DEEZER_BASE,
    DEEZER_DL,
    DEEZER_MAX_Q,
    QOBUZ_BASE,
    QOBUZ_FEATURED_KEYS,
    SOUNDCLOUD_BASE,
    SOUNDCLOUD_CLIENT_ID,
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
)
from .spoofbuz import Spoofer
from .utils import gen_threadsafe_session, get_quality

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
    def get_file_url(self, track_id, quality=3) -> Union[dict, str]:
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
        click.secho(f"Logging into {self.source}", fg="green")
        email: str = kwargs["email"]
        pwd: str = kwargs["pwd"]
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

        self.session = gen_threadsafe_session(
            headers={"User-Agent": AGENT, "X-App-Id": self.app_id}
        )

        self._api_login(email, pwd)
        logger.debug("Logged into Qobuz")
        self._validate_secrets()
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

    def _gen_pages(self, epoint: str, params: dict) -> Generator:
        """When there are multiple pages of results, this yields them.

        :param epoint:
        :type epoint: str
        :param params:
        :type params: dict
        :rtype: dict
        """
        page, status_code = self._api_request(epoint, params)
        logger.debug(
            "Keys returned from _gen_pages: %s", ", ".join(page.keys())
        )
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
        for secret in self.secrets:
            if self._test_secret(secret):
                self.sec = secret
                logger.debug(
                    "Working secret and app_id: %s - %s", secret, self.app_id
                )
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
            "label": "albums",  # not tested
        }

        if media_type in extras:
            params.update({"extra": extras[media_type]})

        epoint = f"{media_type}/get"

        response, status_code = self._api_request(epoint, params)
        if status_code != 200:
            raise Exception(
                f'Error fetching metadata. "{response["message"]}"'
            )

        return response

    def _api_search(
        self, query: str, media_type: str, limit: int = 500
    ) -> Generator:
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
            raise AuthenticationError(
                f"Invalid credentials from params {params}"
            )
        elif status_code == 400:
            raise InvalidAppIdError(f"Invalid app id from params {params}")
        else:
            logger.info("Logged in to Qobuz")

        if not resp["user"]["credential"]["parameters"]:
            raise IneligibleError(
                "Free accounts are not eligible to download tracks."
            )

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

        quality = int(get_quality(quality, self.source))
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
            raise InvalidAppSecretError(
                "Invalid app secret from params %s" % params
            )

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
            return r.json(), r.status_code
        except Exception:
            logger.error(
                "Problem getting JSON. Status code: %s", r.status_code
            )
            raise

    def _test_secret(self, secret: str) -> bool:
        """Test the authenticity of a secret.

        :param secret:
        :type secret: str
        :rtype: bool
        """
        try:
            self._api_get_file_url("19512574", sec=secret)
            return True
        except InvalidAppSecretError as error:
            logger.debug("Test for %s secret didn't work: %s", secret, error)
            return False


class DeezerClient(Client):
    """DeezerClient."""

    source = "deezer"
    max_quality = 2

    def __init__(self):
        """Create a DeezerClient."""
        self.session = gen_threadsafe_session()

        # no login required
        self.logged_in = True

    def search(
        self, query: str, media_type: str = "album", limit: int = 200
    ) -> dict:
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
            tracks = self.session.get(
                f"{url}/tracks", params={"limit": 1000}
            ).json()
            item["tracks"] = tracks["data"]
            item["track_total"] = len(tracks["data"])
        elif media_type == "artist":
            albums = self.session.get(f"{url}/albums").json()
            item["albums"] = albums["data"]

        logger.debug(item)
        return item

    @staticmethod
    def get_file_url(meta_id: Union[str, int], quality: int = 6):
        """Get downloadable url for a track.

        :param meta_id: The track ID.
        :type meta_id: Union[str, int]
        :param quality:
        :type quality: int
        """
        quality = min(DEEZER_MAX_Q, quality)
        url = f"{DEEZER_DL}/{get_quality(quality, 'deezer')}/{DEEZER_BASE}/track/{meta_id}"
        logger.debug(f"Download url {url}")
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
        """Public method that internally calls _api_get.

        :param item_id:
        :param media_type:
        """
        resp = self._api_get(item_id, media_type)
        logger.debug(resp)
        return resp

    def search(
        self, query: str, media_type: str = "album", limit: int = 100
    ) -> dict:
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
            "audioquality": get_quality(
                min(quality, TIDAL_MAX_Q), self.source
            ),
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        }
        resp = self._api_request(
            f"tracks/{track_id}/playbackinfopostpaywall", params
        )
        try:
            manifest = json.loads(
                base64.b64decode(resp["manifest"]).decode("utf-8")
            )
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

    def _login_new_user(self, launch: bool = True):
        """Create app url where the user can log in.

        :param launch: Launch the browser.
        :type launch: bool
        """
        login_link = f"https://{self._get_device_code()}"

        click.secho(
            f"Go to {login_link} to log into Tidal within 5 minutes.",
            fg="blue",
        )
        if launch:
            click.launch(login_link)

        start = time.time()
        elapsed = 0.0
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
        """Get the device code that will be used to log in on the browser."""
        data = {
            "client_id": TIDAL_CLIENT_INFO["id"],
            "scope": "r_usr+w_usr+w_sub",
        }
        resp = self._api_post(f"{TIDAL_AUTH_URL}/device_authorization", data)

        if "status" in resp and resp["status"] != 200:
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
                        self._api_request(f"{url}/items", {"offset": offset})[
                            "items"
                        ]
                    )

            item["tracks"] = [item["item"] for item in resp["items"]]
        elif media_type == "artist":
            resp = self._api_request(f"{url}/albums")
            item["albums"] = resp["items"]

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
        r = self.session.get(f"{TIDAL_BASE}/{path}", params=params).json()
        return r

    def _get_video_stream_url(self, video_id: str) -> str:
        """Get the HLS video stream url.

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
        stream_url_regex = (
            r'#EXT-X-STREAM-INF:BANDWIDTH=\d+,AVERAGE-BANDWIDTH=\d+,CODECS="[^"]+"'
            r",RESOLUTION=\d+x\d+\n(.+)"
        )
        manifest = json.loads(
            base64.b64decode(resp["manifest"]).decode("utf-8")
        )
        available_urls = self.session.get(manifest["urls"][0])
        url_info = re.findall(stream_url_regex, available_urls.text)

        # highest resolution is last
        return url_info[-1]

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
    logged_in = True

    def __init__(self):
        """Create a SoundCloudClient."""
        self.session = gen_threadsafe_session(headers={"User-Agent": AGENT})

    def login(self):
        """Login is not necessary for SoundCloud."""
        raise NotImplementedError

    def get(self, id, media_type="track"):
        """Get metadata for a media type given an id.

        :param id:
        :param media_type:
        """
        assert media_type in (
            "track",
            "playlist",
        ), f"{media_type} not supported"

        if "http" in str(id):
            resp, _ = self._get(f"resolve?url={id}")
        elif media_type == "track":
            resp, _ = self._get(f"{media_type}s/{id}")
        else:
            raise Exception(id)

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
            r = self._get(f"tracks/{track['id']}/download", resp_obj=True)
            return {"url": r.json()["redirectUri"], "type": "original"}

        else:
            url = None
            for tc in track["media"]["transcodings"]:
                fmt = tc["format"]
                if (
                    fmt["protocol"] == "hls"
                    and fmt["mime_type"] == "audio/mpeg"
                ):
                    url = tc["url"]
                    break

            assert url is not None

            resp, _ = self._get(url, no_base=True)
            return {"url": resp["url"], "type": "mp3"}

    def search(self, query: str, media_type="album"):
        """Search for a query.

        :param query:
        :type query: str
        :param media_type: Can be album, though it will return a playlist
        response.
        """
        params = {"q": query}
        resp, _ = self._get(f"search/{media_type}s", params=params)
        return resp

    def _get(self, path, params=None, no_base=False, resp_obj=False):
        """Send a request to the SoundCloud API.

        :param path:
        :param params:
        :param no_base: Do not append `path` parameter to the SoundCloud API
        base.
        :param resp_obj: Return the object returned by `requests.get` instead
        of the json response dict.
        """
        if params is None:
            params = {}
        params["client_id"] = SOUNDCLOUD_CLIENT_ID
        if no_base:
            url = path
        else:
            url = f"{SOUNDCLOUD_BASE}/{path}"

        logger.debug(f"Fetching url {url}")
        r = self.session.get(url, params=params)
        if resp_obj:
            return r

        return r.json(), r.status_code
