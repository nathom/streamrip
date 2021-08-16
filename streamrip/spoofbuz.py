"""Get app id and secrets for Qobuz.

Credits to Dash for this tool.
"""

import base64
import re
from collections import OrderedDict
from typing import List

import requests


class Spoofer:
    """Spoofs the information required to stream tracks from Qobuz."""

    def __init__(self):
        """Create a Spoofer."""
        self.seed_timezone_regex = (
            r'[a-z]\.initialSeed\("(?P<seed>[\w=]+)",window\.ut'
            r"imezone\.(?P<timezone>[a-z]+)\)"
        )
        # note: {timezones} should be replaced with every capitalized timezone joined by a |
        self.info_extras_regex = (
            r'name:"\w+/(?P<timezone>{timezones})",info:"'
            r'(?P<info>[\w=]+)",extras:"(?P<extras>[\w=]+)"'
        )
        self.app_id_regex = (
            r'{app_id:"(?P<app_id>\d{9})",app_secret:"\w{32}",base_port:"80"'
            r',base_url:"https://www\.qobuz\.com",base_method:"/api\.js'
            r'on/0\.2/"},n\.base_url="https://play\.qobuz\.com"'
        )
        login_page_request = requests.get("https://play.qobuz.com/login")
        login_page = login_page_request.text
        bundle_url_match = re.search(
            r'<script src="(/resources/\d+\.\d+\.\d+-[a-z]\d{3}/bundle\.js)"></script>',
            login_page,
        )
        assert bundle_url_match is not None
        bundle_url = bundle_url_match.group(1)
        bundle_req = requests.get("https://play.qobuz.com" + bundle_url)
        self.bundle = bundle_req.text

    def get_app_id(self) -> str:
        """Get the app id.

        :rtype: str
        """
        match = re.search(self.app_id_regex, self.bundle)
        if match is not None:
            return str(match.group("app_id"))

        raise Exception("Could not find app id.")

    def get_secrets(self) -> List[str]:
        """Get secrets."""
        seed_matches = re.finditer(self.seed_timezone_regex, self.bundle)
        secrets = OrderedDict()
        for match in seed_matches:
            seed, timezone = match.group("seed", "timezone")
            secrets[timezone] = [seed]
        """
        The code that follows switches around the first and second timezone.
        Qobuz uses two ternary (a shortened if statement) conditions that
        should always return false. The way Javascript's ternary syntax
        works, the second option listed is what runs if the condition returns
        false. Because of this, we must prioritize the *second* seed/timezone
        pair captured, not the first.
        """
        keypairs = list(secrets.items())
        secrets.move_to_end(keypairs[1][0], last=False)

        info_extras_regex = self.info_extras_regex.format(
            timezones="|".join(timezone.capitalize() for timezone in secrets)
        )
        info_extras_matches = re.finditer(info_extras_regex, self.bundle)
        for match in info_extras_matches:
            timezone, info, extras = match.group("timezone", "info", "extras")
            secrets[timezone.lower()] += [info, extras]

        for secret_pair in secrets:
            secrets[secret_pair] = base64.standard_b64decode(
                "".join(secrets[secret_pair])[:-44]
            ).decode("utf-8")

        vals: List[str] = list(secrets.values())
        vals.remove("")
        return vals
