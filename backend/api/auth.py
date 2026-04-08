"""Auth API routes."""

import logging

from fastapi import APIRouter, Request
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
        authenticated = client is not None and getattr(client, 'logged_in', False)
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

    # Hot-reload clients
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
