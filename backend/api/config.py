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

    # Manual qobuz_token paste path: if the token in the PATCH body differs
    # from what's currently stored AND the user didn't also provide an
    # explicit qobuz_app_id, assume it's a manually-extracted web player
    # token and pin qobuz_app_id=798273057.  That matches the spoofer's
    # signing secret, which is the only secret we have without an override.
    #
    # OAuth-issued tokens use a different code path
    # (/api/auth/qobuz/oauth-from-url) that atomically sets qobuz_app_id
    # to the OAuth app, so this branch never fires for OAuth flows.
    if "qobuz_token" in updates and not updates.get("qobuz_app_id"):
        new_token = updates["qobuz_token"] or ""
        old_token = db.get_config("qobuz_token") or ""
        if new_token and new_token != old_token:
            updates["qobuz_app_id"] = "798273057"
            logger.info(
                "Detected manual qobuz_token change — pinning qobuz_app_id=798273057 "
                "(web player; required for download signing)"
            )

    for key, value in updates.items():
        db.set_config(key, str(value))

    # Hot-reload clients if credentials changed
    cred_keys = {
        "qobuz_token", "qobuz_user_id", "qobuz_app_id", "qobuz_app_secret",
        "tidal_access_token",
    }
    if cred_keys & set(updates.keys()):
        await _reload_clients(request)

    # Restart the auto-sync loop if its config changed
    auto_sync_keys = {"auto_sync_enabled", "auto_sync_interval"}
    if auto_sync_keys & set(updates.keys()):
        from ..main import _start_auto_sync_if_enabled
        sync_service = request.app.state.sync_service
        sync_service.stop_auto_sync()
        _start_auto_sync_if_enabled(
            db, sync_service, request.app.state._clients_ref
        )

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

    # Resolve the real Qobuz app_id and secret.  This also corrects
    # the X-App-Id session header if the client was built with a stale
    # cached app_id (see _resolve_qobuz_credentials docstring in main.py).
    qobuz = clients.get("qobuz")
    if qobuz:
        from ..main import _resolve_qobuz_credentials
        await _resolve_qobuz_credentials(db, qobuz)

    # Update all service references
    request.app.state.library_service.clients = clients
    request.app.state.download_service.clients = clients
    request.app.state.sync_service.clients = clients
    request.app.state._clients_ref = clients
