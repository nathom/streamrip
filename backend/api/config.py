"""Config API routes."""
import logging

from fastapi import APIRouter, Request
from ..models.schemas import AppConfig, ConfigUpdate

router = APIRouter(prefix="/api/config", tags=["config"])
logger = logging.getLogger("streamrip")


@router.get("")
async def get_config(request: Request) -> AppConfig:
    db = request.app.state.db
    raw = db.get_all_config()
    config_dict = {}
    for key, value in raw.items():
        if key in ("qobuz_quality", "tidal_quality", "max_connections"):
            config_dict[key] = int(value)
        elif key in ("auto_sync_enabled", "qobuz_download_booklets",
                      "source_subdirectories", "disc_subdirectories", "embed_artwork"):
            config_dict[key] = value.lower() in ("true", "1", "yes")
        else:
            config_dict[key] = value
    return AppConfig(**config_dict)


@router.patch("")
async def update_config(request: Request, body: ConfigUpdate):
    db = request.app.state.db
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        db.set_config(key, str(value))

    # Hot-reload clients if credentials changed
    cred_keys = {"qobuz_token", "qobuz_user_id", "tidal_access_token"}
    if cred_keys & set(updates.keys()):
        await _reload_clients(request)

    return await get_config(request)


@router.post("/reset")
async def reset_database(request: Request):
    """Reset library data and download history. Config and credentials are preserved."""
    db = request.app.state.db
    with db._connect() as conn:
        conn.execute("DELETE FROM albums")
        conn.execute("DELETE FROM tracks")
        conn.execute("DELETE FROM sync_runs")
    logger.info("Database reset — library data cleared, config preserved")
    return {"message": "Library, tracks, and sync history cleared. Config and credentials preserved. Files on disk unchanged."}


async def _reload_clients(request: Request):
    """Re-initialize streaming clients after credential changes."""
    from ..main import _init_clients

    db = request.app.state.db

    # Close existing sessions (all clients are SDK async context managers now).
    old_clients = getattr(request.app.state, '_clients_ref', {})
    for client in old_clients.values():
        try:
            await client.__aexit__(None, None, None)
        except Exception:
            pass

    # Create new clients and open their sessions
    clients = _init_clients(db)
    for name, client in clients.items():
        try:
            await client.__aenter__()
            logger.info("Hot-reloaded %s (session opened)", name)
        except Exception:
            logger.exception("Failed to initialize %s during hot-reload", name)

    # Fetch app_secret for Qobuz if needed
    qobuz = clients.get("qobuz")
    if qobuz and hasattr(qobuz, 'streaming') and not getattr(qobuz, '_app_secret_cached', False):
        try:
            from qobuz.spoofer import fetch_app_credentials, find_working_secret
            app_id, secrets = await fetch_app_credentials()
            token = db.get_config("qobuz_token")
            if token:
                secret = await find_working_secret(app_id, secrets, token)
                qobuz.streaming._app_secret = secret
                qobuz._app_secret_cached = True
                db.set_config("qobuz_app_id", app_id)
                logger.info("Qobuz app secret resolved during hot-reload")
        except Exception:
            logger.exception("Failed to resolve Qobuz app secret during hot-reload")

    # Update all service references
    request.app.state.library_service.clients = clients
    request.app.state.download_service.clients = clients
    request.app.state.sync_service.clients = clients
    request.app.state._clients_ref = clients
