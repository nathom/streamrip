"""Authentication helpers for the Qobuz API."""

from __future__ import annotations

import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import aiohttp

APP_ID = "304027809"
PRIVATE_KEY = "6lz8C03UDIC7"
BASE_URL = "https://www.qobuz.com/api.json/0.2"
CONFIG_DIR = Path.home() / ".config" / "qobuz"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"


def get_oauth_url(port: int = 11111) -> str:
    """Build the OAuth URL for browser login."""
    redirect = f"http://localhost:{port}/callback"
    return f"https://www.qobuz.com/signin/oauth?ext_app_id={APP_ID}&redirect_url={redirect}"


def extract_code_from_url(url: str) -> str:
    """Extract code_autorisation from a callback URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    codes = params.get("code_autorisation", [])
    if not codes:
        raise ValueError(f"No code_autorisation found in URL: {url}")
    return codes[0]


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback code."""

    code: str | None = None

    def do_GET(self):
        try:
            _CallbackHandler.code = extract_code_from_url(
                f"http://localhost{self.path}"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authenticated!</h1>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        except ValueError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code_autorisation parameter")

    def log_message(self, format, *args):
        pass  # Silence request logging


def wait_for_callback(port: int = 11111) -> str:
    """Start a local HTTP server and wait for the OAuth callback.

    Returns the auth code.
    """
    _CallbackHandler.code = None
    server = HTTPServer(("localhost", port), _CallbackHandler)
    server.handle_request()  # Handle exactly one request
    server.server_close()
    if _CallbackHandler.code is None:
        raise RuntimeError("Did not receive auth code from callback")
    return _CallbackHandler.code


async def exchange_code(code: str) -> dict:
    """Exchange an OAuth code for a user auth token."""
    async with aiohttp.ClientSession() as session:
        # Step 1: Exchange code
        async with session.get(
            f"{BASE_URL}/oauth/callback",
            params={"code": code, "private_key": PRIVATE_KEY},
            headers={"X-App-Id": APP_ID},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Token exchange failed: {resp.status}")
            data = await resp.json()

        token = data["token"]
        user_id = data["user_id"]

        # Step 2: Validate and get profile
        async with session.post(
            f"{BASE_URL}/user/login",
            data="extra=partner",
            headers={
                "X-App-Id": APP_ID,
                "X-User-Auth-Token": token,
                "Content-Type": "text/plain;charset=UTF-8",
            },
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Login validation failed: {resp.status}")
            profile = await resp.json()

    return {
        "app_id": APP_ID,
        "user_auth_token": token,
        "user_id": user_id,
        "display_name": profile.get("user", {}).get("display_name", ""),
    }


def save_credentials(creds: dict) -> Path:
    """Save credentials to ~/.config/qobuz/credentials.json with restrictive permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    import os
    fd = os.open(str(CREDENTIALS_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(creds, f, indent=2)
    return CREDENTIALS_FILE


def load_credentials() -> dict | None:
    """Load saved credentials, or None if not found."""
    if CREDENTIALS_FILE.exists():
        return json.loads(CREDENTIALS_FILE.read_text())
    return None


async def login(port: int = 11111, no_browser: bool = False) -> dict:
    """Full login flow. Returns credentials dict.

    If no_browser=True, prints URL and waits for user to paste the redirect URL.
    Otherwise, opens browser and runs a local server to catch the callback.
    """
    import asyncio

    url = get_oauth_url(port)

    if no_browser:
        print(f"\nOpen this URL in a browser on any device:\n")
        print(f"  {url}\n")
        print(f"After logging in, you'll be redirected to a page that may not load.")
        print(
            f"Copy the FULL URL from your browser's address bar and paste it here:\n"
        )
        redirect_url = input("> ").strip()
        code = extract_code_from_url(redirect_url)
    else:
        print(f"Opening browser for Qobuz login...")
        opened = webbrowser.open(url)
        if not opened:
            print(f"\nCould not open browser. Open this URL manually:\n")
            print(f"  {url}\n")
        print(f"Waiting for callback on localhost:{port}...")
        code = await asyncio.to_thread(wait_for_callback, port)

    print("Exchanging code for token...")
    creds = await exchange_code(code)
    path = save_credentials(creds)
    print(f"\nAuthenticated as {creds['display_name']}")
    print(f"  Token saved to {path}")
    return creds
