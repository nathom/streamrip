import base64
import time

from ..config import Config
from .client import Client

BASE = "https://api.tidalhifi.com/v1"
AUTH_URL = "https://auth.tidal.com/v1/oauth2"

CLIENT_ID = base64.b64decode("elU0WEhWVmtjMnREUG80dA==").decode("iso-8859-1")
CLIENT_SECRET = base64.b64decode(
    "VkpLaERGcUpQcXZzUFZOQlY2dWtYVEptd2x2YnR0UDd3bE1scmM3MnNlND0="
).decode("iso-8859-1")


class TidalClient(Client):
    """TidalClient."""

    source = "tidal"
    max_quality = 3

    def __init__(self, config: Config):
        self.logged_in = False
        self.global_config = config
        self.config = config.session.tidal
        self.rate_limiter = self.get_rate_limiter(
            config.session.downloads.requests_per_minute
        )

    async def login(self):
        self.session = await self.get_session()
        c = self.config
        if not c.access_token:
            raise Exception("Access token not found in config.")

        self.token_expiry = float(c.token_expiry)
        self.refresh_token = c.refresh_token

        if self.token_expiry - time.time() < 86400:  # 1 day
            await self._refresh_access_token()
        else:
            await self._login_by_access_token(c.access_token, c.user_id)

        self.logged_in = True

    async def _login_by_access_token(self, token: str, user_id: str):
        """Login using the access token.

        Used after the initial authorization.

        :param token: access token
        :param user_id: To verify that the user is correct
        """
        headers = {"authorization": f"Bearer {token}"}  # temporary
        async with self.session.get(
            "https://api.tidal.com/v1/sessions", headers=headers
        ) as _resp:
            resp = await _resp.json()

        if resp.get("status", 200) != 200:
            raise Exception(f"Login failed {resp}")

        if str(resp.get("userId")) != str(user_id):
            raise Exception(f"User id mismatch {resp['userId']} v {user_id}")

        c = self.config
        c.user_id = resp["userId"]
        c.country_code = resp["countryCode"]
        c.access_token = token
        self._update_authorization_from_config()

    async def _get_login_link(self) -> str:
        data = {
            "client_id": CLIENT_ID,
            "scope": "r_usr+w_usr+w_sub",
        }
        _resp = await self._api_post(f"{AUTH_URL}/device_authorization", data)
        resp = await _resp.json()

        if resp.get("status", 200) != 200:
            raise Exception(f"Device authorization failed {resp}")

        device_code = resp["deviceCode"]
        return f"https://{device_code}"

    def _update_authorization_from_config(self):
        self.session.headers.update(
            {"authorization": f"Bearer {self.config.access_token}"}
        )

    async def _get_auth_status(self, device_code) -> tuple[int, dict[str, int | str]]:
        """Check if the user has logged in inside the browser.

        returns (status, authentication info)
        """
        data = {
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "scope": "r_usr+w_usr+w_sub",
        }
        _resp = await self._api_post(
            f"{AUTH_URL}/token",
            data,
            (CLIENT_ID, CLIENT_SECRET),
        )
        resp = await _resp.json()

        if resp.get("status", 200) != 200:
            if resp["status"] == 400 and resp["sub_status"] == 1002:
                return 2, {}
            else:
                return 1, {}

        ret = {}
        ret["user_id"] = resp["user"]["userId"]
        ret["country_code"] = resp["user"]["countryCode"]
        ret["access_token"] = resp["access_token"]
        ret["refresh_token"] = resp["refresh_token"]
        ret["token_expiry"] = resp["expires_in"] + time.time()
        return 0, ret

    async def _refresh_access_token(self):
        """Refresh the access token given a refresh token.

        The access token expires in a week, so it must be refreshed.
        Requires a refresh token.
        """
        data = {
            "client_id": CLIENT_ID,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "r_usr+w_usr+w_sub",
        }
        resp = await self._api_post(
            f"{AUTH_URL}/token",
            data,
            (CLIENT_ID, CLIENT_SECRET),
        )
        resp_json = await resp.json()

        if resp_json.get("status", 200) != 200:
            raise Exception("Refresh failed")

        c = self.config
        c.access_token = resp_json["access_token"]
        c.token_expiry = resp_json["expires_in"] + time.time()
        self._update_authorization_from_config()

    async def _get_device_code(self):
        """Get the device code that will be used to log in on the browser."""
        data = {
            "client_id": CLIENT_ID,
            "scope": "r_usr+w_usr+w_sub",
        }
        _resp = await self._api_post(f"{AUTH_URL}/device_authorization", data)
        resp = await _resp.json()

        if resp.get("status", 200) != 200:
            raise Exception(f"Device authorization failed {resp}")

        return resp["verificationUriComplete"]

    async def _api_post(self, url, data, auth=None):
        """Post to the Tidal API.

        :param url:
        :param data:
        :param auth:
        """
        async with self.session.post(url, data=data, auth=auth, verify=False) as resp:
            return resp
