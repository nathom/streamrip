"""FastAPI application for streamrip web UI."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .models.database import AppDatabase
from .services.event_bus import EventBus

logger = logging.getLogger("streamrip")


def create_app(db_path: str = "data/streamrip.db") -> FastAPI:
    db = AppDatabase(db_path)
    event_bus = EventBus()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("streamrip web UI started")
        yield
        logger.info("streamrip web UI shutting down")

    app = FastAPI(title="streamrip", version="3.0.0", lifespan=lifespan)

    app.state.db = db
    app.state.event_bus = event_bus

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/auth/status")
    async def auth_status():
        return []

    return app
