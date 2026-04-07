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


async def _reload_clients(request: Request):
    """Re-initialize streaming clients after credential changes."""
    from ..main import _init_clients

    db = request.app.state.db

    # Close existing sessions
    old_clients = getattr(request.app.state, '_clients_ref', {})
    for client in old_clients.values():
        if hasattr(client, 'session') and client.session:
            try:
                await client.session.close()
            except Exception:
                pass

    # Create new clients
    clients = _init_clients(db)

    # Login
    for name, client in clients.items():
        try:
            if not client.logged_in:
                await client.login()
                logger.info("Hot-reloaded and logged in to %s", name)
        except Exception:
            logger.exception("Failed to login to %s during hot-reload", name)

    # Update all service references
    request.app.state.library_service.clients = clients
    request.app.state.download_service.clients = clients
    request.app.state.sync_service.clients = clients
    request.app.state._clients_ref = clients
