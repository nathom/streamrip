"""FastAPI application for streamrip web UI."""
import logging
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


def create_app(db_path: str = "data/streamrip.db") -> FastAPI:
    db = AppDatabase(db_path)
    event_bus = EventBus()

    for event_type in ("download_progress", "download_complete", "download_failed",
                        "sync_started", "sync_complete", "library_updated", "token_expired"):
        async def _handler(data, et=event_type):
            await manager.broadcast(et, data)
        event_bus.subscribe(event_type, _handler)

    library_service = LibraryService(db, event_bus, clients={})
    download_service = DownloadService(db, event_bus, clients={}, download_path="/tmp")
    sync_service = SyncService(db, event_bus, clients={}, library_service=library_service)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("streamrip web UI started")
        yield
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

    import os
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
