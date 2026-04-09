"""FastAPI application for streamrip web UI."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import auth, config, downloads, library, websocket
from .api import sync
from .api.websocket import manager
from .models.database import AppDatabase
from .services.download import DownloadService
from .services.event_bus import EventBus
from .services.library import LibraryService
from .services.sync import SyncService

logger = logging.getLogger("streamrip")


def _init_clients(db: AppDatabase) -> dict:
    """Initialize streaming clients from stored config."""
    clients = {}

    # Qobuz — uses the standalone SDK client
    qobuz_token = db.get_config("qobuz_token")
    if qobuz_token:
        try:
            from qobuz import QobuzClient
            from qobuz.spoofer import fetch_app_credentials, find_working_secret
            import asyncio

            # We need app_id — check if cached, otherwise use default
            app_id = db.get_config("qobuz_app_id") or "798273057"

            client = QobuzClient(
                app_id=app_id,
                user_auth_token=qobuz_token,
            )
            # Note: client session opens on __aenter__, done in lifespan
            clients["qobuz"] = client
            logger.info("Qobuz SDK client initialized")
        except Exception:
            logger.exception("Failed to initialize Qobuz client")

    # Tidal — standalone SDK (same shape as the Qobuz SDK above)
    tidal_token = db.get_config("tidal_access_token")
    if tidal_token:
        try:
            from tidal import TidalClient

            refresh_token = db.get_config("tidal_refresh_token")
            user_id = db.get_config("tidal_user_id") or 0
            country_code = db.get_config("tidal_country_code") or "US"
            token_expiry_str = db.get_config("tidal_token_expiry") or "0"
            try:
                token_expiry = float(token_expiry_str)
            except ValueError:
                token_expiry = 0.0

            client = TidalClient(
                access_token=tidal_token,
                refresh_token=refresh_token,
                user_id=user_id,
                country_code=country_code,
                token_expiry=token_expiry,
            )
            clients["tidal"] = client
            logger.info("Tidal SDK client initialized")
        except Exception:
            logger.exception("Failed to initialize Tidal client")

    return clients


def create_app(db_path: str | None = None) -> FastAPI:
    if db_path is None:
        db_path = os.environ.get("STREAMRIP_DB_PATH", "data/streamrip.db")
    db = AppDatabase(db_path)
    event_bus = EventBus()

    for event_type in ("download_progress", "download_complete", "download_failed",
                        "sync_started", "sync_complete", "library_updated", "token_expired"):
        async def _handler(data, et=event_type):
            await manager.broadcast(et, data)
        event_bus.subscribe(event_type, _handler)

    clients = _init_clients(db)

    download_path = db.get_config("downloads_path") or os.environ.get("STREAMRIP_DOWNLOADS_PATH", "/music")
    library_service = LibraryService(db, event_bus, clients=clients)
    download_service = DownloadService(db, event_bus, clients=clients, download_path=download_path)
    sync_service = SyncService(db, event_bus, clients=clients, library_service=library_service)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Open client sessions — both Qobuz and Tidal SDK clients are
        # async context managers.
        for name, client in clients.items():
            try:
                await client.__aenter__()
                logger.info("Opened session for %s", name)
            except Exception:
                logger.exception("Failed to initialize %s", name)

        # Fetch and cache app_secret for Qobuz downloads (Qobuz-only:
        # Tidal's manifest includes its own signed URLs).
        qobuz = clients.get("qobuz")
        if qobuz and not getattr(qobuz, '_app_secret_cached', False):
            try:
                from qobuz.spoofer import fetch_app_credentials, find_working_secret
                app_id, secrets = await fetch_app_credentials()
                token = db.get_config("qobuz_token")
                if token and secrets:
                    secret = None
                    try:
                        secret = await find_working_secret(app_id, secrets, token)
                    except RuntimeError:
                        logger.warning(
                            "Qobuz secret verification failed (%d candidates); "
                            "using first candidate as fallback",
                            len(secrets),
                        )
                        secret = secrets[0]
                    if secret:
                        qobuz.streaming._app_secret = secret
                        qobuz._app_secret_cached = True
                        db.set_config("qobuz_app_id", app_id)
                        logger.info("Qobuz app secret resolved and cached")
            except Exception:
                logger.exception("Failed to resolve Qobuz app secret")

        yield

        # Cleanup sessions
        for client in clients.values():
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass
        logger.info("streamrip web UI shutting down")

    app = FastAPI(title="streamrip", version="3.0.0", lifespan=lifespan)
    app.state.db = db
    app.state.event_bus = event_bus
    app.state.library_service = library_service
    app.state.download_service = download_service
    app.state.sync_service = sync_service
    app.state._clients_ref = clients

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    app.include_router(library.router)
    app.include_router(downloads.router)
    app.include_router(config.router)
    app.include_router(auth.router)
    app.include_router(websocket.router)
    app.include_router(sync.router)

    from fastapi.responses import FileResponse

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        @app.get("/{path:path}")
        async def serve_frontend(path: str):
            file_path = os.path.join(static_dir, path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(static_dir, "index.html"))

    return app
