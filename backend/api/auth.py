"""Auth API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger("streamrip")


@router.get("/status")
async def auth_status(request: Request):
    clients = getattr(request.app.state, '_clients_ref', {})
    db = request.app.state.db
    sources = []
    for source in ("qobuz", "tidal"):
        client = clients.get(source)
        # Both clients are now SDK clients with an open async session while
        # the FastAPI lifespan holds them — check _transport._session.
        authenticated = (
            client is not None
            and getattr(client, "_transport", None) is not None
            and client._transport._session is not None
        )
        token_key = f"{source}_token" if source == "qobuz" else f"{source}_access_token"
        sources.append({
            "source": source,
            "authenticated": authenticated,
            "user_id": db.get_config(f"{source}_user_id"),
            "has_credentials": bool(db.get_config(token_key)),
        })
    return sources


@router.get("/qobuz/oauth-url")
async def qobuz_oauth_url(port: int = 11111):
    """Get the Qobuz OAuth URL for browser login."""
    from qobuz.auth import get_oauth_url
    return {"url": get_oauth_url(port)}


class OAuthCodeRequest(BaseModel):
    code: str


@router.post("/qobuz/oauth-callback")
async def qobuz_oauth_callback(request: Request, body: OAuthCodeRequest):
    """Exchange an OAuth code for credentials and save them."""
    from qobuz.auth import exchange_code

    try:
        creds = await exchange_code(body.code)
    except Exception as e:
        logger.exception("OAuth code exchange failed")
        return {"error": str(e)}, 400

    db = request.app.state.db
    db.set_config("qobuz_token", creds["user_auth_token"])
    db.set_config("qobuz_user_id", str(creds["user_id"]))

    from .config import _reload_clients
    await _reload_clients(request)

    return {
        "success": True,
        "user_id": creds["user_id"],
        "display_name": creds["display_name"],
    }


class OAuthRedirectRequest(BaseModel):
    redirect_url: str


@router.post("/qobuz/oauth-from-url")
async def qobuz_oauth_from_url(request: Request, body: OAuthRedirectRequest):
    """Extract code from a redirect URL, exchange for credentials, and save.

    For headless/remote machines where the browser callback can't reach localhost.
    """
    from qobuz.auth import extract_code_from_url, exchange_code

    try:
        code = extract_code_from_url(body.redirect_url)
        creds = await exchange_code(code)
    except Exception as e:
        logger.exception("OAuth URL exchange failed")
        return {"error": str(e)}, 400

    db = request.app.state.db
    db.set_config("qobuz_token", creds["user_auth_token"])
    db.set_config("qobuz_user_id", str(creds["user_id"]))

    from .config import _reload_clients
    await _reload_clients(request)

    return {
        "success": True,
        "user_id": creds["user_id"],
        "display_name": creds["display_name"],
    }


# ── Tidal ──────────────────────────────────────────────────────────────────


@router.post("/tidal/device-code")
async def tidal_device_code():
    """Start the Tidal device-code OAuth flow.

    Returns the verification URL and user code the browser must open,
    plus the device_code the caller must pass to the poll endpoint.
    """
    from tidal.auth import request_device_code

    try:
        data = await request_device_code()
    except Exception as e:
        logger.exception("Failed to start Tidal device-code flow")
        raise HTTPException(status_code=502, detail=str(e))

    verification_url = data.get("verificationUriComplete") or data.get("verificationUri") or ""
    if verification_url and not verification_url.startswith("http"):
        verification_url = f"https://{verification_url}"

    return {
        "device_code": data["deviceCode"],
        "user_code": data["userCode"],
        "verification_url": verification_url,
        "expires_in": data.get("expiresIn", 300),
        "interval": data.get("interval", 5),
    }


class TidalPollRequest(BaseModel):
    device_code: str


@router.post("/tidal/poll")
async def tidal_poll(request: Request, body: TidalPollRequest):
    """Poll the Tidal token endpoint.

    Returns ``{"status": "pending"}`` while the user hasn't approved yet,
    ``{"status": "authorized", "user_id": ...}`` on success, or
    ``{"status": "error", "error": "..."}`` on failure.
    """
    from tidal.auth import poll_device_code

    try:
        status, data = await poll_device_code(body.device_code)
    except Exception as e:
        logger.exception("Tidal poll request failed")
        return {"status": "error", "error": str(e)}

    if status == 2:
        return {"status": "pending"}
    if status != 0:
        return {"status": "error", "error": data.get("error_description") or str(data)}

    # Authorized — persist credentials and hot-reload the client
    db = request.app.state.db
    db.set_config("tidal_access_token", data["access_token"])
    db.set_config("tidal_refresh_token", data["refresh_token"])
    db.set_config("tidal_user_id", str(data["user_id"]))
    db.set_config("tidal_country_code", data["country_code"])
    db.set_config("tidal_token_expiry", str(data["token_expiry"]))

    from .config import _reload_clients
    await _reload_clients(request)

    return {"status": "authorized", "user_id": data["user_id"]}
