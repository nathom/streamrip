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

    # Qobuz
    qobuz_token = db.get_config("qobuz_token")
    qobuz_user_id = db.get_config("qobuz_user_id")
    if qobuz_token and qobuz_user_id:
        try:
            from streamrip.config import Config

            config_path = os.environ.get(
                "STREAMRIP_CONFIG_PATH",
                os.path.expanduser("~/.config/streamrip/config.toml"),
            )
            if os.path.exists(config_path):
                cfg = Config(config_path)
            else:
                cfg = Config.defaults()

            # Override with DB values
            cfg.session.qobuz.use_auth_token = True
            cfg.session.qobuz.email_or_userid = qobuz_user_id
            cfg.session.qobuz.password_or_token = qobuz_token

            from streamrip.client.qobuz import QobuzClient

            clients["qobuz"] = QobuzClient(cfg)
            logger.info("Qobuz client initialized for user %s", qobuz_user_id)
        except Exception:
            logger.exception("Failed to initialize Qobuz client")

    # Tidal
    tidal_token = db.get_config("tidal_access_token")
    if tidal_token:
        try:
            from streamrip.config import Config

            config_path = os.environ.get(
                "STREAMRIP_CONFIG_PATH",
                os.path.expanduser("~/.config/streamrip/config.toml"),
            )
            if os.path.exists(config_path):
                cfg = Config(config_path)
            else:
                cfg = Config.defaults()

            cfg.session.tidal.access_token = tidal_token

            from streamrip.client.tidal import TidalClient

            clients["tidal"] = TidalClient(cfg)
            logger.info("Tidal client initialized")
        except Exception:
            logger.exception("Failed to initialize Tidal client")

    return clients


def create_app(db_path: str = "data/streamrip.db") -> FastAPI:
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
        # Login clients that need async initialization
        for name, client in clients.items():
            try:
                if not client.logged_in:
                    await client.login()
                    logger.info("Logged in to %s", name)
            except Exception:
                logger.exception("Failed to login to %s", name)
        yield
        # Cleanup sessions
        for client in clients.values():
            if hasattr(client, 'session') and client.session:
                await client.session.close()
        logger.info("streamrip web UI shutting down")

    app = FastAPI(title="streamrip", version="3.0.0", lifespan=lifespan)
    app.state.db = db
    app.state.event_bus = event_bus
    app.state.library_service = library_service
    app.state.download_service = download_service
    app.state.sync_service = sync_service

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
