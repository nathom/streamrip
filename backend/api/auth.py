"""Auth API routes."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/auth", tags=["auth"])

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
