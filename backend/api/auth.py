"""Auth API routes."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.get("/status")
async def auth_status(request: Request):
    db = request.app.state.db
    sources = []
    for source in ("qobuz", "tidal"):
        token_key = f"{source}_token" if source == "qobuz" else f"{source}_access_token"
        token = db.get_config(token_key)
        sources.append({"source": source, "authenticated": bool(token), "user_id": db.get_config(f"{source}_user_id")})
    return sources
