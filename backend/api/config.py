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
        if key in ("qobuz_quality", "tidal_quality", "max_connections",
                    "conversion_sampling_rate", "conversion_bit_depth"):
            config_dict[key] = int(value)
        elif key in ("conversion_enabled", "auto_sync_enabled", "qobuz_download_booklets",
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
    """Reset all library data, download history, and config. Files on disk are not affected."""
    db = request.app.state.db
    with db._connect() as conn:
        conn.execute("DELETE FROM albums")
        conn.execute("DELETE FROM tracks")
        conn.execute("DELETE FROM sync_runs")
        conn.execute("DELETE FROM config")
    logger.info("Database reset — all library data cleared")
    return {"message": "Database reset. Library, tracks, and config cleared. Files on disk unchanged."}


async def _reload_clients(request: Request):
    """Re-initialize streaming clients after credential changes."""
    from ..main import _init_clients

    db = request.app.state.db

    # Close existing sessions
    old_clients = getattr(request.app.state, '_clients_ref', {})
    for client in old_clients.values():
        try:
            if hasattr(client, '__aexit__'):
                await client.__aexit__(None, None, None)
            elif hasattr(client, 'session') and client.session:
                await client.session.close()
        except Exception:
            pass

    # Create new clients
    clients = _init_clients(db)

    # Open sessions and login
    for name, client in clients.items():
        try:
            if hasattr(client, '__aenter__'):
                # SDK client — open async session
                await client.__aenter__()
                logger.info("Hot-reloaded %s (session opened)", name)
            elif hasattr(client, 'logged_in') and not client.logged_in:
                # Streamrip client — login
                await client.login()
                logger.info("Hot-reloaded and logged in to %s", name)
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
