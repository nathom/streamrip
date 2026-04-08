"""App ID and secret extraction from play.qobuz.com's JavaScript bundle.

This scrapes the same data that streamrip's QobuzSpoofer extracts,
making the SDK fully standalone without depending on streamrip.
"""

from __future__ import annotations

import base64
import re
from collections import OrderedDict

import aiohttp


_SEED_TZ_RE = (
    r'[a-z]\.initialSeed\("(?P<seed>[\w=]+)",window\.ut'
    r"imezone\.(?P<timezone>[a-z]+)\)"
)
_APP_ID_RE = r'production:{api:{appId:"(?P<app_id>\d{9})",appSecret:"(\w{32})'
_BUNDLE_RE = r'<script src="(/resources/\d+\.\d+\.\d+-[a-z]\d{3}/bundle\.js)"></script>'
_INFO_EXTRAS_TEMPLATE = (
    r'name:"\w+/(?P<timezone>{timezones})",info:"'
    r'(?P<info>[\w=]+)",extras:"(?P<extras>[\w=]+)"'
)


async def fetch_app_credentials() -> tuple[str, list[str]]:
    """Fetch app_id and app secrets from Qobuz's web player.

    Returns:
        (app_id, list_of_secrets) — the secrets need to be tested
        against a real track to find the working one.
    """
    async with aiohttp.ClientSession() as session:
        # Fetch login page to find bundle URL
        async with session.get("https://play.qobuz.com/login") as resp:
            login_page = await resp.text()

        bundle_match = re.search(_BUNDLE_RE, login_page)
        if bundle_match is None:
            raise RuntimeError("Could not find bundle.js URL in login page")

        bundle_url = "https://play.qobuz.com" + bundle_match.group(1)

        # Fetch the JavaScript bundle
        async with session.get(bundle_url) as resp:
            bundle = await resp.text()

    # Extract app_id
    app_id_match = re.search(_APP_ID_RE, bundle)
    if app_id_match is None:
        raise RuntimeError("Could not find app_id in bundle")
    app_id = app_id_match.group("app_id")

    # Extract seed/timezone pairs
    seed_matches = re.finditer(_SEED_TZ_RE, bundle)
    secrets: OrderedDict[str, list[str]] = OrderedDict()
    for match in seed_matches:
        seed, timezone = match.group("seed", "timezone")
        secrets[timezone] = [seed]

    # Swap first and second timezone (Qobuz's ternary logic quirk)
    keypairs = list(secrets.items())
    if len(keypairs) >= 2:
        secrets.move_to_end(keypairs[1][0], last=False)

    # Extract info/extras for each timezone
    info_extras_re = _INFO_EXTRAS_TEMPLATE.format(
        timezones="|".join(tz.capitalize() for tz in secrets),
    )
    for match in re.finditer(info_extras_re, bundle):
        timezone, info, extras = match.group("timezone", "info", "extras")
        secrets[timezone.lower()] += [info, extras]

    # Decode secrets from base64
    decoded: list[str] = []
    for parts in secrets.values():
        raw = "".join(parts)[:-44]
        try:
            secret = base64.standard_b64decode(raw).decode("utf-8")
            if secret:
                decoded.append(secret)
        except Exception:
            pass

    if not decoded:
        raise RuntimeError("No app secrets found in bundle")

    return app_id, decoded


async def find_working_secret(
    app_id: str,
    secrets: list[str],
    user_auth_token: str,
    test_track_id: int = 19512574,
) -> str:
    """Test each secret against a real track and return the first working one."""
    from qobuz import QobuzClient

    for secret in secrets:
        try:
            async with QobuzClient(
                app_id=app_id,
                user_auth_token=user_auth_token,
                app_secret=secret,
            ) as client:
                await client.streaming.get_file_url(test_track_id, quality=2)
                return secret
        except Exception:
            continue

    raise RuntimeError(f"No working secret found from {len(secrets)} candidates")
